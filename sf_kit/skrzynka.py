"""Skrzynka wiadomości agenta — odbiór przez PULL (ADVERTPR-812, zakres D).

v0.3 (28.09.2026) - APro Agents / borys-sf
  0.3 — SF-86 pola kontraktu po stronie odbiornika: pilne wątki pierwsze (kolejność w wątku
        nietknięta) + alarm Iris `-u` raz przy przyjęciu, termin ważności (po terminie nie
        wykonujemy, plik sprzątamy), instancja/generacja w potwierdzeniach, dzierżawa przy
        dwóch sesjach, odmowa odbiornika jako `failed` z powodem, eskalacja bez dubla.
v0.2 (28.09.2026) - APro Agents / borys-sf
  0.2 — SF-86 etap 3: `przyjmij` w KAŻDYM takcie (plik z `fsync` → ack `delivered`),
        `zdejmij_z_kolejki` po odbiorze. Wcześniej skrzynka żyła tylko przy starcie zadania.
v0.1 (16.09.2026) - APro Agents / borys-sf

PO CO
═════
Agent dowiadywał się o rzeczach dotyczących jego pracy czterema półkanałami (mail, wiadomość
konsoli z guardem tmux, box, `tmux-say`) i żaden nie miał cyklu „wysłana → dostarczona →
odebrana → odpowiedziana". Trzy incydenty z jednej doby: 816 (sprawa z formularza bez maila
i bez konsoli), 801 (wpis Kodeksa do Agaty nieodebrany), SECO-176 (GO Damiana po 40 minutach).

Od 812 SF ma skrzynkę ze statusem PER ADRESAT. Kit robi z niej to, co robi z zadaniami:
**pobiera w swoim takcie i potwierdza odbiór**. Most tic zostaje budzikiem dla sesji, które
akurat nic nie robią — nie jedynym sposobem dowiedzenia się czegokolwiek.

DWIE RZECZY, KTÓRE TU PILNUJĘ
═════════════════════════════
1. **Potwierdzam odbiór DOPIERO gdy treść trafiła do agenta.** Potwierdzenie przy samym
   odczycie znaczyłoby „odebrane" dla wiadomości, która poszła w powietrze razem z procesem.
   Kolejność jest ta sama, co przy bramce floty: najpierw zapis/pokazanie, potem ack.
2. **Skrzynka nie ma prawa zatrzymać pracy.** Błąd odczytu, 503 przed rewizją, klucz bez
   właściciela — wszystko to znaczy „dziś bez skrzynki", a nie „nie pracuj". Zadanie wykona
   się tak jak przed 812.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .api import BladAPI, Klient, Konflikt

#: Statusy, w których wiadomość CZEKA na agenta. `replied` i `consumed` są już za nim.
STANY_DO_ODEBRANIA = ("new", "delivered", "failed")

#: Ile wiadomości bierzemy w jednym takcie. Nie „wszystkie": skrzynka z zaległościami po
#: tygodniowej przerwie potrafi mieć ich setki, a wstrzyknięcie setki treści do jednego prompta
#: nie jest przekazaniem informacji, tylko jej utopieniem. Reszta zostaje w SF i przyjdzie
#: w następnym takcie — dlatego skrzynka oddaje `razem`, żeby dało się powiedzieć „i 47 dalej".
LIMIT_TAKTU = 5

#: Ranga priorytetu (SF-86). Nieznana wartość = `normal`: nowy priorytet po stronie SF nie ma
#: prawa wyrzucić wiadomości z kolejki ani wypchnąć jej na sam początek.
RANGI_PRIORYTETU = {"pilne": 0, "normal": 1, "niski": 2}

#: Generacja instancji = czas startu PROCESU (rośnie przy każdym restarcie) — ta sama konwencja
#: co puls SF-87. Instancja jest tu PROCESEM (`host:slug:pid`), nie parą maszyna+slug jak
#: w pulsie: dzierżawa ma rozstrzygać między DWIEMA sesjami tego samego agenta na tej samej
#: maszynie, a para maszyna+slug dałaby im identyczną tożsamość — obie „miałyby” dzierżawę.
_GENERACJA = int(time.time())


def ta_instancja(slug: str) -> tuple[str, int]:
    """`(instancja, generacja)` tego procesu — do potwierdzeń i dzierżawy."""
    host = socket.gethostname().split(".")[0] or "host"
    surowa = f"{host}:{slug}:{os.getpid()}"
    return "".join(z if z.isalnum() or z in "_.:@-" else "-" for z in surowa)[:64], _GENERACJA


def _termin(w: dict) -> datetime | None:
    surowy = w.get("wazne_do")
    if not surowy:
        return None
    try:
        return datetime.fromisoformat(str(surowy).replace("Z", "+00:00"))
    except ValueError:
        return None


def po_terminie(w: dict, teraz: datetime | None = None) -> bool:
    """Dyspozycja po terminie ważności — NIE wykonywać (Kodeks: oznaczać, nie wykonywać).

    Druga warstwa: SF sam oznacza takie wiadomości `expired` przy odczycie kolejki i nie oddaje
    ich w `tylko_nieodebrane`. Kit sprawdza jeszcze raz, bo między pobraniem a przekazaniem
    wykonawcy mija czas — a plik w lokalnej kolejce potrafi przeleżeć termin.
    """
    termin = _termin(w)
    return termin is not None and termin < (teraz or datetime.now(timezone.utc))


def uloz(wiadomosci: list[dict]) -> list[dict]:
    """Kolejka odbiornika: wątki z pilną wiadomością NAJPIERW, w wątku — kolejność z SF.

    Kodeks: „pilne wyprzedza inne wątki, nie własne zależności”. Dlatego pilna odpowiedź
    przesuwa do przodu CAŁY swój wątek (z wcześniejszymi wiadomościami, na których stoi),
    a nie przeskakuje ich. Między wątkami o tej samej randze — kolejność pierwszego wystąpienia
    (SF oddaje najstarsze pierwsze), więc bez priorytetów wynik jest identyczny jak dotąd.
    """
    watki: dict[str, list[tuple[int, dict]]] = {}
    for nr, w in enumerate(wiadomosci):
        watek = str(w.get("watek_id") or w.get("message_id") or nr)
        watki.setdefault(watek, []).append((nr, w))
    kolejnosc = sorted(watki.values(), key=lambda pozycje: (
        min(RANGI_PRIORYTETU.get(w.get("priorytet") or "normal", 1) for _, w in pozycje),
        pozycje[0][0]))
    return [w for pozycje in kolejnosc for _, w in pozycje]


def alarm(tytul: str, tresc: str) -> bool:
    """Alarm Iris `-u` (pilne). ALARM, NIE POTWIERDZENIE — o odbiorze mówi tylko SF.

    Iris jest narzędziem maca (`~/.iris/bin/iris-notify`); na VPS go nie ma i to nie jest
    błąd — `False`, a wołający loguje. Ścieżkę można wskazać zmienną `SF_KIT_IRIS`. Treści
    wiadomości do alarmu NIE dajemy (nadawca i identyfikator wystarczą, żeby zajrzeć do SF):
    powiadomienie ląduje poza SF, a treść bywa wewnętrzna.
    """
    binarka = Path(os.environ.get("SF_KIT_IRIS") or Path.home() / ".iris" / "bin" / "iris-notify")
    if not binarka.is_file():
        return False
    try:
        subprocess.run([str(binarka), "-u", "-p", "aproagents", "-t", tytul, tresc],
                       capture_output=True, timeout=6, check=False)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


@dataclass
class Odebrane:
    """Co przyszło w tym takcie i co z tego wynikło."""

    #: Wiadomości przekazane agentowi (już potwierdzone).
    wiadomosci: list[dict] = field(default_factory=list)
    #: Ile jest w skrzynce RAZEM (cała skrzynka, nie ten takt).
    razem: int = 0
    #: Ile czeka dłużej niż próg zaległości — liczone przez SF, nie przez Kit.
    zalegle: int = 0
    #: Wiadomości, których nie udało się potwierdzić (przekazane, ale ack nie przeszedł).
    niepotwierdzone: list[str] = field(default_factory=list)
    #: Powód, dla którego skrzynki dziś nie ma. `None` = skrzynka działa.
    powod_braku: str | None = None
    #: SF-86: pominięte, bo po terminie ważności (Kit ich nie wykonuje).
    wygasle: int = 0
    #: SF-86: dzierżawa u innej instancji tego samego agenta — wykonuje tamta.
    u_innej_instancji: list[str] = field(default_factory=list)
    #: SF-86: alarmy Iris wysłane w tym takcie (pilne / eskalacja).
    alarmy: int = 0

    @property
    def cos_jest(self) -> bool:
        return bool(self.wiadomosci)

    @property
    def ile_dalej(self) -> int:
        """Ile zostało w skrzynce po tym takcie. Zero = wzięliśmy wszystko."""
        return max(0, self.razem - len(self.wiadomosci))


def pobierz(klient: Klient, *, limit: int = LIMIT_TAKTU, dni: int | None = None,
            teraz: datetime | None = None) -> Odebrane:
    """Nieodebrane wiadomości z MOJEJ skrzynki. Nie potwierdza — to osobny krok.

    Rozdzielenie pobrania od potwierdzenia jest celowe: między jednym a drugim treść musi
    trafić do agenta. Funkcja, która robiłaby oba naraz, potwierdzałaby odbiór rzeczy, której
    nikt jeszcze nie zobaczył.
    """
    # Pobieramy SZERZEJ niż oddajemy: pilna wiadomość bywa trzydziesta w kolejce (SF oddaje
    # najstarsze pierwsze), a przy pobraniu pięciu nigdy nie dostałaby szansy wyprzedzić.
    try:
        dane = klient.skrzynka(dni=dni, limit=max(limit, LIMIT_PRZYJECIA),
                               tylko_nieodebrane=True)
    except BladAPI as blad:
        # 503 = tabela adresatów jeszcze nie istnieje (rewizja po stronie SF). 422 = klucz bez
        # właściciela albo konto bez sluga agenckiego. Oba są stanem konfiguracji, nie awarią
        # — i oba mają brzmieć jak stan, żeby nikt nie szukał usterki w Kicie.
        return Odebrane(powod_braku=str(blad))
    except Exception as blad:       # noqa: BLE001 — patrz punkt 2 w nagłówku pliku
        # DLACZEGO TAK SZEROKO, I DLACZEGO Z NAZWĄ WYJĄTKU W POWODZIE
        # ══════════════════════════════════════════════════════════
        # Skrzynka jest dodatkiem do pracy, nie jej warunkiem — obietnica z nagłówka tego pliku.
        # Pierwsza wersja łapała tylko `BladAPI` i `AttributeError` ze starszego klienta (bez
        # metody `skrzynka`) **zatrzymywał worker w połowie zadania**: 16 testów kitu zapaliło
        # się od razu, i dobrze, bo na produkcji byłby to worker, który przestał brać zadania
        # po podniesieniu samego SF.
        #
        # Ale fail-soft potrafi POŁKNĄĆ LITERÓWKĘ (`NameError` wygląda wtedy jak „nie ma
        # skrzynki"), więc nazwa wyjątku wchodzi do `powod_braku` — a wołający ją loguje.
        # Cisza byłaby tu gorsza niż przerwanie.
        return Odebrane(powod_braku=f"{type(blad).__name__}: {blad}")

    czekajace = [w for w in (dane.get("wiadomosci") or []) if w.get("status") in STANY_DO_ODEBRANIA]
    zywe = [w for w in czekajace if not po_terminie(w, teraz)]
    return Odebrane(
        wiadomosci=uloz(zywe)[:limit],
        razem=int(dane.get("nieodebrane") or 0),
        zalegle=int(dane.get("zalegle") or 0),
        wygasle=len(czekajace) - len(zywe),
    )


def potwierdz(klient: Klient, odebrane: Odebrane, *, status: str = "consumed",
              instancja: str | None = None, generacja: int | None = None) -> Odebrane:
    """Potwierdź odbiór wiadomości, które JUŻ trafiły do agenta.

    Potwierdzamy każdą osobno i porażkę pojedynczej zapisujemy, zamiast przerywać całość:
    wiadomość przekazana i niepotwierdzona wróci w następnym takcie (to zła rzecz, ale mała),
    a przerwanie pętli po pierwszym błędzie zostawiłoby nieodebrane wszystkie następne.
    """
    for w in odebrane.wiadomosci:
        mid = str(w.get("message_id") or "")
        if not mid:
            continue
        try:
            klient.potwierdz_odbior(mid, status=status, instancja=instancja, generacja=generacja)
        except Exception:       # noqa: BLE001 — jak wyżej: brak ack jest mały, brak pracy duży
            odebrane.niepotwierdzone.append(mid)
    return odebrane


def zadzierzaw(klient: Klient, odebrane: Odebrane, *, instancja: str, sekundy: int) -> Odebrane:
    """Zostaw tylko wiadomości, na które TA instancja dostała dzierżawę (SF-86, Kodeks pkt 3).

    Dwie sesje jednego agenta widzą tę samą skrzynkę. Bez dzierżawy obie dokleiłyby tę samą
    wiadomość do swojego zadania i obie by ją „wykonały”. Cudza, ważna dzierżawa (409) =
    wiadomość wypada z TEGO zadania — wykonuje ją tamta sesja; to nie jest błąd.

    Dzierżawa niedostępna (SF sprzed rewizji: 503, starsza instalacja bez trasy: 404, sieć)
    = zachowanie sprzed SF-86: wiadomość zostaje. Brak mechanizmu nie może zatrzymać kanału.
    """
    sekundy = max(30, min(3600, int(sekundy)))
    zostaja = []
    for w in odebrane.wiadomosci:
        mid = str(w.get("message_id") or "")
        try:
            wynik = klient.dzierzawa(mid, instancja=instancja, sekundy=sekundy)
        except Exception:       # noqa: BLE001 — patrz wyżej: bez dzierżawy jak przed SF-86
            zostaja.append(w)
            continue
        if wynik.get("przyznana"):
            zostaja.append(w)
        else:
            odebrane.u_innej_instancji.append(mid)
    odebrane.wiadomosci = zostaja
    return odebrane


def oddaj(klient: Klient, odebrane: Odebrane, *, instancja: str) -> None:
    """Oddaj dzierżawy (`sekundy=0`) — wiadomość nieprzekazana ma od razu wrócić do puli."""
    for w in odebrane.wiadomosci:
        try:
            klient.dzierzawa(str(w.get("message_id") or ""), instancja=instancja, sekundy=0)
        except Exception:       # noqa: BLE001 — dzierżawa i tak wygaśnie sama
            pass


def odmowa(klient: Klient, odebrane: Odebrane, *, powod: str, instancja: str | None = None,
           generacja: int | None = None) -> Odebrane:
    """Odbiornik NIE przyjął wiadomości (np. wykonawca bez ramki) → `failed` z powodem.

    Po stronie SF to kolejna próba (`proby + 1`, `ostatni_blad`) — czujka zaległości widzi
    wiadomość, która utknęła, i WIE DLACZEGO. Wcześniej taka wiadomość wisiała jako
    `delivered` bez śladu, że odbiornik jej nie wziął.
    """
    for w in odebrane.wiadomosci:
        mid = str(w.get("message_id") or "")
        try:
            klient.potwierdz_odbior(mid, status="failed", powod=powod, instancja=instancja,
                                    generacja=generacja)
        except Exception:       # noqa: BLE001 — zgłoszenie porażki jest dodatkiem
            odebrane.niepotwierdzone.append(mid)
    return odebrane


#: Ile bierzemy przy PRZYJMOWANIU do kolejki. Więcej niż `LIMIT_TAKTU`, i to jest konieczne,
#: nie hojne: skrzynka oddaje nieodebrane NAJSTARSZE pierwsze, a `delivered` dalej jest
#: nieodebrane. Przy limicie 5 pięć wiadomości przyjętych i czekających na zadanie zasłaniałoby
#: każdą nowszą — worker bez zadań nie przyjąłby już niczego.
LIMIT_PRZYJECIA = 50


def _zapisz_trwale(sciezka: Path, wiadomosc: dict) -> None:
    """Plik → `fsync` → `rename` → `fsync` katalogu. Dopiero to wolno nazwać „trwale przyjętą".

    Ta sama kolejność, co u bramki floty (`write` + `fsync`, potem ack). Bez `fsync` katalogu
    `rename` potrafi nie przeżyć utraty zasilania, a wtedy SF ma `delivered`, a dysk — nic.
    """
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    tymczasowy = sciezka.with_suffix(".tmp")
    with open(tymczasowy, "w", encoding="utf-8") as plik:
        json.dump(wiadomosc, plik, ensure_ascii=False)
        plik.flush()
        os.fsync(plik.fileno())
    os.replace(tymczasowy, sciezka)
    katalog = os.open(sciezka.parent, os.O_RDONLY)
    try:
        os.fsync(katalog)
    finally:
        os.close(katalog)


def przyjmij(klient: Klient, katalog: Path, *, limit: int = LIMIT_PRZYJECIA,
             slug: str = "", teraz: datetime | None = None) -> Odebrane:
    """W KAŻDYM takcie, także bez zadania: nowe wiadomości do lokalnej kolejki + ack `delivered`.

    PO CO (SF-86, etap 3)
    ═════════════════════
    Do SF-86 worker czytał skrzynkę wyłącznie przy starcie zadania. Worker bez zadań nie
    dowiadywał się o niczym, a SF nie umiał odróżnić „worker leży" od „worker żyje, tylko nie
    miał pracy" — jedno i drugie wyglądało jak `new` bez końca.

    „Doręczona" znaczy tu dokładnie to, co w kontrakcie z opinii Kodeksa: **trwale przyjęta
    przez kolejkę odbiornika** — plik z `fsync` w katalogu workera. Nie „przeczytana": odbiór
    (`consumed`) potwierdza dalej `obsluz_zadanie`, PO przekazaniu treści wykonawcy.

    Plik, który już jest, nie jest pisany drugi raz, a ack `delivered` na wiadomości już
    `delivered` nie idzie wcale — to jest deduplikacja po stronie odbiornika, po `message_id`,
    odporna na restart procesu (stan leży na dysku, nie w pamięci).
    """
    odebrane = pobierz(klient, limit=limit, teraz=teraz)
    if odebrane.powod_braku:
        return odebrane
    _sprzataj_po_terminie(katalog, teraz)
    instancja, generacja = ta_instancja(slug or "kit")
    przyjete: list[dict] = []
    for w in odebrane.wiadomosci:
        mid = str(w.get("message_id") or "")
        if not mid:
            continue
        plik = katalog / f"{mid}.json"
        if not plik.exists():
            _zapisz_trwale(plik, w)
            if w.get("priorytet") == "pilne":
                odebrane.alarmy += alarm(f"SF pilne → {slug or 'agent'}",
                                         f"od {w.get('nadawca') or '?'} · wiadomość {mid}")
        else:
            _zanotuj_eskalacje(plik, w, slug, odebrane)
        if w.get("status") == "delivered":
            continue
        try:
            klient.potwierdz_odbior(mid, status="delivered", instancja=instancja,
                                    generacja=generacja)
        except Konflikt:
            # Starsza generacja niż ta, która już potwierdziła — nowsza sesja tego agenta
            # ma tę wiadomość. Nie ponawiamy w kółko i nie traktujemy jak zwykłej porażki.
            odebrane.u_innej_instancji.append(mid)
            continue
        except Exception:       # noqa: BLE001 — brak acka wróci w następnym takcie, plik już jest
            odebrane.niepotwierdzone.append(mid)
            continue
        przyjete.append(w)
    odebrane.wiadomosci = przyjete
    return odebrane


def _zanotuj_eskalacje(plik: Path, w: dict, slug: str, odebrane: Odebrane) -> None:
    """Czujka SF eskalowała TEN SAM rekord (`eskalowano_at`) — jeden alarm na eskalację.

    Nie nowy plik, nie nowy ack, nie nowy prompt: to ta sama wiadomość, tylko pilniejsza
    (Kodeks pkt 2: eskalacja TEGO SAMEGO rekordu). Plik dostaje nowy znacznik eskalacji, więc
    następny takt z tym samym znacznikiem nie alarmuje drugi raz — także po restarcie procesu.
    """
    eskalacja = w.get("eskalowano_at")
    if not eskalacja:
        return
    try:
        zapisana = json.loads(plik.read_text(encoding="utf-8")).get("eskalowano_at")
    except (OSError, ValueError):
        zapisana = None
    if zapisana == eskalacja:
        return
    _zapisz_trwale(plik, w)
    odebrane.alarmy += alarm(f"SF eskalacja → {slug or 'agent'}",
                             f"bez odbioru od {w.get('utworzono') or '?'} · wiadomość "
                             f"{w.get('message_id')}")


def _sprzataj_po_terminie(katalog: Path, teraz: datetime | None) -> int:
    """Pliki wiadomości po terminie ważności wypadają z lokalnej kolejki.

    SF oznacza je `expired` i przestaje oddawać — więc bez sprzątania leżałyby tu wiecznie
    jako „przyjęte, czekają na zadanie”. Zwraca liczbę usuniętych.
    """
    if not katalog.is_dir():
        return 0
    usuniete = 0
    for plik in katalog.glob("*.json"):
        try:
            w = json.loads(plik.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if po_terminie(w, teraz):
            plik.unlink(missing_ok=True)
            usuniete += 1
    return usuniete


def zdejmij_z_kolejki(katalog: Path, odebrane: Odebrane) -> None:
    """Po potwierdzonym `consumed` plik przestaje być potrzebny — prawdą jest SF.

    Pliki NIEpotwierdzonych zostają: wiadomość wróci w następnym takcie i musi dać się
    odróżnić od nowej.
    """
    for w in odebrane.wiadomosci:
        mid = str(w.get("message_id") or "")
        if mid and mid not in odebrane.niepotwierdzone:
            (katalog / f"{mid}.json").unlink(missing_ok=True)


def opis(odebrane: Odebrane) -> str:
    """Skrzynka jako tekst do wstrzyknięcia w prompt albo wypisania w terminalu.

    Treść wiadomości jest tu DOSŁOWNA — nagłówek kontekstu skleja SF (`console/naglowek.py`),
    żeby ta sama wiadomość wyglądała identycznie w tmuxie, w API i tutaj. Kit niczego nie
    dokleja do cudzej treści i niczego nie skraca.
    """
    if not odebrane.wiadomosci:
        return ""
    czesci = [f"── SKRZYNKA ({len(odebrane.wiadomosci)} nowych) ──"]
    for w in odebrane.wiadomosci:
        znacznik = (w.get("utworzono") or "")[:16].replace("T", " ")
        zalega = " [ZALEGA]" if w.get("zalega") else ""
        pilne = " [PILNE]" if w.get("priorytet") == "pilne" else ""
        eskalowana = " [ESKALOWANA]" if w.get("eskalowano_at") else ""
        czesci.append(f"[{znacznik}] od {w.get('nadawca') or '?'}{pilne}{eskalowana}{zalega}\n"
                      f"{w.get('body') or ''}")
    if odebrane.ile_dalej:
        czesci.append(f"(i {odebrane.ile_dalej} dalej w skrzynce — przyjdą w następnym takcie)")
    return "\n\n".join(czesci)
