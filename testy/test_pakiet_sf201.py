"""Kit 0.16.0 (SF-201): pakiet dla Claude Code z JEDNEGO manifestu — strażnik i generator.

v1.0.0 (02.10.2026) - APro Agents / borys-sf · projekt: wpis 33cda66a; GO Damiana (SF-203)

CZEGO PILNUJĄ
· Każda komenda manifestu wskazuje ISTNIEJĄCĄ podkomendę `sf-kit` (parser, nie lista z pamięci).
· Komendy, aliasy i skille nie kolidują (jedna przestrzeń nazw pluginu `/sf-kit:…`).
· `plugin/`, `.claude-plugin/marketplace.json` i tabela w AGENT.md = dokładnie to, co daje manifest.
· Alias niesie TĘ SAMĄ instrukcję co komenda kanoniczna; komend model sam nie wywołuje.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import WERSJA, pakiet  # noqa: E402

KORZEN = Path(__file__).resolve().parents[1]


class TestStraznik(unittest.TestCase):
    def setUp(self):
        self.manifest = pakiet.wczytaj()
        self.podkomendy = pakiet._podkomendy()

    def test_prawdziwy_manifest_bez_bledow(self):
        self.assertEqual(pakiet.waliduj(self.manifest, self.podkomendy), [])

    def test_repo_zgodne_z_manifestem(self):
        self.assertEqual(pakiet.roznice(), [], "uruchom `python3 -m sf_kit.pakiet --zapisz`")

    def test_nieistniejaca_podkomenda(self):
        m = copy.deepcopy(self.manifest)
        m["komendy"][0]["cli"] = "nie-ma-takiej"
        self.assertTrue(any("nie-ma-takiej" in b for b in pakiet.waliduj(m, self.podkomendy)))

    def test_kolizja_komendy_ze_skillem_i_aliasem(self):
        m = copy.deepcopy(self.manifest)
        m["komendy"][0]["aliasy"] = [m["skille"][0]["id"]]
        m["komendy"][1]["aliasy"] = [m["komendy"][2]["id"]]
        bledy = pakiet.waliduj(m, self.podkomendy)
        self.assertEqual(sum("zajęta" in b for b in bledy), 2)

    def test_zla_nazwa_brak_skilla_brak_pliku(self):
        m = copy.deepcopy(self.manifest)
        m["komendy"][0]["id"] = "Sprawy Wielkie"
        m["komendy"][1]["skille"] = ["nie-ma"]
        m["skille"][0]["zrodlo"] = "pakiet/wiedza/nie-ma.md"
        bledy = " | ".join(pakiet.waliduj(m, self.podkomendy))
        for fragment in ("dozwolone małe litery", "skill „nie-ma”", "brak pliku źródłowego"):
            self.assertIn(fragment, bledy)


class TestGenerator(unittest.TestCase):
    def setUp(self):
        self.manifest = pakiet.wczytaj()
        self.pliki = pakiet.generuj(self.manifest, WERSJA)

    def test_alias_ta_sama_instrukcja(self):
        kanon = self.pliki[Path("plugin/commands/report-work.md")]
        alias = self.pliki[Path("plugin/commands/zglos.md")]
        self.assertEqual(kanon.split("---", 2)[2], alias.split("---", 2)[2])
        self.assertIn("to samo co /sf-kit:report-work", alias)

    def test_komendy_tylko_czlowiek_wywoluje(self):
        komendy = [t for p, t in self.pliki.items() if p.parts[:2] == ("plugin", "commands")]
        self.assertTrue(komendy)
        for t in komendy:
            self.assertIn("disable-model-invocation: true", t)
            self.assertIn('allowed-tools: "Bash(sf-kit:*), PowerShell(sf-kit *)"', t)

    def test_odpowiedz_ostrzega_ze_widzi_klient(self):
        self.assertIn("domyślnie widzi to klient", self.pliki[Path("plugin/commands/odpowiedz.md")])

    def test_skill_ma_name_i_description_i_tresc_z_wiedzy(self):
        tresc = self.pliki[Path("plugin/skills/wpis-czytelny/SKILL.md")]
        self.assertIn('name: "wpis-czytelny"', tresc)
        self.assertIn("description:", tresc)
        self.assertIn("Wzmianka działa tylko pełnym adresem", tresc)

    def test_wersja_pluginu_i_marketplace_to_wersja_kita(self):
        plugin = json.loads(self.pliki[Path("plugin/.claude-plugin/plugin.json")])
        rynek = json.loads(self.pliki[Path(".claude-plugin/marketplace.json")])
        self.assertEqual(plugin["version"], WERSJA)
        self.assertEqual(rynek["plugins"][0], {**rynek["plugins"][0], "name": "sf-kit",
                                               "source": "./plugin", "version": WERSJA})

    def test_role_filtruja(self):
        m = copy.deepcopy(self.manifest)
        m["komendy"][0]["rola"] = "asystent"
        pliki = pakiet.generuj(m, WERSJA, role=("wszyscy",))
        self.assertNotIn(Path(f"plugin/commands/{m['komendy'][0]['id']}.md"), pliki)

    def test_readme_sekcja_podmieniana_nie_dopisywana(self):
        tabela = pakiet.tabela_readme(self.manifest)
        raz = pakiet.wstaw_do_readme("# Kit\n", tabela)
        dwa = pakiet.wstaw_do_readme(raz, tabela)
        self.assertEqual(raz, dwa)
        self.assertEqual(raz.count(pakiet.README_START), 1)

    def test_zapis_usuwa_osierocone_pliki(self):
        with tempfile.TemporaryDirectory() as d:
            korzen = Path(d)
            (korzen / "pakiet" / "wiedza").mkdir(parents=True)
            for plik in ("pakiet/komendy.json", pakiet.PLIK_TABELI, *[s["zrodlo"] for s in self.manifest["skille"]]):
                (korzen / plik).write_text((KORZEN / plik).read_text(encoding="utf-8"), encoding="utf-8")
            sierota = korzen / "plugin" / "commands" / "stara-komenda.md"
            sierota.parent.mkdir(parents=True)
            sierota.write_text("x", encoding="utf-8")
            pakiet.zapisz(korzen)
            self.assertFalse(sierota.exists())
            self.assertEqual(pakiet.roznice(korzen), [])


if __name__ == "__main__":
    unittest.main()
