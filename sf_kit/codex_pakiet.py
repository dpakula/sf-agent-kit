"""Pakiet SF Kita dla Codex CLI: instalacja (`sf-kit init --codex`) i odświeżenie (`sf-kit update`) — SF-203.

v1.0.0 (02.10.2026) - APro Agents / borys-sf · Agata 14:00 (kolejność pakietów: Claude Code → Codex → Kimi → Gemini)

GDZIE (dokumentacja Codex CLI, sprawdzone 02.10)
═══════════════════════════════════════════════
- **Instrukcje:** globalny `AGENTS.md` w `CODEX_HOME` (domyślnie `~/.codex`). Gdy jest tam niepusty
  `AGENTS.override.md`, Codex czyta JEGO zamiast `AGENTS.md` — wtedy sekcję Kita kładziemy tam, inaczej
  byłaby martwa. Sekcja między znacznikami; reszta pliku zostaje bajt w bajt (wzorzec `sf-kit start`).
- **Skille:** `$HOME/.agents/skills/<nazwa>/` (zakres użytkownika). Nie `~/.codex/skills` — dokumentacja
  wymienia `.agents/skills`.
- Własne prompty (`~/.codex/prompts`) — PRZESTARZAŁE wg dokumentacji; nie instalujemy.

CUDZE ZOSTAJE
═════════════
Nadpisujemy i usuwamy WYŁĄCZNIE katalogi skilli, których `SKILL.md` niesie nasz znacznik generatora.
Katalog o tej samej nazwie bez znacznika = cudzy: pomijamy i mówimy to w raporcie.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import pakiet

ZNACZNIK = "wygenerowano z pakiet/komendy.json przez sf-kit"


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


def _nasz(katalog: Path) -> bool:
    skill = katalog / "SKILL.md"
    return skill.is_file() and ZNACZNIK in skill.read_text(encoding="utf-8", errors="replace")


def wstaw_sekcje(tekst: str, sekcja: str) -> str:
    if pakiet.CODEX_START in tekst and pakiet.CODEX_KONIEC in tekst:
        przed = tekst.split(pakiet.CODEX_START, 1)[0]
        po = tekst.split(pakiet.CODEX_KONIEC, 1)[1]
        return przed + sekcja.rstrip("\n") + po
    return (tekst.rstrip("\n") + "\n\n" if tekst.strip() else "") + sekcja


def zainstalowany() -> bool:
    plik = plik_instrukcji()
    return plik.is_file() and pakiet.CODEX_START in plik.read_text(encoding="utf-8", errors="replace")


def zainstaluj(korzen: Path = pakiet.KORZEN) -> tuple[bool, list[str]]:
    zrodlo = korzen / pakiet.KATALOG_CODEX
    if not (zrodlo / "AGENTS.md").is_file():
        return False, [f"Brak pakietu Codex w {zrodlo} — Kit jest niepełny (`sf-kit update`)."]
    raport: list[str] = []

    plik = plik_instrukcji()
    plik.parent.mkdir(parents=True, exist_ok=True)
    stary = plik.read_text(encoding="utf-8") if plik.is_file() else ""
    nowy = wstaw_sekcje(stary, (zrodlo / "AGENTS.md").read_text(encoding="utf-8"))
    if nowy != stary:
        plik.write_text(nowy, encoding="utf-8")
    raport.append(f"{plik}: sekcja SF Kita {'zapisana' if nowy != stary else 'aktualna'}"
                  + (" (Codex czyta AGENTS.override.md zamiast AGENTS.md)" if plik.name.startswith("AGENTS.override") else ""))

    cel = katalog_skilli()
    cel.mkdir(parents=True, exist_ok=True)
    nowe = {d.name for d in (zrodlo / "skills").iterdir() if d.is_dir()}
    pominiete, zapisane = [], 0
    for nazwa in sorted(nowe):
        docelowy = cel / nazwa
        if docelowy.exists() and not _nasz(docelowy):
            pominiete.append(nazwa)
            continue
        if docelowy.exists():
            shutil.rmtree(docelowy)
        shutil.copytree(zrodlo / "skills" / nazwa, docelowy)
        zapisane += 1
    usuniete = [d.name for d in cel.iterdir() if d.is_dir() and d.name.startswith("sf-")
                and d.name not in nowe and _nasz(d)]
    for nazwa in usuniete:
        shutil.rmtree(cel / nazwa)
    raport.append(f"{cel}: {zapisane} skilli SF Kita"
                  + (f", usunięte nieaktualne: {', '.join(usuniete)}" if usuniete else ""))
    if pominiete:
        raport.append(f"POMINIĘTE (cudze katalogi o tej samej nazwie): {', '.join(pominiete)}")
    raport.append("W Codexie: `$sf-…` albo `/skills`; po zmianach uruchom nową sesję Codexa.")
    return not pominiete, raport


def odswiez(korzen: Path = pakiet.KORZEN) -> list[str]:
    """`sf-kit update`: odśwież pakiet Codex, gdy był zainstalowany. Inaczej cisza."""
    if not zainstalowany():
        return []
    _, raport = zainstaluj(korzen)
    return ["Pakiet Codex odświeżony:", *raport]
