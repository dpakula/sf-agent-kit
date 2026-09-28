"""Puls workera do SF — `POST /flota/puls` (SF-87).

v0.1 (28.09.2026) - APro Agents / borys-sf

PO CO
═════
Ekran „Flota” w SF liczył życie workera z ostatniego śladu (wpisu, zadania). Worker bez pracy
nie zostawia śladu i wyglądał jak martwy; worker w długim zadaniu — tak samo. Od SF-87 worker
melduje się sam, własnym kluczem (klucz agenta melduje WYŁĄCZNIE siebie — reguła po stronie SF).

TO NIE JEST TĘTNO USŁUGI
════════════════════════
`usluga.zapisz_tetno` to plik dla LOKALNEJ czujki (restart usługi). Tu mówimy do SF, dla ludzi.
Dwa odbiorcy, dwie semantyki: czujka potrzebuje „do kiedy ten stan jest legalny”, ekran — stanu
i świeżości liczonej zegarem serwera.

TRZY ZASADY
═══════════
1. **W trakcie zadania puls idzie z WĄTKU co `OKRES_S`.** Wykonawca to blokujący proces —
   bez wątku SF po trzech minutach pokazałby „brak aktualnego sygnału” przy workerze, który
   właśnie pracuje, czyli odwrotność prawdy.
2. **Porządek po stronie SF:** `generacja` = czas startu procesu (rośnie przy każdym restarcie),
   `nr_sekw` = licznik w procesie. Stary proces nie cofnie stanu nowego.
3. **Puls nigdy nie zatrzymuje pracy.** 503 przed rewizją, 403, brak sieci — to jest „SF dziś
   nie przyjmuje pulsu”, a nie powód, żeby nie wykonać zadania. W logu raz na zmianę powodu.
"""
from __future__ import annotations

import socket
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

#: Okres pulsu — ten sam, na który umawia się SF (`puls.OKRES_S`, 3 braki = brak sygnału).
OKRES_S = 60

#: Czas startu PROCESU — generacja instancji. Stała dla procesu, rośnie przy restarcie.
_GENERACJA = int(time.time())


def _teraz() -> str:
    return datetime.now(timezone.utc).isoformat()


class PulsSF:
    """Meldunki jednej instancji workera. Bezpieczne wątkowo (wątek pulsu + pętla główna)."""

    def __init__(self, klient, slug: str, *, loguj=None, maszyna: str | None = None,
                 generacja: int | None = None):
        self._klient = klient
        self.slug = slug
        self.maszyna = (maszyna or socket.gethostname())[:128]
        # Instancja = maszyna + slug: jeden worker agenta na maszynie. Drugi proces tego
        # samego agenta na tej samej maszynie dostanie tę samą instancję i przegra porządkiem
        # generacji — co jest właściwe, bo to on jest „tym starszym” albo „tym nowszym”.
        self.instancja = f"{self.maszyna}:{slug}"[:64]
        self.generacja = _GENERACJA if generacja is None else generacja
        self._nr = 0
        self._stan: str | None = None
        self._stan_od: str | None = None
        self._blokada = threading.Lock()
        self._loguj = loguj or (lambda _t: None)
        self._ostatni_powod: str | None = None

    def melduj(self, stan: str, *, przyczyna: str | None = None,
               zadanie: dict | None = None, postep: bool = False) -> str | None:
        """Wyślij jeden meldunek. Zwraca wynik SF (`przyjety`…) albo `None`, gdy nie doszedł."""
        with self._blokada:
            if stan != self._stan:
                self._stan, self._stan_od = stan, _teraz()
            self._nr += 1
            meldunek = {
                "agent_slug": self.slug, "instancja": self.instancja,
                "generacja": self.generacja, "nr_sekw": self._nr,
                "maszyna": self.maszyna, "zrodlo": "kit",
                "stan": stan, "stan_od": self._stan_od, "zgloszono_o": _teraz(),
            }
            if przyczyna:
                meldunek["przyczyna"] = przyczyna[:240]
            if zadanie:
                meldunek["zadanie_id"] = str(zadanie.get("id")) if zadanie.get("id") else None
                meldunek["ticket_id"] = (str(zadanie.get("ticket_id"))
                                         if zadanie.get("ticket_id") else None)
            if postep:
                meldunek["ostatni_postep_o"] = _teraz()
        try:
            odp = self._klient.puls([meldunek])
        except Exception as blad:       # noqa: BLE001 — patrz zasada 3 w nagłówku
            powod = f"{type(blad).__name__}: {blad}"
            if powod != self._ostatni_powod:
                self._loguj(f"puls do SF nie doszedł: {powod}")
            self._ostatni_powod = powod
            return None
        self._ostatni_powod = None
        wyniki = (odp or {}).get("wyniki") or [{}]
        return wyniki[0].get("wynik")

    @contextmanager
    def w_trakcie(self, zadanie: dict, *, okres_s: float = OKRES_S):
        """Na czas wykonania: `pracuje` od razu i co `okres_s` z wątku, do wyjścia z bloku."""
        koniec = threading.Event()
        self.melduj("pracuje", zadanie=zadanie, postep=True)

        def _petla():
            while not koniec.wait(okres_s):
                self.melduj("pracuje", zadanie=zadanie)

        watek = threading.Thread(target=_petla, name=f"puls-sf-{self.slug}", daemon=True)
        watek.start()
        try:
            yield self
        finally:
            koniec.set()
            watek.join(timeout=5)
