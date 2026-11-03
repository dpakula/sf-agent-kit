"""SF-491: `sf-kit poczta wyslij` — mail z konta Poczty SF (warstwa biblioteki i CLI, bez sieci).

v1.0.0 (04.11.2026) - APro Agents / borys-sf · kontrakt backend/docs/API-POCZTA-WYSLIJ-SF491.md (repo salesforge)

Co pilnujemy: ciało multipart (`dane` = JSON, pliki pod `plik`), `Idempotency-Key` w nagłówku i liczony z TREŚCI
polecenia (powtórka = ten sam klucz, inna treść = inny), `--szkic` → `tryb: szkic`, wątek (`--odpowiedz-na`),
kod wyjścia przy odrzuceniu.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli  # noqa: E402
from sf_kit.api import Klient  # noqa: E402


def _rozbierz(cialo: bytes, typ: str) -> dict:
    """Ciało multipart → {nazwa pola: [(nazwa pliku | None, bajty)]} — sprawdzamy, co naprawdę poszło."""
    granica = typ.split("boundary=")[1].encode()
    wynik: dict = {}
    for czesc in cialo.split(b"--" + granica):
        if b"Content-Disposition" not in czesc:
            continue
        glowa, _, tresc = czesc.partition(b"\r\n\r\n")
        nazwa = glowa.split(b'name="')[1].split(b'"')[0].decode()
        plik = glowa.split(b'filename="')[1].split(b'"')[0].decode() if b"filename=" in glowa else None
        wynik.setdefault(nazwa, []).append((plik, tresc.rstrip(b"\r\n")))
    return wynik


class TestKlientPoczty(unittest.TestCase):

    def test_multipart_dane_pliki_i_klucz(self):
        zapis = {}

        class K(Klient):
            def __init__(self):
                pass

            def _wywolaj_surowo(self, metoda, sciezka, *, dane, typ_tresci, dodatkowe=None):
                zapis.update(metoda=metoda, sciezka=sciezka, dane=dane, typ=typ_tresci, dodatkowe=dodatkowe)
                return {"stan": "wyslana"}

        with tempfile.TemporaryDirectory() as kat:
            p = Path(kat) / "oferta.pdf"
            p.write_bytes(b"%PDF-1.4 oferta")
            K().poczta_wyslij({"konto": "a@b.pl", "temat": "T", "tresc_md": "x"}, [p], klucz_idem="k-1")
        self.assertEqual((zapis["metoda"], zapis["sciezka"]), ("POST", "poczta/wyslij"))
        self.assertEqual(zapis["dodatkowe"], {"Idempotency-Key": "k-1"})
        czesci = _rozbierz(zapis["dane"], zapis["typ"])
        self.assertEqual(json.loads(czesci["dane"][0][1])["konto"], "a@b.pl")
        self.assertEqual(czesci["plik"], [("oferta.pdf", b"%PDF-1.4 oferta")])

    def test_bez_plikow_tez_multipart(self):
        zapis = {}

        class K(Klient):
            def __init__(self):
                pass

            def _wywolaj_surowo(self, metoda, sciezka, *, dane, typ_tresci, dodatkowe=None):
                zapis.update(dane=dane, typ=typ_tresci)
                return {}

        K().poczta_wyslij({"konto": "a@b.pl"}, [], klucz_idem="k")
        self.assertNotIn("plik", _rozbierz(zapis["dane"], zapis["typ"]))


class TestKluczWysylki(unittest.TestCase):

    def test_ta_sama_tresc_ten_sam_klucz_inna_inny(self):
        d = {"konto": "a@b.pl", "do": ["x@y.pl"], "temat": "T", "tresc_md": "x", "tryb": "wyslij"}
        self.assertEqual(cli.klucz_wysylki(d, []), cli.klucz_wysylki(dict(d), []))
        self.assertNotEqual(cli.klucz_wysylki(d, []), cli.klucz_wysylki({**d, "tresc_md": "y"}, []))
        self.assertNotEqual(cli.klucz_wysylki(d, []), cli.klucz_wysylki(d, ["/tmp/inny.pdf"]))


class TestPolecenie(unittest.TestCase):

    def _uruchom(self, argv: list[str], wynik: dict):
        wyslane = {}

        class Atrapa:
            def poczta_wyslij(self, dane, pliki, *, klucz_idem):
                wyslane.update(dane=dane, pliki=pliki, klucz=klucz_idem)
                return wynik

        with tempfile.TemporaryDirectory() as kat:
            md = Path(kat) / "mail.md"
            md.write_text("# Dzień dobry\n\nTreść.", encoding="utf-8")
            argv = [a.replace("MAIL", str(md)) for a in argv]
            with mock.patch.object(cli.konfiguracja, "wczytaj", return_value=mock.Mock(adres="https://sf.test")), \
                 mock.patch.object(cli, "_klient_dla_zapisu", return_value=(Atrapa(), None)), \
                 redirect_stdout(io.StringIO()) as wyjscie:
                kod = cli.main(argv)
        return kod, wyslane, wyjscie.getvalue()

    def test_szkic_i_odpowiedz_w_watku(self):
        kod, w, out = self._uruchom(
            ["poczta", "wyslij", "--konto", "d.pakula@advertpro.co", "--do", "a@x.pl", "--do", "b@x.pl",
             "--temat", "Oferta", "--tresc", "MAIL", "--odpowiedz-na", "11111111-1111-1111-1111-111111111111",
             "--szkic"],
            {"stan": "szkic", "ticket_id": "t-1", "konto": {"adres": "d.pakula@advertpro.co"}, "wersja_nr": 1})
        self.assertEqual(kod, 0)
        self.assertEqual(w["dane"]["tryb"], "szkic")
        self.assertEqual(w["dane"]["do"], ["a@x.pl", "b@x.pl"])
        self.assertEqual(w["dane"]["w_odpowiedzi_do"], "11111111-1111-1111-1111-111111111111")
        self.assertTrue(w["dane"]["tresc_md"].startswith("# Dzień dobry"))
        self.assertTrue(w["klucz"].startswith("sfkit-poczta-"))
        self.assertIn("szkic", out)

    def test_bez_szkicu_wysyla_a_odrzucona_daje_kod_2(self):
        kod, w, out = self._uruchom(
            ["poczta", "wyslij", "--konto", "a@b.pl", "--do", "x@y.pl", "--temat", "T", "--tresc", "MAIL"],
            {"stan": "odrzucona", "ticket_id": "t-2", "konto": {"adres": "a@b.pl"}, "wersja_nr": 1})
        self.assertEqual(w["dane"]["tryb"], "wyslij")
        self.assertEqual(kod, 2)
        self.assertIn("odrzucił", out)


if __name__ == "__main__":
    unittest.main()
