"""Ekran statusu zwięzły (v0.5, ADVERTPR-1075 / 1167): domyślny `sf-kit status` ≤ 12 linii.

v0.1 (03.11.2026) - APro Agents / klaudiusz-general

CZEGO TU PILNUJĘ (Damian 02.11: „nieczytelny, cały niebieski, za dużo tekstu, cały ekran; nikt przez to nie przebrnie”)
═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
1. **≤ 12 linii**: nagłówek, 4 paski w stałej kolejności, pod KAŻDYM jedna linia „powód → co zrobić”, stopka z wersją.
2. **Kolor tylko na pasku (kolor POZIOMU) i strzałce** — linie tekstu w kolorze terminala.
3. **Presja > 999 % = „> 10× pojemności”**, nie „3218 %”.
4. **Doba w toku = „doba otwarta od …”**, nie data ostatniej zamkniętej.
5. **`--pelny`** = dawny ekran z rozbiciem; tam HP z tempem v7 pokazuje „od DD.MM HH:00 (N h)”, nie „od None dób”.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sf_kit import cli, postac  # noqa: E402
from test_postac_1075 import dane  # noqa: E402

ANSI = re.compile(r"\033\[[0-9;]*m")


def dane_v8():
    d = dane(manifest=8)
    d["hp"].update({"procent": 92, "poziom": "zielony", "data": "2026-11-01", "alarm": False,
                    "doba_otwarta_od": "2026-11-02T06:00",
                    "tendencja": {"pkt_h": 0.5, "na_dobe": 12, "znak": 1, "kierunek": "rosnie", "strzalka": "↗",
                                  "ocena": "dobrze", "od": "2026-10-28T06:00", "od_godzin": 138,
                                  "opis": "↗ +12/dobę — urlop"},
                    "slad_damiana": {"sesje": 1.63, "w_drodze": 1.0, "sf": 0.97}})
    d["hp"]["wglad"].update({"tryb_doby": "urlop", "alarm": None, "trend": d["hp"]["tendencja"],
                             "skladowe": [{"nazwa": "urlop (regeneracja)", "punkty": 12}],
                             "podpowiedzi": ["tempo teraz ↗ +12/dobę — urlop (od 28.10 06:00, 138 h) — manifest § 5b",
                                             "urlop dziś: Damian 1,63 h sesji pracy → pełny urlop",
                                             "zamknięcie doby (/sleep) przed 00:00 = +15"]})
    return d


def zwiezly(d=None, **kw):
    kw.setdefault("kolor", "nigdy")
    return postac.ekran(kto=kw.pop("kto", None), dane=d or dane_v8(), **kw)


class Zwiezly(unittest.TestCase):
    def test_do_12_linii_4_paski_i_linia_pod_kazdym(self):
        t = zwiezly().splitlines()
        self.assertLessEqual(len(t), 12, "\n".join(t))
        etykiety = [i for i, x in enumerate(t) if re.search(r"(MANA|ENERGIA|PRESJA D|ZDROWIE) +\[", x)]
        self.assertEqual(len(etykiety), 4)
        for i in etykiety:
            self.assertIn("→", t[i + 1], t[i + 1])
        self.assertIn("manifest v8", t[-1])
        self.assertIn("--pelny", t[-1])
        self.assertNotIn("rozbicie składowych", "\n".join(t))

    def test_powod_to_najciezsza_skladowa_i_jej_podpowiedz(self):
        t = zwiezly()
        self.assertIn("przerost dokumentów −3 pola (CLAUDE.md 8,6/6 KB) → odchudzić o 2,6 KB = +1 pole (+17 %)", t)
        self.assertIn("urlop · 1,63 h sesji + 1 h w drodze → zamknięcie doby (/sleep) przed 00:00 = +15", t)

    def test_presja_ponad_999_jako_wielokrotnosc(self):
        t = zwiezly()
        self.assertIn("> 10× pojemności", t)
        self.assertNotIn("3401 %", t)

    def test_doba_otwarta(self):
        t = zwiezly()
        self.assertIn("doba otwarta od 02.11 06:00", t)
        self.assertNotIn("doba 01.11", t)

    def test_kolor_tylko_pasek_i_strzalka(self):
        t = zwiezly(kolor="zawsze").splitlines()
        hp = next(x for x in t if "ZDROWIE" in x)
        self.assertIn(postac.KOLOR_POZIOMU["zielony"] + "[", hp)            # pasek HP w kolorze poziomu
        self.assertIn(postac.KOLOR_OCENY["dobrze"] + "↗", hp)               # strzałka w kolorze oceny
        presja = next(x for x in t if "PRESJA" in x)
        self.assertIn(postac.KOLOR_POZIOMU["czerwony"] + "[", presja)
        for x in t:
            if "→" in x and "[" not in x:                                     # linie „powód → co zrobić”
                self.assertEqual(ANSI.sub("", x), x, x)
        self.assertNotIn(postac.KOLOR["mana"], "\n".join(t))                # bez dawnego niebieskiego

    def test_pelny_hp_tempo_bez_none(self):
        t = zwiezly(pelny=True)
        self.assertNotIn("None", t)
        self.assertIn("od 28.10 06:00 (138 h)", t)
        self.assertIn("doba otwarta od 02.11 06:00", t)

    def test_cli_pelny(self):
        p = cli.zbuduj_parser() if hasattr(cli, "zbuduj_parser") else None
        if p is None:
            self.skipTest("parser CLI bez publicznej fabryki")
        a = p.parse_args(["status", "--pelny"])
        self.assertTrue(a.pelny)


if __name__ == "__main__":
    unittest.main()
