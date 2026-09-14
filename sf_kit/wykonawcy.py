"""Wykonawcy zadań — `codex`, `shell`. Jeden interfejs, żeby dołożenie kolejnego był plikiem.

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


class WykonawcaCodex(Wykonawca):
    """`codex exec` — bezobsługowy przebieg Codexa z promptem na wejściu.

    `--sandbox workspace-write`: Codex może pisać w katalogu roboczym i nie może poza nim.
    To jest ustawienie, którego NIE wystawiam w konfiguracji — zadanie z cudzego systemu nie
    ma prawa dostać swobody zapisu na całej maszynie tylko dlatego, że ktoś wpisał flagę.

    Prompt idzie przez **wejście standardowe**, nie przez argument: treść zadania bywa długa
    i wielolinijkowa, a argumenty procesu widzi `ps` (to ta sama zasada, co przy kluczu —
    tyle że tu chodzi o cudzą treść, nie o sekret).
    """

    nazwa = "codex"

    def dostepny(self) -> tuple[bool, str]:
        if shutil.which("codex"):
            return True, ""
        return False, ("nie znalazłem polecenia `codex` w PATH. Zainstaluj Codex CLI albo "
                       "uruchom workera z `--runtime shell`.")

    def wykonaj(self, polecenie: str, *, katalog: str, limit_s: int) -> Wynik:
        return _uruchom(
            ["codex", "exec", "--sandbox", "workspace-write", "-"],
            katalog=katalog, limit_s=limit_s, wejscie=polecenie)


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


_WYKONAWCY = {w.nazwa: w for w in (WykonawcaCodex(), WykonawcaShell())}


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
