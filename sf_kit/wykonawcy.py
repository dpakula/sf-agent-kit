"""Wykonawcy zadań — `codex`, `kimi`, `shell`. Jeden interfejs, żeby dołożenie kolejnego było plikiem.

v0.1 (14.09.2026) - APro Agents / borys-sf

DLACZEGO INTERFEJS, SKORO DZIŚ JEST JEDEN WYKONAWCA
═══════════════════════════════════════════════════
Bo drugi jest już zamówiony: po Codexie Damiana wchodzą pracownicy Krzyśka i Wójt u Michała,
a Wójt nie jest Codexem. Interfejs dołożony teraz kosztuje dwadzieścia linii; dołożony później
kosztuje przepisanie workera, który w międzyczasie zdążył komuś działać.

`shell` NIE jest atrapą do testów jednostkowych — jest wykonawcą do **testu odbiorczego bez
modelu**. Zanim sprawdzimy, czy Codex dobrze rozumie zadanie, chcemy wiedzieć, czy w ogóle
cała pętla (odbiór → wykonanie → wpis → zamknięcie) działa. Te dwie rzeczy psują się osobno
i mylenie ich kosztuje pół dnia szukania nie tam, gdzie trzeba.

CZEGO WYKONAWCA NIE DOSTAJE
**Klucza API.** Model rozmawia z plikami i z powłoką, a z SalesForge rozmawia worker. To jest
granica, przez którą nic nie przechodzi — i dlatego `Wynik` nie ma pola na nic, co przyszłoby
z SF poza samą treścią zadania.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class Wynik:
    """Co wyszło z wykonawcy. `udalo_sie=False` znaczy „nie kończ zadania"."""

    udalo_sie: bool
    wyjscie: str
    powod_niepowodzenia: str = ""


class Wykonawca:
    """Interfejs. Dołożenie nowego = nowa klasa i jedna linia w `wybierz`."""

    nazwa = "?"

    #: Czy ten wykonawca ma dostać treść zadania w RAMCE (kim jesteś, gdzie, co oddać).
    #:
    #: Rozróżnienie nie jest kosmetyczne. Model CZYTA to, co dostaje, więc ramka mu pomaga.
    #: Powłoka WYKONUJE to, co dostaje — ramka po polsku jest dla niej błędem składni i kończy
    #: się „unexpected EOF" zamiast pracą. Złapały to testy przy pierwszym wpięciu ramki.
    chce_ramke = False

    def dostepny(self) -> tuple[bool, str]:
        """`(czy da się uruchomić, co powiedzieć człowiekowi, gdy nie)`."""
        raise NotImplementedError

    def wykonaj(self, polecenie: str, *, katalog: str, limit_s: int) -> Wynik:
        raise NotImplementedError


def _uruchom(argumenty: list[str], *, katalog: str, limit_s: int,
             wejscie: str | None = None) -> Wynik:
    """Wspólne uruchomienie podprocesu — jedno miejsce na limit czasu i na obsługę błędów.

    `cwd` podajemy ZAWSZE jawnie. Podproces dziedziczący katalog roboczy workera pracowałby
    tam, gdzie akurat stoi worker, a nie tam, gdzie każe zadanie — i zrobiłby to po cichu.
    """
    try:
        proces = subprocess.run(
            argumenty, cwd=katalog or None, input=wejscie, text=True,
            capture_output=True, timeout=limit_s,
        )
    except subprocess.TimeoutExpired:
        return Wynik(False, "", f"przekroczony limit czasu ({limit_s} s)")
    except FileNotFoundError:
        return Wynik(False, "", f"nie znalazłem programu: {argumenty[0]}")
    except OSError as blad:
        return Wynik(False, "", f"nie udało się uruchomić {argumenty[0]}: {blad}")

    wyjscie = (proces.stdout or "").strip()
    blad = (proces.stderr or "").strip()
    if proces.returncode != 0:
        # Wyjście standardowe dokładamy do powodu, bo przy nieudanym przebiegu to zwykle TAM
        # jest wyjaśnienie, a `stderr` bywa pustym echem. Obcinamy — wpis ma być do czytania.
        szczegol = blad or wyjscie or "(brak wyjścia)"
        return Wynik(False, wyjscie, f"program zakończył się kodem {proces.returncode}: "
                                     f"{szczegol[:800]}")
    return Wynik(True, wyjscie or blad or "(program nic nie wypisał)")


#: Flaga wyłączająca pytania o zgodę. Idzie PRZED podkomendą `exec` — i to nie jest kwestia
#: gustu: `codex exec --ask-for-approval never` kończy się kodem 2 („unexpected argument"),
#: mimo że dokumentacja opisuje tę flagę jako globalną (openai/codex#26602). Forma
#: `codex --ask-for-approval never exec …` działa.
FLAGA_BEZ_PYTAN = ("--ask-for-approval", "never")

#: Ile czekamy na samą sondę wersji. To jest `--version`, nie praca — jeśli nie odpowie
#: w pięć sekund, to i tak nie jest sprawny Codex.
LIMIT_SONDY_S = 5


class WykonawcaCodex(Wykonawca):
    """`codex exec` — bezobsługowy przebieg Codexa z promptem na wejściu.

    `--sandbox workspace-write`: Codex może pisać w katalogu roboczym i nie może poza nim.
    To jest ustawienie, którego NIE wystawiam w konfiguracji — zadanie z cudzego systemu nie
    ma prawa dostać swobody zapisu na całej maszynie tylko dlatego, że ktoś wpisał flagę.

    Prompt idzie przez **wejście standardowe**, nie przez argument: treść zadania bywa długa
    i wielolinijkowa, a argumenty procesu widzi `ps` (to ta sama zasada, co przy kluczu —
    tyle że tu chodzi o cudzą treść, nie o sekret).

    DLACZEGO SONDUJEMY FLAGĘ ZAMIAST JĄ ZAŁOŻYĆ
    ═══════════════════════════════════════════
    Bez wyłączonego pytania o zgodę `codex exec` potrafi CZEKAĆ na zatwierdzenie polecenia.
    Worker chodzi bez nadzoru, więc nikt tego nie zatwierdzi — przebieg wisi do limitu czasu
    i kończy się komunikatem „przekroczony limit czasu", który wskazuje na wolny model, a nie
    na to, co się naprawdę stało. Fałszywa diagnoza gorsza od awarii.

    Ale sama flaga bywa nieprzyjmowana: jej obsługa różni się między wydaniami Codexa, a Kit
    trafia na cudze maszyny z wersjami, których nie znamy. Dlatego **pytamy Codexa, który stoi
    u użytkownika**, zamiast zgadywać z numeru wersji: jedno tanie `--version` z flagą mówi
    prawdę o tej instalacji. Wynik zapamiętujemy na czas życia procesu.
    """

    nazwa = "codex"
    chce_ramke = True

    def __init__(self) -> None:
        self._flagi: tuple[str, ...] | None = None

    def dostepny(self) -> tuple[bool, str]:
        if shutil.which("codex"):
            return True, ""
        return False, ("nie znalazłem polecenia `codex` w PATH. Zainstaluj Codex CLI albo "
                       "uruchom workera z `--runtime shell`.")

    def flagi_globalne(self) -> tuple[str, ...]:
        """Flagi przed podkomendą, sprawdzone na TEJ instalacji Codexa."""
        if self._flagi is not None:
            return self._flagi
        try:
            proba = subprocess.run(
                ["codex", *FLAGA_BEZ_PYTAN, "exec", "--version"],
                capture_output=True, text=True, timeout=LIMIT_SONDY_S)
            self._flagi = FLAGA_BEZ_PYTAN if proba.returncode == 0 else ()
        except (OSError, subprocess.SubprocessError):
            # Sonda nie jest warta wywracania pracy. Idziemy bez flagi — najwyżej Codex
            # o coś zapyta, a to widać w wyjściu.
            self._flagi = ()
        return self._flagi

    def wykonaj(self, polecenie: str, *, katalog: str, limit_s: int) -> Wynik:
        polecenia = ["codex", *self.flagi_globalne(), "exec",
                     "--sandbox", "workspace-write"]
        if not _w_repozytorium_git(katalog):
            # Codex domyślnie odmawia pracy poza repozytorium git (żeby dało się cofnąć jego
            # zmiany). Katalog roboczy agenta zwykle repozytorium nie jest, więc bez tej flagi
            # KAŻDE zadanie kończyłoby się odmową. Mówimy o tym w wyjściu zamiast po cichu
            # zdejmować cudze zabezpieczenie.
            polecenia.append("--skip-git-repo-check")
        polecenia.append("-")
        return _uruchom(polecenia, katalog=katalog, limit_s=limit_s, wejscie=polecenie)


def _w_repozytorium_git(katalog: str) -> bool:
    """Czy katalog leży w repozytorium git. Po drzewie w górę, bez wołania `git`."""
    sciezka = os.path.abspath(katalog or ".")
    while True:
        if os.path.isdir(os.path.join(sciezka, ".git")):
            return True
        rodzic = os.path.dirname(sciezka)
        if rodzic == sciezka:
            return False
        sciezka = rodzic


class WykonawcaShell(Wykonawca):
    """Powłoka — do testu odbiorczego bez modelu.

    Treść zadania jest wykonywana JAK SKRYPT. To jest oczywiście niebezpieczne i dlatego:
    `shell` nigdy nie jest domyślny, trzeba go wybrać jawnie flagą albo w konfiguracji,
    a README mówi, do czego służy. Nie udajemy, że to jest bezpieczny tryb — udawanie
    byłoby gorsze niż samo ryzyko.
    """

    nazwa = "shell"

    def dostepny(self) -> tuple[bool, str]:
        return True, ""

    def wykonaj(self, polecenie: str, *, katalog: str, limit_s: int) -> Wynik:
        return _uruchom(["bash", "-lc", polecenie], katalog=katalog, limit_s=limit_s)


class WykonawcaKimi(Wykonawca):
    """Kimi Code CLI w trybie bezobsługowym (ADVERTPR-807 C3, składnia z wpisu `1c831e48` na 803).

    `--print` to tryb nieinteraktywny (włącza `--afk`, czyli bez pytań do człowieka), `--yolo`
    daje automatyczną zgodę na polecenia i edycje — razem odpowiednik `codex --ask-for-approval
    never exec`. Bez obu worker chodzący bez nadzoru wisiałby do limitu czasu na pytaniu,
    którego nikt nie zatwierdzi, i meldował „przekroczony limit czasu": diagnoza wskazująca
    na wolny model zamiast na to, co się naprawdę stało.

    PROMPT IDZIE ARGUMENTEM I TO JEST RÓŻNICA WZGLĘDEM CODEXA — ŚWIADOMA, NIE PRZEOCZONA
    ═════════════════════════════════════════════════════════════════════════════════════
    `WykonawcaCodex` podaje treść zadania przez wejście standardowe, bo **argumenty procesu
    widzi `ps` każdy użytkownik maszyny**, a na serwerach agentów wszyscy chodzą jako `ubuntu`.
    Kimi w udokumentowanej składni przyjmuje prompt wyłącznie jako `--prompt` / `--command`,
    więc treść zadania — cudza, czasem klienta — jest tu przez czas przebiegu widoczna w `ps`.

    Nie udaję, że tego nie ma, i nie zdejmuję tego po cichu: zgłoszone wpisem na 807 z prośbą
    o jedno sprawdzenie na maszynie z Kimi (`kimi --prompt -`, czy czyta stdin). Gdy odpowiedź
    będzie twierdząca, ten adapter przechodzi na stdin jedną linią, tak jak Codex.

    `--output-format text`: wynik czytamy ze stdout. `stream-json` dałby strukturę, ale worker
    i tak przekazuje dalej całe wyjście — struktura bez odbiorcy to koszt bez pożytku.
    """

    nazwa = "kimi"
    chce_ramke = True

    def __init__(self) -> None:
        self._sprawdzony: tuple[bool, str] | None = None

    def dostepny(self) -> tuple[bool, str]:
        """Obecność w `PATH` **i** faktyczne uruchomienie.

        Sam `which` mówi tylko, że plik jest. Zepsuta albo niedokończona instalacja przechodzi
        ten test i wywraca się dopiero na pierwszym zadaniu — czyli po tym, jak worker zdążył
        je sobie przypisać. Jedno `--version` kosztuje ułamek sekundy i zamienia awarię
        w środku pracy na czytelną odmowę przed jej rozpoczęciem. Wynik pamiętamy na czas
        życia procesu, żeby nie sondować przy każdym takcie pętli.
        """
        if self._sprawdzony is not None:
            return self._sprawdzony

        if not shutil.which("kimi"):
            self._sprawdzony = (False, (
                "nie znalazłem polecenia `kimi` w PATH. Zainstaluj Kimi Code CLI "
                "(MoonshotAI/kimi-cli) i zaloguj się przez `kimi login`, albo uruchom workera "
                "z `--runtime codex` lub `--runtime shell`."))
            return self._sprawdzony

        try:
            proba = subprocess.run(["kimi", "--version"],
                                   capture_output=True, text=True, timeout=LIMIT_SONDY_S)
        except (OSError, subprocess.SubprocessError) as blad:
            self._sprawdzony = (False, f"`kimi` jest w PATH, ale nie daje się uruchomić: {blad}")
            return self._sprawdzony

        if proba.returncode != 0:
            # Pierwsza linia błędu wystarcza: pełny ślad stosu w komunikacie dla człowieka
            # ukrywa zdanie, które ma przeczytać.
            powod = (proba.stderr or proba.stdout or "").strip().splitlines()
            self._sprawdzony = (False, (
                "`kimi --version` kończy się błędem — instalacja jest niesprawna"
                + (f": {powod[0]}" if powod else ".")))
            return self._sprawdzony

        self._sprawdzony = (True, "")
        return self._sprawdzony

    def wykonaj(self, polecenie: str, *, katalog: str, limit_s: int) -> Wynik:
        return _uruchom(
            ["kimi", "--prompt", polecenie, "--print", "--output-format", "text", "--yolo"],
            katalog=katalog, limit_s=limit_s)

_WYKONAWCY = {w.nazwa: w for w in (WykonawcaCodex(), WykonawcaKimi(), WykonawcaShell())}


def wybierz(nazwa: str) -> Wykonawca:
    wykonawca = _WYKONAWCY.get(nazwa)
    if wykonawca is None:
        raise ValueError(
            f"nie znam wykonawcy „{nazwa}”. Dostępne: " + ", ".join(sorted(_WYKONAWCY)))
    return wykonawca


def katalog_zadania(zadanie: dict, *, domyslny: str) -> tuple[str, str]:
    """`(katalog, powód odmowy)`. Niepusty powód = NIE wykonuj tego zadania.

    Kolejność: katalog z zadania (gdyby SF kiedyś takie pole miało) → katalog z konfiguracji.
    Gdy nie ma żadnego, a wykonawca musi gdzieś pracować — **odmawiamy zamiast zgadywać**.
    Zgadnięty katalog to praca wykonana na cudzych plikach; taki błąd jest cichy w chwili
    popełnienia i głośny dopiero u kogoś innego.
    """
    z_zadania = (zadanie.get("katalog_roboczy") or "").strip()
    katalog = z_zadania or (domyslny or "").strip()
    if not katalog:
        return "", ("zadanie nie mówi, w którym katalogu pracować, a Kit nie ma katalogu "
                    "domyślnego w konfiguracji. Nie zgaduję.")
    if not os.path.isdir(katalog):
        return "", f"katalog roboczy nie istnieje: {katalog}"
    return katalog, ""
