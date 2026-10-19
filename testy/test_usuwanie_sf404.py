"""`sf-kit wpis-usun` / `zalacznik-usun` — usuwanie z adnotacją (SF-404).

v1.0.0 (19.10.2026) - APro Agents / borys-sf

Powód obowiązkowy już w Kicie (SF też go wymaga — 422), ciało = `{"powod"}` jak w `EntryDeleteRequest`,
odmowy z komunikatem „co zrobić” (403 kto może, 405 serwer bez SF-404, 409 ślad audytowy).

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli  # noqa: E402
from sf_kit import config as konfiguracja  # noqa: E402
from sf_kit.api import BladAPI, BrakUprawnienia, Klient  # noqa: E402

A = "aaaaaaaa-0000-4000-8000-000000000001"
Z = "zzzzzzzz-0000-4000-8000-000000000009"


class _Atrapa:
    def __init__(self, *, odp=None, blad=None):
        self.odp, self.blad, self.wyslane = odp or {}, blad, None

    def sprawy(self, *, limit=50, szukaj=None):
        return [{"id": "sprawa-1", "ticket_number": 220, "ticket_prefix": "SECO"}]

    def wpisy_sprawy(self, ticket_id, *, limit=100, offset=0):
        return {"pozycje": [{"id": A}] if offset == 0 else []}

    def usun_wpis(self, ticket_id, entry_id, powod):
        self.wyslane = ("wpis", ticket_id, entry_id, powod)
        if self.blad:
            raise self.blad
        return self.odp

    def usun_zalacznik(self, attachment_id, powod):
        self.wyslane = ("zalacznik", attachment_id, powod)
        if self.blad:
            raise self.blad
        return self.odp


class TestUsuwanie(unittest.TestCase):

    def setUp(self):
        self._stare = (konfiguracja.wczytaj, cli._klient)
        konfiguracja.wczytaj = lambda: konfiguracja.Konfiguracja(adres="https://x")

    def tearDown(self):
        konfiguracja.wczytaj, cli._klient = self._stare

    def _uruchom(self, argv, klient):
        cli._klient = lambda *_a, **_k: klient
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            kod = cli.main(argv)
        return kod, out.getvalue(), err.getvalue()

    def test_wpis_usun_wysyla_powod_i_mowi_co_stoi_na_osi(self):
        k = _Atrapa(odp={"kto": "api:k-seco", "juz_wczesniej": False})
        kod, out, _ = self._uruchom(["wpis-usun", "SECO-220", "aaaaaaaa", "--powod", "pusty wpis po HTML"], k)
        self.assertEqual(kod, 0)
        self.assertEqual(k.wyslane, ("wpis", "sprawa-1", A, "pusty wpis po HTML"))
        self.assertIn("usunięte przez api:k-seco — pusty wpis po HTML", out)

    def test_bez_powodu_nie_wysyla(self):
        k = _Atrapa()
        kod, _, err = self._uruchom(["wpis-usun", "SECO-220", "aaaaaaaa", "--powod", " x "], k)
        self.assertEqual(kod, 2)
        self.assertIsNone(k.wyslane)
        self.assertIn("powód", err)

    def test_drugi_raz_mowi_ze_juz_byl(self):
        k = _Atrapa(odp={"juz_wczesniej": True, "kiedy": "2026-10-19T07:30:00Z", "powod": "duplikat"})
        kod, out, _ = self._uruchom(["wpis-usun", "SECO-220", "aaaaaaaa", "--powod", "duplikat"], k)
        self.assertEqual(kod, 0)
        self.assertIn("był już usunięty", out)

    def test_403_mowi_kto_moze(self):
        blad = BrakUprawnienia("403", kod=403, szczegoly='{"detail":"Wpis usuwa superadmin…"}')
        kod, _, err = self._uruchom(["wpis-usun", "SECO-220", "aaaaaaaa", "--powod", "duplikat"], _Atrapa(blad=blad))
        self.assertEqual(kod, 1)
        self.assertIn("entries:delete", err)

    def test_zalacznik_405_to_stary_serwer(self):
        blad = BladAPI("405", kod=405, szczegoly='{"detail":"Method Not Allowed"}')
        kod, _, err = self._uruchom(["zalacznik-usun", Z, "--powod", "zły plik"], _Atrapa(blad=blad))
        self.assertEqual(kod, 1)
        self.assertIn("SF-404", err)

    def test_zalacznik_usun_wysyla_powod(self):
        k = _Atrapa(odp={"kto": "agata", "juz_wczesniej": False})
        kod, out, _ = self._uruchom(["zalacznik-usun", Z, "--powod", "zły plik"], k)
        self.assertEqual(kod, 0)
        self.assertEqual(k.wyslane, ("zalacznik", Z, "zły plik"))

    def test_klient_wola_delete_z_cialem_powodu(self):
        wolania = []
        kl = Klient.__new__(Klient)
        kl._wywolaj = lambda metoda, sciezka, cialo=None: wolania.append((metoda, sciezka, cialo)) or {}
        kl.usun_wpis("t", "e", "p")
        kl.usun_zalacznik("z", "p")
        self.assertEqual(wolania, [("DELETE", "tickets/t/entries/e", {"powod": "p"}),
                                   ("DELETE", "tickets/attachments/z", {"powod": "p"})])


if __name__ == "__main__":
    unittest.main()
