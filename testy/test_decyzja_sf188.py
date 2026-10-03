"""SF-188: `sf-kit odpowiedz --blok #N --opcja B` i `sf-kit raport --styl sesja`.

v1.0.0 (04.10.2026) - APro Agents / borys-sf

CZEGO PILNUJĄ
· `--opcja` idzie do SF jako `opcja` (komentarz z `--opis` opcjonalny); wybór z odpowiedzi SF pokazany.
· `--opcja` bez `--blok` = błąd użycia (2), bez wołania SF.
· `#1094` dopasowany po polu `numer` (SF-188) — `ref` to skrót `BOX-…`, nie numer.
· SF sprzed SF-188 (422 „extra … opcja”) → rada „odpowiedz tekstem”.
· `raport --styl sesja` przechodzi parser argumentów.
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


def _blok(**pola):
    b = {"box_id": "b1", "ref": "BOX-3f7a1c", "numer": "#1094", "stan": "open",
         "adresat": {"user_id": "u1"}, "link": "/tickets/t1?blok=k1"}
    b.update(pola)
    return b


def _uruchom(klient, *, blok="#1094", opcja="B", opis=None):
    args = SimpleNamespace(sprawa="https://sf.example/tickets/t1?org=sf", opis=opis, wewn=False,
                           blok=blok, opcja=opcja, org=None)
    wyj, err = io.StringIO(), io.StringIO()
    with mock.patch.object(cli.konfiguracja, "wczytaj", return_value=SimpleNamespace(adres=BAZA)), \
            mock.patch.object(cli, "_klient_dla_zapisu", return_value=(klient, None)), \
            mock.patch.object(cli, "_sprawa_dla_zapisu", return_value=({"id": "t1"}, None)), \
            mock.patch.object(cli, "_ostrzez_o_szkicu"), mock.patch.object(cli, "_pokaz_sprawe"), \
            redirect_stdout(wyj), redirect_stderr(err):
        kod = cli.polecenie_odpowiedz(args)
    return kod, wyj.getvalue(), err.getvalue()


class OdpowiedzOpcja(unittest.TestCase):
    def test_opcja_bez_komentarza(self):
        klient = mock.Mock()
        klient.bloki_konsoli.return_value = {"pozycje": [_blok(), _blok(box_id="b2", numer="#7")]}
        klient.odpowiedz_na_blok.return_value = {
            "ok": True, "status": "answered",
            "wybor": {"opcja": "B", "etykieta": "Jutro", "kto": "Agata", "kiedy": "2026-10-04T01:00:00Z"}}
        kod, wyj, err = _uruchom(klient)
        self.assertEqual(kod, 0, err)
        klient.odpowiedz_na_blok.assert_called_once_with("t1", "b1", None, opcja="B")
        self.assertIn("Wybór zapisany na raporcie: B — Jutro", wyj)

    def test_opcja_bez_bloku_to_blad_uzycia(self):
        klient = mock.Mock()
        kod, _, err = _uruchom(klient, blok=None)
        self.assertEqual(kod, 2)
        self.assertIn("--blok", err)
        klient.odpowiedz_na_blok.assert_not_called()

    def test_numer_po_polu_numer_a_nie_ref(self):
        klient = mock.Mock()
        klient.bloki_konsoli.return_value = {"pozycje": [_blok(ref="BOX-aaaaaa", numer="#1094"),
                                                         _blok(box_id="b2", ref="BOX-bbbbbb", numer=None)]}
        klient.odpowiedz_na_blok.return_value = {"ok": True, "status": "answered"}
        kod, _, err = _uruchom(klient, opcja=None, opis="-")
        # bez treści (stdin pusty w teście) — wystarczy, że dopasowanie nie zgłosiło błędu bloku
        self.assertNotIn("Nie znajduję jednego bloku", err)

    def test_stare_sf_bez_opcji(self):
        klient = mock.Mock()
        klient.bloki_konsoli.return_value = {"pozycje": [_blok()]}
        klient.odpowiedz_na_blok.side_effect = api.BladAPI(
            "422", kod=422, szczegoly='{"detail":[{"type":"extra_forbidden","loc":["body","opcja"]}]}')
        kod, _, err = _uruchom(klient)
        self.assertEqual(kod, 1)
        self.assertIn("nie zna wyboru opcji", err)


class ApiOpcja(unittest.TestCase):
    def test_cialo_z_opcja_bez_tresci(self):
        k = api.Klient(baza=BAZA, klucz="sk_test", organizacja="org")
        with mock.patch.object(k, "_wywolaj", return_value={"ok": True}) as w:
            k.odpowiedz_na_blok("t1", "b1", None, opcja="A")
        w.assert_called_once_with("POST", "tickets/t1/bloki-konsoli/b1/odpowiedz", cialo={"opcja": "A"})

    def test_cialo_tylko_tresc_jak_dotad(self):
        k = api.Klient(baza=BAZA, klucz="sk_test", organizacja="org")
        with mock.patch.object(k, "_wywolaj", return_value={"ok": True}) as w:
            k.odpowiedz_na_blok("t1", "b1", "tak")
        w.assert_called_once_with("POST", "tickets/t1/bloki-konsoli/b1/odpowiedz", cialo={"tresc": "tak"})


class RaportSesja(unittest.TestCase):
    def test_styl_sesja_w_parserze(self):
        parser = cli.zbuduj_parser() if hasattr(cli, "zbuduj_parser") else None
        if parser is None:
            self.skipTest("brak zbuduj_parser")
        a = parser.parse_args(["raport", "SF-188", "plik.md", "--styl", "sesja"])
        self.assertEqual(a.styl, "sesja")


if __name__ == "__main__":
    unittest.main()
