"""Kit 0.16.0 (SF-203): rozszerzenie Gemini CLI z tego samego manifestu — generator i instalator (bez Gemini).

v1.0.0 (02.10.2026) - APro Agents / borys-sf · formaty z dokumentacji gemini-cli (extensions/reference, custom-commands)

CZEGO PILNUJĄ
· Komendy: poprawny TOML (`prompt`, `description`), przestrzeń `/sf:…` (podkatalog `commands/sf/`),
  `{{args}}` zamiast `$ARGUMENTS`; manifest rozszerzenia z `contextFileName` i nazwą = katalog.
· Instalacja: kopia pod `~/.gemini/extensions/sf-kit`, globalny GEMINI.md nietknięty, cudzy katalog
  `sf-kit` nienadpisywany.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import json
import sys
import tempfile
try:
    import tomllib  # Python 3.11+; Kit obsługuje 3.9 — bez tomllib test TOML jest pomijany
except ImportError:  # pragma: no cover
    tomllib = None
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import WERSJA, gemini_pakiet, pakiet  # noqa: E402


class TestGeneratorGemini(unittest.TestCase):
    def setUp(self):
        self.m = pakiet.wczytaj()
        self.pliki = pakiet.generuj_gemini(self.m, WERSJA)

    def test_manifest_rozszerzenia(self):
        dane = json.loads(self.pliki[Path("gemini/gemini-extension.json")])
        self.assertEqual(dane, {**dane, "name": "sf-kit", "version": WERSJA, "contextFileName": "GEMINI.md"})

    @unittest.skipIf(tomllib is None, "tomllib dopiero od Pythona 3.11")
    def test_komendy_toml_poprawne_z_args(self):
        komendy = {p: t for p, t in self.pliki.items() if p.parts[:3] == ("gemini", "commands", "sf")}
        self.assertEqual(len(komendy), sum(1 + len(k["aliasy"]) for k in self.m["komendy"]))
        for sciezka, tresc in komendy.items():
            dane = tomllib.loads(tresc)
            self.assertEqual(set(dane), {"description", "prompt"}, sciezka)
            self.assertNotIn("$ARGUMENTS", dane["prompt"])
        zglos = tomllib.loads(komendy[Path("gemini/commands/sf/zglos.toml")])
        self.assertIn("`sf-kit zglos {{args}}`", zglos["prompt"])
        self.assertIn("to samo co /sf:report-work", zglos["description"])

    def test_kontekst_bez_znacznikow_sekcji_i_z_komendami_sf(self):
        kontekst = self.pliki[Path("gemini/GEMINI.md")]
        self.assertNotIn(pakiet.CODEX_START, kontekst)
        self.assertNotIn("`$sf-", kontekst)
        self.assertIn("`/sf:zglos`", kontekst)
        self.assertIn("`sf-wpis-czytelny`", kontekst)


class TestInstalatorGemini(unittest.TestCase):
    def test_kopia_globalny_gemini_md_nietkniety_cudze_zostaje(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(Path, "home", return_value=Path(d)):
            dom = Path(d)
            (dom / ".gemini").mkdir()
            (dom / ".gemini" / "GEMINI.md").write_text("# Moje\n", encoding="utf-8")
            ok, _ = gemini_pakiet.zainstaluj()
            self.assertTrue(ok)
            self.assertEqual((dom / ".gemini" / "GEMINI.md").read_text(encoding="utf-8"), "# Moje\n")
            self.assertTrue((dom / ".gemini" / "extensions" / "sf-kit" / "commands" / "sf" / "zglos.toml").is_file())
            self.assertTrue(gemini_pakiet.zainstalowany())
            self.assertTrue(gemini_pakiet.odswiez())

    def test_cudzy_katalog_sf_kit_nie_nadpisany(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(Path, "home", return_value=Path(d)):
            cudzy = Path(d) / ".gemini" / "extensions" / "sf-kit"
            cudzy.mkdir(parents=True)
            (cudzy / "gemini-extension.json").write_text("{}", encoding="utf-8")
            ok, raport = gemini_pakiet.zainstaluj()
            self.assertFalse(ok)
            self.assertEqual((cudzy / "gemini-extension.json").read_text(encoding="utf-8"), "{}")
            self.assertIn("nie nadpisuję", raport[0])


if __name__ == "__main__":
    unittest.main()
