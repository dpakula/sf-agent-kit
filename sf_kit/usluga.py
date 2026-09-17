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

#: Gdzie worker zostawia ślad życia. Ścieżka wyliczalna z samego sluga, bo czujka czyta ją
#: przez SSH i nie ma jak zapytać o konfigurację agenta.
KATALOG_TETNA = Path.home() / ".sf-kit"

#: Tętno SPRZED v0.5.3 — jeden plik na konto systemowe. Zostaje wyłącznie do ODCZYTU, żeby
#: czujka nie ogłosiła martwym workera, który jeszcze nie dostał nowej wersji.
PLIK_TETNA_STARY = KATALOG_TETNA / "heartbeat"


def plik_tetna(slug: str) -> Path:
    """Tętno JEDNEGO workera: `~/.sf-kit/heartbeat-{slug}` (v0.5.3, ADVERTPR-850).

    DLACZEGO PER SLUG, A NIE PER KONTO SYSTEMOWE. Do v0.5.2 wszyscy workerzy na jednym koncie
    pisali do `~/.sf-kit/heartbeat`. Przy jednym workerze na maszynę to działało i dokładnie
    dlatego nikt tego nie zauważył. Decyzja z 17.09 daje **dwa konta na wykonawcę**
    (`kodeks-worker` + `kodeks`, tak jak Kimi), więc dwa workery na tym samym koncie
    systemowym nadpisywałyby sobie ślad życia nawzajem: czujka widziałaby jedno tętno,
    uznała oba za żywe i nie zauważyła, że jeden z nich leży.

    Nazwa pliku ma slug w NAZWIE, a nie w treści, bo czujka sprawdza istnienie pliku przez SSH
    jednym `test -f` — zaglądanie do środka po to, żeby dowiedzieć się, czyje to tętno, kazałoby
    jej parsować JSON dla każdego kandydata.
    """
    czysty = "".join(z for z in (slug or "") if z.isalnum() or z in "-_") or "bez-slugu"
    return KATALOG_TETNA / f"heartbeat-{czysty}"

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
    plik = plik or plik_tetna(slug)
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
             prog_s: int = PROG_MARTWOTY_S, slug: str | None = None) -> tuple[bool, str]:
    """`(czy żyje, co powiedzieć człowiekowi)`. Używane przez czujkę i przez `sf-kit heartbeat`.

    Gdy podano `slug`, czytamy `heartbeat-{slug}`, a **gdy go nie ma — spadamy na plik sprzed
    v0.5.3**. Zapas jest tu dlatego, że aktualizacja Kitu na maszynach nie dzieje się w jednej
    chwili: czujka z nową wersją odpytywałaby workera ze starą i ogłaszała go martwym, choć
    ten pracuje. Zapas zniknie, gdy wszystkie maszyny przejdą na v0.5.3+.
    """
    if plik is None and slug:
        nowy = plik_tetna(slug)
        plik = nowy if nowy.exists() else PLIK_TETNA_STARY
    plik = plik or PLIK_TETNA_STARY
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


#: launchd (macOS). Zapisywany jako `~/Library/LaunchAgents/pl.dpakula.sf-kit.worker.{slug}.plist`.
PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{etykieta}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{polecenie}</string>
    <string>--agent</string><string>{slug}</string>
    <string>worker</string>
  </array>
  <key>WorkingDirectory</key><string>{katalog_domowy}</string>
  <!-- KeepAlive, nie RunAtLoad+exit: worker ma wstawać po każdej awarii, tak samo jak
       `Restart=always` w systemd. Bez tego jedna utrata sieci kończy pracę na cały dzień. -->
  <key>KeepAlive</key><true/>
  <key>RunAtLoad</key><true/>
  <!-- Odstęp po padzie. Domyślne 1 s przy awarii sieci daje setki startów na minutę
       i log, w którym nie da się znaleźć przyczyny. -->
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log_bledow}</string>
  <!-- launchd NIE czyta profilu powłoki: proces dostaje goły PATH i nie znajduje ani
       `codex`, ani `kimi`, ani samego `sf-kit`. To jest najczęstsza przyczyna „usługa
       wstała i nic nie robi" na macOS, więc PATH podajemy wprost. -->
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>{sciezka_path}</string>
    <key>SF_KIT_AGENT</key><string>{slug}</string>
  </dict>
</dict>
</plist>
"""


def etykieta_launchd(slug: str) -> str:
    return f"pl.dpakula.sf-kit.worker.{slug}"


def sciezka_plist(slug: str, *, katalog: Path | None = None) -> Path:
    """`~/Library/LaunchAgents/…` — agent UŻYTKOWNIKA, instalacja bez `sudo`.

    Ta sama zasada co przy systemd: Kit ma się dać uruchomić bez proszenia administratora.
    `/Library/LaunchDaemons/` (systemowy) wymagałby roota i chodziłby bez zalogowanego
    użytkownika — kto tego potrzebuje, kopiuje ten sam plik.
    """
    katalog = katalog or (Path.home() / "Library" / "LaunchAgents")
    return katalog / f"{etykieta_launchd(slug)}.plist"


def tresc_plist(*, slug: str, polecenie: str, katalog_domowy: str,
                log: str | None = None, sciezka_path: str | None = None) -> str:
    """Treść agenta launchd dla tego workera (v0.5.3, ADVERTPR-850).

    `log` w `~/Library/Logs/`, bo tam macOS trzyma logi aplikacji użytkownika i tam szuka ich
    Console.app — plik w katalogu domowym byłby niewidoczny dla każdego, kto nie wie, gdzie
    patrzeć. Osobny plik błędów, bo przy `KeepAlive` to on odpowiada na pytanie „dlaczego
    wstaje w kółko".
    """
    baza_logow = Path.home() / "Library" / "Logs" / "sf-kit"
    log = log or str(baza_logow / f"worker-{slug}.log")
    return PLIST.format(
        etykieta=etykieta_launchd(slug),
        slug=slug,
        polecenie=polecenie,
        katalog_domowy=katalog_domowy,
        log=log,
        log_bledow=log.replace(".log", ".err.log") if log.endswith(".log") else f"{log}.err",
        sciezka_path=sciezka_path or _domyslny_path(),
    )


def _domyslny_path(sciezka: str | None = None) -> str:
    """PATH dla launchd: bieżący PATH plus miejsca, w których stoją narzędzia modeli.

    Bierzemy PATH procesu, bo `sf-kit usluga` uruchamia człowiek ze swojej powłoki — czyli
    z tym PATH-em, w którym `codex`/`kimi` NA PEWNO działają (właśnie ich używa). Dokładamy
    dwie ścieżki Homebrew (Intel i Apple Silicon), bo plist bywa przenoszony między maszynami.
    """
    import os as _os

    czesci = [c for c in (sciezka or _os.environ.get("PATH", "")).split(":") if c]
    for dodatkowa in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"):
        if dodatkowa not in czesci:
            czesci.append(dodatkowa)
    return ":".join(czesci)


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
