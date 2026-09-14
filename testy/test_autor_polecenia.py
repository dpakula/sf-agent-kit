"""Polecenia profilu AUTOR: rozpoznanie sprawy, szablon opisu, zachowanie przy błędach.

v0.3 (15.09.2026) - APro Agents / borys-sf

Trzy rzeczy, które tu najłatwiej zepsuć bez objawu:
  · dopisanie postępu do NIEWŁAŚCIWEJ sprawy (wygląda jak poprawna praca),
  · zgłoszenie z pustym opisem (wygląda jak zgłoszone),
  · sprawa założona, ale załączniki, które nie poszły (wygląda jak komplet).

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import autor  # noqa: E402


class AtrapaKlienta:
    def __init__(self, sprawy):
        self._sprawy = sprawy

    def sprawy(self, *, limit=50):
        return self._sprawy


def _sprawa(numer, prefiks="FM", tytul="Makieta"):
    return {"id": f"id-{prefiks}-{numer}", "ticket_number": numer,
            "ticket_prefix": prefiks, "title": tytul, "status": "new"}


class TestNazwaSprawy(unittest.TestCase):

    def test_numer_z_prefiksem(self):
        self.assertEqual(autor.numer_sprawy(_sprawa(12)), "FM-12")

    def test_sprawa_bez_numeru_nie_udaje_ze_go_ma(self):
        """Numeracja spraw jest dopiero projektowana (ADVERTPR-762) — część spraw go nie ma."""
        self.assertEqual(autor.numer_sprawy({"id": "x"}), "")


class TestRozpoznanieSprawy(unittest.TestCase):

    def test_numer_z_prefiksem_trafia(self):
        k = AtrapaKlienta([_sprawa(11), _sprawa(12)])
        self.assertEqual(autor.znajdz_sprawe(k, "FM-12")["id"], "id-FM-12")

    def test_prefiks_malymi_literami_to_ta_sama_sprawa(self):
        k = AtrapaKlienta([_sprawa(12)])
        self.assertEqual(autor.znajdz_sprawe(k, "fm-12")["id"], "id-FM-12")

    def test_sam_numer_dziala_gdy_jest_jednoznaczny(self):
        """Ludzie mówią „dwunastka", nie „ef-em myślnik dwanaście”."""
        k = AtrapaKlienta([_sprawa(12), _sprawa(13)])
        self.assertEqual(autor.znajdz_sprawe(k, "12")["id"], "id-FM-12")

    def test_niejednoznaczny_numer_ODMAWIA_zamiast_zgadywac(self):
        """Sedno: dopisanie postępu do niewłaściwej sprawy wygląda jak poprawna praca.

        Ten sam numer w dwóch prefiksach zdarzy się, gdy tylko Kit obsłuży drugą Organizację.
        """
        k = AtrapaKlienta([_sprawa(12, "FM"), _sprawa(12, "ADVERTPR")])
        with self.assertRaises(ValueError) as p:
            autor.znajdz_sprawe(k, "12")
        self.assertIn("FM-12", str(p.exception))
        self.assertIn("ADVERTPR-12", str(p.exception))

    def test_uuid_nie_kosztuje_pytania_o_liste(self):
        class Zabroniona(AtrapaKlienta):
            def sprawy(self, *, limit=50):
                raise AssertionError("po UUID nie pytamy o listę")

        uuid = "42c50a50-fc93-4a28-89f3-f446ccfe7524"
        self.assertEqual(autor.znajdz_sprawe(Zabroniona([]), uuid)["id"], uuid)

    def test_nieznana_sprawa_mowi_gdzie_szukac(self):
        with self.assertRaises(ValueError) as p:
            autor.znajdz_sprawe(AtrapaKlienta([_sprawa(1)]), "FM-99")
        self.assertIn("sf-kit sprawy", str(p.exception))

    def test_bzdura_zamiast_numeru_nie_jest_brana_za_numer(self):
        with self.assertRaises(ValueError):
            autor.znajdz_sprawe(AtrapaKlienta([]), "makieta gotowa")


class TestSzablonOpisu(unittest.TestCase):

    def test_szkielet_ma_trzy_pytania_odbiorcy(self):
        opis = autor.opis_domyslny("Makieta strony głównej gotowa")
        self.assertIn("**Sedno**", opis)
        self.assertIn("**Co jest**", opis)
        self.assertIn("**Jak odebrać**", opis)
        self.assertIn("Makieta strony głównej gotowa", opis)

    def test_niewypelniony_szkielet_jest_ROZPOZNAWALNY(self):
        """Kit tego nie blokuje, ale ma o tym powiedzieć — inaczej pusty opis idzie dalej."""
        self.assertTrue(autor.czy_opis_wymaga_uzupelnienia(autor.opis_domyslny("X")))

    def test_wypelniony_opis_nie_wywoluje_ostrzezenia(self):
        wlasny = "**Sedno** — gotowe.\n\n**Co jest** — trzy widoki.\n\n**Jak odebrać** — index.html"
        self.assertFalse(autor.czy_opis_wymaga_uzupelnienia(wlasny))

    def test_kropka_z_tytulu_nie_dubluje_sie_w_zdaniu(self):
        self.assertIn("Makieta gotowa.", autor.opis_domyslny("Makieta gotowa."))
        self.assertNotIn("gotowa..", autor.opis_domyslny("Makieta gotowa."))


class TestAdresSprawy(unittest.TestCase):

    def test_adres_sklada_sie_z_biezacej_bazy(self):
        self.assertEqual(
            autor.adres_sprawy("abc", baza="https://sf.dpakula.pl/"),
            "https://sf.dpakula.pl/tickets/abc")


if __name__ == "__main__":
    unittest.main()
