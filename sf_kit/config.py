"""Konfiguracja Kitu — wszystko POZA kluczem.

v0.1 (14.09.2026) - APro Agents / borys-sf

Rozdział jest celowy: konfiguracja jest do oglądania i poprawiania ręcznie (`cat`, edytor,
wklejenie do zgłoszenia), klucz nie jest. Trzymanie ich razem znaczyłoby, że pokazanie komuś
własnych ustawień pokazuje mu też klucz.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .klucz import sciezka_konfiguracji

PLIK = "config.json"

#: Domyślny odstęp odpytywania. Minuta, bo zadania w SF nie pojawiają się częściej niż ludzie
#: je zakładają, a każde odpytanie to żądanie do cudzego serwera. Do zmiany flagą.
DOMYSLNY_ODSTEP_S = 60

#: Domyślny limit czasu na jedno zadanie. Pół godziny: dłuższa praca to znak, że zadanie było
#: za duże, a nie że model potrzebuje więcej czasu — i lepiej, żeby wtedy wróciło do człowieka.
DOMYSLNY_LIMIT_ZADANIA_S = 1800


@dataclass
class Konfiguracja:
    """Ustawienia Kitu. Pola bez wartości domyślnych są wymagane przy `init`."""

    adres: str = "https://sf.dpakula.pl"
    #: DOMYŚLNA Organizacja — wygoda, nie wymóg (v0.4). Pusta znaczy „pytaj SF i wymagaj --org,
    #: gdy jest z czego wybierać". Konfiguracja z 0.3 miała tu wpisaną Organizację i to dalej
    #: działa: to, co było wpisane, jest po prostu domyślne.
    organizacja: str = ""              # identyfikator Organizacji (X-Tenant-Id)
    slug: str = ""                     # mój slug agenta — po nim odsiewam swoje zadania
    katalog_roboczy: str = ""          # gdzie wykonawca ma pracować; pusty = bieżący
    #: Który profil Kitu. Jedno narzędzie, trzy role — i pomoc pokazuje tylko to, co do tej
    #: roli należy. `worker` CIĄGNIE zadania z kolejki, `autor` PCHA do SF gotową pracę
    #: człowieka, `koordynator` dojdzie po `GET /me` (bez niego nie da się sprawdzić, czy
    #: ktoś ma do tego prawo, a profil obiecujący polecenia, które kończą się 403, jest gorszy
    #: od jego braku).
    profil: str = "worker"
    runtime: str = "codex"             # codex | kimi | shell
    odstep_s: int = DOMYSLNY_ODSTEP_S
    limit_zadania_s: int = DOMYSLNY_LIMIT_ZADANIA_S

    #: Czy wolno uruchamiać wykonawcę `shell`. **Domyślnie nie** i tak ma zostać u każdego,
    #: kto nie wie, po co miałby to zmienić.
    #:
    #: `shell` wykonuje treść zadania JAK SKRYPT. To jest narzędzie do sprawdzenia, czy cała
    #: pętla (odbiór → wykonanie → wpis → zamknięcie) działa BEZ modelu — i do niczego więcej.
    #: Sama flaga `--runtime shell` wystarczała do 0.1, więc każdy, kto ją zobaczył w pomocy,
    #: mógł zamienić dowolne zadanie z kolejki w polecenie powłoki na swojej maszynie.
    #: Teraz trzeba jeszcze świadomie dopisać to pole do pliku ustawień — a dopisuje je
    #: administrator, nie osoba, która przegląda `--help`.
    zezwol_shell: bool = False

    #: Kto ma dostawać powiadomienia o sprawach zakładanych przez tego agenta —
    #: identyfikatory KONT w SalesForge (nie adresy).
    #:
    #: Sprawdzone w kodzie SF: przy kluczu API backend **nie dopisuje nikogo poza samym
    #: autorem** („skip for API key" w `create_ticket`). Sprawa założona przez agenta spoza
    #: floty bez tej listy nie powiadomiłaby NIKOGO — leżałaby, wyglądając na zgłoszoną.
    #:
    #: Identyfikatory wpisuje ADMINISTRATOR: agent nie ma ich jak odczytać, bo lista kont
    #: jest dla jego klucza niedostępna. To jest znana niedogodność, zgłoszona jako luka
    #: (README, „Ograniczenia") — nie docelowy kształt.
    obserwatorzy_domyslni: list = field(default_factory=list)

    def braki(self) -> list[str]:
        """Czego brakuje, żeby worker mógł ruszyć. Pusta lista = wszystko jest.

        Sprawdzamy TUTAJ, a nie przy pierwszym żądaniu — worker, który wystartował i dopiero
        po minucie mówi „nie mam sluga", wygląda jak worker, który działa.
        """
        puste = []
        if not self.adres:
            puste.append("adres")
        if not self.slug:
            puste.append("slug (twoja nazwa agenta w SF)")
        # ORGANIZACJI TU JUŻ NIE MA i to jest zmiana v0.4. Do v0.3 brak Organizacji w pliku
        # był brakiem konfiguracji; od `GET /me` (ADVERTPR-796) jest normalnym stanem: agent
        # podaje `--org` przy poleceniu albo ma dokładnie jedną Organizację z nadaniami i Kit
        # ją rozpozna. Zostawienie tego warunku znaczyłoby, że `init` dalej MUSI o nią pytać.
        return puste


def sciezka() -> Path:
    return sciezka_konfiguracji() / PLIK


def wczytaj_jesli_jest() -> Konfiguracja | None:
    """Konfiguracja, ale tylko gdy PLIK ISTNIEJE — inaczej `None`.

    Używane przez `init`, zanim wiadomo, o którego agenta chodzi: przy kilku agentach na
    maszynie samo `wczytaj()` nie ma jak wybrać i słusznie odmawia. Tutaj brak odpowiedzi
    jest poprawną odpowiedzią („nie mam czego podpowiedzieć"), więc odmowę połykamy.
    """
    from .klucz import WieluAgentow

    try:
        plik = sciezka()
    except WieluAgentow:
        return None
    return wczytaj() if plik.exists() else None


def wczytaj() -> Konfiguracja:
    """Konfiguracja z pliku albo domyślna. Nieznane klucze POMIJAMY, nie wywracamy się.

    Plik pisze człowiek i pisze go ręcznie. Literówka w nazwie pola ma znaczyć „to pole
    zostaje domyślne", a nie „Kit się nie uruchamia" — bo drugie zmusza do zgadywania,
    które pole jest niedobre.
    """
    plik = sciezka()
    if not plik.exists():
        return Konfiguracja()
    try:
        dane = json.loads(plik.read_text(encoding="utf-8"))
    except json.JSONDecodeError as blad:
        raise RuntimeError(
            f"{plik} nie jest poprawnym JSON-em ({blad}). Popraw plik albo go skasuj "
            f"i uruchom `sf-kit init` jeszcze raz.") from None
    znane = {p for p in Konfiguracja.__dataclass_fields__}
    return Konfiguracja(**{k: v for k, v in dane.items() if k in znane})


def zapisz(konf: Konfiguracja) -> Path:
    katalog = sciezka_konfiguracji()
    katalog.mkdir(parents=True, exist_ok=True)
    plik = sciezka()
    plik.write_text(json.dumps(asdict(konf), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return plik
