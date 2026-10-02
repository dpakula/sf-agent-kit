"""Pakiet SF Kita dla Kimi Code: instalacja (`sf-kit init --kimi`) i odświeżenie (`sf-kit update`) — SF-203.

v1.0.0 (02.10.2026) - APro Agents / borys-sf · Agata 14:12 (kolejność: Claude Code → Codex → Kimi → Gemini)

GDZIE (dokumentacja Kimi Code — moonshotai.github.io/kimi-code/en: configuration/data-locations,
customization/skills, customization/agents — czytane 02.10; binarki NIE uruchamiamy)
═══════════════════════════════════════════════════════════════════════════════════
- **Instrukcje:** `KIMI_CODE_HOME/AGENTS.md` (domyślnie `~/.kimi-code/AGENTS.md`) — „Global Kimi-specific
  instructions”. Sekcja między znacznikami; reszta pliku zostaje.
- **Skille:** `KIMI_CODE_HOME/skills/<nazwa>/SKILL.md` — katalog swoisty dla Kimi. Kimi czyta TEŻ
  `~/.agents/skills/` (tam kładzie skille pakiet Codex); kolejności przy tej samej nazwie w dwóch
  katalogach użytkownika dokumentacja nie opisuje — pytanie na SF-203.
- `~/.kimi` to katalog STAREGO `kimi-cli` (Python), nie Kimi Code — tam nic nie piszemy.
"""
from __future__ import annotations

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


def cel(korzen: Path = pakiet.KORZEN) -> ip.Cel:
    return ip.Cel(nazwa="Kimi Code", zrodlo=korzen / pakiet.KATALOG_KIMI, plik_instrukcji=plik_instrukcji,
                  katalog_skilli=katalog_skilli, start=pakiet.KIMI_START, koniec=pakiet.KIMI_KONIEC,
                  podpowiedz="W Kimi Code: `/skill:sf-…`; po zmianach uruchom nową sesję.")


def zainstalowany() -> bool:
    return ip.zainstalowany(cel())


def zainstaluj(korzen: Path = pakiet.KORZEN) -> tuple[bool, list[str]]:
    return ip.zainstaluj(cel(korzen))


def odswiez(korzen: Path = pakiet.KORZEN) -> list[str]:
    return ip.odswiez(cel(korzen))
