"""Wspólny instalator pakietu SF Kita dla asystentów z plikiem instrukcji i katalogiem skilli (SF-203).

v1.0.0 (02.10.2026) - APro Agents / borys-sf · wydzielone z `codex_pakiet` przy pakiecie Kimi

Codex i Kimi Code instalują się tak samo: sekcja Kita między znacznikami w globalnym pliku instrukcji
(reszta pliku zostaje bajt w bajt) + skille skopiowane do katalogu użytkownika. Różnią się tylko
ŚCIEŻKAMI i znacznikami — to jest `Cel`. Jedna implementacja reguł „cudze zostaje”:
- nadpisujemy i usuwamy WYŁĄCZNIE katalogi skilli z naszym znacznikiem generatora,
- katalog o tej samej nazwie bez znacznika = cudzy: pomijamy, zgłaszamy, kod 1 (nie udajemy sukcesu).
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ZNACZNIK = "wygenerowano z pakiet/komendy.json przez sf-kit"


@dataclass(frozen=True)
class Cel:
    nazwa: str                               # „Codex”, „Kimi Code” — do raportu
    zrodlo: Path                             # katalog wygenerowanego pakietu w repo Kita
    plik_instrukcji: Callable[[], Path]      # plik, który narzędzie FAKTYCZNIE czyta
    katalog_skilli: Callable[[], Path]
    start: str                               # znaczniki sekcji
    koniec: str
    podpowiedz: str                          # ostatnia linia raportu: jak użyć w narzędziu
    po_instalacji: Callable[[], list[str]] | None = None   # np. rejestracja serwera MCP (SF-203)


def _nasz(katalog: Path) -> bool:
    skill = katalog / "SKILL.md"
    return skill.is_file() and ZNACZNIK in skill.read_text(encoding="utf-8", errors="replace")


def wstaw_sekcje(tekst: str, sekcja: str, start: str, koniec: str) -> str:
    if start in tekst and koniec in tekst:
        przed = tekst.split(start, 1)[0]
        po = tekst.split(koniec, 1)[1]
        return przed + sekcja.rstrip("\n") + po
    return (tekst.rstrip("\n") + "\n\n" if tekst.strip() else "") + sekcja


def zainstalowany(cel: Cel) -> bool:
    plik = cel.plik_instrukcji()
    return plik.is_file() and cel.start in plik.read_text(encoding="utf-8", errors="replace")


def zainstaluj(cel: Cel) -> tuple[bool, list[str]]:
    if not (cel.zrodlo / "AGENTS.md").is_file():
        return False, [f"Brak pakietu {cel.nazwa} w {cel.zrodlo} — Kit jest niepełny (`sf-kit update`)."]
    raport: list[str] = []

    plik = cel.plik_instrukcji()
    plik.parent.mkdir(parents=True, exist_ok=True)
    stary = plik.read_text(encoding="utf-8") if plik.is_file() else ""
    nowy = wstaw_sekcje(stary, (cel.zrodlo / "AGENTS.md").read_text(encoding="utf-8"), cel.start, cel.koniec)
    if nowy != stary:
        plik.write_text(nowy, encoding="utf-8")
    raport.append(f"{plik}: sekcja SF Kita {'zapisana' if nowy != stary else 'aktualna'}")

    docelowy_kat = cel.katalog_skilli()
    docelowy_kat.mkdir(parents=True, exist_ok=True)
    nowe = {d.name for d in (cel.zrodlo / "skills").iterdir() if d.is_dir()}
    pominiete, zapisane = [], 0
    for nazwa in sorted(nowe):
        docelowy = docelowy_kat / nazwa
        if docelowy.exists() and not _nasz(docelowy):
            pominiete.append(nazwa)
            continue
        if docelowy.exists():
            shutil.rmtree(docelowy)
        shutil.copytree(cel.zrodlo / "skills" / nazwa, docelowy)
        zapisane += 1
    usuniete = [d.name for d in docelowy_kat.iterdir() if d.is_dir() and d.name.startswith("sf-")
                and d.name not in nowe and _nasz(d)]
    for nazwa in usuniete:
        shutil.rmtree(docelowy_kat / nazwa)
    raport.append(f"{docelowy_kat}: {zapisane} skilli SF Kita"
                  + (f", usunięte nieaktualne: {', '.join(usuniete)}" if usuniete else ""))
    if pominiete:
        raport.append(f"POMINIĘTE (cudze katalogi o tej samej nazwie): {', '.join(pominiete)}")
    if cel.po_instalacji:
        raport.extend(cel.po_instalacji())
    raport.append(cel.podpowiedz)
    return not pominiete, raport


def odswiez(cel: Cel) -> list[str]:
    if not zainstalowany(cel):
        return []
    _, raport = zainstaluj(cel)
    return [f"Pakiet {cel.nazwa} odświeżony:", *raport]
