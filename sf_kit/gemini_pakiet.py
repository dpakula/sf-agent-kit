"""Pakiet SF Kita dla Gemini CLI — rozszerzenie `sf-kit` (`sf-kit init --gemini`, `sf-kit update`) — SF-203.

v1.0.0 (02.10.2026) - APro Agents / borys-sf · Agata 14:12 (kolejność: Claude Code → Codex → Kimi → Gemini)

GDZIE (dokumentacja gemini-cli docs/extensions/reference.md, czytane 02.10)
════════════════════════════════════════════════════════════════════════
„Gemini CLI loads extensions from `<home>/.gemini/extensions`. Each extension must have a
`gemini-extension.json` file in its root directory” — nazwa = nazwa katalogu (`sf-kit`). Kit kopiuje
wygenerowany katalog `gemini/` z repo pod `~/.gemini/extensions/sf-kit/`. Globalnego `GEMINI.md`
użytkownika NIE ruszamy: kontekst Kita to `contextFileName` rozszerzenia.

Bez `gemini extensions install` (wymaga binarki i gita; na serwerze jej nie ma) — dokumentacja mówi,
że install robi KOPIĘ; robimy tę samą kopię sami. Czy Gemini wymaga dodatkowo włączenia rozszerzenia
(`gemini extensions enable`), dokumentacja nie rozstrzyga — pytanie na SF-203.

Cudze zostaje: katalog `sf-kit` bez naszego znacznika w `GEMINI.md` = cudzy → pomijamy, kod 1.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import instalator_pakietu as ip
from . import pakiet


def katalog_rozszerzenia() -> Path:
    return Path.home() / ".gemini" / "extensions" / "sf-kit"


def _nasz(katalog: Path) -> bool:
    kontekst = katalog / "GEMINI.md"
    return kontekst.is_file() and ip.ZNACZNIK in kontekst.read_text(encoding="utf-8", errors="replace")


def zainstalowany() -> bool:
    return _nasz(katalog_rozszerzenia())


def zainstaluj(korzen: Path = pakiet.KORZEN) -> tuple[bool, list[str]]:
    zrodlo = korzen / pakiet.KATALOG_GEMINI
    if not (zrodlo / "gemini-extension.json").is_file():
        return False, [f"Brak pakietu Gemini w {zrodlo} — Kit jest niepełny (`sf-kit update`)."]
    cel = katalog_rozszerzenia()
    if cel.exists() and not _nasz(cel):
        return False, [f"{cel} istnieje i NIE jest rozszerzeniem Kita — nie nadpisuję. "
                       "Usuń je albo zmień jego nazwę, potem `sf-kit init --gemini`."]
    if cel.exists():
        shutil.rmtree(cel)
    cel.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(zrodlo, cel)
    wersja = json.loads((cel / "gemini-extension.json").read_text(encoding="utf-8")).get("version")
    return True, [f"{cel}: rozszerzenie sf-kit {wersja}",
                  "W Gemini CLI: `/sf:…` (np. `/sf:sprawy`), `/extensions list`; po zmianach uruchom Gemini ponownie."]


def odswiez(korzen: Path = pakiet.KORZEN) -> list[str]:
    if not zainstalowany():
        return []
    _, raport = zainstaluj(korzen)
    return ["Rozszerzenie Gemini odświeżone:", *raport]
