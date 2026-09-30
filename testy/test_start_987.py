"""`sf-kit start` i `sf-kit sprawa <link>` (ADVERTPR-987, 0.15.1).

v1.0.0 (30.09.2026) - APro Agents / borys-sf

Czego te testy pilnują — rzeczy, które psują się bez objawu:
  · cudza treść CLAUDE.md / settings.json znika po `start` (człowiek traci swoje instrukcje),
  · drugie `start` dokleja drugą sekcję zamiast podmienić pierwszą,
  · zepsuty settings.json zostaje „naprawiony” przez nadpisanie,
  · `start` w katalogu domowym — CLAUDE.md czytałby wtedy każdy projekt,
  · `sprawa <link>` kończy się tracebackiem (scenariusz „co jest w sprawie <link>”).

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, start, tozsamosc  # noqa: E402

README = Path("/opt/sf-kit/README.md")


def _przygotuj(katalog, **kw):
    return start.przygotuj(katalog, org_slug=kw.get("slug", "formarketing"),
                           org_nazwa="ForMarketing", readme=README, agent=kw.get("agent"))


class TestPlikiStartu(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.k = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pusty_katalog_dostaje_trzy_pliki(self):
        _przygotuj(self.k)
        for nazwa in ("CLAUDE.md", "AGENTS.md"):
            tresc = (self.k / nazwa).read_text(encoding="utf-8")
            self.assertIn("--org formarketing", tresc)
            self.assertIn(str(README), tresc)
            self.assertIn("pokaż sprawy", tresc)
        ust = json.loads((self.k / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(ust["permissions"]["allow"], ["Bash(sf-kit:*)"])

    def test_kazde_polecenie_w_sciadze_niesie_org(self):
        """Zapis bez --org Kit odrzuca (0.13.0) — ściąga nie może uczyć polecenia bez niego."""
        tresc = start.instrukcja(org_slug="fm", org_nazwa="FM", readme=README, agent=None)
        for linia in tresc.splitlines():
            if linia.startswith("| „"):
                self.assertIn("sf-kit --org fm ", linia, linia)

    def test_agent_wskazany_trafia_do_polecen(self):
        tresc = start.instrukcja(org_slug="fm", org_nazwa="FM", readme=README, agent="claude-jk")
        self.assertIn("sf-kit --agent claude-jk --org fm whoami", tresc)

    def test_cudza_tresc_zostaje_a_druga_sekcja_nie_powstaje(self):
        (self.k / "CLAUDE.md").write_text("# Mój projekt\n\nMoje zasady.\n", encoding="utf-8")
        _przygotuj(self.k, slug="stara")
        _przygotuj(self.k, slug="nowa")
        tresc = (self.k / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertTrue(tresc.startswith("# Mój projekt\n\nMoje zasady.\n"))
        self.assertEqual(tresc.count(start.ZNACZNIK_START), 1)
        self.assertIn("--org nowa", tresc)
        self.assertNotIn("--org stara", tresc)

    def test_tresc_po_naszej_sekcji_tez_zostaje(self):
        _przygotuj(self.k)
        plik = self.k / "AGENTS.md"
        plik.write_text(plik.read_text(encoding="utf-8") + "\n## Dopisane przez człowieka\n",
                        encoding="utf-8")
        _przygotuj(self.k, slug="inna")
        self.assertIn("## Dopisane przez człowieka", plik.read_text(encoding="utf-8"))

    def test_drugi_start_niczego_nie_zmienia(self):
        _przygotuj(self.k)
        przed = {p: p.read_bytes() for p in self.k.rglob("*") if p.is_file()}
        raport = _przygotuj(self.k)
        po = {p: p.read_bytes() for p in self.k.rglob("*") if p.is_file()}
        self.assertEqual(przed, po)
        self.assertIn("reguła już była", "\n".join(raport))

    def test_istniejace_ustawienia_dostaja_regule_obok_swoich(self):
        (self.k / ".claude").mkdir()
        (self.k / ".claude" / "settings.json").write_text(json.dumps(
            {"model": "opus", "permissions": {"allow": ["Bash(git status)"], "deny": ["Read(.env)"]}}),
            encoding="utf-8")
        _przygotuj(self.k)
        ust = json.loads((self.k / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(ust["model"], "opus")
        self.assertEqual(ust["permissions"]["deny"], ["Read(.env)"])
        self.assertEqual(ust["permissions"]["allow"], ["Bash(git status)", "Bash(sf-kit:*)"])

    def test_zepsuty_json_NIE_jest_nadpisywany(self):
        (self.k / ".claude").mkdir()
        plik = self.k / ".claude" / "settings.json"
        plik.write_text("{ to nie json", encoding="utf-8")
        raport = _przygotuj(self.k)
        self.assertEqual(plik.read_text(encoding="utf-8"), "{ to nie json")
        self.assertIn("NIE ZMIENIONY", "\n".join(raport))
        self.assertTrue((self.k / "CLAUDE.md").exists())      # instrukcja i tak zapisana


class TestPolecenieStart(unittest.TestCase):

    def test_katalog_domowy_odmawia(self):
        with tempfile.TemporaryDirectory() as dom, \
                mock.patch.object(Path, "home", return_value=Path(dom)):
            err = io.StringIO()
            with redirect_stderr(err):
                kod = cli.main(["start", "--katalog", dom])
            self.assertEqual(kod, 2)
            self.assertIn("katalog domowy", err.getvalue())
            self.assertFalse((Path(dom) / "CLAUDE.md").exists())

    def test_start_zapisuje_z_organizacja_z_sf(self):
        org = tozsamosc.Organizacja(uuid="u-1", slug="formarketing", nazwa="ForMarketing")
        with tempfile.TemporaryDirectory() as k, \
                mock.patch.object(cli.konfiguracja, "wczytaj", return_value=object()), \
                mock.patch.object(cli, "_klient_i_organizacja", return_value=(None, org)), \
                mock.patch.object(cli.aktualizacje, "ostrzezenie_przed_poleceniem",
                                  return_value=None):
            out = io.StringIO()
            with redirect_stdout(out):
                kod = cli.main(["start", "--katalog", k])
            self.assertEqual(kod, 0)
            self.assertIn("--org formarketing", (Path(k) / "CLAUDE.md").read_text(encoding="utf-8"))
            self.assertIn("Tekstu startowego nie trzeba", out.getvalue())


class TestSprawaZLinku(unittest.TestCase):
    UUID = "d70a914b-3b44-406a-964c-ea4f8a3ac78b"

    def _uruchom(self, argv):
        pobrane = []

        class Klient:
            def sprawa(self, sid):
                pobrane.append(sid)
                return {"id": sid, "title": "T", "entries": []}

        wskazana_org = []

        def klient(konf, args=None):
            wskazana_org.append(getattr(args, "org", None))
            return Klient()

        with mock.patch.object(cli.konfiguracja, "wczytaj", return_value=object()), \
                mock.patch.object(cli.konfiguracja, "wczytaj_jesli_jest", return_value=None), \
                mock.patch.object(cli, "_klient", side_effect=klient), \
                mock.patch("sf_kit.kontekst._tekst", return_value="KARTA"):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                kod = cli.main(argv)
        return kod, pobrane, wskazana_org, out.getvalue(), err.getvalue()

    def test_link_z_org_czyta_te_sprawe_w_tej_organizacji(self):
        kod, pobrane, org, out, _ = self._uruchom(
            ["sprawa", f"https://sf.dpakula.pl/tickets/{self.UUID}?org=advertpro-co"])
        self.assertEqual(kod, 0)
        self.assertEqual(pobrane, [self.UUID])
        self.assertEqual(org, ["advertpro-co"])
        self.assertIn("KARTA", out)

    def test_jawne_org_wygrywa_z_linkiem(self):
        _, _, org, _, _ = self._uruchom(
            ["--org", "formarketing", "sprawa", f"https://sf.dpakula.pl/tickets/{self.UUID}?org=x"])
        self.assertEqual(org, ["formarketing"])

    def test_niezrozumiale_wskazanie_to_komunikat_nie_traceback(self):
        kod, _, _, _, err = self._uruchom(["sprawa", "https://example.com/cos"])
        self.assertEqual(kod, 1)
        self.assertIn("nie rozumiem", err)


if __name__ == "__main__":
    unittest.main()
