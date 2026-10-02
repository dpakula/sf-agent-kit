"""Pakiet SF Kita dla Codex CLI: instalacja (`sf-kit init --codex`) i odświeżenie (`sf-kit update`) — SF-203.

v1.1.0 (02.10.2026) - APro Agents / borys-sf · reguły instalacji wspólne z Kimi (`instalator_pakietu`)
v1.0.0 (02.10.2026) - APro Agents / borys-sf · Agata 14:00 (kolejność pakietów: Claude Code → Codex → Kimi → Gemini)

GDZIE (dokumentacja Codex CLI, sprawdzone 02.10)
═══════════════════════════════════════════════
- **Instrukcje:** globalny `AGENTS.md` w `CODEX_HOME` (domyślnie `~/.codex`). Gdy jest tam niepusty
  `AGENTS.override.md`, Codex czyta JEGO zamiast `AGENTS.md` — wtedy sekcję Kita kładziemy tam.
- **Skille:** `$HOME/.agents/skills/<nazwa>/` (zakres użytkownika; nie `~/.codex/skills`).
- Własne prompty (`~/.codex/prompts`) — PRZESTARZAŁE wg dokumentacji; nie instalujemy.
- Reguły zezwoleń (`~/.codex/rules`) — NIE zapisujemy (eksperymentalne; decyzja Q2 na SF-203).
"""
from __future__ import annotations

import os
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


def cel(korzen: Path = pakiet.KORZEN) -> ip.Cel:
    return ip.Cel(nazwa="Codex", zrodlo=korzen / pakiet.KATALOG_CODEX, plik_instrukcji=plik_instrukcji,
                  katalog_skilli=katalog_skilli, start=pakiet.CODEX_START, koniec=pakiet.CODEX_KONIEC,
                  podpowiedz="W Codexie: `$sf-…` albo `/skills`; po zmianach uruchom nową sesję Codexa.")


def wstaw_sekcje(tekst: str, sekcja: str) -> str:
    return ip.wstaw_sekcje(tekst, sekcja, pakiet.CODEX_START, pakiet.CODEX_KONIEC)


def zainstalowany() -> bool:
    return ip.zainstalowany(cel())


def zainstaluj(korzen: Path = pakiet.KORZEN) -> tuple[bool, list[str]]:
    return ip.zainstaluj(cel(korzen))


def odswiez(korzen: Path = pakiet.KORZEN) -> list[str]:
    return ip.odswiez(cel(korzen))
