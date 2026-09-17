"""Ostrzeżenie przed wygaśnięciem klucza — żeby termin nie wyglądał jak awaria (ADVERTPR-779).

v1.0.0 (17.09.2026) - APro Agents / borys-sf

Klucze agentów dostają termin ważności (30 dni, przedłużenie do 180). Bez ostrzeżenia dzień
wygaśnięcia wygląda z zewnątrz jak awaria SalesForge: worker przestaje brać zadania, w dzienniku
stoi odmowa serwera, a człowiek szuka usterki w kodzie Kita.

CO TU JEST SPRAWDZANE
1. że ostrzeżenie **milczy**, gdy nie ma o czym mówić (klucz bezterminowy, termin daleko,
   data nie do odczytania) — ostrzeżenie, które odzywa się zawsze, przestaje być ostrzeżeniem;
2. że **odzywa się** w oknie siedmiu dni, w dniu terminu i po nim — i że mówi te trzy rzeczy
   RÓŻNIE, bo „wygasa jutro" i „wygasł wczoraj" wymagają innych działań;
3. że awaria po drodze (brak sieci, zmieniony kształt `GET /me`) **nie zatrzymuje workera** —
   to informacja, nie warunek pracy.
"""
import unittest
from datetime import datetime, timedelta, timezone

from sf_kit import tozsamosc, worker


TERAZ = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def _toz(wygasa):
    return tozsamosc.Tozsamosc(
        konto_nazwa="Borys", konto_kind="agent", klucz_prefiks="sk_live_1234",
        klucz_scope="user", klucz_zawezony=True, organizacje=[], klucz_wygasa=wygasa,
    )


def _za(dni: int) -> str:
    return (TERAZ + timedelta(days=dni)).isoformat().replace("+00:00", "Z")


class TestKiedyMilczy(unittest.TestCase):
    def test_klucz_bezterminowy_nie_generuje_szumu(self):
        """`wygasa = null` znaczy BRAK TERMINU, nie „nie wiem" — nie ma czego zapowiadać."""
        self.assertIsNone(tozsamosc.ostrzezenie_o_waznosci(_toz(None), teraz=TERAZ))

    def test_termin_daleko_to_cisza(self):
        self.assertIsNone(tozsamosc.ostrzezenie_o_waznosci(_toz(_za(30)), teraz=TERAZ))

    def test_prog_jest_domkniety_z_obu_stron(self):
        """Dzień przed progiem cisza, dzień na progu już nie — inaczej próg jest życzeniem."""
        self.assertIsNone(tozsamosc.ostrzezenie_o_waznosci(_toz(_za(8)), teraz=TERAZ))
        self.assertIsNotNone(tozsamosc.ostrzezenie_o_waznosci(_toz(_za(7)), teraz=TERAZ))

    def test_nieczytelna_data_nie_wywraca_kita(self):
        """Gdyby SF zmieniło format, worker ma pracować dalej — tylko bez ostrzeżenia."""
        self.assertIsNone(tozsamosc.dni_do_wygasniecia(_toz("kiedyś tam"), teraz=TERAZ))
        self.assertIsNone(tozsamosc.ostrzezenie_o_waznosci(_toz("kiedyś tam"), teraz=TERAZ))


class TestCoMowi(unittest.TestCase):
    def test_przed_terminem_mowi_ile_zostalo_i_kto_zalatwia(self):
        zdanie = tozsamosc.ostrzezenie_o_waznosci(_toz(_za(5)), teraz=TERAZ)
        self.assertIn("za 5 dni", zdanie)
        self.assertIn("przedłużenie", zdanie)

    def test_jeden_dzien_odmienia_sie_po_polsku(self):
        self.assertIn("za 1 dzień", tozsamosc.ostrzezenie_o_waznosci(_toz(_za(1)), teraz=TERAZ))

    def test_w_dniu_terminu_mowi_DZIS(self):
        zdanie = tozsamosc.ostrzezenie_o_waznosci(_toz(_za(0)), teraz=TERAZ)
        self.assertIn("DZIŚ", zdanie)

    def test_po_terminie_mowi_ze_to_NIE_jest_awaria_SF(self):
        """Najważniejsze zdanie w całym module: człowiek ma nie szukać usterki w kodzie."""
        zdanie = tozsamosc.ostrzezenie_o_waznosci(_toz(_za(-2)), teraz=TERAZ)
        self.assertIn("WYGASŁ", zdanie)
        self.assertIn("nie jest awaria", zdanie)
        self.assertIn("sf-kit init", zdanie)


class TestWorker(unittest.TestCase):
    class _Klient:
        def __init__(self, odpowiedz=None, blad=None):
            self.odpowiedz, self.blad, self.pytano = odpowiedz, blad, 0

        def me(self):
            self.pytano += 1
            if self.blad:
                raise self.blad
            return self.odpowiedz

    def test_worker_oglasza_zblizajacy_sie_termin(self):
        kl = self._Klient({"konto": {"nazwa": "Borys"},
                           "klucz": {"prefiks": "sk_live_1", "wygasa": _za(3)},
                           "organizacje": []})
        zdanie = worker.ostrzez_o_kluczu(kl, teraz=TERAZ)
        self.assertIsNotNone(zdanie)
        self.assertIn("za 3 dni", zdanie)

    def test_awaria_sprawdzenia_nie_zatrzymuje_workera(self):
        """FAIL-SOFT. Zatrzymać workera ma SF, gdy odmówi — nie pole informacyjne."""
        kl = self._Klient(blad=RuntimeError("sieć padła"))
        self.assertIsNone(worker.ostrzez_o_kluczu(kl, teraz=TERAZ))
        self.assertEqual(kl.pytano, 1)

    def test_klucz_bezterminowy_nie_zasmieca_dziennika_workera(self):
        kl = self._Klient({"konto": {}, "klucz": {"wygasa": None}, "organizacje": []})
        self.assertIsNone(worker.ostrzez_o_kluczu(kl, teraz=TERAZ))


if __name__ == "__main__":
    unittest.main()
