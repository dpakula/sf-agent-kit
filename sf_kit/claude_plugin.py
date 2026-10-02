"""Plugin `sf-kit` w Claude Code: instalacja (`sf-kit init --claude`) i odświeżenie (`sf-kit update`).

v1.0.0 (02.10.2026) - APro Agents / borys-sf · SF-201; decyzje Q-A/Q-B (Agata 13:42, w ramach GO Damiana)

DECYZJE
═══════
- **Q-A: marketplace = repo Kita** (`dpakula/sf-agent-kit`, katalog `.claude-plugin/`), nazwa `sf-plugins`.
- **Q-B: zakres UŻYTKOWNIKA** — plugin działa w każdym katalogu (Q1 „globalnie”), nie tylko w folderze pracy.

JAK
═══
Gdy na maszynie jest CLI `claude` — wołamy JEGO polecenia (`claude plugin marketplace add`, `install`,
`update`): to jedyna droga, przy której plugin faktycznie ląduje na dysku, a nie tylko „jest
zapowiedziany” w ustawieniach. Gdy `claude` nie ma (np. tylko aplikacja desktop) — dopisujemy do
`~/.claude/settings.json` `extraKnownMarketplaces` i `enabledPlugins` (obiekty, wg dokumentacji) i mówimy
uczciwie, co wpisać w Claude Code, jeśli plugin się nie pojawi. Cudzych kluczy ustawień nie ruszamy;
zepsutego JSON-a nie nadpisujemy (ten sam wzorzec co `sf-kit start`).

Nic tu nie wywraca Kita: błąd `claude` wraca jako zdanie w raporcie, a `init`/`update` kończą swoją pracę.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

#: Źródło marketplace'u. `SF_KIT_MARKETPLACE` podmienia je na ścieżkę lokalną — do sprawdzenia
#: instalacji z gałęzi, zanim trafi na `main` (i w testach).
ZRODLO = os.environ.get("SF_KIT_MARKETPLACE") or "dpakula/sf-agent-kit"
MARKETPLACE = "sf-plugins"
PLUGIN = "sf-kit"
ID = f"{PLUGIN}@{MARKETPLACE}"
LIMIT_S = 180


def plik_ustawien() -> Path:
    """`~/.claude/settings.json` — albo w katalogu z `CLAUDE_CONFIG_DIR`, gdy ktoś go przeniósł."""
    baza = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(baza) if baza else Path.home() / ".claude") / "settings.json"


def _claude() -> str | None:
    return shutil.which("claude")


def _uruchom(argv: list[str], uruchom=subprocess.run) -> tuple[int, str]:
    try:
        w = uruchom(argv, capture_output=True, text=True, timeout=LIMIT_S)
    except (OSError, subprocess.TimeoutExpired) as blad:
        return 1, str(blad)
    return w.returncode, ((w.stdout or "") + (w.stderr or "")).strip()


def zainstalowany(uruchom=subprocess.run) -> bool | None:
    """Czy plugin jest zainstalowany (wg `claude plugin list --json`); `None` = nie umiem sprawdzić."""
    exe = _claude()
    if not exe:
        return None
    kod, wyjscie = _uruchom([exe, "plugin", "list", "--json"], uruchom)
    if kod != 0:
        return None
    return ID in wyjscie or f'"{PLUGIN}"' in wyjscie


def dopisz_ustawienia(plik: Path | None = None) -> str:
    """Wpisz marketplace + włączony plugin do ustawień użytkownika. Oddaje zdanie do raportu."""
    plik = plik or plik_ustawien()
    dane: dict = {}
    if plik.exists():
        try:
            dane = json.loads(plik.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as blad:
            return (f"{plik} nie jest poprawnym JSON-em ({blad}) — NIE zmieniam go. Dopisz ręcznie: "
                    f'"extraKnownMarketplaces": {{"{MARKETPLACE}": {{"source": {{"source": "github", '
                    f'"repo": "{ZRODLO}"}}}}}}, "enabledPlugins": {{"{ID}": true}}')
        if not isinstance(dane, dict):
            return f"{plik} nie jest obiektem JSON — NIE zmieniam go."
    rynki = dane.setdefault("extraKnownMarketplaces", {})
    wlaczone = dane.setdefault("enabledPlugins", {})
    if not isinstance(rynki, dict) or not isinstance(wlaczone, dict):
        return f"{plik}: `extraKnownMarketplaces`/`enabledPlugins` mają nieoczekiwany kształt — NIE zmieniam."
    zrodlo = ({"source": "directory", "path": ZRODLO} if Path(ZRODLO).exists()
              else {"source": "github", "repo": ZRODLO})
    zmiana = rynki.get(MARKETPLACE) != {"source": zrodlo} or wlaczone.get(ID) is not True
    rynki[MARKETPLACE] = {"source": zrodlo}
    wlaczone[ID] = True
    if zmiana:
        plik.parent.mkdir(parents=True, exist_ok=True)
        plik.write_text(json.dumps(dane, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return f"{plik}: dopisane `{MARKETPLACE}` i włączony `{ID}`"
    return f"{plik}: `{ID}` już był włączony"


def zainstaluj(uruchom=subprocess.run) -> tuple[bool, list[str]]:
    """`sf-kit init --claude`: marketplace + plugin w zakresie użytkownika. Oddaje (sukces, raport)."""
    raport: list[str] = []
    exe = _claude()
    if not exe:
        raport.append("Nie widzę polecenia `claude` w PATH (np. tylko aplikacja desktop).")
        raport.append(dopisz_ustawienia())
        raport.append(f"Jeśli w Claude Code nie ma komend `/sf-kit:…`, wpisz w nim: "
                      f"`/plugin marketplace add {ZRODLO}`, potem `/plugin install {ID}`.")
        return False, raport
    kod, wyjscie = _uruchom([exe, "plugin", "marketplace", "add", ZRODLO, "--scope", "user"], uruchom)
    if kod != 0 and "already" not in wyjscie.lower():
        raport.append(f"Nie udało się dodać marketplace'u {ZRODLO}: {wyjscie[-400:]}")
        return False, raport
    if kod != 0:   # już był — odśwież katalog, żeby instalacja wzięła bieżącą wersję
        _uruchom([exe, "plugin", "marketplace", "update", MARKETPLACE], uruchom)
    raport.append(f"marketplace `{MARKETPLACE}` ({ZRODLO}): gotowy")
    kod, wyjscie = _uruchom([exe, "plugin", "install", ID, "--scope", "user", "-y"], uruchom)
    if kod != 0:
        raport.append(f"Instalacja `{ID}` nie powiodła się: {wyjscie[-400:]}")
        return False, raport
    raport.append(f"plugin `{ID}` zainstalowany (zakres: użytkownik) — komendy `/sf-kit:…` "
                  "będą widoczne po ponownym uruchomieniu Claude Code")
    return True, raport


def odswiez(uruchom=subprocess.run) -> list[str]:
    """`sf-kit update`: gdy plugin jest zainstalowany — odśwież marketplace i plugin. Inaczej cisza."""
    if not zainstalowany(uruchom):
        return []
    exe = _claude()
    _uruchom([exe, "plugin", "marketplace", "update", MARKETPLACE], uruchom)
    kod, wyjscie = _uruchom([exe, "plugin", "update", ID, "--scope", "user", "-y"], uruchom)
    if kod != 0:
        return [f"Plugin `{ID}` nie zaktualizował się: {wyjscie[-300:]} — w Claude Code: `/plugin update {ID}`"]
    return [f"plugin `{ID}` zaktualizowany (zadziała po ponownym uruchomieniu Claude Code)"]
