"""Instalacja Kita bez gita — jednym poleceniem, na macOS, Linuksie i Windows (ADVERTPR-987).

v0.1 (29.09.2026) - APro Agents / borys-sf · projekt: wpis 26017d47 na ADVERTPR-987

PO CO
═════
Do 0.14 Kit instalowało się `git clone` i działał „na Windows tylko w WSL". Kursanci
ForMarketing to w większości Windows i ludzie, którzy nie wiedzą, co to git. Od 0.15.0:

    macOS/Linux:  curl -fsSL https://raw.githubusercontent.com/dpakula/sf-agent-kit/main/install.sh | sh
    Windows:      irm https://raw.githubusercontent.com/dpakula/sf-agent-kit/main/install.ps1 | iex

Skrypty robią TYLKO to, czego Python zrobić nie może, zanim go znajdziemy: znajdują Pythona
3.9+, pobierają ZIP wydania i rozpakowują go do katalogu tymczasowego. Całą resztę — podmianę
katalogu, uruchamiacz `sf-kit`, PATH — robi ten moduł (`sf-kit instaluj`), bo Python jest
jeden na trzy systemy i daje się przetestować; dwa skrypty powłoki rozjechałyby się przy
pierwszej zmianie.

UKŁAD NA DYSKU
══════════════
    korzeń   macOS/Linux: ~/.local/share/sf-kit   ($XDG_DATA_HOME, gdy ustawione)
             Windows:     %LOCALAPPDATA%\\sf-kit
    korzeń/app/                 kod (zawartość archiwum) + `.instalacja.json` (skąd i z czego)
    polecenie macOS/Linux: ~/.local/bin/sf-kit        (skrypt `exec python … "$@"`)
              Windows:     korzeń\\bin\\sf-kit.cmd       (PATH użytkownika, bez administratora)

Konfiguracja i klucz leżą gdzie indziej (`klucz.py`) — reinstalacja i aktualizacja ich nie
dotykają.

SKĄD WIEMY, ŻE ARCHIWUM JEST Z TEGO COMMITA
═══════════════════════════════════════════
Archiwa GitHuba (`codeload …/zip/<ref>`) niosą w KOMENTARZU ZIP-a pełny SHA commita, także
pobrane po tagu (sprawdzone 29.09 na v0.14.1). `sf-kit aktualizuj` porównuje go z commitem
wskazanym przez SF i przy rozjeździe odmawia PRZED podmianą — odpowiednik `tag^{commit}`
z drogi gitowej (`aktualizacje.Repo.potwierdz_zgodnosc`).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = "dpakula/sf-agent-kit"
#: Adres archiwum dla tagu albo commita. `codeload` oddaje ZIP bez logowania (repo publiczne).
ADRES_ARCHIWUM = "https://codeload.github.com/" + REPO + "/zip/{ref}"
KATALOG_KODU = "app"
PLIK_ZNACZNIKA = ".instalacja.json"
#: Znacznik w pliku startowym powłoki — po nim poznajemy, że linię PATH dopisaliśmy już wcześniej.
ZNACZNIK_PATH = "# sf-kit (ADVERTPR-987)"
_SHA = re.compile(r"^[0-9a-f]{40}$")


class BladInstalacji(RuntimeError):
    """Instalacja albo aktualizacja nie przeszła — NIC nie zostało podmienione."""


# ── gdzie ────────────────────────────────────────────────────────────────────────────────

def czy_windows() -> bool:
    return os.name == "nt"


def korzen() -> Path:
    if czy_windows():
        baza = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(baza) / "sf-kit"
    baza = os.environ.get("XDG_DATA_HOME")
    return (Path(baza) if baza else Path.home() / ".local" / "share") / "sf-kit"


def katalog_polecenia() -> Path:
    return korzen() / "bin" if czy_windows() else Path.home() / ".local" / "bin"


def katalog_tego_kodu() -> Path:
    """Katalog, z którego biegnie TEN kod (tam, gdzie leży `sf-kit`)."""
    return Path(__file__).resolve().parents[1]


def ta_instalacja() -> dict | None:
    """Znacznik instalacji z ZIP-a obok TEGO kodu albo `None` (klon gita, kopia ręczna)."""
    plik = katalog_tego_kodu() / PLIK_ZNACZNIKA
    try:
        return json.loads(plik.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ── archiwum ─────────────────────────────────────────────────────────────────────────────

def pobierz(adres: str, plik: Path, *, limit_s: int = 60) -> None:
    from . import WERSJA

    zadanie = urllib.request.Request(adres, headers={"User-Agent": f"sf-kit/{WERSJA}"})
    try:
        with urllib.request.urlopen(zadanie, timeout=limit_s) as odp, open(plik, "wb") as f:
            shutil.copyfileobj(odp, f)
    except OSError as blad:
        raise BladInstalacji(f"nie udało się pobrać {adres}: {blad}") from None


def rozpakuj(archiwum: Path, cel: Path, *, oczekiwany_commit: str | None = None) -> tuple[Path, str | None]:
    """Rozpakuj ZIP z GitHuba do `cel`. Oddaje `(katalog z kodem, commit z komentarza)`.

    Każda ścieżka w archiwum musi zostać WEWNĄTRZ `cel` (bez `..`, bez ścieżek bezwzględnych)
    — archiwum z `../../.bashrc` nie ma prawa pisać poza katalogiem tymczasowym. Przy
    `oczekiwany_commit` komentarz ZIP-a musi się z nim zgadzać, inaczej odmowa PRZED
    rozpakowaniem czegokolwiek.
    """
    try:
        z = zipfile.ZipFile(archiwum)
    except zipfile.BadZipFile:
        raise BladInstalacji("pobrany plik nie jest archiwum ZIP (przerwane pobieranie?)") from None
    with z:
        commit = z.comment.decode("ascii", "replace").strip() or None
        if commit and not _SHA.match(commit):
            commit = None
        if oczekiwany_commit and commit != oczekiwany_commit:
            raise BladInstalacji(
                f"WERYFIKACJA NIE PRZESZŁA: archiwum jest z commitu {(commit or '?')[:12]}, "
                f"a SF wymaga {oczekiwany_commit[:12]}. Niczego nie zmieniłem.")
        cel = cel.resolve()
        for nazwa in z.namelist():
            docelowa = (cel / nazwa).resolve()
            if docelowa != cel and cel not in docelowa.parents:
                raise BladInstalacji(f"archiwum zawiera ścieżkę spoza katalogu: {nazwa!r} — odmawiam")
        z.extractall(cel)
    katalogi = [p for p in cel.iterdir() if p.is_dir()]
    if len(katalogi) != 1 or not (katalogi[0] / "sf-kit").is_file() or not (katalogi[0] / "sf_kit").is_dir():
        raise BladInstalacji("archiwum nie wygląda na Kita (brak `sf-kit` i `sf_kit/`)")
    return katalogi[0], commit


# ── instalacja ───────────────────────────────────────────────────────────────────────────

def zainstaluj(zrodlo: Path, *, commit: str | None, ref: str | None, python: str | None = None,
               baza: Path | None = None, bin_: Path | None = None, mow=print,
               dopisz_path: bool = True) -> Path:
    """Skopiuj `zrodlo` do `korzeń/app` (podmiana w dwóch przemianowaniach), załóż polecenie
    `sf-kit`, dopilnuj PATH. Oddaje ścieżkę polecenia.

    Podmiana: kopia do `app.nowy` → `app` na `app.stary` → `app.nowy` na `app`. Jeśli coś
    padnie przy kopiowaniu, `app` jest nietknięty; okno, w którym `app` nie ma, to dwa
    przemianowania w jednym katalogu.
    """
    from . import WERSJA

    baza = baza or korzen()
    bin_ = bin_ or katalog_polecenia()
    python = python or sys.executable
    baza.mkdir(parents=True, exist_ok=True)
    app, nowy, stary = baza / KATALOG_KODU, baza / (KATALOG_KODU + ".nowy"), baza / (KATALOG_KODU + ".stary")

    if Path(zrodlo).resolve() == app.resolve():
        raise BladInstalacji("źródło instalacji to już zainstalowany katalog — nie ma czego kopiować")
    shutil.rmtree(nowy, ignore_errors=True)
    shutil.copytree(zrodlo, nowy, ignore=shutil.ignore_patterns("__pycache__", ".git"))
    wersja = _wersja_w(nowy) or WERSJA
    (nowy / PLIK_ZNACZNIKA).write_text(json.dumps({
        "sposob": "zip", "ref": ref, "commit": commit, "wersja": wersja,
        "zainstalowano": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    shutil.rmtree(stary, ignore_errors=True)
    if app.exists():
        app.rename(stary)
    try:
        nowy.rename(app)
    except OSError:
        if stary.exists() and not app.exists():
            stary.rename(app)                  # przywróć poprzednią wersję
        raise
    # Na Windows plik używany przez działający proces bywa zablokowany — stara wersja zostanie
    # wtedy na dysku do następnej instalacji. Nie jest to błąd: działa już nowa.
    shutil.rmtree(stary, ignore_errors=True)

    polecenie = zaloz_polecenie(app, bin_=bin_, python=python)
    if dopisz_path:
        _dopilnuj_path(bin_, mow=mow)
    mow(f"Kit v{wersja} zainstalowany w {app}")
    return polecenie


def _wersja_w(katalog: Path) -> str | None:
    try:
        tekst = (katalog / "sf_kit" / "__init__.py").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r'^WERSJA\s*=\s*"([^"]+)"', tekst, re.M)
    return m.group(1) if m else None


def zaloz_polecenie(app: Path, *, bin_: Path, python: str) -> Path:
    """Uruchamiacz `sf-kit` wskazujący TEN Python i TEN katalog kodu.

    Nie dowiązanie symboliczne: `sf-kit` liczy `sys.path` z `abspath(__file__)`, które dowiązania
    nie rozwija — import `sf_kit` szukałby w `~/.local/bin`. Python podany ścieżką bezwzględną,
    bo na Windows `python` w PATH bywa atrapą Sklepu, a na macOS — innym Pythonem niż ten,
    który sprawdził instalator.
    """
    bin_.mkdir(parents=True, exist_ok=True)
    skrypt = app / "sf-kit"
    if czy_windows():
        plik = bin_ / "sf-kit.cmd"
        # PYTHONUTF8: polskie znaki także wtedy, gdy wyjście czyta program (Claude Code), a nie konsola.
        plik.write_text(f'@echo off\r\nset "PYTHONUTF8=1"\r\n"{python}" "{skrypt}" %*\r\n', encoding="utf-8")
        return plik
    plik = bin_ / "sf-kit"
    plik.write_text(f'#!/bin/sh\nexec "{python}" "{skrypt}" "$@"\n', encoding="utf-8")
    plik.chmod(0o755)
    return plik


def _dopilnuj_path(bin_: Path, *, mow=print) -> None:
    if czy_windows():
        _path_windows(bin_, mow=mow)
    else:
        _path_posix(bin_, mow=mow)


def _w_path(katalog: Path, path: str | None = None) -> bool:
    path = os.environ.get("PATH", "") if path is None else path
    cel = os.path.normcase(os.path.normpath(str(katalog)))
    return any(os.path.normcase(os.path.normpath(p)) == cel for p in path.split(os.pathsep) if p)


def plik_startowy_powloki(powloka: str | None = None, *, macos: bool | None = None) -> Path:
    """Plik, do którego dopisujemy PATH: zsh → ~/.zshrc, bash → ~/.bashrc (macOS: ~/.bash_profile),
    reszta → ~/.profile. Z `$SHELL`, bo to powłoka, którą człowiek otworzy w NOWYM oknie."""
    powloka = os.path.basename(powloka if powloka is not None else os.environ.get("SHELL", ""))
    macos = sys.platform == "darwin" if macos is None else macos
    dom = Path.home()
    if powloka == "zsh":
        return dom / ".zshrc"
    if powloka == "bash":
        return dom / (".bash_profile" if macos else ".bashrc")
    return dom / ".profile"


def _path_posix(bin_: Path, *, mow=print) -> None:
    if _w_path(bin_):
        return
    plik = plik_startowy_powloki()
    linia = f'export PATH="{bin_}:$PATH"'
    try:
        obecna = plik.read_text(encoding="utf-8") if plik.exists() else ""
    except OSError:
        obecna = ""
    if ZNACZNIK_PATH not in obecna:
        with open(plik, "a", encoding="utf-8") as f:
            f.write(f"\n{ZNACZNIK_PATH}\n{linia}\n")
        mow(f"Dopisałem {bin_} do PATH w {plik}.")
    mow("Otwórz NOWE okno terminala, żeby polecenie `sf-kit` było widoczne.\n"
        f"W tym oknie działa pełna ścieżka: {bin_ / 'sf-kit'}")


def _path_windows(bin_: Path, *, mow=print) -> None:
    """PATH użytkownika w rejestrze (HKCU\\Environment) — bez uprawnień administratora.
    Nowe okna PowerShell zobaczą go od razu; bieżące okno aktualizuje `install.ps1`."""
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_READ | winreg.KEY_WRITE) as klucz:
        try:
            obecna, typ = winreg.QueryValueEx(klucz, "Path")
        except FileNotFoundError:
            obecna, typ = "", winreg.REG_EXPAND_SZ
        if _w_path(bin_, os.path.expandvars(obecna)):
            return
        nowa = f"{obecna};{bin_}" if obecna else str(bin_)
        winreg.SetValueEx(klucz, "Path", 0, typ if typ in (winreg.REG_SZ, winreg.REG_EXPAND_SZ)
                          else winreg.REG_EXPAND_SZ, nowa)
    _oglos_zmiane_srodowiska()
    mow(f"Dodałem {bin_} do PATH Twojego konta Windows.")


def _oglos_zmiane_srodowiska() -> None:
    """WM_SETTINGCHANGE „Environment" — Eksplorator i nowe terminale czytają PATH od nowa."""
    try:
        import ctypes
        HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x001A, 0x0002
        wynik = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
                                                 SMTO_ABORTIFHUNG, 2000, ctypes.byref(wynik))
    except Exception:                          # noqa: BLE001 — ogłoszenie to uprzejmość, nie warunek
        pass


# ── aktualizacja z ZIP-a ─────────────────────────────────────────────────────────────────

def aktualizuj_z_zip(*, tag: str, commit: str, mow=print, baza: Path | None = None,
                     pobieranie=pobierz) -> Path:
    """Pobierz ZIP DOKŁADNIE tego commita, sprawdź komentarz archiwum, zainstaluj na miejsce
    obecnego kodu. Odmowa (`BladInstalacji`) zostawia obecną wersję nietkniętą."""
    if not _SHA.match(commit or ""):
        raise BladInstalacji(f"commit z SF nie wygląda na SHA: {commit!r}")
    obecna = ta_instalacja() or {}
    baza = baza or katalog_tego_kodu().parent
    with tempfile.TemporaryDirectory(prefix="sf-kit-") as tmp:
        archiwum = Path(tmp) / "kit.zip"
        pobieranie(ADRES_ARCHIWUM.format(ref=commit), archiwum)
        zrodlo, _ = rozpakuj(archiwum, Path(tmp) / "rozpakowane", oczekiwany_commit=commit)
        return zainstaluj(zrodlo, commit=commit, ref=tag, baza=baza,
                          python=obecna.get("python") or sys.executable, mow=mow,
                          dopisz_path=False)
