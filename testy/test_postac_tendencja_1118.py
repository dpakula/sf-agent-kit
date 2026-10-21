"""Ekran statusu (/mood): tendencja presji D i A z `wskazniki.py --json` 3.4 (ADVERTPR-1118) — Kit tylko rysuje.

v0.1 (21.10.2026) - APro Agents / klaudiusz-general

CZEGO TU PILNUJĘ
════════════════
1. Strzałka tendencji przy pasku presji (D i A), jak przy HP.
2. W rozbiciu linia z deltą 3 h i 24 h w pp (brak próbki → „n/d”).
3. Stary wynik bez `tendencja` rysuje się jak dotąd (bez strzałki, bez linii).

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_postac_1075 import dane, ekran  # noqa: E402

TD = {"kierunek": "rosnie", "strzalka": "↑", "delta_pp": 16.7, "podstawa": "3h",
      "porownania": {"3h": {"delta_pp": 16.7, "wtedy": 10.0, "ts": "2026-10-21T09:00:00+00:00"}, "24h": None}}
TA = {"kierunek": "maleje", "strzalka": "↓", "delta_pp": -100.0, "podstawa": "24h",
      "porownania": {"3h": {"delta_pp": -2.0, "wtedy": 202.0, "ts": "2026-10-21T09:00:00+00:00"},
                     "24h": {"delta_pp": -100.0, "wtedy": 300.0, "ts": "2026-10-20T12:00:00+00:00"}}}


def z_tendencja():
    d = dane()
    for kto, t in (("damian", TD), ("agent", TA)):
        d["presja"][kto]["tendencja"] = t
        d["presja"][kto]["wglad"]["tendencja"] = t
    return d


class TendencjaPresji(unittest.TestCase):
    def test_strzalka_przy_pasku_damiana(self):
        linia = next(l for l in ekran(z_tendencja(), rozbicie=False).splitlines() if "PRESJA D" in l)
        self.assertIn("100%+  ↑ 102 dni · czerwony", linia)

    def test_strzalka_przy_pasku_agaty(self):
        linia = next(l for l in ekran(z_tendencja(), kto="agata", rozbicie=False).splitlines() if "PRESJA A" in l)
        self.assertIn("↓ 1,2 dni · pomarańczowy", linia)

    def test_delta_w_rozbiciu(self):
        t = ekran(z_tendencja())
        self.assertIn("· ↑ rośnie: 3h +16,7 pp (z 10 %) · 24h n/d", t)
        t = ekran(z_tendencja(), kto="agata")
        self.assertIn("· ↓ maleje: 3h −2 pp (z 202 %) · 24h −100 pp (z 300 %)", t)

    def test_bez_tendencji_jak_dotad(self):
        t = ekran()
        self.assertNotIn("rośnie:", t)
        linia = next(l for l in ekran(rozbicie=False).splitlines() if "PRESJA D" in l)
        self.assertNotIn("↑", linia)


if __name__ == "__main__":
    unittest.main()
