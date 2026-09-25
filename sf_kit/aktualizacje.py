"""Sprawdzanie i instalowanie aktualizacji Kita (ADVERTPR-960).

v0.1 (25.09.2026) - APro Agents / kimi-autor · kontrakt z GO Damiana 25.09 23:2x

DWIE RÓŻNE RZECZY, KTÓRE TEN MODUŁ ROBI
════════════════════════════════════════
1. **MÓWI, ŻE JEST NOWA WERSJA.** Raz na dobę Kit pyta SF (`GET /api/v1/kit/version`),
   zapisuje odpowiedź w pamięci podręcznej i — gdy wyszło nowe wydanie — pisze na stderr
   JEDNĄ linię: `Dostępny Kit 0.13.3 — sf-kit update`. Gdy nasza wersja jest NIŻSZA niż
   wymagane minimum, ostrzeżenie dostaje człowiek przy KAŻDYM poleceniu, a gdy wydanie
   zrywa zgodność (`breaking`), Kit odmawia pracy z instrukcją. Alarm codzienny jest
   jednoliniowy celowo: komunikat, który pojawia się przy każdym poleceniu, przestaje
   być czytany (to jest jedna z trzech przyczyn krytyki na sprawie).
2. **PODMIENIA KOD.** `sf-kit update [--check]` oraz automatyczny patch workera
   (`auto_update: patch`) chodzą TĄ SAMĄ drogą: odmowa przy brudnym drzewie śledzonych
   plików, pobranie tagów, przejście na tag WSKAZANY PRZEZ SF i weryfikacja, że
   HEAD == commit z SF — przy rozjazdzie zmiana jest wycofywana i zgłaszany błąd.
   SF jest tu jedynym źródłem prawdy o tym, CO zainstalować: tag na GitHubie sam w sobie
   nic nie znaczy, dopiero zgodność z commit-em z SF coś potwierdza (krytyka „łańcuch
   dostaw" z opisu sprawy).

DLACZEGO WORKER SIĘ RESTARTUJE KODEM WYJŚCIA
Podmiana kodu pod działającym procesem psuje importy (stary worker padłby przy pierwszym
`import` po zmianie `autor.py` → `asystent.py` w v0.13.2). Dlatego automatyczna aktualizacja
kończy proces KODEM PRZEZNACZONYM DO RESTARTU (`KOD_RESTARTU_PO_AKTUALIZACJI`) i to
systemd/launchd (`Restart=always` / `KeepAlive`, patrz `usluga.py`) wstawia nowy proces
już na nowym kodzie. Wszystko to dzieje się MIĘDZY zadaniami, nigdy w trakcie.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

from . import WERSJA
from .api import BladAPI
from .klucz import sciezka_konfiguracji

#: Plik pamięci podręcznej w katalogu konfiguracji agenta. Trzyma OSTATNIĄ odpowiedź
#: `GET /kit/version` plus znaczniki czasu: kiedy sprawdzano, kiedy ostrzegano,
#: kiedy ponawiać po błędzie. Ręczna edycja jest bezpieczna — brakujące pola znaczą
#: „sprawdź od nowa", nie „nie działaj".
PLIK_PAMIECI = "aktualizacje.json"

#: Jak długo odpowiedź SF uchodzi za świeżą. Dobę: wydania Kitu nie pojawiają się
#: częściej, a każde sprawdzenie to żądanie do cudzego serwera (ta sama zasada co
#: przy odstępie odpytywania kolejki w `worker.uruchom`).
SWIEZOSC_S = 24 * 3600

#: Ile czekać z ponowną PRÓBĄ odpytania SF po nieudanym sprawdzeniu. Godzina: przy
#: padniętym SF nie ma sensu pytać przy każdym poleceniu, a przy zgubionej sieci
#: właściciela klucza informacja o nowej wersji i tak jest bezużyteczna.
PRZERWA_PO_BLEDZIE_SF_S = 3600

#: Ile czekać z kolejną PRÓBĄ AKTUALIZACJI po nieudanym podejściu (brudne drzewo,
#: niezgodny commit, awaria gita). Sześć godzin: błąd, którego człowiek ma naprawić
#: (np. zacommitować łatkę), nie naprawi się między jednym a drugim taktem pętli,
#: a co takt to kolejne wywołanie gita i powtórzony wpis w dzienniku.
PRZERWA_PO_NIEUDANEJ_AKTUALIZACJI_S = 6 * 3600

#: Kod, którym worker kończy proces PO udanej automatycznej aktualizacji. 75 to
#: `EX_TEMPFAIL` z sysexits: „chwilowa niedyspozycja — wstań mnie ponownie". systemd
#: (`Restart=always`) i launchd (`KeepAlive`) wstawiają proces niezależnie od kodu,
#: więc liczba jest przede wszystkim dokumentacją dla człowieka czytającego `journalctl`.
KOD_RESTARTU_PO_AKTUALIZACJI = 75

#: Pola, które kontrakt (wpis z 25.09 23:2x) wymaga w odpowiedzi `GET /kit/version`.
#: Bez któregokolwiek z nich nie wiemy, CO zainstalować, więc traktujemy odpowiedź
#: jako niezgodną z kontraktem, nie jako „brak aktualizacji".
WYMAGANE_POLA = ("latest", "min", "tag", "commit")


class BladAktualizacji(RuntimeError):
    """Aktualizacja nie doszła do skutku — komunikat mówi człowiekowi, co zrobić."""


class OdmowaAktualizacji(BladAktualizacji):
    """Warunki nie pozwalają aktualizować (brudne drzewo, brak gita) — NIE wycofujemy nic."""


class OdmowaPrzedPoleceniem(RuntimeError):
    """Wersja Kita poniżej minimalnej przy wydaniu zrywającym zgodność — praca zabroniona.

    Wywoływana PRZED wykonaniem każdego polecenia (z wyjątkiem `init` i `update`),
    bo worker na przestarzałej wersji miałby pracować wbrew API i psuć dane.
    """


# ── wersje ───────────────────────────────────────────────────────────────────


def _czesci(wersja: str) -> tuple[int, ...]:
    """`"0.13.2"` → `(0, 13, 2)`. Prowadzące `v` i końcówki typu `-rc1` odpadają."""
    czysta = (wersja or "").strip().lstrip("v")
    czysta = re.split(r"[-+]", czysta)[0]
    wynik = []
    for czesc in czysta.split("."):
        wynik.append(int(czesc) if czesc.isdigit() else 0)
    return tuple(wynik or [0])


def porownaj_wersje(a: str, b: str) -> int:
    """-1 gdy a < b, 0 gdy równe, 1 gdy a > b. Porównuje numer po numerze, nie napisy —
    inaczej `0.13.10` wyglądałoby na starsze niż `0.13.9`. Różną długość wyrównuje
    zerami (`0.13` == `0.13.0`), bo kontrakt podaje pełne trzy człony, a człowiek
    przy wpisywaniu porównania w skrypcie może skrócić."""
    xa, xb = _czesci(a), _czesci(b)
    dlugosc = max(len(xa), len(xb))
    xa += (0,) * (dlugosc - len(xa))
    xb += (0,) * (dlugosc - len(xb))
    return (xa > xb) - (xa < xb)


def ten_sam_minor(a: str, b: str) -> bool:
    """Czy dwie wersje mieszczą się w tym samym minor (0.13.x). Automatyczna
    aktualizacja dotyczy WYŁĄCZNIE poprawek — minor i major zawsze instaluje człowiek."""
    xa, xb = _czesci(a), _czesci(b)
    return xa[:2] == xb[:2]


# ── pamięć podręczna ──────────────────────────────────────────────────────────


def plik_pamieci() -> Path:
    return sciezka_konfiguracji() / PLIK_PAMIECI


def wczytaj_pamiec(plik: Path | None = None) -> dict:
    """Zawartość pamięci albo `{}`. Uszkodzony plik traktujemy jak pusty — to tylko
    pamięć podręczna, a zła odpowiedź ma znaczyć „sprawdź od nowa", nie „nie działaj"."""
    plik = plik or plik_pamieci()
    try:
        dane = json.loads(plik.read_text(encoding="utf-8"))
        return dane if isinstance(dane, dict) else {}
    except (OSError, ValueError):
        return {}


def zapisz_pamiec(dane: dict, plik: Path | None = None) -> None:
    """Zapis przez plik tymczasowy i `replace` — czytelnik w połowie zapisu dostałby
    pustą połowę i uznał pamięć za pustą (sprawdziłby zatem SF dwa razy z rzędu)."""
    plik = plik or plik_pamieci()
    try:
        plik.parent.mkdir(parents=True, exist_ok=True)
        tymczasowy = plik.with_name(plik.name + ".tmp")
        tymczasowy.write_text(json.dumps(dane, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        tymczasowy.replace(plik)
    except OSError:
        # Pamięć podręczna, której nie da się zapisać, nie może wywrócić polecenia —
        # najwyżej następne sprawdzenie będzie kolejnym zapytaniem do SF.
        pass


# ── rozmowa z SF ──────────────────────────────────────────────────────────────


def pobierz_info(klient) -> dict:
    """ŚWIEŻA odpowiedź `GET /kit/version`, z walidacją pól wymaganych kontraktem."""
    try:
        info = klient.wersja_kita()
    except BladAPI as blad:
        raise BladAktualizacji(
            f"nie udało się sprawdzić wersji Kita w SF: {blad}") from None
    if not isinstance(info, dict):
        raise BladAktualizacji(
            "SF oddał niezrozumiałą odpowiedź na `GET /kit/version` — kontrakt się zmienił?")
    braki = [pole for pole in WYMAGANE_POLA if not info.get(pole)]
    if braki:
        raise BladAktualizacji(
            f"SF nie podał w `GET /kit/version` pól: {', '.join(braki)} — bez nich nie "
            f"wiem, co zainstalować. Kontrakt (ADVERTPR-960) się zmienił?")
    return info


def sprawdz_wersje(klient, *, teraz: float | None = None, wymusz: bool = False,
                   plik: Path | None = None) -> dict | None:
    """Pamięć podręczna + ewentualne świeże zapytanie. Oddaje stan wiedzy o wersjach
    (słownik z pamięci albo `None`, gdy nigdy się nie udało).

    Odpytuje SF tylko gdy pamięć jest starsza niż `SWIEZOSC_S` albo gdy `wymusz` —
    i nie częściej niż raz na `PRZERWA_PO_BLEDzie_SF_S` po nieudanej próbie (inaczej
    padnięty SF oznaczałby dodatkowe żądanie przy KAŻDYM poleceniu Kita).
    """
    teraz = time.time() if teraz is None else teraz
    pamiec = wczytaj_pamiec(plik)

    def swieza(pole: str) -> bool:
        wartosc = pamiec.get(pole)
        try:
            return teraz - float(wartosc) < SWIEZOSC_S
        except (TypeError, ValueError):
            return False

    if not wymusz and swieza("sprawdzono_o") and all(p in pamiec for p in WYMAGANE_POLA):
        return pamiec

    nastepna = pamiec.get("nastepna_proba_o")
    if not wymusz:
        try:
            if teraz < float(nastepna):
                return pamiec if all(p in pamiec for p in WYMAGANE_POLA) else None
        except (TypeError, ValueError):
            pass

    try:
        info = pobierz_info(klient)
    except BladAktualizacji:
        pamiec["nastepna_proba_o"] = teraz + PRZERWA_PO_BLEDZIE_SF_S
        zapisz_pamiec(pamiec, plik)
        return pamiec if all(p in pamiec for p in WYMAGANE_POLA) else None

    pamiec.update(info)
    pamiec["sprawdzono_o"] = teraz
    pamiec.pop("nastepna_proba_o", None)
    zapisz_pamiec(pamiec, plik)
    return pamiec


# ── ostrzeżenia przed poleceniem ──────────────────────────────────────────────


def linia_o_dostepnej(pamiec: dict) -> str | None:
    """Jednolinijkowe `Dostępny Kit 0.13.3 — sf-kit update` — RAZ NA DOBĘ, nie co polecenie."""
    latest = pamiec.get("latest") or ""
    if latest and porownaj_wersje(WERSJA, latest) < 0:
        return f"Dostępny Kit {latest} — sf-kit update"
    return None


def ostrzezenie_przed_poleceniem(klient, *, teraz: float | None = None,
                                 plik: Path | None = None) -> str | None:
    """Tekst na stderr PRZED każdym poleceniem (albo `None`). Trzy poziomy:

    · wersja < min i `breaking`  → OdmowaPrzedPoleceniem (praca zabroniona, z instrukcją);
    · wersja < min               → ostrzeżenie PRZY KAŻDYM poleceniu;
    · wersja < latest            → jedna linia RAZ NA DOBĘ (znacznik `ostrzezono_o`).

    FAIL-SOFT jak w `worker.ostrzez_o_kluczu`: brak sieci, brak klucza, brak konfiguracji
    kończą się ciszą — informacja o nowej wersji nie ma prawa zatrzymać pracy.
    """
    teraz = time.time() if teraz is None else teraz
    pamiec = sprawdz_wersje(klient, teraz=teraz, plik=plik)
    if not pamiec:
        return None

    minimalna = pamiec.get("min") or ""
    if minimalna and porownaj_wersje(WERSJA, minimalna) < 0:
        tag = pamiec.get("tag") or "?"
        if pamiec.get("breaking"):
            raise OdmowaPrzedPoleceniem(
                f"Ten Kit (v{WERSJA}) nie jest już obsługiwany — wydanie {tag} zrywa "
                f"zgodność, a wymagana wersja to {minimalna} lub nowsza.\n"
                f"Zaktualizuj: sf-kit update\n"
                f"Opis zmian: {pamiec.get('notes_url') or '—'}")
        return (f"Kit v{WERSJA} jest poniżej wymaganej wersji minimalnej ({minimalna}) — "
                f"zacznij od `sf-kit update`.")

    linia = linia_o_dostepnej(pamiec)
    if linia:
        ostrzezono = pamiec.get("ostrzezono_o")
        try:
            ponow = teraz - float(ostrzezono) >= SWIEZOSC_S
        except (TypeError, ValueError):
            ponow = True
        if ponow:
            pamiec["ostrzezono_o"] = teraz
            zapisz_pamiec(pamiec, plik)
            return linia
    return None


# ── repozytorium gita ─────────────────────────────────────────────────────────


class Repo:
    """Klon sf-agent-kit, w którym stoi TEN plik. Wszystkie operacje przez `git -C`,
    bez powłoki — ścieżki z nietypowymi znakami nie mają jak zepsuć polecenia."""

    def __init__(self, katalog: Path):
        self.katalog = Path(katalog)

    @classmethod
    def znajdz(cls) -> "Repo | None":
        """Katalog z klonem albo `None`. Kit instaluje się przez `git clone` (README),
        więc kod zawsze stoi w klonie — gdy nie stoi (ktoś przekopiował katalog), nie
        wiemy, skąd brać tagi i uczciwie odmawiamy zamiast zgadywać."""
        katalog = Path(__file__).resolve().parents[1]
        probe = subprocess.run(["git", "-C", str(katalog), "rev-parse",
                                "--is-inside-work-tree"],
                               capture_output=True, text=True)
        if probe.returncode != 0 or probe.stdout.strip() != "true":
            return None
        top = subprocess.run(["git", "-C", str(katalog), "rev-parse",
                              "--show-toplevel"],
                             capture_output=True, text=True)
        if top.returncode != 0 or not top.stdout.strip():
            return None
        return cls(Path(top.stdout.strip().splitlines()[0]))

    def _git(self, *argumenty: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.katalog), *argumenty],
                              capture_output=True, text=True)

    def _git_albo_blad(self, czynnosc: str, *argumenty: str) -> str:
        wynik = self._git(*argumenty)
        if wynik.returncode != 0:
            szczegoly = (wynik.stderr or wynik.stdout or "").strip()[:400]
            raise BladAktualizacji(
                f"nie udało się {czynnosc} (`git {' '.join(argumenty)}`): {szczegoly}")
        return wynik.stdout

    def brudne_pliki(self) -> list[str]:
        """Zmienione ŚLEDOZONE pliki. Nieśledzone (`??`) pomijamy celowo: lokalne łatki
        typu `wykonawcy.py.lokalna-latka` mają PRZEŻYĆ aktualizację (krytyka z opisu
        sprawy), a checkout ich nie rusza — więc nie ma powodu odmawiać przez nie pracy."""
        wyjscie = self._git_albo_blad("sprawdzić stan drzewa", "status", "--porcelain")
        return [linia for linia in wyjscie.splitlines() if linia and not linia.startswith("??")]

    def pobierz_tagi(self) -> None:
        self._git_albo_blad("pobrać tagi", "fetch", "--tags", "origin")

    def head(self) -> str:
        return self._git_albo_blad("odczytać HEAD", "rev-parse", "HEAD").strip()

    def przejdz_na(self, tag: str) -> None:
        # BEZ `--` przed refem: po `--` git czyta argument jako ŚCIEŻKĘ i `checkout -- v0.13.3`
        # kończy się „pathspec did not match" (złapał to test end-to-end na prawdziwym klonie).
        self._git_albo_blad("przejść na wydanie", "checkout", tag)

    def wroc_do(self, ref: str) -> None:
        self._git_albo_blad("wycofać zmianę", "checkout", ref)

    def dziennik_zmian(self, od_sha: str, do_sha: str) -> str:
        """`git log --oneline od..do` — co się zmieniło między wersjami, dla człowieka."""
        return self._git_albo_blad("odczytać zmiany", "log", "--oneline", "--no-decorate",
                                   f"{od_sha}..{do_sha}").strip()


# ── właściwa aktualizacja ─────────────────────────────────────────────────────


def aktualizuj(klient, *, repo: Repo | None = None, mow=print) -> bool:
    """Przejdź na wydanie wskazane przez SF. Oddaje `True`, gdy kod faktycznie podmieniono.

    Droga (jedna dla `sf-kit update` i dla automatycznego patcha workera):
    brudne drzewo → odmowa · pobranie tagów · checkout tagu z SF · WERYFIKACJA
    HEAD == commit z SF (przy rozjazdzie wycofanie i błąd) · pokazanie zmian.
    """
    repo = repo if repo is not None else Repo.znajdz()
    if repo is None:
        raise OdmowaAktualizacji(
            "Kit nie jest klonem gita — nie wiem, skąd wziąć wydanie. Zainstaluj od nowa: "
            "git clone https://github.com/dpakula/sf-agent-kit.git i przenieś config.json.")

    info = pobierz_info(klient)
    tag = info["tag"]
    commit = info["commit"]

    if porownaj_wersje(WERSJA, info["latest"]) >= 0:
        mow(f"Masz najnowszą wersję Kita (v{WERSJA}).")
        return False

    brudne = repo.brudne_pliki()
    if brudne:
        wypisane = "\n".join(f"  {linia}" for linia in brudne[:10])
        wiecej = f"\n  … i {len(brudne) - 10} dalszych" if len(brudne) > 10 else ""
        raise OdmowaAktualizacji(
            "aktualizacja odmówiona — masz ZMIENIONE pliki śledzone w katalogu Kita:\n"
            f"{wypisane}{wiecej}\n"
            "Zacommituj je, schowaj (`git stash`) albo usuń, i spróbuj ponownie. "
            "Nieśledzone pliki (np. `*.lokalna-latka`) zostają nietknięte.")

    mow(f"Aktualizuję Kita z v{WERSJA} do {tag}…")
    repo.pobierz_tagi()
    stary_head = repo.head()
    repo.przejdz_na(tag)

    if repo.head() != commit:
        repo.wroc_do(stary_head)
        raise BladAktualizacji(
            f"WERYFIKACJA NIE PRZESZŁA: po przejściu na {tag} HEAD to {repo.head()[:12]}, "
            f"a SF wymaga {commit[:12]}. Zmiana wycofana — zostałeś przy v{WERSJA}.\n"
            f"To oznacza rozjazd między repo a SF (tag przesunięty albo SF wskazuje inny "
            f"commit, niż wypuszczono). Zgłoś to na sprawie ADVERTPR-960 — dalej nie ruszaj.")

    zmiany = repo.dziennik_zmian(stary_head, commit)
    if zmiany:
        mow(f"\nZmiany od v{WERSJA}:")
        mow(zmiany)
    mow(f"\nZaktualizowano: v{WERSJA} → {tag} "
        f"(sprawdzone zgodnie z SF: HEAD == {commit[:12]}).")
    if info.get("breaking"):
        mow(f"UWAGA: to wydanie ZRYWA zgodność — przeczytaj: {info.get('notes_url') or '—'}")
    return True


def pokaz_status(klient, *, mow=print, plik: Path | None = None) -> int:
    """`sf-kit update --check` — tylko informacja, zero gita. Kod 0 zawsze (stan to nie
    błąd) — wyjątek oznacza, że o wersjach nie wiadomo NIC: SF milczy i pamięć jest pusta.
    Przy braku sieci pokazujemy TO, CO WIEMY z pamięci, z widoczną adnotacją — wczorajsza
    prawda oznaczona datą jest uczciwsza niż udawana świeżość albo pusta odmowa."""
    try:
        info = pobierz_info(klient)
        pamiec = wczytaj_pamiec(plik)
        pamiec.update(info)
        pamiec["sprawdzono_o"] = time.time()
        zapisz_pamiec(pamiec, plik)
        sprawdzono_o = None
    except BladAktualizacji as blad:
        pamiec = wczytaj_pamiec(plik)
        if not all(p in pamiec for p in WYMAGANE_POLA):
            raise BladAktualizacji(
                f"nie udało się dowiedzieć od SF o wersjach ({blad}) i nie mam żadnej "
                f"pamięci podręcznej — sprawdź adres i sieć.") from None
        info = pamiec
        sprawdzono_o = pamiec.get("sprawdzono_o")

    mow(f"Twój Kit:  v{WERSJA}")
    mow(f"Najnowsza: {info.get('latest')}  (tag {info.get('tag')})")
    mow(f"Wymagana:  {info.get('min')}")
    if info.get("breaking"):
        mow("To wydanie zrywa zgodność ze starszymi wersjami.")
    if sprawdzono_o is not None:
        from datetime import datetime, timezone
        kiedy = datetime.fromtimestamp(float(sprawdzono_o), tz=timezone.utc)
        mow(f"(dane z pamięci podręcznej — SF nie odpowiada; sprawdzono "
            f"{kiedy.strftime('%Y-%m-%d %H:%M')} UTC)")
    linia = linia_o_dostepnej(info)
    mow(linia if linia else "Jesteś na bieżąco.")
    return 0


# ── automatyczny patch workera ────────────────────────────────────────────────


def _raz_na_dobe(pamiec: dict, znacznik: str, teraz: float, plik: Path | None,
                 mow, tekst: str) -> None:
    """Wypisz linię, gdy jej znacznik jest starszy niż dobę — i odśwież znacznik."""
    poprzednio = pamiec.get(znacznik)
    try:
        ponow = teraz - float(poprzednio) >= SWIEZOSC_S
    except (TypeError, ValueError):
        ponow = True
    if ponow:
        pamiec[znacznik] = teraz
        zapisz_pamiec(pamiec, plik)
        mow(tekst)


def auto_patch(klient, konf, *, teraz: float | None = None, repo=None,
               mow=print, plik: Path | None = None) -> int | None:
    """Jeden krok pętli workera: czy TERAZ podmienić kod? Oddaje KOD WYJŚCIA procesu
    (`KOD_RESTARTU_PO_AKTUALIZACJI`) albo `None` — pracuj dalej.

    Warunki (wszystkie naraz, kontrakt z GO): `auto_update: patch` w config.json ·
    profil `worker` · najnowsza wersja to POPRAWKA w tym samym minor (`0.13.x`) ·
    nie było nieudanej próby w ostatnich `PRZERWA_PO_NIEUDANEJ_AKTUALIZACJI_S`.
    Wydanie większe niż poprawka NIE aktualizuje się samo — worker informuje o nim
    raz na dobę, instaluje je człowiek (`sf-kit update`). Wywołanie między zadaniami,
    nigdy w trakcie, i tylko gdy przed chwilą udało się porozmawiać z SF.
    """
    if getattr(konf, "auto_update", "off") != "patch":
        return None
    if getattr(konf, "profil", "") != "worker":
        return None

    teraz = time.time() if teraz is None else teraz
    try:
        pamiec = sprawdz_wersje(klient, teraz=teraz, plik=plik)
        if not pamiec:
            return None

        latest = pamiec.get("latest") or ""
        if not latest or porownaj_wersje(WERSJA, latest) >= 0:
            return None

        if not ten_sam_minor(WERSJA, latest):
            _raz_na_dobe(pamiec, "wieksze_wydanie_o", teraz, plik, mow,
                         f"Dostępny Kit {latest} — to więcej niż poprawka, więc instaluje "
                         f"ją człowiek (`sf-kit update`); automatycznie biorę tylko poprawki.")
            return None

        rezygnacja = pamiec.get("rezygnacja_o")
        try:
            if teraz < float(rezygnacja):
                return None
        except (TypeError, ValueError):
            pass

        def mow_do_logu(tekst: str) -> None:
            for linia in str(tekst).splitlines() or [""]:
                mow(linia)

        try:
            podmieniono = aktualizuj(klient, repo=repo, mow=mow_do_logu)
        except BladAktualizacji as blad:
            pamiec["rezygnacja_o"] = teraz + PRZERWA_PO_NIEUDANEJ_AKTUALIZACJI_S
            zapisz_pamiec(pamiec, plik)
            mow(f"auto_update: {blad} — kolejna próba za "
                f"{PRZERWA_PO_NIEUDANEJ_AKTUALIZACJI_S // 3600} h.")
            return None
        return KOD_RESTARTU_PO_AKTUALIZACJI if podmieniono else None
    except Exception:                      # noqa: BLE001 — aktualizacja to dodatek, nie warunek pracy
        return None


def restart_hint(konf) -> str:
    """Przypomnienie o restarcie workera po ręcznym `sf-kit update` — z nazwą usługi."""
    slug = getattr(konf, "slug", "") or "?"
    if sys.platform == "darwin":
        return (f"Worker na tej maszynie działa na STARYM kodzie, dopóki się nie zrestartuje: "
                f"launchctl kickstart -k gui/$(id -u)/pl.dpakula.sf-kit.worker.{slug}")
    return (f"Worker na tej maszynie działa na STARYM kodzie, dopóki się nie zrestartuje: "
            f"systemctl --user restart sf-kit-worker@{slug}")
