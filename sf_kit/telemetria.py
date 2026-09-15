"""Telemetria kroków zadania — „krok N z M" w komentarzach (ADVERTPR-807 C2).

v0.1 (16.09.2026) - APro Agents / borys-sf

PO CO
═════
Zadanie w toku wygląda z zewnątrz tak samo jak zadanie zawieszone: status `in_progress`
i cisza. Człowiek, który czeka, nie ma jak odróżnić „model myśli" od „worker umarł pół
godziny temu" — a to są dwie sytuacje wymagające czegoś zupełnie innego.

DLACZEGO SUFIT JEDEN NA MINUTĘ
Zadanie na dziesięć sekund przechodzi przez wszystkie cztery kroki w mgnieniu oka. Cztery
komentarze pod takim zadaniem to nie telemetria, tylko śmieci przykrywające sprawozdanie —
czyli jedyną rzecz, którą naprawdę warto tam przeczytać. Sufit sprawia, że telemetria
pojawia się dokładnie tam, gdzie ma sens: przy zadaniach trwających na tyle długo, że cisza
zaczyna niepokoić.

Pierwszy krok idzie ZAWSZE, bez czekania na sufit: „wziąłem i zaczynam" jest informacją nawet
przy zadaniu dziesięciosekundowym, bo mówi, że worker żyje i że to on je wziął.

MILCZYMY PRZY ZADANIU BEZ SPRAWY — I TO NIE JEST WYJĄTEK, TYLKO TA SAMA ZASADA
Zadanie bez sprawy nie ma osi, więc wynik ląduje w komentarzu zadania (v0.4, decyzja Damiana)
— i to jest wtedy JEDYNE miejsce, w którym praca zostaje. Telemetria dopisana obok przykryłaby
dokładnie tę jedną rzecz, którą warto tam przeczytać. Sufit chroni przed hałasem; tutaj hałasem
byłby każdy komentarz, więc nie piszemy żadnego.

TELEMETRIA NIGDY NIE PRZERYWA PRACY
Komentarz to dodatek; zadanie ma się wykonać także wtedy, gdy SF akurat nie przyjmuje
komentarzy. Każdy błąd stąd schodzi do logu i tyle.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)

#: Ile najmniej sekund między komentarzami telemetrii.
ODSTEP_S = 60


class Telemetria:
    """Licznik kroków, który mówi o sobie w komentarzach — ale nie za często."""

    def __init__(self, klient, zadanie_id: str, *, krokow: int, wlaczona: bool = True,
                 zegar: Callable[[], float] = time.monotonic, odstep_s: int = ODSTEP_S):
        self._wlaczona = wlaczona
        self._klient = klient
        self._zid = str(zadanie_id)
        self._krokow = krokow
        self._zegar = zegar
        self._odstep = odstep_s
        self._ostatnio: float | None = None
        #: Kroki pominięte przez sufit — do logu, żeby cisza dała się wytłumaczyć.
        self.pominietych = 0
        self.wyslanych = 0

    def krok(self, numer: int, opis: str) -> bool:
        """Zgłoś krok. Zwraca, czy komentarz faktycznie poszedł."""
        if not self._wlaczona:
            return False
        teraz = self._zegar()
        if self._ostatnio is not None and (teraz - self._ostatnio) < self._odstep:
            self.pominietych += 1
            return False

        tresc = f"krok {numer} z {self._krokow}: {opis}"
        try:
            self._klient.komentarz_zadania(self._zid, tresc, wewnetrzny=True)
        except Exception as blad:            # noqa: BLE001 — dodatek nie może wywrócić pracy
            logger.debug("telemetria: nie udało się dodać komentarza: %s", blad)
            return False

        self._ostatnio = teraz
        self.wyslanych += 1
        return True
