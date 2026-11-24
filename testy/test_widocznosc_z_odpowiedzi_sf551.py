"""SF-551: Kit mówi, jaki poziom ZAPISAŁ serwer, a nie jaki był w argumencie.

v1.0.0 (18.11.2026) - APro Agents / borys-sf

Do 0.20.2 `sf-kit wpis-widocznosc … internal` drukował „✓ konsola → internal”, choć SF zostawiał `konsola`
(reguła serwera SF-449 cz. 5: wpis konta floty w Organizacji klienta, niepubliczny, zawsze `konsola`).
CZEGO PILNUJĄ
· `wpis-widocznosc`: rozjazd odpowiedzi z prośbą = „✗ …”, ostrzeżenie z wyjaśnieniem, kod 3; zgodnie = „✓”, kod 0;
  SF bez pola `visibility` (starszy serwer) = jak dotąd „✓”.
· `rozjazd_poziomu`: `external` = `public`; wyjaśnienie reguły floty tylko przy `konsola`.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import argparse
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli  # noqa: E402


def uruchom(funkcja, args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        kod = funkcja(args)
    return kod, out.getvalue(), err.getvalue()


class TestRozjazd(unittest.TestCase):
    def test_zgodnie_albo_brak_pola(self):
        self.assertIsNone(cli.rozjazd_poziomu("internal", {"visibility": "internal"}))
        self.assertIsNone(cli.rozjazd_poziomu("external", {"visibility": "public"}))
        self.assertIsNone(cli.rozjazd_poziomu("internal", {"id": "x"}))
        self.assertIsNone(cli.rozjazd_poziomu("internal", None))

    def test_konsola_z_wyjasnieniem_reguly(self):
        t = cli.rozjazd_poziomu("internal", {"visibility": "konsola"})
        self.assertIn("„konsola”, nie „internal”", t)
        self.assertIn("SF-449", t)
        self.assertIn("zwykły członek", t)
        self.assertNotIn("SF-449", cli.rozjazd_poziomu("team", {"visibility": "internal"}))


class TestWpisWidocznosc(unittest.TestCase):
    def _uruchom(self, odpowiedz, poziom="internal", obecny="konsola"):
        klient = mock.Mock()
        klient.zmien_widocznosc.return_value = odpowiedz
        args = argparse.Namespace(sprawa="SECO-286", wpis="2ee41e5f", poziom=poziom, powod=None)
        with mock.patch.object(cli.konfiguracja, "wczytaj", return_value=mock.Mock()), \
                mock.patch.object(cli, "_klient_dla_zapisu", return_value=(klient, None)), \
                mock.patch.object(cli, "_sprawa_dla_zapisu", return_value=({"id": "s1"}, None)), \
                mock.patch.object(cli, "_id_na_osi", return_value=("t1", obecny)):
            return uruchom(cli.polecenie_wpis_widocznosc, args)

    def test_serwer_zostawil_konsole_to_nie_sukces(self):
        kod, out, err = self._uruchom({"id": "t1", "visibility": "konsola"})
        self.assertEqual(kod, 3)
        self.assertIn("✗ widoczność wpisu: konsola → konsola (bez zmiany)", out)
        self.assertNotIn("✓", out)
        self.assertIn("UWAGA", err)

    def test_zgodnie_to_sukces(self):
        kod, out, _ = self._uruchom({"id": "t1", "visibility": "internal"}, obecny="team")
        self.assertEqual(kod, 0)
        self.assertIn("✓ widoczność wpisu: team → internal", out)

    def test_starszy_serwer_bez_pola(self):
        kod, out, _ = self._uruchom({}, obecny="team")
        self.assertEqual((kod, "✓" in out), (0, True))


if __name__ == "__main__":
    unittest.main()
