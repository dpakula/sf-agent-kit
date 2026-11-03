"""Dziennik audytu zapisów — ten sam wiersz, co `sf_audit` z biblioteki floty (`sf_api.sh` 1.11.0).

v0.1 (03.11.2026) - APro Agents / klaudiusz-general · SF-486 krok 2

PO CO
═════
Zaplecze koordynatora (`scripts/zaplecze/tematy.py`) liczy tematy okna jawnego z `sf_audit.log`:
każda linia z `sesja=jawny` (albo bez pola `sesja`) i UUID sprawy/Organizacji to temat, którym
okno się zajmuje. Gdy koordynator przechodzi z `sf_api.sh` na Kit, a Kit nic do tego pliku nie
pisze, router traci tematy — i zaczyna wtrącać się w rozmowę, którą okno właśnie prowadzi.

Drugi powód: miara sukcesu SF-486 („≥ 80 % operacji koordynatora przez Kit”) liczy `hook=kit`
przeciw wierszom biblioteki. Bez dziennika Kita nie ma czego liczyć.

KIEDY PISZE
═══════════
Tylko gdy wskazano plik: `SF_KIT_AUDIT_LOG` albo ustawienie lokalne `dziennik_audytu`. Kit
u klienta (Codex Krzyśka, Wójt) nie ma żadnego `sf_audit.log` i nie powinien go zakładać.
Zapisujemy wyłącznie ZAPISY (POST/PATCH/PUT/DELETE) — odczyty biblioteka też pomijała.

FORMAT (bez zmian względem biblioteki — parser dzieli po ` | ` i `=`):
    2026-11-03T10:51:38Z | hook=kit | ticket=<uuid|-> | tenant=<uuid|-> | action=POST tickets/…/entries
      | result=HTTP 201 | actor=<slug> | sesja=jawny|zaplecze

`sesja`: `SF_KIT_SESJA` (jawny|zaplecze) albo — zgodność z biblioteką — `AGATA_ROLA=zaplecze`.
Błąd zapisu dziennika NIGDY nie przerywa żądania: dziennik jest śladem, nie bramką.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

ZMIENNA_PLIKU = "SF_KIT_AUDIT_LOG"
ZMIENNA_SESJI = "SF_KIT_SESJA"
SESJE = ("jawny", "zaplecze")

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_SPRAWA_W_SCIEZCE = re.compile(rf"(?:^|/)(?:tickets|ticket)/({_UUID})")
_SPRAWA_W_ENCJI = re.compile(rf"entities/ticket/({_UUID})")


def sesja() -> str:
    jawna = (os.environ.get(ZMIENNA_SESJI) or "").strip().lower()
    if jawna in SESJE:
        return jawna
    return "zaplecze" if os.environ.get("AGATA_ROLA") == "zaplecze" else "jawny"


def sprawa_z_zadania(sciezka: str, cialo: dict | None) -> str:
    """UUID sprawy, której dotyczy zapis: ze ścieżki albo z kotwicy bloku konsoli."""
    trafienie = _SPRAWA_W_SCIEZCE.search(sciezka) or _SPRAWA_W_ENCJI.search(sciezka)
    if trafienie:
        return trafienie.group(1).lower()
    kotwica = (cialo or {}).get("context_anchor") if isinstance(cialo, dict) else None
    if isinstance(kotwica, dict) and re.fullmatch(_UUID, str(kotwica.get("id") or "")):
        return str(kotwica["id"]).lower()
    return "-"


def _czysc(tekst: str) -> str:
    """Pole wiersza bez separatora i bez nowych linii — parser dzieli po ` | `."""
    return re.sub(r"\s+", " ", str(tekst)).replace(" | ", " / ").strip() or "-"


class Dziennik:
    """Zapisywacz jednego pliku. `None` w kliencie = brak dziennika (domyślnie)."""

    def __init__(self, plik: str | Path, *, aktor: str):
        self.plik = Path(os.path.expanduser(str(plik)))
        self.aktor = _czysc(aktor or "kit")

    def zapisz(self, metoda: str, sciezka: str, *, cialo: dict | None, organizacja: str,
               kod: int | None, akcja: str = "") -> None:
        if metoda.upper() == "GET":
            return
        trasa = sciezka.split("?", 1)[0].lstrip("/")
        wiersz = " | ".join([
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hook=kit",
            f"ticket={sprawa_z_zadania(trasa, cialo)}",
            f"tenant={_czysc(organizacja or '-')}",
            f"action={_czysc(akcja or f'{metoda.upper()} {trasa}')}",
            f"result={'HTTP ' + str(kod) if kod else 'brak odpowiedzi'}",
            f"actor={self.aktor}",
            f"sesja={sesja()}",
        ])
        try:
            self.plik.parent.mkdir(parents=True, exist_ok=True)
            with self.plik.open("a", encoding="utf-8") as f:
                f.write(wiersz + "\n")
        except OSError:
            pass


def z_ustawien(konf, aktor: str) -> Dziennik | None:
    """Dziennik z `SF_KIT_AUDIT_LOG` (pierwszeństwo) albo z `dziennik_audytu` w config.json."""
    plik = (os.environ.get(ZMIENNA_PLIKU) or getattr(konf, "dziennik_audytu", "") or "").strip()
    return Dziennik(plik, aktor=aktor) if plik else None
