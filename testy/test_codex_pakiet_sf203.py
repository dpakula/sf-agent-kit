"""Kit 0.16.0 (SF-203): pakiet Codex CLI z tego samego manifestu — generator i instalator.

v1.0.0 (02.10.2026) - APro Agents / borys-sf · Agata 14:00; formaty z dokumentacji Codex CLI (02.10)

CZEGO PILNUJĄ
· Skille Codex mają prefiks `sf-` (brak przestrzeni nazw pluginu), komendy NIE są wywoływane przez model
  (`agents/openai.yaml` allow_implicit_invocation: false), skille wiedzy — tak (bez openai.yaml).
· W treści nie zostaje `$ARGUMENTS` (to podstawienie promptów) ani nazwy skilli bez prefiksu.
· Instalacja: cudza treść AGENTS.md zostaje, AGENTS.override.md ma pierwszeństwo, cudzy skill o tej samej
  nazwie jest pomijany, nasz nieaktualny — usuwany; drugie uruchomienie niczego nie dubluje.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import WERSJA, codex_pakiet, pakiet  # noqa: E402


class TestGeneratorCodex(unittest.TestCase):
    def setUp(self):
        self.m = pakiet.wczytaj()
        self.pliki = pakiet.generuj_codex(self.m, WERSJA)

    def test_komendy_bez_wywolania_przez_model_wiedza_z(self):
        self.assertIn("allow_implicit_invocation: false",
                      self.pliki[Path("codex/skills/sf-zglos/agents/openai.yaml")])
        self.assertNotIn(Path("codex/skills/sf-wpis-czytelny/agents/openai.yaml"), self.pliki)

    def test_nazwy_z_prefiksem_i_bez_arguments(self):
        for sciezka, tresc in self.pliki.items():
            self.assertNotIn("$ARGUMENTS", tresc, sciezka)
            self.assertNotIn("/sf-kit:", tresc, sciezka)
            for s in self.m["skille"]:
                self.assertNotIn(f"`{s['id']}`", tresc, f"{sciezka}: skill bez prefiksu sf-")
        self.assertIn('name: "sf-report-work"', self.pliki[Path("codex/skills/sf-report-work/SKILL.md")])

    def test_sekcja_agents_mala_i_ze_znacznikami(self):
        sekcja = self.pliki[Path("codex/AGENTS.md")]
        self.assertTrue(sekcja.startswith(pakiet.CODEX_START))
        self.assertIn(pakiet.CODEX_KONIEC, sekcja)
        self.assertLess(len(sekcja.encode("utf-8")), pakiet.CODEX_MAKS_BAJTOW)
        self.assertIn("`$sf-zglos`", sekcja)

    def test_za_duza_sekcja_zapala_straznika(self):
        with mock.patch.object(pakiet, "CODEX_MAKS_BAJTOW", 100):
            bledy = pakiet.waliduj(self.m, pakiet._podkomendy())
        self.assertTrue(any("Codex" in b for b in bledy))


class TestInstalatorCodex(unittest.TestCase):
    def _dom(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        dom = Path(d.name)
        patch_home = mock.patch.object(Path, "home", return_value=dom)
        patch_env = mock.patch.dict("os.environ", {"CODEX_HOME": str(dom / ".codex")})
        patch_home.start(); patch_env.start()
        self.addCleanup(patch_home.stop); self.addCleanup(patch_env.stop)
        return dom

    def test_cudze_zostaje_sekcja_raz(self):
        dom = self._dom()
        (dom / ".codex").mkdir()
        (dom / ".codex" / "AGENTS.md").write_text("# Moje\nNie ruszać.\n", encoding="utf-8")
        codex_pakiet.zainstaluj()
        codex_pakiet.zainstaluj()
        tresc = (dom / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(tresc.startswith("# Moje\nNie ruszać.\n"))
        self.assertEqual(tresc.count(pakiet.CODEX_START), 1)
        self.assertTrue(codex_pakiet.zainstalowany())

    def test_override_ma_pierwszenstwo(self):
        dom = self._dom()
        (dom / ".codex").mkdir()
        (dom / ".codex" / "AGENTS.override.md").write_text("# Nadpisanie\n", encoding="utf-8")
        codex_pakiet.zainstaluj()
        self.assertIn(pakiet.CODEX_START, (dom / ".codex" / "AGENTS.override.md").read_text(encoding="utf-8"))
        self.assertFalse((dom / ".codex" / "AGENTS.md").exists())

    def test_cudzy_skill_pomijany_nasz_nieaktualny_usuwany(self):
        dom = self._dom()
        cudzy = dom / ".agents" / "skills" / "sf-wpis"
        cudzy.mkdir(parents=True)
        (cudzy / "SKILL.md").write_text("---\nname: sf-wpis\n---\ncudzy\n", encoding="utf-8")
        stary = dom / ".agents" / "skills" / "sf-stara-komenda"
        stary.mkdir(parents=True)
        (stary / "SKILL.md").write_text(f"<!-- {codex_pakiet.ZNACZNIK} 0.15 -->\n", encoding="utf-8")
        ok, raport = codex_pakiet.zainstaluj()
        self.assertFalse(ok)
        self.assertEqual((cudzy / "SKILL.md").read_text(encoding="utf-8"), "---\nname: sf-wpis\n---\ncudzy\n")
        self.assertFalse(stary.exists())
        self.assertTrue((dom / ".agents" / "skills" / "sf-zglos" / "SKILL.md").is_file())
        self.assertTrue(any("POMINIĘTE" in r and "sf-wpis" in r for r in raport))

    def test_odswiez_tylko_gdy_zainstalowany(self):
        self._dom()
        self.assertEqual(codex_pakiet.odswiez(), [])
        codex_pakiet.zainstaluj()
        self.assertTrue(codex_pakiet.odswiez())


if __name__ == "__main__":
    unittest.main()
