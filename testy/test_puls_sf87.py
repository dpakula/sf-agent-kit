"""Puls workera do SF (SF-87): kształt meldunku, porządek, wątek w trakcie zadania, odporność.

v0.1 (28.09.2026) - APro Agents / borys-sf

CZEGO TU PILNUJĘ
════════════════
1. **`nr_sekw` rośnie przez CAŁY proces** — także między taktami i po podmianie klienta.
   Licznik od zera przy tej samej generacji = SF odrzuca każdy meldunek jako nieaktualny.
2. **W trakcie zadania puls idzie z wątku** — sprawdzane W CHWILI wykonania, nie po fakcie.
3. **`stan_od` nie przesuwa się** przy powtórzeniu tego samego stanu.
4. **Puls nie zatrzymuje pracy** i nie zalewa logu.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import worker  # noqa: E402
from sf_kit.api import BladAPI, WynikSzukania  # noqa: E402
from sf_kit.puls_sf import PulsSF  # noqa: E402
from testy.test_worker import konfiguracja  # noqa: E402


class KlientPulsu:
    def __init__(self, *, pada=None):
        self.meldunki: list[dict] = []
        self.pada = pada

    def puls(self, meldunki):
        if self.pada:
            raise self.pada
        self.meldunki.extend(meldunki)
        return {"wyniki": [{"agent_slug": m["agent_slug"], "instancja": m["instancja"],
                            "wynik": "przyjety"} for m in meldunki]}

    # na potrzeby `przebieg`
    def moje_zadania(self, *, slug, status="queued", ile_najwyzej=None):
        return WynikSzukania(zadania=[], przejrzano=0, wszystkich=0)

    def skrzynka(self, **_):
        return {"wiadomosci": [], "nieodebrane": 0, "zalegle": 0}


class TestMeldunek(unittest.TestCase):
    def test_ksztalt_i_rosnacy_numer(self):
        k = KlientPulsu()
        p = PulsSF(k, "kimi-sf", maszyna="vps", generacja=77)
        self.assertEqual(p.melduj("bezczynny"), "przyjety")
        p.melduj("bezczynny")
        m1, m2 = k.meldunki
        self.assertEqual((m1["zrodlo"], m1["generacja"], m1["instancja"]), ("kit", 77, "vps:kimi-sf"))
        self.assertEqual([m1["nr_sekw"], m2["nr_sekw"]], [1, 2])

    def test_stan_od_stoi_przy_powtorzeniu_i_rusza_przy_zmianie(self):
        k = KlientPulsu()
        p = PulsSF(k, "kimi-sf")
        p.melduj("bezczynny")
        time.sleep(0.01)
        p.melduj("bezczynny")
        time.sleep(0.01)
        p.melduj("pracuje")
        a, b, c = (m["stan_od"] for m in k.meldunki)
        self.assertEqual(a, b)
        self.assertNotEqual(b, c)

    def test_blad_sf_to_none_i_jedna_linia_logu(self):
        log = []
        k = KlientPulsu(pada=BladAPI("HTTP 503: brakuje tabel rewizji", kod=503))
        p = PulsSF(k, "kimi-sf", loguj=log.append)
        self.assertIsNone(p.melduj("bezczynny"))
        p.melduj("bezczynny")
        self.assertEqual(len(log), 1)


class TestWTrakcie(unittest.TestCase):
    def test_watek_pulsuje_w_trakcie_i_milknie_po_wyjsciu(self):
        k = KlientPulsu()
        p = PulsSF(k, "kimi-sf")
        with p.w_trakcie({"id": "z1", "ticket_id": "t1"}, okres_s=0.01):
            time.sleep(0.08)
            w_trakcie = len(k.meldunki)
        po = len(k.meldunki)
        time.sleep(0.05)
        self.assertGreaterEqual(w_trakcie, 3, "pierwszy meldunek + kilka z wątku")
        self.assertEqual(len(k.meldunki), po, "po wyjściu z bloku wątek ma zamilknąć")
        self.assertTrue(all(m["stan"] == "pracuje" and m["zadanie_id"] == "z1" for m in k.meldunki))
        nr = [m["nr_sekw"] for m in k.meldunki]
        self.assertEqual(nr, sorted(set(nr)), "numery z wątku i z pętli nie mogą się powtórzyć")


class TestWWorkerze(unittest.TestCase):
    def setUp(self):
        worker._pulsy.clear()
        worker._ostatni_powod_braku = None
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.stan = Path(self._tmp.name) / "state.json"

    def tearDown(self):
        worker._pulsy.clear()
        self._tmp.cleanup()

    def test_takt_bez_zadan_melduje_bezczynny_a_numer_rosnie_miedzy_taktami(self):
        k = KlientPulsu()
        with mock.patch.object(worker, "_log"):
            worker.przebieg(k, konfiguracja(), plik_stanu=self.stan)
            worker.przebieg(k, konfiguracja(), plik_stanu=self.stan)
        self.assertEqual([m["stan"] for m in k.meldunki], ["bezczynny", "bezczynny"])
        self.assertEqual([m["nr_sekw"] for m in k.meldunki], [1, 2])

    def test_nowy_obiekt_klienta_nie_zeruje_numeru(self):
        k1, k2 = KlientPulsu(), KlientPulsu()
        with mock.patch.object(worker, "_log"):
            worker.przebieg(k1, konfiguracja(), plik_stanu=self.stan)
            worker.przebieg(k2, konfiguracja(), plik_stanu=self.stan)
        self.assertEqual(k2.meldunki[0]["nr_sekw"], 2)

    def test_w_chwili_wykonania_zadania_sf_ma_juz_puls_pracuje(self):
        from sf_kit import wykonawcy
        from testy.test_skrzynka_812 import KlientWorkera
        from testy.test_worker import zadanie

        klient = KlientWorkera()
        wyslane = []
        klient.puls = lambda meldunki: (wyslane.extend(meldunki), {"wyniki": [{"wynik": "przyjety"}]})[1]
        widziane = {}

        class Wykonawca(wykonawcy.Wykonawca):
            nazwa = "szpieg-puls"
            chce_ramke = True

            def dostepny(self):
                return True, ""

            def wykonaj(self, polecenie, *, katalog, limit_s):
                widziane["stany"] = [m["stan"] for m in wyslane]
                return wykonawcy.Wynik(True, "**Sedno** — ok")

        stare = dict(wykonawcy._WYKONAWCY)
        wykonawcy._WYKONAWCY["szpieg-puls"] = Wykonawca()
        try:
            with mock.patch.object(worker, "_log"):
                worker.obsluz_zadanie(klient, konfiguracja(runtime="szpieg-puls"),
                                      zadanie(body_md="zrób coś"),
                                      puls_sf=PulsSF(klient, "agent-testowy"))
        finally:
            wykonawcy._WYKONAWCY.clear()
            wykonawcy._WYKONAWCY.update(stare)
        self.assertEqual(widziane["stany"], ["pracuje"])


if __name__ == "__main__":
    unittest.main()
