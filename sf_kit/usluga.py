"""Worker jako usługa systemd + tętno (ADVERTPR-807 C6).

v0.1 (16.09.2026) - APro Agents / borys-sf · decyzja Damiana 15.09 21:2x

PO CO USŁUGA
════════════
Worker uruchamiany ręcznie w terminalu żyje tak długo, jak sesja SSH. Po rozłączeniu, po
restarcie maszyny albo po jednym nieobsłużonym wyjątku po prostu znika — i nikt się o tym nie
dowiaduje, bo brak workera wygląda dokładnie tak samo jak brak zadań w kolejce. Usługa
z `Restart=always` zamienia „zniknął" w „wrócił po trzydziestu sekundach".

TĘTNO JEST PLIKIEM, I TO NIE JEST PROWIZORKA
Zadanie przewidywało trasę w SF. Sprawdziłem: **pola per AGENT nie ma** (`fleet_agents` to
`fleet_id`, `agent_user_id`, `slug`, `home_path`), a istniejące `fleets.last_seen_at` opisuje
BRAMKĘ floty, nie pojedynczego workera, i zapisuje je zupełnie inna droga (klucz floty, nie
klucz agenta). Dopisanie się tam kluczem agenta znaczyłoby „bramka żyje", czyli nieprawdę.

Plik ma zresztą własność, której trasa nie ma: **worker bez łączności z SF nadal go zapisuje**.
Tętno pisane do SF milczałoby dokładnie wtedy, gdy zawodzi sieć — czyli w jednym z dwóch
przypadków, dla których tętno w ogóle istnieje, nie dałoby się odróżnić „worker padł" od
„worker żyje, ale nie ma jak tego powiedzieć". Czujka czyta plik przez SSH i widzi różnicę.

Propozycja kolumny per agent poszła wpisem na 807; gdy powstanie, ten moduł dokłada wysyłkę
obok pliku, nie zamiast niego.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

#: Gdzie worker zostawia ślad życia. Stała ścieżka, bo czujka czyta ją przez SSH i nie ma
#: jak zapytać o konfigurację agenta.
KATALOG_TETNA = Path.home() / ".sf-kit"
PLIK_TETNA = KATALOG_TETNA / "heartbeat"

#: Po ilu sekundach bez tętna uznajemy workera za martwego. Dwie minuty to trzy takty pętli
#: przy domyślnym odstępie 60 s — jeden zgubiony takt nie ma budzić nikogo w nocy.
PROG_MARTWOTY_S = 120


def zapisz_tetno(*, slug: str, stan: str = "czekam", wazne_przez_s: int = PROG_MARTWOTY_S,
                 plik: Path | None = None) -> None:
    """Zostaw ślad życia. Błąd zapisu NIE może zatrzymać workera.

    `wazne_przez_s` to deklaracja workera: „ten stan może legalnie trwać tyle". Bez niej czujka
    musiałaby zgadywać jednym progiem dla wszystkiego — a zadanie z limitem trzydziestu minut
    NIE odświeża tętna w trakcie wykonania i po dwóch minutach wyglądałoby na martwe. Restart
    usługi w połowie pracy modelu byłby wtedy gorszy od awarii, której miał zapobiec.

    Tętno jest diagnostyką; worker, który przestaje pracować, bo nie da się zapisać pliku
    diagnostycznego, zamienia drobną usterkę w awarię.
    """
    plik = plik or PLIK_TETNA
    try:
        plik.parent.mkdir(parents=True, exist_ok=True)
        # Zapis przez plik tymczasowy i `replace`: czujka czytająca w trakcie zapisu
        # dostałaby inaczej połowę linii i uznała tętno za uszkodzone.
        tymczasowy = plik.with_suffix(".tmp")
        tymczasowy.write_text(json.dumps({
            "slug": slug,
            "stan": stan,
            "kiedy": int(time.time()),
            "wazne_do": int(time.time()) + int(wazne_przez_s),
            "pid": os.getpid(),
        }, ensure_ascii=False), encoding="utf-8")
        os.replace(tymczasowy, plik)
    except OSError:
        pass


def czy_zywy(plik: Path | None = None, *, teraz: float | None = None,
             prog_s: int = PROG_MARTWOTY_S) -> tuple[bool, str]:
    """`(czy żyje, co powiedzieć człowiekowi)`. Używane przez czujkę i przez `sf-kit heartbeat`."""
    plik = plik or PLIK_TETNA
    teraz = teraz if teraz is not None else time.time()
    try:
        dane = json.loads(plik.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False, f"brak pliku tętna ({plik}) — worker nigdy nie wystartował albo padł przy starcie"
    except (OSError, ValueError):
        return False, f"plik tętna ({plik}) jest nieczytelny"

    kiedy = float(dane.get("kiedy", 0))
    ile = teraz - kiedy
    # Worker deklaruje, jak długo BIEŻĄCY stan może legalnie trwać. Starsze tętna (sprzed
    # dołożenia tego pola) wracają do stałego progu — bez tego aktualizacja Kitu ogłaszałaby
    # wszystkie workery martwymi.
    wazne_do = dane.get("wazne_do")
    granica = float(wazne_do) if wazne_do else kiedy + prog_s

    if teraz > granica:
        return False, (f"ostatnie tętno {int(ile)} s temu, a stan „{dane.get('stan', '?')}” "
                       f"miał trwać najwyżej do {int(granica - kiedy)} s — "
                       f"worker „{dane.get('slug', '?')}” nie odpowiada")
    return True, (f"worker „{dane.get('slug', '?')}” żyje, ostatnie tętno {int(ile)} s temu "
                  f"(stan: {dane.get('stan', '?')})")


UNIT = """\
[Unit]
Description=SF Agent Kit — worker agenta {slug}
# Po sieci, bo pierwsze, co worker robi, to zapytanie do SalesForge.
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={katalog_domowy}
ExecStart={polecenie} --agent {slug} worker
# Klucz NIE stoi w tym pliku: unit bywa czytany szerzej niż katalog agenta, a sekret
# przepisany do opisu usługi zostaje tam na zawsze i wraca w każdym `systemctl cat`.
EnvironmentFile=-{plik_srodowiska}
Restart=always
RestartSec=30
# Worker pada najczęściej na sieci, a wtedy chcemy ponawiania bez końca, nie poddania się
# po pięciu próbach — stąd zdjęty limit startów.
StartLimitIntervalSec=0
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""


def tresc_unitu(*, slug: str, polecenie: str, katalog_domowy: str,
                plik_srodowiska: str) -> str:
    """Treść pliku jednostki dla tego agenta."""
    return UNIT.format(slug=slug, polecenie=polecenie, katalog_domowy=katalog_domowy,
                       plik_srodowiska=plik_srodowiska)


def nazwa_unitu(slug: str) -> str:
    return f"sf-kit-worker@{slug}.service"


def sciezka_unitu(slug: str, *, katalog: Path | None = None) -> Path:
    """Domyślnie jednostka UŻYTKOWNIKA — instalacja bez `sudo`.

    Usługa systemowa wymagałaby praw roota na cudzej maszynie, a Kit jest narzędziem, które
    ma się dać uruchomić bez proszenia administratora o cokolwiek. Kto chce systemowej,
    kopiuje ten sam plik do `/etc/systemd/system/` — treść jest identyczna.
    """
    katalog = katalog or (Path.home() / ".config" / "systemd" / "user")
    return katalog / nazwa_unitu(slug)
