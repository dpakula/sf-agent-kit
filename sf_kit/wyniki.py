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

JSON I HTML PAKUJEMY DO ZIP, NIE ODRZUCAMY
SF nie przyjmuje tych dwóch typów (`multipart.TYPY_PRZYJMOWANE`) i ma po temu powody. Ale
odrzucenie wyniku dlatego, że ma złe rozszerzenie, znaczyłoby, że praca jest zrobiona i przepada
— więc pakujemy. Pakujemy POJEDYNCZO (`raport.json` → `raport.json.zip`), a nie wszystko w jedno
archiwum: człowiek otwierający sprawę ma widzieć, ile rzeczy dostał i jak się nazywają.
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
MAKS_PLIKOW = 12

#: Sufit rozmiaru POJEDYNCZEGO pliku. Większy wynik to znak, że oddajemy nie to, co trzeba
#: (zrzut bazy zamiast raportu) — lepiej powiedzieć to wprost niż wysyłać 200 MB przez multipart.
MAKS_BAJTOW = 25 * 1024 * 1024


@dataclass
class Zebrane:
    """Co udało się zebrać i czego świadomie NIE bierzemy — oba potrzebne w sprawozdaniu."""
    pliki: list[Path] = field(default_factory=list)
    pominiete: list[str] = field(default_factory=list)
    #: Pliki spakowane do zip po drodze — do posprzątania przez wołającego.
    tymczasowe: list[Path] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.pliki)


def sciezki_z_tresci(tresc: str) -> list[str]:
    """Ścieżki z linii `WYNIK:`. Kolejność zachowana — człowiek wypisał je w jakiejś kolejności."""
    return [m.group(1).strip() for m in WZORZEC_WYNIKU.finditer(tresc or "")]


def zbierz(tresc: str, *, katalog: Path | str, od_czasu: float) -> Zebrane:
    """Pliki wynikowe zadania. `od_czasu` = znacznik startu zadania (`time.time()`).

    Kolejność dróg jest częścią kontraktu: jawne `WYNIK:` WYGRYWA i wtedy `outgoing/` w ogóle
    nie przeglądamy. Inaczej zadanie, które wskazało jeden plik, dostałoby do niego wszystko,
    co model zapisał po drodze — a autor zadania powiedział wprost, czego oczekuje.
    """
    baza = Path(katalog).expanduser().resolve()
    zebrane = Zebrane()

    wskazane = sciezki_z_tresci(tresc)
    if wskazane:
        for surowa in wskazane:
            _dodaj(zebrane, _rozwin(baza, surowa), etykieta=surowa)
        return _dopasuj_do_sf(zebrane)

    katalog_wyjsc = baza / KATALOG_WYNIKOW
    if not katalog_wyjsc.is_dir():
        return zebrane

    # Tylko NOWE — patrz nagłówek. `outgoing/` bywa pełen rzeczy z poprzednich zadań.
    swieze = sorted(
        (p for p in katalog_wyjsc.rglob("*")
         if p.is_file() and p.stat().st_mtime >= od_czasu),
        key=lambda p: p.stat().st_mtime,
    )
    for p in swieze:
        _dodaj(zebrane, p, etykieta=str(p.relative_to(baza)))
    return _dopasuj_do_sf(zebrane)


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


def _spakuj(plik: Path) -> Path | None:
    """`raport.json` → `raport.json.zip` w katalogu TYMCZASOWYM. `None`, gdy się nie udało.

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
    return "\n\n".join(czesci)
