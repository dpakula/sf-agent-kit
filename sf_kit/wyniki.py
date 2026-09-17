"""Co worker oddaje jako WYNIK i jak to trafia na sprawę (SF Agent Kit v0.4, ADVERTPR-777 B).

v0.4 (15.09.2026) - APro Agents / borys-sf

DLACZEGO ZAŁĄCZNIK, A NIE ŚCIEŻKA W TREŚCI WPISU
Damian (15.09, ADVERTPR-799): *„czy agent nie powinien dodać treści jako załączniki?"*. Do v0.3
worker pisał w sprawozdaniu ścieżkę pliku na SWOJEJ maszynie — czyli informację bezużyteczną dla
każdego, kto tej maszyny nie ma. Wynik pracy ma być **do kliknięcia w sprawie**, nie do
odtworzenia przez SSH.

SKĄD WIEMY, CO JEST WYNIKIEM — DWIE DROGI, W TEJ KOLEJNOŚCI
1. **`WYNIK: <ścieżka>` w treści zadania.** Jawne wskazanie zawsze wygrywa: człowiek pisząc
   zadanie wie, co ma z niego wyjść. Wiele linii dozwolone.
2. **Wszystko NOWE w `outgoing/` od startu zadania.** Bo taka jest konwencja katalogu roboczego
   agentów i bo bez niej każde zadanie musiałoby pamiętać o dopisaniu linii.

Druga droga patrzy na czas modyfikacji, nie na samą obecność pliku: katalog `outgoing/` bywa
pełen rzeczy z poprzednich zadań, a doklejanie ich do cudzej sprawy to wyciek — pliki z jednego
klienta wylądowałyby w sprawie drugiego.

NIEDOZWOLONY TYP NIE MOŻE SKASOWAĆ WYNIKU
Pliki `.py`, `.json` i `.mp4` wysyłamy jako kopie `.txt`, zgodnie z kontraktem API, i opisujemy
to we wpisie. Inne niedozwolone typy pakujemy pojedynczo do ZIP.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .multipart import TYPY_PRZYJMOWANE, typ_pliku

#: Linia wskazująca wynik. Dwukropek obowiązkowy, wielkość liter bez znaczenia, wiodące znaki
#: listy (`- `, `* `) dozwolone — bo ludzie piszą zadania w Markdownie, a nie w formacie.
WZORZEC_WYNIKU = re.compile(r"^\s*[-*]?\s*WYNIK\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)

#: Katalog, w którym agenci zostawiają to, co oddają. Konwencja starsza niż Kit.
KATALOG_WYNIKOW = "outgoing"

#: Sufit liczby załączników na jeden wpis. Nie z ostrożności: wpis z czterdziestoma plikami
#: jest nieczytelny, a zadanie, które tyle produkuje, było za duże.
#:
#: Podniesiony z 12 do 20 razem ze zmianą kontraktu w `zbierz` (17.09): skoro bierzemy teraz
#: DWIE drogi naraz, a nie jedną, dwunastka obcinałaby wyniki, które wcześniej się mieściły.
MAKS_PLIKOW = 20

#: Odrzucane przez API, a będące TEKSTEM — kopia `.txt` zachowuje wynik i daje dozwolony MIME.
#: Kit sam tę drogę podpowiada człowiekowi (`multipart.PODPOWIEDZI` przy `application/json`),
#: więc worker robi to, co i tak byśmy komuś doradzili.
#:
#: WYŁĄCZNIE TEKST — i to jest granica, nie przeoczenie. `.mp4` stało tu w PR #1 i wypadło:
#: film przemianowany na `.txt` to nie plik tekstowy, tylko bajty z kłamiącą nazwą. Człowiek,
#: który go pobierze, dostaje coś, czego nie otworzy bez zgadnięcia, że ma zmienić rozszerzenie
#: z powrotem. ZIP niesie binaria bez kłamstwa i jest przez API przyjmowany — więc wszystko,
#: co nie jest tekstem, idzie drogą zipa niżej.
ROZSZERZENIA_JAKO_TEKST = {".py", ".json"}

#: Sufit rozmiaru POJEDYNCZEGO pliku. Większy wynik to znak, że oddajemy nie to, co trzeba
#: (zrzut bazy zamiast raportu) — lepiej powiedzieć to wprost niż wysyłać 200 MB przez multipart.
MAKS_BAJTOW = 25 * 1024 * 1024


@dataclass
class Zebrane:
    """Co udało się zebrać i czego świadomie NIE bierzemy — oba potrzebne w sprawozdaniu."""
    pliki: list[Path] = field(default_factory=list)
    pominiete: list[str] = field(default_factory=list)
    uwagi: list[str] = field(default_factory=list)
    #: Pliki spakowane do zip po drodze — do posprzątania przez wołającego.
    tymczasowe: list[Path] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.pliki)


def sciezki_z_tresci(tresc: str) -> list[str]:
    """Ścieżki z linii `WYNIK:`. Kolejność zachowana — człowiek wypisał je w jakiejś kolejności."""
    return [m.group(1).strip() for m in WZORZEC_WYNIKU.finditer(tresc or "")]


def zbierz(tresc: str, *, katalog: Path | str, od_czasu: float,
           katalogi_swiezych: list[str] | None = None) -> Zebrane:
    """Pliki wynikowe zadania. `od_czasu` = znacznik startu zadania (`time.time()`).

    DWIE DROGI, OBIE NARAZ — ZMIANA KONTRAKTU Z 17.09 (PR #1 Kodeksa)
    ════════════════════════════════════════════════════════════════
    Do v0.5.5 jawne `WYNIK:` WYGRYWAŁO i katalogów nie czytaliśmy wcale. Powód był dobry:
    zadanie, które wskazało jeden plik, nie miało dostać wszystkiego, co model zapisał po
    drodze. Powód PRZECIWNY okazał się mocniejszy w praktyce — wykonawca zapisywał wynik
    w innym umówionym katalogu niż ten, który wymienił w `WYNIK:`, i **praca przepadała po
    cichu**. Cisza jest gorsza niż jeden załącznik za dużo, więc bierzemy obie drogi.

    Czego to NIE znaczy: że bierzemy cokolwiek. Nadal obowiązują trzy granice i to one, a nie
    „wskazanie wygrywa", bronią przed doklejeniem cudzego wyniku:
      · tylko pliki zmodyfikowane PO starcie zadania (`od_czasu`),
      · tylko spod katalogu roboczego (`_rozwin` odrzuca wyjście poza),
      · sufit `MAKS_PLIKOW`, a to, co nie weszło, jest wymienione w sprawozdaniu.
    """
    baza = Path(katalog).expanduser().resolve()
    zebrane = Zebrane()

    wskazane = sciezki_z_tresci(tresc)
    if wskazane:
        for surowa in wskazane:
            znaleziony = _znajdz_wskazany(baza, surowa)
            _dodaj(zebrane, znaleziony, etykieta=surowa)

    # Pliki zmodyfikowane podczas zadania dokładamy także przy jawnym wskazaniu.
    for nazwa in katalogi_swiezych or ["work/zadania", KATALOG_WYNIKOW]:
        katalog_wyjsc = _rozwin(baza, nazwa)
        if katalog_wyjsc is None or not katalog_wyjsc.is_dir():
            continue
        swieze = sorted(
            (p for p in katalog_wyjsc.rglob("*")
             if p.is_file() and p.stat().st_mtime >= od_czasu),
            key=lambda p: (p.stat().st_mtime, str(p)),
        )
        for p in swieze:
            _dodaj(zebrane, p, etykieta=str(p.relative_to(baza)))
    return _dopasuj_do_sf(zebrane)


def _znajdz_wskazany(baza: Path, surowa: str) -> Path | None:
    """Znajdź wskazany plik w umówionej kolejności, nadal wyłącznie pod katalogiem pracy."""
    p = Path(surowa).expanduser()
    if p.is_absolute() or len(p.parts) > 1:
        return _rozwin(baza, surowa)
    for katalog in ("work/zadania", "work", KATALOG_WYNIKOW, "."):
        kandydat = _rozwin(baza, str(Path(katalog) / p))
        if kandydat is not None and kandydat.is_file():
            return kandydat
    return _rozwin(baza, surowa)


def _rozwin(baza: Path, surowa: str) -> Path | None:
    """Ścieżka z zadania → plik na dysku. `None`, gdy wychodzi poza katalog roboczy.

    Wyjście poza katalog jest ODMOWĄ, nie błędem ścieżki: treść zadania pisze ktoś inny niż
    właściciel maszyny, a `WYNIK: ../../.ssh/id_rsa` wygląda dokładnie jak literówka.
    """
    p = Path(surowa).expanduser()
    pelna = (p if p.is_absolute() else baza / p).resolve()
    try:
        pelna.relative_to(baza)
    except ValueError:
        return None
    return pelna


def _dodaj(zebrane: Zebrane, sciezka: Path | None, *, etykieta: str) -> None:
    if sciezka is None:
        zebrane.pominiete.append(f"{etykieta} — poza katalogiem roboczym")
        return
    if sciezka in zebrane.pliki:
        # Ten sam plik wskazany dwa razy (dwie linie `WYNIK:` na tę samą ścieżkę albo dowiązanie)
        # — cicho pomijamy. Dwa identyczne załączniki w jednym wpisie wyglądają jak usterka SF,
        # a są usterką wołającego. Zauważone przy próbie na żywej sprawie 15.09.
        return
    if not sciezka.exists():
        zebrane.pominiete.append(f"{etykieta} — nie ma takiego pliku")
        return
    if sciezka.is_dir():
        zebrane.pominiete.append(f"{etykieta} — to katalog, nie plik")
        return
    if sciezka.stat().st_size == 0:
        zebrane.pominiete.append(f"{etykieta} — plik jest pusty")
        return
    if sciezka.stat().st_size > MAKS_BAJTOW:
        zebrane.pominiete.append(
            f"{etykieta} — {sciezka.stat().st_size // (1024 * 1024)} MB, powyżej limitu")
        return
    if len(zebrane.pliki) >= MAKS_PLIKOW:
        zebrane.pominiete.append(f"{etykieta} — powyżej {MAKS_PLIKOW} załączników na wpis")
        return
    zebrane.pliki.append(sciezka)


def _dopasuj_do_sf(zebrane: Zebrane) -> Zebrane:
    """Typy, których SF nie przyjmie, pakujemy do zip. Reszta idzie bez zmian."""
    gotowe: list[Path] = []
    for p in zebrane.pliki:
        if p.suffix.lower() in ROZSZERZENIA_JAKO_TEKST:
            kopia = _kopia_txt(p)
            if kopia is None:
                zebrane.pominiete.append(f"{p.name} — nie udało się utworzyć kopii .txt")
                continue
            gotowe.append(kopia)
            zebrane.tymczasowe.append(kopia)
            zebrane.uwagi.append(
                f"{p.name} — API odrzuca {p.suffix.lower()}, wysłano jako {kopia.name}")
            continue
        if typ_pliku(p) in TYPY_PRZYJMOWANE:
            gotowe.append(p)
            continue
        spakowany = _spakuj(p)
        if spakowany is None:
            zebrane.pominiete.append(f"{p.name} — nie udało się spakować")
            continue
        gotowe.append(spakowany)
        zebrane.tymczasowe.append(spakowany)
    zebrane.pliki = gotowe
    return zebrane


def _kopia_txt(plik: Path) -> Path | None:
    try:
        katalog = Path(tempfile.mkdtemp(prefix="sf-kit-wynik-"))
        cel = katalog / (plik.name + ".txt")
        shutil.copyfile(plik, cel)
        return cel
    except OSError:
        return None


def _spakuj(plik: Path) -> Path | None:
    """Niedozwolony plik → osobny ZIP w katalogu TYMCZASOWYM. `None`, gdy się nie udało.

    POZA KATALOGIEM ROBOCZYM — i to jest poprawka z 15.09, po dowodzie na żywej sprawie.
    Pierwsza wersja pakowała OBOK oryginału, „żeby człowiek miał archiwum tam, gdzie pracuje".
    Skutek zobaczyłem przy próbie na sprawie 777: archiwum ląduje w `outgoing/`, więc przy
    następnym zbieraniu jest **nowym plikiem** i idzie jako wynik NASTĘPNEGO zadania — czyli
    na sprawę innego klienta. Dokładnie ten wyciek, przed którym broni filtr po czasie startu.

    Sprzątanie po sobie tego nie załatwiało: wystarczy, że raz się nie uda (katalog tylko do
    odczytu, przerwany proces) i śmieć zostaje na zawsze. Katalog tymczasowy usuwa całą klasę
    problemu zamiast łatać jeden jej przypadek. Oryginał zostaje w `outgoing/`, więc nic nie
    ginie — powtórzenie zadania zbuduje archiwum na nowo.
    """
    try:
        katalog = Path(tempfile.mkdtemp(prefix="sf-kit-wynik-"))
        cel = katalog / (plik.name + ".zip")
        with zipfile.ZipFile(cel, "w", zipfile.ZIP_DEFLATED) as archiwum:
            archiwum.write(plik, arcname=plik.name)
    except OSError:
        return None
    return cel


def posprzataj(zebrane: Zebrane) -> None:
    """Skasuj archiwa zrobione po drodze — razem z ich katalogami tymczasowymi.

    Oryginały zostają: to praca człowieka, nie nasza. Nawet gdyby to sprzątanie się nie udało,
    nic złego się nie dzieje — archiwa leżą POZA katalogiem roboczym, więc nie wejdą jako
    wynik następnego zadania (patrz `_spakuj`). Sprzątanie jest tu higieną, nie zabezpieczeniem.
    """
    for p in zebrane.tymczasowe:
        shutil.rmtree(p.parent, ignore_errors=True)
    zebrane.tymczasowe = []


def opis_dla_wpisu(zebrane: Zebrane) -> str:
    """Zdanie o załącznikach do sprawozdania. Pominięte wymieniamy — cisza o nich byłaby stratą."""
    czesci = []
    if zebrane.pliki:
        nazwy = ", ".join(p.name for p in zebrane.pliki)
        czesci.append(f"**Załączam wynik:** {nazwy}")
    if zebrane.pominiete:
        czesci.append("**Nie załączono:** " + "; ".join(zebrane.pominiete))
    if zebrane.uwagi:
        czesci.append("**Zmieniono nazwę do wysyłki:** " + "; ".join(zebrane.uwagi))
    return "\n\n".join(czesci)
