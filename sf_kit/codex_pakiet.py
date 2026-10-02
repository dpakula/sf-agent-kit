"""Pakiet SF Kita dla Codex CLI: instalacja (`sf-kit init --codex`) i odświeżenie (`sf-kit update`) — SF-203.

v1.2.0 (02.10.2026) - APro Agents / borys-sf · rejestracja serwera MCP (`codex mcp add` / config.toml)
v1.1.0 (02.10.2026) - APro Agents / borys-sf · reguły instalacji wspólne z Kimi (`instalator_pakietu`)
v1.0.0 (02.10.2026) - APro Agents / borys-sf · Agata 14:00 (kolejność pakietów: Claude Code → Codex → Kimi → Gemini)

GDZIE (dokumentacja Codex CLI, sprawdzone 02.10)
═══════════════════════════════════════════════
- **Instrukcje:** globalny `AGENTS.md` w `CODEX_HOME` (domyślnie `~/.codex`). Gdy jest tam niepusty
  `AGENTS.override.md`, Codex czyta JEGO zamiast `AGENTS.md` — wtedy sekcję Kita kładziemy tam.
- **Skille:** `$HOME/.agents/skills/<nazwa>/` (zakres użytkownika; nie `~/.codex/skills`).
- Własne prompty (`~/.codex/prompts`) — PRZESTARZAŁE wg dokumentacji; nie instalujemy.
- Reguły zezwoleń (`~/.codex/rules`) — NIE zapisujemy (eksperymentalne; decyzja Q2 na SF-203).
- **MCP:** `codex mcp add sf-kit -- sf-kit mcp` (dokumentacja „MCP”), gdy `codex` jest w PATH; bez niego
  dopisujemy tabelę `[mcp_servers.sf-kit]` do `CODEX_HOME/config.toml` (reszta pliku zostaje).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from . import instalator_pakietu as ip
from . import pakiet

ZNACZNIK = ip.ZNACZNIK


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))


def katalog_skilli() -> Path:
    return Path.home() / ".agents" / "skills"


def plik_instrukcji() -> Path:
    """Plik AGENTS, który Codex faktycznie czyta na poziomie globalnym."""
    nadpisanie = codex_home() / "AGENTS.override.md"
    if nadpisanie.is_file() and nadpisanie.read_text(encoding="utf-8").strip():
        return nadpisanie
    return codex_home() / "AGENTS.md"


TABELA_MCP = "[mcp_servers.sf-kit]"


def zarejestruj_mcp(uruchom=subprocess.run) -> list[str]:
    """Serwer MCP Kita w Codexie: `codex mcp add`, a bez `codex` — wpis w config.toml (SF-203)."""
    exe = shutil.which("codex")
    if exe:
        try:
            w = uruchom([exe, "mcp", "add", "sf-kit", "--", "sf-kit", "mcp"],
                        capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as blad:
            return [f"MCP: `codex mcp add` nie zadziałało ({blad})"]
        tekst = ((w.stdout or "") + (w.stderr or "")).strip()
        if w.returncode == 0 or "already" in tekst.lower():
            return ["MCP: serwer `sf-kit` zarejestrowany w Codexie (`codex mcp add`)"]
        return [f"MCP: `codex mcp add` odmówił: {tekst[-300:]}"]
    plik = codex_home() / "config.toml"
    tresc = plik.read_text(encoding="utf-8") if plik.is_file() else ""
    if TABELA_MCP in tresc:
        return [f"MCP: {plik} już ma `{TABELA_MCP}`"]
    plik.parent.mkdir(parents=True, exist_ok=True)
    dopisek = f'{TABELA_MCP}\ncommand = "sf-kit"\nargs = ["mcp"]\n'
    plik.write_text((tresc.rstrip("\n") + "\n\n" if tresc.strip() else "") + dopisek, encoding="utf-8")
    return [f"MCP: dopisane `{TABELA_MCP}` do {plik} (brak `codex` w PATH)"]


def cel(korzen: Path = pakiet.KORZEN) -> ip.Cel:
    return ip.Cel(nazwa="Codex", zrodlo=korzen / pakiet.KATALOG_CODEX, plik_instrukcji=plik_instrukcji,
                  katalog_skilli=katalog_skilli, start=pakiet.CODEX_START, koniec=pakiet.CODEX_KONIEC,
                  podpowiedz="W Codexie: `$sf-…` albo `/skills`; narzędzia MCP `sf-kit`; po zmianach nowa sesja.",
                  po_instalacji=zarejestruj_mcp)


def wstaw_sekcje(tekst: str, sekcja: str) -> str:
    return ip.wstaw_sekcje(tekst, sekcja, pakiet.CODEX_START, pakiet.CODEX_KONIEC)


def zainstalowany() -> bool:
    return ip.zainstalowany(cel())


def zainstaluj(korzen: Path = pakiet.KORZEN) -> tuple[bool, list[str]]:
    return ip.zainstaluj(cel(korzen))


def odswiez(korzen: Path = pakiet.KORZEN) -> list[str]:
    return ip.odswiez(cel(korzen))
