"""Kit 0.20.1: `sf-kit uwaga` — uwagi do Kita z kontekstem maszyny i ostatnim błędem (SF-506 pkt 1).

v1.0.0 (09.11.2026) - APro Agents / klaudiusz-general · SF-506

CZEGO PILNUJĄ
· `wyczysc`: klucze `sk_…`, Bearer, `HASLO=`, hasło w adresie, wartość własnego klucza — znikają; proza testera
  („hasło: nie przechodzi”, „token wygasł”) zostaje.
· `zapisz_blad` / `ostatni_blad`: zapis oczyszczony, plik 0600, błąd starszy niż doba = brak; `usun_blad` sprząta.
· `_wykonaj`: nieudane polecenie zostawia `ostatni-blad.json` z komunikatem (także z `SystemExit("…")`);
  udane i samo `uwaga` — nie.
· `polecenie_uwaga`: sprawa w Org `sf`, kategoria bug (z błędem) / feedback (zestaw SF, 422 na inną), tagi SalesForge + Błąd/Feedback, błąd dołączony
  i po wysłaniu usunięty; brak członkostwa / błąd API = plik w `uwagi-niewyslane/`, kod 1; `--sucho` nic nie wysyła.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import io
import json
import os
import stat
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, tozsamosc, uwagi  # noqa: E402
from sf_kit.api import BladAPI  # noqa: E402

KLUCZ = "sk_live_TESTOWYklucz1234567890"


class TestWyczysc(unittest.TestCase):
    def test_sekrety_znikaja(self):
        t = (f"klucz {KLUCZ} | Authorization: Bearer abcdefghijkl | PASS=tajne1 | DB_PASSWORD: 'a b' "
             f"| https://u:haslo@host/x | --klucz sk_test_abcd1234")
        w = uwagi.wyczysc(t, KLUCZ)
        for sekret in ("TESTOWYklucz", "abcdefghijkl", "tajne1", "'a b'", "haslo@", "abcd1234"):
            self.assertNotIn(sekret, w, w)

    def test_wlasny_klucz_w_innym_ksztalcie(self):
        self.assertNotIn("XyZ12345678", uwagi.wyczysc("ciąg XyZ12345678 w logu", "XyZ12345678"))

    def test_proza_zostaje(self):
        for t in ("hasło: nie przechodzi", "token wygasł wczoraj", "nie widzę numeru wpisu"):
            self.assertEqual(uwagi.wyczysc(t, KLUCZ, proza=True), t)
        self.assertNotIn("abc123", uwagi.wyczysc("PASS=abc123", proza=True))


class TestZapisBledu(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kat = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_zapis_odczyt_usun(self):
        plik = uwagi.zapisz_blad(self.kat, argv=["wpis", "SF-1", "--klucz", KLUCZ], kod=2,
                                 stderr="x" * 10000 + f"\nBłąd: {KLUCZ}", wersja="0.20.1", klucz=KLUCZ)
        self.assertEqual(stat.S_IMODE(os.stat(plik).st_mode), 0o600)
        dane = uwagi.ostatni_blad(self.kat)
        self.assertNotIn("TESTOWY", json.dumps(dane))
        self.assertLessEqual(len(dane["stderr"]), uwagi.LIMIT_STDERR)
        self.assertTrue(dane["polecenie"].startswith("sf-kit wpis SF-1"))
        uwagi.usun_blad(self.kat)
        self.assertIsNone(uwagi.ostatni_blad(self.kat))

    def test_stary_blad_nie_liczy_sie(self):
        uwagi.zapisz_blad(self.kat, argv=["x"], kod=1, stderr="e", wersja="0", teraz=time.time() - 2 * 86400)
        self.assertIsNone(uwagi.ostatni_blad(self.kat))

    def test_zepsuty_plik(self):
        (self.kat / uwagi.PLIK_BLEDU).write_text("{nie json", encoding="utf-8")
        self.assertIsNone(uwagi.ostatni_blad(self.kat))

    def test_lustro_ograniczone(self):
        cel = io.StringIO()
        l = uwagi.Lustro(cel, limit=100)
        for i in range(1000):
            l.write(f"linia {i}\n")
        self.assertIn("linia 999", l.koncowka())
        self.assertLessEqual(len(l.koncowka()), 100)
        self.assertIn("linia 0\n", cel.getvalue())          # na ekran poszło wszystko


class TestHookWykonaj(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kat = Path(self.tmp.name)
        self.p = [mock.patch.object(cli, "_katalog_agenta", return_value=self.kat),
                  mock.patch.object(cli, "_klucz_po_cichu", return_value=KLUCZ),
                  mock.patch.object(cli.konfiguracja, "wczytaj_jesli_jest", return_value=None)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def _parser(self, funkcja, nazwa="whoami"):
        parser = cli.zbuduj_parser()
        orig = parser.parse_args

        def parse(argv):
            a = orig(argv)
            a.funkcja = funkcja
            return a
        parser.parse_args = parse
        return parser

    def test_porazka_zapisuje(self):
        def zle(args):
            print(f"Nie udało się: {KLUCZ}", file=sys.stderr)
            return 3
        with redirect_stderr(io.StringIO()):
            self.assertEqual(cli._wykonaj(self._parser(zle), ["whoami"]), 3)
        d = uwagi.ostatni_blad(self.kat)
        self.assertEqual((d["kod"], d["polecenie"]), ("3", "sf-kit whoami"))
        self.assertIn("Nie udało się", d["stderr"])
        self.assertNotIn("TESTOWY", d["stderr"])

    def test_system_exit_z_komunikatem(self):
        def zle(args):
            raise SystemExit("Konfiguracja jest niepełna — brakuje: slug.")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli._wykonaj(self._parser(zle), ["whoami"])
        self.assertIn("niepełna", uwagi.ostatni_blad(self.kat)["stderr"])

    def test_sukces_nie_zapisuje(self):
        with redirect_stderr(io.StringIO()):
            cli._wykonaj(self._parser(lambda a: 0), ["whoami"])
        self.assertIsNone(uwagi.ostatni_blad(self.kat))

    def test_uwaga_nie_nadpisuje(self):
        with redirect_stderr(io.StringIO()):
            cli._wykonaj(self._parser(lambda a: 1), ["uwaga", "x"])
        self.assertIsNone(uwagi.ostatni_blad(self.kat))

    def test_stderr_przywrocony(self):
        przed = sys.stderr
        cli._wykonaj(self._parser(lambda a: 0), ["whoami"])
        self.assertIs(sys.stderr, przed)


class Atrapa:
    def __init__(self, blad_zalozenia=None):
        self.organizacja = None
        self.zalozone = []
        self.tagi = []
        self.pliki = []
        self.blad_zalozenia = blad_zalozenia

    def zaloz_sprawe(self, **kw):
        if self.blad_zalozenia:
            raise self.blad_zalozenia
        self.zalozone.append({**kw, "org": self.organizacja})
        return {"ticket_id": "t-1", "ticket_number": 507, "ticket_prefix": "SF"}

    def wpis_z_plikami(self, sprawa, tresc, pliki):
        self.pliki.append(pliki)


TYPY = [{"id": "p", "name": "Projekt", "slug": "project", "tags": [{"id": "g1", "name": "SalesForge"}]},
        {"id": "k", "name": "Kategoria", "slug": "ticket_category",
         "tags": [{"id": "g2", "name": "Błąd"}, {"id": "g3", "name": "Feedback"}]}]


class TestPolecenieUwaga(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kat = Path(self.tmp.name)
        konf = SimpleNamespace(profil="asystent", slug="wojt", organizacja="", adres="https://sales-forge.pl",
                               obserwatorzy_domyslni=[])
        self.klient = Atrapa()
        org = SimpleNamespace(uuid="uuid-sf", slug="sf")
        self.nadane = []
        self.p = [mock.patch.object(cli, "_katalog_agenta", return_value=self.kat),
                  mock.patch.object(cli.konfiguracja, "wczytaj", return_value=konf),
                  mock.patch.object(cli.magazyn_klucza, "wczytaj", return_value=KLUCZ),
                  mock.patch.object(cli, "_klient_bez_organizacji", side_effect=lambda k: self.klient),
                  mock.patch.object(cli, "_tozsamosc", return_value=None),
                  mock.patch.object(cli.tozsamosc, "wybierz_dla_zapisu", return_value=org),
                  mock.patch.object(cli.konsola, "typy_wszystkie", return_value=TYPY),
                  mock.patch.object(cli.konsola, "nadaj_tag",
                                    side_effect=lambda k, s, tag, typ: self.nadane.append(tag["name"]) or [])]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def _args(self, tekst="po wpisie nie widzę numeru", **kw):
        return SimpleNamespace(**{"tekst": tekst, "plik": [], "kontekst": None, "bez_bledu": False,
                                  "sucho": False, "json": False, "org": None, **kw})

    def _uruchom(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            kod = cli.polecenie_uwaga(args)
        return kod, out.getvalue(), err.getvalue()

    def test_sprawa_w_sf_z_bledem(self):
        uwagi.zapisz_blad(self.kat, argv=["wpis", "SF-1"], kod=1, stderr="Nie znaleziono sprawy SF-1", wersja="0.20.1")
        kod, out, _ = self._uruchom(self._args(plik=["zrzut.png"]))
        self.assertEqual(kod, 0)
        z = self.klient.zalozone[0]
        self.assertEqual((z["org"], z["kategoria"]), ("uuid-sf", "bug"))
        self.assertTrue(z["tytul"].startswith("Uwaga do Kita: po wpisie"))
        self.assertIn("Nie znaleziono sprawy SF-1", z["opis"])
        self.assertIn("| agent | wojt |", z["opis"])
        self.assertEqual(self.nadane, ["SalesForge", "Błąd"])
        self.assertEqual(self.klient.pliki, [["zrzut.png"]])
        self.assertIsNone(uwagi.ostatni_blad(self.kat))      # nie pojedzie drugi raz
        self.assertIn("SF-507", out)

    def test_bez_bledu_feedback(self):
        uwagi.zapisz_blad(self.kat, argv=["x"], kod=1, stderr="E", wersja="0")
        self._uruchom(self._args(bez_bledu=True))
        self.assertNotIn("Ostatnie nieudane", self.klient.zalozone[0]["opis"])
        self.assertEqual(self.klient.zalozone[0]["kategoria"], "feedback")
        self.assertEqual(self.nadane, ["SalesForge", "Feedback"])
        self.assertIsNotNone(uwagi.ostatni_blad(self.kat))   # nie wysłany = zostaje

    def test_sucho_nic_nie_wysyla(self):
        kod, out, _ = self._uruchom(self._args(sucho=True))
        self.assertEqual((kod, self.klient.zalozone), (0, []))
        self.assertIn("nic nie wysłano", out)

    def test_pusta_uwaga(self):
        self.assertEqual(self._uruchom(self._args(tekst="  "))[0], 2)

    def test_brak_czlonkostwa_plik(self):
        with mock.patch.object(cli.tozsamosc, "wybierz_dla_zapisu", side_effect=tozsamosc.BrakWyboru("x")):
            kod, _, err = self._uruchom(self._args())
        self.assertEqual(kod, 1)
        pliki = list((self.kat / uwagi.KATALOG_NIEWYSLANYCH).glob("*.md"))
        self.assertEqual(len(pliki), 1)
        self.assertIn("po wpisie nie widzę numeru", pliki[0].read_text(encoding="utf-8"))
        self.assertIn("członkostwo", err)

    def test_blad_api_plik(self):
        self.klient = Atrapa(blad_zalozenia=BladAPI("403 brak tickets:write"))
        kod, _, err = self._uruchom(self._args())
        self.assertEqual(kod, 1)
        self.assertIn("403", err)
        self.assertTrue(list((self.kat / uwagi.KATALOG_NIEWYSLANYCH).glob("*.md")))

    def test_tag_nie_blokuje(self):
        with mock.patch.object(cli.konsola, "typy_wszystkie", side_effect=BladAPI("brak taxonomy:read")):
            kod, _, err = self._uruchom(self._args())
        self.assertEqual(kod, 0)
        self.assertIn("tagi", err)

    def test_org_ze_zmiennej(self):
        with mock.patch.dict(os.environ, {uwagi.ZMIENNA_ORG_UWAG: "inna"}):
            self.assertEqual(uwagi.org_uwag(None), "inna")
            self.assertEqual(uwagi.org_uwag("jawna"), "jawna")
        self.assertEqual(uwagi.org_uwag(None), "sf")


if __name__ == "__main__":
    unittest.main()
