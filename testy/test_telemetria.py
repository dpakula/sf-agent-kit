"""Telemetria kroków — sufit, cisza i to, czego nie zagłusza (ADVERTPR-807 C2).

v0.1 (16.09.2026) - APro Agents / borys-sf

Telemetria jest dodatkiem, więc każdy jej błąd ma jeden kształt: **hałas przykrywający
to, co ważne**, albo **awaria z powodu dodatku**. Oba są tu pilnowane osobno.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit.telemetria import Telemetria  # noqa: E402
from sf_kit.worker import obsluz_zadanie  # noqa: E402
from testy.test_worker import AtrapaKlienta, konfiguracja, zadanie  # noqa: E402


class Zegar:
    """Sterowany zegar — sufit czasowy testujemy przesuwając czas, nie czekając."""

    def __init__(self):
        self.teraz = 1000.0

    def __call__(self) -> float:
        return self.teraz

    def przesun(self, sekund: float) -> None:
        self.teraz += sekund


class AtrapaKomentarzy:
    def __init__(self, *, pada=False):
        self.komentarze = []
        self._pada = pada

    def komentarz_zadania(self, task_id, tresc, *, wewnetrzny=True):
        if self._pada:
            raise RuntimeError("atrapa: SF nie przyjmuje komentarzy")
        self.komentarze.append(tresc)
        return {}


class TestSufit(unittest.TestCase):

    def test_pierwszy_krok_idzie_ZAWSZE(self):
        """„Wziąłem i zaczynam" jest informacją nawet przy zadaniu dziesięciosekundowym."""
        klient, zegar = AtrapaKomentarzy(), Zegar()
        puls = Telemetria(klient, "z1", krokow=4, zegar=zegar)

        self.assertTrue(puls.krok(1, "zaczynam"))
        self.assertEqual(klient.komentarze, ["krok 1 z 4: zaczynam"])

    def test_kroki_w_tej_samej_minucie_sa_POMIJANE(self):
        """Cztery komentarze pod zadaniem na dziesięć sekund to śmieci, nie telemetria."""
        klient, zegar = AtrapaKomentarzy(), Zegar()
        puls = Telemetria(klient, "z1", krokow=4, zegar=zegar)

        puls.krok(1, "a")
        zegar.przesun(5)
        self.assertFalse(puls.krok(2, "b"))
        zegar.przesun(5)
        self.assertFalse(puls.krok(3, "c"))

        self.assertEqual(len(klient.komentarze), 1)
        self.assertEqual(puls.pominietych, 2, "pominięte mają być POLICZONE, nie przemilczane")

    def test_po_minucie_telemetria_wraca(self):
        klient, zegar = AtrapaKomentarzy(), Zegar()
        puls = Telemetria(klient, "z1", krokow=4, zegar=zegar)

        puls.krok(1, "a")
        zegar.przesun(61)
        self.assertTrue(puls.krok(2, "b"))
        self.assertEqual(klient.komentarze[-1], "krok 2 z 4: b")
        self.assertEqual(puls.wyslanych, 2)

    def test_sufit_liczy_sie_od_OSTATNIO_WYSLANEGO_a_nie_od_proby(self):
        """Pominięta próba nie może przesuwać zegara — inaczej częste kroki uciszałyby
        telemetrię na zawsze, każdy odsuwając następny."""
        klient, zegar = AtrapaKomentarzy(), Zegar()
        puls = Telemetria(klient, "z1", krokow=4, zegar=zegar)

        puls.krok(1, "a")
        for _ in range(5):
            zegar.przesun(20)
            puls.krok(2, "próba")          # 20, 40, 60, 80, 100 s od pierwszego
        # Po przekroczeniu minuty któraś z prób MUSI przejść.
        self.assertGreaterEqual(puls.wyslanych, 2)


class TestCiszaGdzieTrzeba(unittest.TestCase):

    def test_wylaczona_telemetria_nie_pisze_NIC(self):
        klient, zegar = AtrapaKomentarzy(), Zegar()
        puls = Telemetria(klient, "z1", krokow=4, wlaczona=False, zegar=zegar)

        self.assertFalse(puls.krok(1, "a"))
        zegar.przesun(300)
        self.assertFalse(puls.krok(2, "b"))
        self.assertEqual(klient.komentarze, [])

    def test_zadanie_BEZ_SPRAWY_nie_dostaje_telemetrii(self):
        """Tam komentarz zadania jest JEDYNYM miejscem, w którym zostaje wynik (v0.4).
        Telemetria dopisana obok przykryłaby dokładnie to, co warto przeczytać."""
        klient = AtrapaKlienta()
        obsluz_zadanie(klient, konfiguracja(), zadanie(ticket_id=None, body_md="echo ok"))

        tresci = [t for _, t in klient.komentarze]
        self.assertEqual(len(tresci), 1, "pod zadaniem bez sprawy ma zostać SAM wynik")
        self.assertNotIn("krok 1 z 4", tresci[0])

    def test_zadanie_ZE_SPRAWA_dostaje_pierwszy_krok(self):
        klient = AtrapaKlienta()
        obsluz_zadanie(klient, konfiguracja(), zadanie(body_md="echo ok"))

        tresci = [t for _, t in klient.komentarze]
        self.assertTrue(tresci, "zadanie ze sprawą ma dostać telemetrię")
        self.assertIn("krok 1 z 4", tresci[0])


class TestOdpornosc(unittest.TestCase):

    def test_awaria_komentarza_NIE_wywraca_pracy(self):
        """Telemetria jest dodatkiem; zadanie ma się wykonać także wtedy, gdy SF milczy."""
        klient, zegar = AtrapaKomentarzy(pada=True), Zegar()
        puls = Telemetria(klient, "z1", krokow=4, zegar=zegar)

        self.assertFalse(puls.krok(1, "a"))
        self.assertEqual(puls.wyslanych, 0)

    def test_nieudany_komentarz_nie_blokuje_nastepnego(self):
        """Po awarii zegar sufitu ma zostać nieruszony — inaczej jedna awaria uciszyłaby
        telemetrię na całą minutę, choć nic nie poszło."""
        klient, zegar = AtrapaKomentarzy(pada=True), Zegar()
        puls = Telemetria(klient, "z1", krokow=4, zegar=zegar)
        puls.krok(1, "a")

        klient._pada = False
        self.assertTrue(puls.krok(2, "b"), "druga próba ma pójść od razu, bo pierwsza nie doszła")


if __name__ == "__main__":
    unittest.main()
