"""Trwały, mały stan ponowień workera."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


OPOZNIENIA_S = (600, 3600)


class StanProb:
    def __init__(self, plik: Path):
        self.plik = Path(plik)
        self.proby: dict[str, dict] = {}
        try:
            dane = json.loads(self.plik.read_text(encoding="utf-8"))
            self.proby = dane.get("proby", {}) if isinstance(dane, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self.proby = {}

    def gotowe(self, zadanie: dict, *, teraz: datetime | None = None) -> bool:
        zid = str(zadanie.get("id"))
        wpis = self.proby.get(zid)
        if not wpis:
            return True
        # Inna wersja oznacza, że człowiek ruszył status po ostatnim odłożeniu.
        if wpis.get("version") is not None and zadanie.get("version") != wpis.get("version"):
            self.wyczysc(zid)
            return True
        if int(wpis.get("liczba", 0)) >= 3:
            return False
        teraz = teraz or datetime.now(timezone.utc)
        return teraz >= datetime.fromisoformat(wpis["nastepna_proba"])

    def niepowodzenie(self, zid: str, blad: str, *, version: int | None = None,
                      teraz: datetime | None = None) -> int:
        teraz = teraz or datetime.now(timezone.utc)
        liczba = int(self.proby.get(zid, {}).get("liczba", 0)) + 1
        wpis = {"liczba": liczba, "ostatni_blad": blad, "version": version}
        if liczba <= len(OPOZNIENIA_S):
            wpis["nastepna_proba"] = (
                teraz + timedelta(seconds=OPOZNIENIA_S[liczba - 1])).isoformat()
        self.proby[zid] = wpis
        self.zapisz()
        return liczba

    def wyczysc(self, zid: str) -> None:
        if self.proby.pop(str(zid), None) is not None:
            self.zapisz()

    def zapisz(self) -> None:
        self.plik.parent.mkdir(parents=True, exist_ok=True)
        tymczasowy = self.plik.with_suffix(self.plik.suffix + ".tmp")
        tymczasowy.write_text(
            json.dumps({"proby": self.proby}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        os.replace(tymczasowy, self.plik)
