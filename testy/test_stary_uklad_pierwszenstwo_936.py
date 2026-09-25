"""Stary układ ma pierwszeństwo przed JEDYNYM nowym agentem (ADVERTPR-936, wariant B, 26.09).

Usterka: `~/.config/sf-kit/config.json` (np. Kodeks, worker bez `--agent`) + pierwszy agent
w podkatalogu → każde uruchomienie bez flagi brało podkatalog, czyli cudzy klucz i Organizację.
Teraz bez flagi wygrywa stary układ (z jednym ostrzeżeniem), a nowy agent wymaga `--agent`.
"""
import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sf_kit import klucz  # noqa: E402
from test_wielu_agentow import _Swiat  # noqa: E402


class StaryUkladPierwszenstwo(unittest.TestCase):
    def setUp(self):
        klucz._ostrzezono_o_starym = False

    def _sciezka(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            sciezka = klucz.sciezka_konfiguracji()
        return sciezka, err.getvalue()

    def test_bez_flagi_stary_uklad_i_ostrzezenie(self):
        with _Swiat(agenci=("nowy",), stary_uklad=True) as s:
            sciezka, err = self._sciezka()
            self.assertEqual(sciezka, s.korzen)
            self.assertIn("--agent nowy", err)
            self.assertIn("sprzed podziału", err)

    def test_ostrzezenie_raz_na_uruchomienie(self):
        with _Swiat(agenci=("nowy",), stary_uklad=True):
            self._sciezka()
            _, drugi = self._sciezka()
            self.assertEqual(drugi, "")

    def test_z_flaga_nowy_agent(self):
        with _Swiat(agenci=("nowy",), stary_uklad=True) as s:
            klucz.ustaw_agenta("nowy")
            sciezka, err = self._sciezka()
            self.assertEqual(sciezka, s.korzen / "nowy")
            self.assertEqual(err, "")

    def test_dwoch_nowych_i_stary_dalej_odmowa(self):
        with _Swiat(agenci=("a", "b"), stary_uklad=True):
            with self.assertRaises(klucz.WieluAgentow):
                klucz.sciezka_konfiguracji()

    def test_sam_jeden_nowy_bez_zmian(self):
        with _Swiat(agenci=("nowy",)) as s:
            sciezka, err = self._sciezka()
            self.assertEqual(sciezka, s.korzen / "nowy")
            self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
