"""Pakiet SF Kita dla Kimi Code: instalacja (`sf-kit init --kimi`) i odświeżenie (`sf-kit update`) — SF-203.

v1.1.0 (02.10.2026) - APro Agents / borys-sf · rejestracja MCP w mcp.json (Agata 14:42)
v1.0.0 (02.10.2026) - APro Agents / borys-sf · Agata 14:12 (kolejność: Claude Code → Codex → Kimi → Gemini)

GDZIE (dokumentacja Kimi Code — moonshotai.github.io/kimi-code/en: configuration/data-locations,
customization/skills, customization/agents — czytane 02.10; binarki NIE uruchamiamy)
═══════════════════════════════════════════════════════════════════════════════════
- **Instrukcje:** `KIMI_CODE_HOME/AGENTS.md` (domyślnie `~/.kimi-code/AGENTS.md`) — „Global Kimi-specific
  instructions”. Sekcja między znacznikami; reszta pliku zostaje.
- **Skille:** `KIMI_CODE_HOME/skills/<nazwa>/SKILL.md` — katalog swoisty dla Kimi. Kimi czyta TEŻ
  `~/.agents/skills/` (tam kładzie skille pakiet Codex); kolejności przy tej samej nazwie w dwóch
  katalogach użytkownika dokumentacja nie opisuje — pytanie na SF-203.
- `~/.kimi` to katalog STAREGO `kimi-cli` (Python), nie Kimi Code — tam nic nie piszemy
  (workery Kimi na 98a0 używają wyłącznie `~/.kimi-code` — potwierdzone przez Agatę 02.10).
- **MCP:** `KIMI_CODE_HOME/mcp.json` → `mcpServers.sf-kit` (dokumentacja „MCP”; Kimi nie ma `mcp add`).
  Cudze serwery zostają; zepsutego JSON-a nie nadpisujemy.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import instalator_pakietu as ip
from . import pakiet


def kimi_home() -> Path:
    return Path(os.environ.get("KIMI_CODE_HOME") or (Path.home() / ".kimi-code"))


def katalog_skilli() -> Path:
    return kimi_home() / "skills"


def plik_instrukcji() -> Path:
    return kimi_home() / "AGENTS.md"


def zarejestruj_mcp() -> list[str]:
    """Serwer MCP Kita w `KIMI_CODE_HOME/mcp.json` (SF-203)."""
    plik = kimi_home() / "mcp.json"
    dane: dict = {}
    if plik.is_file():
        try:
            dane = json.loads(plik.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as blad:
            return [f"MCP: {plik} nie jest poprawnym JSON-em ({blad}) — NIE zmieniam; dopisz ręcznie "
                    f'"sf-kit": {json.dumps(pakiet.MCP_SERWER["mcpServers"]["sf-kit"])} w "mcpServers"']
    serwery = dane.setdefault("mcpServers", {}) if isinstance(dane, dict) else None
    if not isinstance(serwery, dict):
        return [f"MCP: {plik} ma nieoczekiwany kształt — NIE zmieniam"]
    wpis = pakiet.MCP_SERWER["mcpServers"]["sf-kit"]
    if serwery.get("sf-kit") == wpis:
        return [f"MCP: {plik} już ma serwer `sf-kit`"]
    serwery["sf-kit"] = wpis
    plik.parent.mkdir(parents=True, exist_ok=True)
    plik.write_text(json.dumps(dane, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return [f"MCP: serwer `sf-kit` dopisany do {plik}"]


def cel(korzen: Path = pakiet.KORZEN) -> ip.Cel:
    return ip.Cel(nazwa="Kimi Code", zrodlo=korzen / pakiet.KATALOG_KIMI, plik_instrukcji=plik_instrukcji,
                  katalog_skilli=katalog_skilli, start=pakiet.KIMI_START, koniec=pakiet.KIMI_KONIEC,
                  podpowiedz="W Kimi Code: `/skill:sf-…`; narzędzia MCP `sf-kit` (`/mcp`); po zmianach nowa sesja.",
                  po_instalacji=zarejestruj_mcp)


def zainstalowany() -> bool:
    return ip.zainstalowany(cel())


def zainstaluj(korzen: Path = pakiet.KORZEN) -> tuple[bool, list[str]]:
    return ip.zainstaluj(cel(korzen))


def odswiez(korzen: Path = pakiet.KORZEN) -> list[str]:
    return ip.odswiez(cel(korzen))
