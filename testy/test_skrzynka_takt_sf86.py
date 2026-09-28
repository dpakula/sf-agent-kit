"""Skrzynka w KAŻDYM takcie workera — przyjęcie do kolejki i `delivered` (SF-86 etap 3).

v0.1 (28.09.2026) - APro Agents / borys-sf

CZEGO TU PILNUJĘ
════════════════
1. **Kolejność: plik z `fsync`, POTEM ack `delivered`.** Atrapa sprawdza istnienie pliku
   w chwili acka — nie tylko to, że oba kiedyś się stały. Ack przed zapisem znaczyłby
   „trwale przyjęta" dla wiadomości, której nie ma nigdzie.
2. **Worker BEZ zadania też przyjmuje.** Do SF-86 skrzynka żyła tylko przy starcie zadania,
   więc worker bez pracy nie dowiadywał się o niczym.
3. **Deduplikacja po stronie odbiornika.** Drugi takt nie pisze pliku drugi raz i nie wysyła
   drugiego acka; ack, który nie przeszedł, jest ponawiany, a plik zostaje.
4. **Skrzynka nie przerywa taktu** i jej odmowa nie zalewa logu co 60 s.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import skrzynka, worker  # noqa: E402
from sf_kit.api import BladAPI, WynikSzukania  # noqa: E402
from testy.test_skrzynka_812 import wiadomosc  # noqa: E402
from testy.test_worker import konfiguracja  # noqa: E402


class KlientTaktu:
    """Atrapa: skrzynka + ack z zapisem, czy plik istniał W CHWILI acka."""

    def __init__(self, wiadomosci, *, katalog=None, ack_pada=False, odczyt_pada=None):
        self.wiadomosci = wiadomosci
        self.katalog = katalog
        self.ack_pada = ack_pada
        self.odczyt_pada = odczyt_pada
        self.acki: list[tuple[str, str, bool]] = []
        self.odczyty = 0

    def skrzynka(self, *, dni=None, limit=None, tylko_nieodebrane=False):
        self.odczyty += 1
        if self.odczyt_pada:
            raise self.odczyt_pada
        return {"wiadomosci": self.wiadomosci, "nieodebrane": len(self.wiadomosci), "zalegle": 0}

    def potwierdz_odbior(self, message_id, *, status="consumed", powod=None):
        plik_byl = bool(self.katalog and (Path(self.katalog) / f"{message_id}.json").exists())
        self.acki.append((str(message_id), status, plik_byl))
        if self.ack_pada:
            raise BladAPI("atrapa: ack nie przeszedł", kod=500)
        return {}

    def moje_zadania(self, *, slug, status="queued", ile_najwyzej=None):
        return WynikSzukania(zadania=[], przejrzano=0, wszystkich=0)


class TestPrzyjmij(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.katalog = Path(self._tmp.name) / "skrzynka-agent-testowy"

    def tearDown(self):
        self._tmp.cleanup()

    def test_nowa_wiadomosc_najpierw_plik_potem_ack_delivered(self):
        k = KlientTaktu([wiadomosc(mid="m1")], katalog=self.katalog)
        wynik = skrzynka.przyjmij(k, self.katalog)
        self.assertEqual(k.acki, [("m1", "delivered", True)])
        self.assertTrue((self.katalog / "m1.json").exists())
        self.assertEqual([w["message_id"] for w in wynik.wiadomosci], ["m1"])

    def test_juz_doreczona_nie_dostaje_drugiego_acka_ani_drugiego_zapisu(self):
        k = KlientTaktu([wiadomosc(mid="m1")], katalog=self.katalog)
        skrzynka.przyjmij(k, self.katalog)
        znacznik = (self.katalog / "m1.json").stat().st_mtime_ns

        k.wiadomosci = [wiadomosc(mid="m1", status="delivered")]
        skrzynka.przyjmij(k, self.katalog)
        self.assertEqual(len(k.acki), 1)
        self.assertEqual((self.katalog / "m1.json").stat().st_mtime_ns, znacznik)

    def test_doreczona_bez_pliku_na_dysku_jest_odtwarzana_bez_acka(self):
        """SF mówi `delivered`, dysk nie ma pliku (katalog wyczyszczony) — plik wraca, ack nie."""
        k = KlientTaktu([wiadomosc(mid="m1", status="delivered")], katalog=self.katalog)
        skrzynka.przyjmij(k, self.katalog)
        self.assertTrue((self.katalog / "m1.json").exists())
        self.assertEqual(k.acki, [])

    def test_ack_ktory_nie_przeszedl_jest_ponawiany_a_plik_zostaje(self):
        k = KlientTaktu([wiadomosc(mid="m1")], katalog=self.katalog, ack_pada=True)
        wynik = skrzynka.przyjmij(k, self.katalog)
        self.assertEqual(wynik.niepotwierdzone, ["m1"])
        self.assertTrue((self.katalog / "m1.json").exists())

        k.ack_pada = False
        skrzynka.przyjmij(k, self.katalog)
        self.assertEqual([a[1] for a in k.acki], ["delivered", "delivered"])

    def test_odmowa_skrzynki_to_powod_a_nie_wyjatek_i_nic_nie_trafia_na_dysk(self):
        k = KlientTaktu([], katalog=self.katalog,
                        odczyt_pada=BladAPI("HTTP 422: klucz bez właściciela", kod=422))
        wynik = skrzynka.przyjmij(k, self.katalog)
        self.assertIn("422", wynik.powod_braku)
        self.assertFalse(self.katalog.exists())

    def test_zdejmij_z_kolejki_usuwa_tylko_potwierdzone(self):
        k = KlientTaktu([wiadomosc(mid="m1"), wiadomosc(mid="m2")], katalog=self.katalog)
        skrzynka.przyjmij(k, self.katalog)
        odebrane = skrzynka.Odebrane(wiadomosci=[wiadomosc(mid="m1"), wiadomosc(mid="m2")],
                                     niepotwierdzone=["m2"])
        skrzynka.zdejmij_z_kolejki(self.katalog, odebrane)
        self.assertFalse((self.katalog / "m1.json").exists())
        self.assertTrue((self.katalog / "m2.json").exists())


class TestOdbiorWZadaniu(unittest.TestCase):
    def test_po_odbiorze_w_zadaniu_plik_znika_z_kolejki(self):
        """Przyjęta w takcie → przekazana wykonawcy w zadaniu → `consumed` → pliku już nie ma."""
        from sf_kit import wykonawcy
        from testy.test_skrzynka_812 import KlientWorkera
        from testy.test_worker import zadanie

        with tempfile.TemporaryDirectory() as tmp:
            katalog = Path(tmp) / "skrzynka-agent-testowy"
            klient = KlientWorkera()
            skrzynka._zapisz_trwale(katalog / "m1.json", wiadomosc(mid="m1"))

            class Wykonawca(wykonawcy.Wykonawca):
                nazwa = "szpieg-sf86"
                chce_ramke = True

                def dostepny(self):
                    return True, ""

                def wykonaj(self, polecenie, *, katalog, limit_s):
                    return wykonawcy.Wynik(True, "**Sedno** — ok")

            stare = dict(wykonawcy._WYKONAWCY)
            wykonawcy._WYKONAWCY["szpieg-sf86"] = Wykonawca()
            try:
                with mock.patch.object(worker, "_log"):
                    worker.obsluz_zadanie(klient, konfiguracja(runtime="szpieg-sf86"),
                                          zadanie(body_md="zrób coś"), katalog_skrzynki=katalog)
            finally:
                wykonawcy._WYKONAWCY.clear()
                wykonawcy._WYKONAWCY.update(stare)

            self.assertEqual(klient.potwierdzone, ["m1"])
            self.assertFalse((katalog / "m1.json").exists())


class TestWorkerBezZadania(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.stan = Path(self._tmp.name) / "state.json"
        worker._ostatni_powod_braku = None

    def tearDown(self):
        self._tmp.cleanup()

    def test_takt_bez_zadan_przyjmuje_skrzynke(self):
        katalog = self.stan.with_name("skrzynka-agent-testowy")
        k = KlientTaktu([wiadomosc(mid="m1")], katalog=katalog)
        with mock.patch.object(worker, "_log"):
            self.assertEqual(worker.przebieg(k, konfiguracja(), plik_stanu=self.stan), 0)
        self.assertEqual(k.acki, [("m1", "delivered", True)])

    def test_ta_sama_odmowa_trafia_do_logu_raz_a_nie_co_takt(self):
        k = KlientTaktu([], odczyt_pada=BladAPI("HTTP 422: konto bez sluga", kod=422))
        with mock.patch.object(worker, "_log") as log:
            for _ in range(3):
                worker.przebieg(k, konfiguracja(), plik_stanu=self.stan)
        linie = [c.args[0] for c in log.call_args_list if "skrzynka niedostępna" in c.args[0]]
        self.assertEqual(len(linie), 1)
        self.assertEqual(k.odczyty, 3)


if __name__ == "__main__":
    unittest.main()
