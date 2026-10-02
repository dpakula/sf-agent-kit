"""Kit 0.16.0 (SF-203): pakiet Kimi Code z tego samego manifestu — generator i instalator (bez uruchamiania Kimi).

v1.0.0 (02.10.2026) - APro Agents / borys-sf · Agata 14:12; formaty z dokumentacji Kimi Code (moonshotai.github.io/kimi-code)

CZEGO PILNUJĄ
· Komendy: `disable-model-invocation: true` (model sam nie wywoła), `$ARGUMENTS` zostaje (Kimi go podstawia);
  skille wiedzy bez tego pola (Kimi dobiera je sam).
· Odwołania `/skill:sf-…`, nazwy skilli z prefiksem; w sekcji AGENTS.md nie ma składni Codexa (`$sf-…`).
· Instalacja w `KIMI_CODE_HOME` (domyślnie `~/.kimi-code`), cudza treść AGENTS.md zostaje, sekcja raz.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import WERSJA, kimi_pakiet, pakiet  # noqa: E402


class TestGeneratorKimi(unittest.TestCase):
    def setUp(self):
        self.m = pakiet.wczytaj()
        self.pliki = pakiet.generuj_kimi(self.m, WERSJA)

    def test_komendy_z_flaga_wiedza_bez(self):
        self.assertIn("disable-model-invocation: true", self.pliki[Path("kimi/skills/sf-zglos/SKILL.md")])
        self.assertNotIn("disable-model-invocation", self.pliki[Path("kimi/skills/sf-wpis-czytelny/SKILL.md")])

    def test_arguments_zostaje_i_odwolania_kimi(self):
        self.assertIn("`sf-kit zglos $ARGUMENTS`", self.pliki[Path("kimi/skills/sf-zglos/SKILL.md")])
        for sciezka, tresc in self.pliki.items():
            self.assertNotIn("/sf-kit:", tresc, sciezka)
            self.assertNotIn("`$sf-", tresc, sciezka)
            for s in self.m["skille"]:
                self.assertNotIn(f"`{s['id']}`", tresc, sciezka)
        self.assertIn("`/skill:sf-zglos`", self.pliki[Path("kimi/AGENTS.md")])

    def test_sekcja_ze_znacznikami_kimi(self):
        sekcja = self.pliki[Path("kimi/AGENTS.md")]
        self.assertTrue(sekcja.startswith(pakiet.KIMI_START))
        self.assertIn(pakiet.KIMI_KONIEC, sekcja)
        self.assertNotIn(pakiet.CODEX_START, sekcja)


class TestInstalatorKimi(unittest.TestCase):
    def test_kimi_code_home_cudze_zostaje_sekcja_raz(self):
        with tempfile.TemporaryDirectory() as d:
            dom = Path(d)
            with mock.patch.dict("os.environ", {"KIMI_CODE_HOME": str(dom / "inny-kimi")}):
                (dom / "inny-kimi").mkdir()
                (dom / "inny-kimi" / "AGENTS.md").write_text("# Moje\n", encoding="utf-8")
                ok, _ = kimi_pakiet.zainstaluj()
                kimi_pakiet.zainstaluj()
                tresc = (dom / "inny-kimi" / "AGENTS.md").read_text(encoding="utf-8")
                self.assertTrue(ok)
                self.assertTrue(tresc.startswith("# Moje\n"))
                self.assertEqual(tresc.count(pakiet.KIMI_START), 1)
                self.assertTrue((dom / "inny-kimi" / "skills" / "sf-zglos" / "SKILL.md").is_file())
                self.assertTrue(kimi_pakiet.zainstalowany())
                self.assertTrue(kimi_pakiet.odswiez())

    def test_mcp_json_cudze_serwery_zostaja_wpis_raz(self):
        import json
        with tempfile.TemporaryDirectory() as d, mock.patch.dict("os.environ", {"KIMI_CODE_HOME": d}):
            plik = Path(d) / "mcp.json"
            plik.write_text(json.dumps({"mcpServers": {"inny": {"command": "x"}}}), encoding="utf-8")
            kimi_pakiet.zarejestruj_mcp()
            raport = kimi_pakiet.zarejestruj_mcp()
            dane = json.loads(plik.read_text(encoding="utf-8"))
            self.assertEqual(dane["mcpServers"]["inny"], {"command": "x"})
            self.assertEqual(dane["mcpServers"]["sf-kit"], {"command": "sf-kit", "args": ["mcp"]})
            self.assertIn("już ma", raport[0])
            plik.write_text("{ zepsuty", encoding="utf-8")
            self.assertIn("NIE zmieniam", kimi_pakiet.zarejestruj_mcp()[0])
            self.assertEqual(plik.read_text(encoding="utf-8"), "{ zepsuty")

    def test_stary_katalog_kimi_cli_nietkniety(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(Path, "home", return_value=Path(d)), \
                mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("KIMI_CODE_HOME", None)
            kimi_pakiet.zainstaluj()
            self.assertTrue((Path(d) / ".kimi-code" / "AGENTS.md").is_file())
            self.assertFalse((Path(d) / ".kimi").exists(), "`~/.kimi` to stary kimi-cli — nie piszemy tam")


if __name__ == "__main__":
    unittest.main()
