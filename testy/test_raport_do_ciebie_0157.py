"""Kit 0.15.7: `sf-kit raport` (SF-184) i sekcja „Do Ciebie” w `sf-kit sprawa` (SF-182).

v1.0.0 (01.10.2026) - APro Agents / borys-sf

CZEGO PILNUJĄ
· `raport` wysyła `entry_type: report` + `styl`; odmowę 422 SF pokazuje jako listę „linia · blok:
  zdanie” i kończy kodem 1 (nic nie zapisane); SF sprzed SF-184 → jawna rada „wyślij wpisem”.
· Ciało błędu 422 nie jest obcinane do 500 znaków (lista błędów to JSON do sparsowania).
· „Do Ciebie”: bloki do mnie z linkiem do osi (z `?org=`), znacznik innej Organizacji, liczba
  bloków do innych; SF bez trasy → jedno zdanie, nie „nic do Ciebie”; brak czegokolwiek → cisza.
"""
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import api, cli, do_ciebie  # noqa: E402

BAZA = "https://sf.example"


def _blok(**pola):
    b = {"box_id": "b1", "ref": "#1094", "rodzaj": "action", "tresc": "Q1: czy przypinanie z UI?",
         "stan": "open", "adresat": {"user_id": "u1"}, "z_innej_organizacji": True,
         "blok_id": "k1", "link": "/tickets/t1?blok=k1"}
    b.update(pola)
    return b


class SekcjaDoCiebie(unittest.TestCase):
    def test_blok_do_mnie_z_linkiem_i_organizacja(self):
        tekst = do_ciebie.sekcja({"pozycje": [_blok()], "razem": 1},
                                 {"pozycje": [_blok(), _blok(box_id="b2")], "razem": 2},
                                 baza=BAZA, org="sf")
        self.assertIn("Do Ciebie — otwarte bloki konsoli: 1", tekst)
        self.assertIn("[decyzja] #1094 Q1: czy przypinanie z UI?", tekst)
        self.assertIn("z Konsoli A innej Organizacji", tekst)
        self.assertIn(f"{BAZA}/tickets/t1?blok=k1&org=sf", tekst)
        self.assertIn("do innych osób przy tej sprawie: 1", tekst)

    def test_sf_bez_trasy_to_zdanie_a_nie_nic(self):
        tekst = do_ciebie.sekcja(None, None, baza=BAZA, org=None)
        self.assertIn("nie pokazuje jeszcze bloków konsoli", tekst)

    def test_nic_otwartego_to_cisza(self):
        self.assertIsNone(do_ciebie.sekcja({"pozycje": [], "razem": 0}, {"pozycje": [], "razem": 0},
                                           baza=BAZA, org="sf"))

    def test_tylko_do_innych(self):
        tekst = do_ciebie.sekcja({"pozycje": [], "razem": 0}, {"pozycje": [_blok()], "razem": 1},
                                 baza=BAZA, org="sf")
        self.assertIn("otwarte bloki konsoli: 0", tekst)
        self.assertIn("do innych osób przy tej sprawie: 1", tekst)

    def test_dluga_tresc_skrocona_i_jednolinijkowa(self):
        tekst = do_ciebie.sekcja({"pozycje": [_blok(tresc="a\n" * 400)], "razem": 1}, None,
                                 baza=BAZA, org=None)
        linia = [l for l in tekst.splitlines() if "[decyzja]" in l][0]
        # Skracana jest TREŚĆ (≤ DLUGOSC_TRESCI), nie cała linia: prefiks i dopisek źródła dochodzą.
        tresc = linia.split("#1094 ", 1)[1].split(" · z Konsoli A", 1)[0]
        self.assertLessEqual(len(tresc), do_ciebie.DLUGOSC_TRESCI)
        self.assertTrue(tresc.endswith("…"))
        self.assertNotIn("\n", tresc)


class BlokiKonsoliApi(unittest.TestCase):
    def _klient(self):
        return api.Klient(baza=BAZA, klucz="sk_test", organizacja="org")

    def test_trasa_nieznana_to_none(self):
        k = self._klient()
        blad = api.BladAPI("404", kod=404, szczegoly='{"detail":"Not Found"}')
        with mock.patch.object(k, "_wywolaj", side_effect=blad):
            self.assertIsNone(k.bloki_konsoli("t1"))

    def test_inny_404_leci_dalej(self):
        k = self._klient()
        blad = api.BladAPI("404", kod=404, szczegoly='{"detail":"Nie ma takiej sprawy"}')
        with mock.patch.object(k, "_wywolaj", side_effect=blad):
            with self.assertRaises(api.BladAPI):
                k.bloki_konsoli("t1")

    def test_parametry(self):
        k = self._klient()
        with mock.patch.object(k, "_wywolaj", return_value={"pozycje": []}) as w:
            k.bloki_konsoli("t1", do_mnie=True)
        self.assertEqual(w.call_args[0], ("GET", "tickets/t1/bloki-konsoli?status=open&do_mnie=true"))

    def test_raport_wysyla_typ_i_styl(self):
        k = self._klient()
        with mock.patch.object(k, "_wywolaj", return_value={}) as w:
            k.raport("t1", "# SITREP", styl="sitrep")
        self.assertEqual(w.call_args.kwargs["cialo"],
                         {"entry_type": "report", "styl": "sitrep", "content": "# SITREP",
                          "visibility": "internal"})


class LimitTresciBledu(unittest.TestCase):
    def test_422_nie_obciete_do_500(self):
        self.assertGreater(api._limit_tresci_bledu(422), 4000)
        self.assertEqual(api._limit_tresci_bledu(500), api.LIMIT_TRESCI_BLEDU)

    def test_bledy_raportu(self):
        cialo = json.dumps({"detail": "Raport: 1 błąd", "bledy": [{"blok": "kpi", "linia": 7, "komunikat": "x"}]})
        self.assertEqual(api.bledy_raportu(SimpleNamespace(szczegoly=cialo))[0]["linia"], 7)
        self.assertEqual(api.bledy_raportu(SimpleNamespace(szczegoly="nie json")), [])
        self.assertEqual(api.bledy_raportu(SimpleNamespace(szczegoly='{"detail":"x"}')), [])


class PolecenieRaport(unittest.TestCase):
    def _uruchom(self, plik: Path, klient):
        args = SimpleNamespace(sprawa="SF-184", plik=str(plik), styl="sitrep", widocznosc="internal",
                               org="sf")
        wyj, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli.konfiguracja, "wczytaj", return_value=SimpleNamespace(adres=BAZA)), \
                mock.patch.object(cli, "_klient_dla_zapisu", return_value=(klient, None)), \
                mock.patch.object(cli, "_sprawa_dla_zapisu", return_value=({"id": "t1"}, None)), \
                mock.patch.object(cli, "_ostrzez_o_szkicu"), \
                mock.patch.object(cli, "_pokaz_sprawe"), \
                mock.patch.object(cli.asystent, "numer_sprawy", return_value="SF-184"), \
                redirect_stdout(wyj), redirect_stderr(err):
            kod = cli.polecenie_raport(args)
        return kod, wyj.getvalue(), err.getvalue()

    def setUp(self):
        import tempfile
        self.katalog = tempfile.TemporaryDirectory()
        self.plik = Path(self.katalog.name) / "sitrep.md"
        self.plik.write_text("# SITREP\n```kpi\nw pracy: 4\n```\n", encoding="utf-8")

    def tearDown(self):
        self.katalog.cleanup()

    def test_sukces(self):
        klient = mock.Mock()
        kod, _, _ = self._uruchom(self.plik, klient)
        self.assertEqual(kod, 0)
        klient.raport.assert_called_once()
        self.assertEqual(klient.raport.call_args.kwargs["styl"], "sitrep")

    def test_odmowa_422_lista_bledow(self):
        klient = mock.Mock()
        klient.raport.side_effect = api.BladAPI("422", kod=422, szczegoly=json.dumps({
            "detail": "Raport: 2 błędy", "bledy": [
                {"blok": "kpi", "linia": 7, "komunikat": "brak dwukropka"},
                {"linia": 1, "komunikat": "znaczniki HTML są w raporcie niedozwolone"}]}))
        kod, _, err = self._uruchom(self.plik, klient)
        self.assertEqual(kod, 1)
        self.assertIn("2 błędy", err)
        self.assertIn("linia 7 · blok kpi: brak dwukropka", err)
        self.assertIn("linia 1: znaczniki HTML", err)
        self.assertIn("nic nie zostało zapisane", err)

    def test_sf_bez_raportow_rada(self):
        klient = mock.Mock()
        klient.raport.side_effect = api.BladAPI("422", kod=422, szczegoly=json.dumps({
            "detail": [{"loc": ["body", "entry_type"], "msg": "Input should be 'created', …"}]}))
        kod, _, err = self._uruchom(self.plik, klient)
        self.assertEqual(kod, 1)
        self.assertIn("nie przyjmuje jeszcze raportów", err)

    def test_pusty_plik(self):
        self.plik.write_text("  \n", encoding="utf-8")
        kod, _, err = self._uruchom(self.plik, mock.Mock())
        self.assertEqual(kod, 2)
        self.assertIn("bez treści", err)


class OdpowiedzNaBlok(unittest.TestCase):
    """`sf-kit odpowiedz <sprawa> --blok #1094` (SF-185)."""

    def _uruchom(self, klient, blok="#1094", wewn=False):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("Decyzja: tak")
        args = SimpleNamespace(sprawa="https://sf.example/tickets/t1?org=sf", opis=f.name, wewn=wewn,
                               blok=blok, org=None)
        wyj, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli.konfiguracja, "wczytaj", return_value=SimpleNamespace(adres=BAZA)), \
                mock.patch.object(cli, "_klient_dla_zapisu", return_value=(klient, None)), \
                mock.patch.object(cli, "_sprawa_dla_zapisu", return_value=({"id": "t1"}, None)), \
                mock.patch.object(cli, "_ostrzez_o_szkicu"), mock.patch.object(cli, "_pokaz_sprawe"), \
                redirect_stdout(wyj), redirect_stderr(err):
            kod = cli.polecenie_odpowiedz(args)
        Path(f.name).unlink()
        return kod, wyj.getvalue(), err.getvalue()

    def test_numer_rozwiazany_i_odpowiedz_wyslana(self):
        klient = mock.Mock()
        klient.bloki_konsoli.return_value = {"pozycje": [_blok(), _blok(box_id="b2", ref="#7")]}
        klient.odpowiedz_na_blok.return_value = {"ok": True, "status": "answered"}
        kod, wyj, _ = self._uruchom(klient)
        self.assertEqual(kod, 0)
        klient.odpowiedz_na_blok.assert_called_once_with("t1", "b1", "Decyzja: tak")
        self.assertIn("answered", wyj)
        klient.wpis.assert_not_called()                    # nie zwykły wpis

    def test_brak_jednego_bloku(self):
        klient = mock.Mock()
        klient.bloki_konsoli.return_value = {"pozycje": [_blok(ref="#7")]}
        kod, _, err = self._uruchom(klient)
        self.assertEqual(kod, 1)
        self.assertIn("Nie znajduję jednego bloku", err)
        klient.odpowiedz_na_blok.assert_not_called()

    def test_404_mowi_po_ludzku(self):
        klient = mock.Mock()
        klient.bloki_konsoli.return_value = {"pozycje": [_blok()]}
        klient.odpowiedz_na_blok.side_effect = api.BladAPI("404", kod=404, szczegoly='{"detail":"x"}')
        kod, _, err = self._uruchom(klient)
        self.assertEqual(kod, 1)
        self.assertIn("Nie ma takiego bloku", err)

    def test_wewn_z_blokiem_to_blad_uzycia(self):
        kod, _, err = self._uruchom(mock.Mock(), wewn=True)
        self.assertEqual(kod, 2)
        self.assertIn("--wewn", err)


if __name__ == "__main__":
    unittest.main()
