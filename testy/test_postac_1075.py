"""Ekran statusu `sf-kit status` (ADVERTPR-1075): cztery paski, rozbicie, podpowiedzi — Kit tylko rysuje.

v0.1 (15.10.2026) - APro Agents / klaudiusz-general

CZEGO TU PILNUJĘ
════════════════
1. **Cztery paski jednej szerokości, w stałej kolejności** (mana, energia, presja, zdrowie), wartości w %,
   presja ponad próg jako „100%+”, tendencja HP przy pasku.
2. **Podpowiedzi idą 1:1 z `wskazniki.py --json`** — Kit nie dopisuje własnych (drugi wzór = druga prawda).
3. **`--kto`**: agata → presja A i HP „nie dotyczy”; <agent> → dom homes/<agent>, presja n/d (SF-289).
4. **Dawny `status` koordynatora** nadal pod `--kolejka` (i przy --agent-slug/--status).
5. **Bez wskazniki.py ekran mówi wprost, czego brakuje** — nie rysuje pustych pasków jak „wszystko OK”.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, postac  # noqa: E402

ANSI = re.compile(r"\033\[[0-9;]*m")


def dane(**zmiany):
    d = {
        "manifest": 3,
        "mana": {"procent": 44, "zapelnienie_okna": 56,
                 "wglad": {"skladowe": [{"nazwa": "zapełnienie okna kontekstu", "opis": "56 % okna zajęte"}],
                           "podpowiedzi": [], "trend": None}},
        "energia": {"procent": 50, "pola": 3, "pola_max": 6, "poziom": "zmeczona",
                    "ubytki": {"przerost": 3, "rozgrywka": 0, "flota": 0}, "limit_7d": 100,
                    "wglad": {"skladowe": [
                        {"nazwa": "przerost dokumentów", "ubytek": 3, "opis": "CLAUDE.md 8,6/6 KB"},
                        {"nazwa": "limit 7d", "procent": 100, "opis": "zapas 96 %"}],
                        "podpowiedzi": ["CLAUDE.md 8,6/6 KB → odchudzić o 2,6 KB = +1 pole (+17 %)"],
                        "trend": {"od": "2026-10-15T00:18:10", "dni": 0.1, "co_najmniej": True}}},
        "presja": {
            "damian": {"procent": 3401, "dni": 102.0, "kolor": "czerwony", "punkty": 1530.5, "pozycji": 413,
                       "wglad": {"skladowe": [{"priorytet": "wysoki", "wiek": "ponad_7_dni", "pilne": False, "n": 132,
                                               "punkty": 792.0, "dni": 52.8,
                                               "opis": "132 poz. high starszych niż 7 dni"}],
                                 "podpowiedzi": ["132 poz. high starszych niż 7 dni (792 pkt) → zamknąć/scalić = −52,8 dni"],
                                 "reakcja": "ciąć kolejkę decyzji (zamykać nieaktualne, scalać), nie dokładać",
                                 "trend": None}},
            "agent": {"procent": 40, "dni": 1.2, "kolor": "pomaranczowy", "punkty": 9.6, "pozycji": 3,
                      "wglad": {"skladowe": [], "podpowiedzi": ["PODPOWIEDŹ AGENTA"], "reakcja": None, "trend": None}},
            "swieze": True, "co_najmniej": False},
        "hp": {"procent": 17, "poziom": "czerwony", "data": "2026-10-13", "alarm": True, "seria_po": 1,
               "tendencja": {"kierunek": "maleje", "strzalka": "↓", "roznica": -28.0, "srednia": 45.0, "od_dni": 2,
                             "przyczyna": {"skladowa": "presja", "opis": "presja", "punkty": 10}},
               "wglad": {"skladowe": [{"nazwa": "presja", "punkty": -5}, {"nazwa": "kalendarz", "punkty": 5}],
                         "podglad_dzis": {"zmiana": -5, "godzin": 3},
                         "podpowiedzi": ["zamknięcie dziś przed 00:00 = +5"],
                         "alarm": "ALARM: HP < 40 przez 3 doby → blok livecare",
                         "trend": {"kierunek": "maleje", "strzalka": "↓", "roznica": -28.0, "od_dni": 2,
                                   "przyczyna": {"opis": "presja"}}}},
        "limity": {"5h": 85, "7d": 15},
        "wyglad": {"pola_paska": 9, "ikony": {"mana": "✦", "energia": "↯", "presja": "🔥", "hp": "♥"},
                   "glify_zapasu": {"90": "●", "65": "◕", "35": "◑", "10": "◔", "0": "○"},
                   "kolory_zapasu": {"50": "zielony", "20": "zolty", "0": "czerwony"}},
    }
    d.update(zmiany)
    return d


def ekran(d=None, **kw):
    kw.setdefault("kolor", "nigdy")
    return postac.ekran(kto=kw.pop("kto", None), dane=d or dane(), **kw)


class Paski(unittest.TestCase):
    def test_cztery_paski_jednej_szerokosci_w_kolejnosci(self):
        linie = ekran(rozbicie=False).splitlines()
        paski = [l for l in linie if "[" in l and ("█" in l or "░" in l)]
        self.assertEqual(len(paski), 4)
        for etykieta, l in zip(("MANA", "ENERGIA", "PRESJA D", "ZDROWIE"), paski):
            self.assertIn(etykieta, l)
            self.assertEqual(len(re.search(r"\[([█░]+)\]", l).group(1)), 18, l)   # 9 kratek manifestu × 2
        # paski zaczynają się w tej samej kolumnie mimo 🔥 (2 kolumny)
        self.assertEqual(len({postac._szer(l[:l.index("[")]) for l in paski}), 1)

    def test_procenty_presja_ponad_prog_i_tendencja_hp(self):
        t = ekran(rozbicie=False)
        self.assertIn(" 44 %", t)
        self.assertIn("100%+", t)
        self.assertIn("↓ czerwony · doba 13.10 · ALARM", t)
        self.assertIn("3/6 · zmęczona", t)

    def test_limity_jako_glify_zapasu(self):
        t = ekran(rozbicie=False)
        self.assertIn("5h ◕ 85 %", t)
        self.assertIn("7d ◔ 15 %", t)

    def test_stopka_z_wersja_manifestu(self):
        self.assertIn("manifest v3", ekran().splitlines()[-1])

    def test_kolory_tylko_na_zyczenie(self):
        self.assertIsNone(ANSI.search(ekran()))
        t = ekran(kolor="zawsze")
        for kod in ("38;5;39", "38;5;220", "38;5;208", "38;5;196", "\033[31m"):   # 7d 15 % = czerwony
            self.assertIn(kod, t)

    def test_energia_zero_czerwona(self):
        d = dane()
        d["energia"]["procent"] = 0
        linia = next(l for l in ekran(d, kolor="zawsze").splitlines() if "ENERGIA" in l)
        self.assertIn("38;5;196", linia)
        self.assertNotIn("38;5;220", linia)


class Wglad(unittest.TestCase):
    def test_podpowiedzi_1_do_1_z_wskaznikow(self):
        t = ekran()
        d = dane()
        for p in (d["energia"]["wglad"]["podpowiedzi"] + d["presja"]["damian"]["wglad"]["podpowiedzi"]
                  + d["hp"]["wglad"]["podpowiedzi"]):
            self.assertIn("   → " + p, t)
        self.assertIn("   → ciąć kolejkę decyzji", t)
        strzalki = [l for l in t.splitlines() if l.startswith("   → ")]
        self.assertEqual(len(strzalki), 1 + 1 + 1 + 1 + 1)   # mana: „nic do zrobienia”

    def test_rozbicie_skladowych_i_trend(self):
        t = ekran()
        self.assertIn("przerost dokumentów", t)
        self.assertIn("−3 pola", t)
        self.assertIn("co najmniej od 15.10 00:18", t)
        self.assertIn("132 poz. high starszych niż 7 dni", t)
        self.assertIn("↓ od 2 dób, −28 pkt vs średnia 7 dób; ciągnie: presja", t)
        self.assertIn("dziś do teraz −5", t)
        self.assertIn("! ALARM", t)

    def test_krotko_bez_rozbicia(self):
        self.assertNotIn("→", ekran(rozbicie=False).split("5h")[1])


class Kto(unittest.TestCase):
    def test_agata_presja_A_hp_nie_dotyczy(self):
        t = ekran(kto="agata")
        self.assertIn("PRESJA A", t)
        self.assertIn("1,2 dni · pomarańczowy", t)
        self.assertIn("nie dotyczy (HP liczone dla człowieka)", t)
        self.assertIn("PODPOWIEDŹ AGENTA", t)
        self.assertNotIn("zamknięcie dziś przed 00:00", t)

    def test_inny_agent_bez_presji_i_hp(self):
        t = ekran(kto="klaudiusz-general")
        self.assertIn("STATUS · klaudiusz-general", t)
        self.assertIn("SF-289", t)
        self.assertIn("nie dotyczy", t)
        self.assertNotIn("132 poz.", t)


class Zrodlo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = Path(self.tmp.name)
        (r / "scripts" / "lib").mkdir(parents=True)
        (r / "homes" / "agata" / "config").mkdir(parents=True)
        (r / "homes" / "kodeks").mkdir(parents=True)
        self.lib = r / "scripts" / "lib" / "wskazniki.py"
        # atrapa: oddaje fikstury i zapisuje, z jakim --dom ją wołano
        self.lib.write_text("import json, sys\n"
                            "a = sys.argv\n"
                            f"open({str(r / 'wolanie.json')!r}, 'w').write(json.dumps(a))\n"
                            f"print(open({str(r / 'dane.json')!r}).read())\n")
        (r / "dane.json").write_text(json.dumps(dane(), ensure_ascii=False))
        self.r = r

    def tearDown(self):
        self.tmp.cleanup()

    def test_wola_wskazniki_z_domem_agaty_i_jednym_manifestem(self):
        t = postac.ekran(kto=None, wskazniki=str(self.lib), kolor="nigdy")
        self.assertIn("manifest v3", t)
        a = json.loads((self.r / "wolanie.json").read_text())
        self.assertEqual(a[a.index("--dom") + 1], str((self.r / "homes" / "agata").resolve()))
        self.assertEqual(a[a.index("--manifest") + 1],
                         str((self.r / "homes" / "agata" / "config" / "wskazniki.json").resolve()))

    def test_agent_dostaje_swoj_dom(self):
        postac.ekran(kto="kodeks", wskazniki=str(self.lib), kolor="nigdy")
        a = json.loads((self.r / "wolanie.json").read_text())
        self.assertEqual(a[a.index("--dom") + 1], str((self.r / "homes" / "kodeks").resolve()))

    def test_nieznany_agent(self):
        with self.assertRaises(postac.BrakWskaznikow):
            postac.ekran(kto="nie-ma-takiego", wskazniki=str(self.lib), kolor="nigdy")

    def test_bez_wskaznikow_mowi_czego_brakuje(self):
        with mock.patch.dict(os.environ, {"SF_KIT_WSKAZNIKI": str(self.r / "brak.py")}):
            with self.assertRaises(postac.BrakWskaznikow) as ctx:
                postac.ekran(kto=None, kolor="nigdy")
        self.assertIn("--wskazniki", str(ctx.exception))
        self.assertIn("SF-289", str(ctx.exception))

    def test_szuka_w_gore_od_domu(self):
        with mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch.object(postac.Path, "home", return_value=self.r / "homes" / "agata"):
            os.environ.pop("SF_KIT_WSKAZNIKI", None)
            self.assertEqual(postac.znajdz_wskazniki().resolve(), self.lib.resolve())

    def test_nie_uruchamia_wskaznikow_z_biezacego_katalogu(self):
        """0.18.0: `pobierz()` WYKONUJE znaleziony plik — cudze repo w bieżącym katalogu nie może go podsunąć."""
        stary = os.getcwd()
        obcy = Path(tempfile.mkdtemp())
        try:
            os.chdir(self.r / "homes" / "agata")
            with mock.patch.dict(os.environ, {}, clear=False), \
                 mock.patch.object(postac.Path, "home", return_value=obcy):
                os.environ.pop("SF_KIT_WSKAZNIKI", None)
                self.assertIsNone(postac.znajdz_wskazniki())
        finally:
            os.chdir(stary)


class Polecenie(unittest.TestCase):
    def _uruchom(self, argv):
        with mock.patch.object(cli, "_status_koordynatora", return_value=0) as stary, \
             mock.patch.object(postac, "ekran", return_value="EKRAN") as nowy, \
             mock.patch.object(cli.aktualizacje, "ostrzezenie_przed_poleceniem", return_value=None), \
             mock.patch("builtins.print"):
            kod = cli.main(argv)
        return kod, stary, nowy

    def test_status_to_ekran(self):
        kod, stary, nowy = self._uruchom(["status", "--kto", "agata", "--kolor", "nigdy"])
        self.assertEqual(kod, 0)
        nowy.assert_called_once()
        self.assertEqual(nowy.call_args.kwargs["kto"], "agata")
        stary.assert_not_called()

    def test_alias_postac(self):
        _, stary, nowy = self._uruchom(["postac", "--krotko"])
        self.assertFalse(nowy.call_args.kwargs["rozbicie"])
        stary.assert_not_called()

    def test_dawny_widok_koordynatora(self):
        for argv in (["status", "--kolejka"], ["status", "--agent-slug", "kodeks"], ["status", "--status", "queued"]):
            _, stary, nowy = self._uruchom(argv)
            stary.assert_called_once()
            nowy.assert_not_called()

    def test_brak_danych_kod_2(self):
        with mock.patch.object(postac, "ekran", side_effect=postac.BrakWskaznikow("brak")), \
             mock.patch.object(cli.aktualizacje, "ostrzezenie_przed_poleceniem", return_value=None), \
             mock.patch("sys.stderr"):
            self.assertEqual(cli.main(["status"]), 2)


if __name__ == "__main__":
    unittest.main()
