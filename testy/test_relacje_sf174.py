"""SF-174 w Kicie: `sf-kit relacje`, `przypnij`, `odepnij` — sprawa w sprawie.

v1.0.0 (04.10.2026) - APro Agents / borys-sf

CZEGO PILNUJĄ
· `przypnij A B` = A ZAWIERA B: POST na A z `sprawa_id` B; 409 → „już przypięta”, kod 1.
· `odepnij A B` szuka AKTYWNEJ relacji z B po obu stronach (zawiera / jest częścią) i wysyła DELETE
  z identyfikatorem relacji; brak relacji → kod 1 bez DELETE.
· `relacje` pokazuje obie listy; sprawa poza wglądem bez tytułu (istnienie nie wycieka).
· API: trasy i ciało zgodne z kontraktem 8f4a2b4d.
"""
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import api, cli  # noqa: E402

BAZA = "https://sf.example"


def _rel(sid, numer, *, kierunek="zawiera", aktywna=True, widoczna=True, rid="r1"):
    r = {"relacja_id": rid, "rodzaj": "czesc", "kierunek": kierunek, "aktywna": aktywna, "widoczna": widoczna}
    if widoczna:
        r["sprawa"] = {"id": sid, "numer": numer, "tytul": f"Sprawa {numer}", "status": "new"}
    return r


def _uruchom(funkcja, klient, **pola):
    args = SimpleNamespace(org="sf", historia=False, **pola)
    sprawy = {"SF-1": {"id": "s1"}, "SF-2": {"id": "s2"}}
    wyj, err = io.StringIO(), io.StringIO()
    with mock.patch.object(cli.konfiguracja, "wczytaj", return_value=SimpleNamespace(adres=BAZA)), \
            mock.patch.object(cli, "_klient_dla_zapisu", return_value=(klient, None)), \
            mock.patch.object(cli, "_klient", return_value=klient), \
            mock.patch.object(cli, "_sprawa_dla_zapisu", side_effect=lambda k, w: (sprawy[w], "")), \
            redirect_stdout(wyj), redirect_stderr(err):
        kod = funkcja(args)
    return kod, wyj.getvalue(), err.getvalue()


class Przypnij(unittest.TestCase):
    def test_a_zawiera_b(self):
        k = mock.Mock()
        k.przypnij_czesc.return_value = _rel("s2", "SF-2")
        kod, wyj, _ = _uruchom(cli.polecenie_przypnij, k, sprawa="SF-1", czesc="SF-2")
        self.assertEqual(kod, 0)
        k.przypnij_czesc.assert_called_once_with("s1", "s2")
        self.assertIn("SF-2", wyj)

    def test_409_juz_przypieta(self):
        k = mock.Mock()
        k.przypnij_czesc.side_effect = api.BladAPI("409", kod=409, szczegoly="{}")
        kod, _, err = _uruchom(cli.polecenie_przypnij, k, sprawa="SF-1", czesc="SF-2")
        self.assertEqual(kod, 1)
        self.assertIn("już przypięta", err)


class Odepnij(unittest.TestCase):
    def test_szuka_po_obu_stronach_i_odpina(self):
        k = mock.Mock()
        k.relacje_sprawy.return_value = {"zawiera": [], "czesc": [_rel("s2", "SF-2", kierunek="czesc", rid="r9")]}
        k.odepnij_relacje.return_value = {}
        kod, wyj, _ = _uruchom(cli.polecenie_odepnij, k, sprawa="SF-1", druga="SF-2")
        self.assertEqual(kod, 0)
        k.odepnij_relacje.assert_called_once_with("s1", "r9")

    def test_brak_aktywnej_relacji(self):
        k = mock.Mock()
        k.relacje_sprawy.return_value = {"zawiera": [_rel("s2", "SF-2", aktywna=False)], "czesc": []}
        kod, _, err = _uruchom(cli.polecenie_odepnij, k, sprawa="SF-1", druga="SF-2")
        self.assertEqual(kod, 1)
        k.odepnij_relacje.assert_not_called()
        self.assertIn("nie są przypięte", err)


class Lista(unittest.TestCase):
    def test_obie_listy_i_niewidoczna_bez_tytulu(self):
        k = mock.Mock()
        k.relacje_sprawy.return_value = {
            "zawiera": [_rel("s2", "SF-2")],
            "czesc": [{"relacja_id": "r2", "kierunek": "czesc", "aktywna": True, "widoczna": False}],
            "liczniki": {"zawiera": 1, "czesc": 0}}
        kod, wyj, _ = _uruchom(cli.polecenie_relacje, k, sprawa="SF-1")
        self.assertEqual(kod, 0)
        self.assertIn("Zawiera (1)", wyj)
        self.assertIn("Sprawa SF-2", wyj)
        self.assertIn("poza Twoim wglądem", wyj)


class Api(unittest.TestCase):
    def _k(self):
        return api.Klient(baza=BAZA, klucz="sk_test", organizacja="org")

    def test_trasy(self):
        k = self._k()
        with mock.patch.object(k, "_wywolaj", return_value={}) as w:
            k.przypnij_czesc("a", "b")
            k.odepnij_relacje("a", "r")
            k.relacje_sprawy("a", historia=True)
        self.assertEqual(w.call_args_list, [
            mock.call("POST", "tickets/a/relacje", cialo={"rodzaj": "czesc", "sprawa_id": "b"}),
            mock.call("DELETE", "tickets/a/relacje/r"),
            mock.call("GET", "tickets/a/relacje?historia=true")])

    def test_parser(self):
        a = cli.zbuduj_parser().parse_args(["przypnij", "SF-1", "SF-2"])
        self.assertEqual((a.sprawa, a.czesc), ("SF-1", "SF-2"))


if __name__ == "__main__":
    unittest.main()
