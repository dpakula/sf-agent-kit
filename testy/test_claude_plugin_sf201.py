"""Kit 0.16.0 (SF-201): `sf-kit init --claude` / `plugin` / odświeżenie w `update` — bez prawdziwego `claude`.

v1.0.0 (02.10.2026) - APro Agents / borys-sf · decyzje Q-A (marketplace = repo Kita), Q-B (zakres użytkownika)

Na żywo sprawdzone 02.10 w izolowanym `CLAUDE_CONFIG_DIR` (claude 2.1.280): marketplace z repo,
`install --scope user`, ponowne `install`, `update` — plugin 0.16.0 widoczny w `claude plugin list`.
Tu pilnujemy zachowania Kita wokół `claude`: kolejności poleceń, zakresu, ścieżki bez `claude`
i tego, że cudzych ustawień nie psujemy.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import claude_plugin as cp  # noqa: E402


class Atrapa:
    """Udaje `subprocess.run` dla `claude plugin …`; zapisuje wywołania."""

    def __init__(self, *, zainstalowany=False, odmowa=None):
        self.wolania = []
        self.zainstalowany = zainstalowany
        self.odmowa = odmowa or set()

    def __call__(self, argv, **_):
        polecenie = " ".join(argv[1:4])
        self.wolania.append(argv[1:])
        if any(o in " ".join(argv) for o in self.odmowa):
            return SimpleNamespace(returncode=1, stdout="", stderr="błąd sieci")
        if polecenie == "plugin list --json":
            wynik = [{"id": cp.ID}] if self.zainstalowany else []
            return SimpleNamespace(returncode=0, stdout=json.dumps(wynik), stderr="")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")


class TestInstalacja(unittest.TestCase):
    def test_kolejnosc_i_zakres_uzytkownika(self):
        a = Atrapa()
        with mock.patch.object(cp, "_claude", return_value="/usr/bin/claude"):
            ok, raport = cp.zainstaluj(uruchom=a)
        self.assertTrue(ok)
        self.assertEqual(a.wolania[0][:3], ["plugin", "marketplace", "add"])
        self.assertIn("--scope", a.wolania[0])
        self.assertEqual(a.wolania[0][a.wolania[0].index("--scope") + 1], "user")
        self.assertEqual(a.wolania[1][:3], ["plugin", "install", cp.ID])
        self.assertIn("-y", a.wolania[1])
        self.assertIn("user", a.wolania[1])

    def test_blad_marketplace_zatrzymuje_i_mowi_dlaczego(self):
        a = Atrapa(odmowa={"marketplace add"})
        with mock.patch.object(cp, "_claude", return_value="/usr/bin/claude"):
            ok, raport = cp.zainstaluj(uruchom=a)
        self.assertFalse(ok)
        self.assertIn("błąd sieci", raport[-1])
        self.assertFalse(any(w[:2] == ["plugin", "install"] for w in a.wolania))

    def test_bez_claude_dopisuje_ustawienia_i_podpowiada(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict("os.environ", {"CLAUDE_CONFIG_DIR": d}), \
                mock.patch.object(cp, "_claude", return_value=None):
            plik = Path(d) / "settings.json"
            plik.write_text(json.dumps({"model": "opus", "enabledPlugins": {"inny@x": True}}), encoding="utf-8")
            ok, raport = cp.zainstaluj()
            dane = json.loads(plik.read_text(encoding="utf-8"))
        self.assertFalse(ok)
        self.assertEqual(dane["model"], "opus", "cudzych kluczy nie ruszamy")
        self.assertEqual(dane["enabledPlugins"], {"inny@x": True, cp.ID: True})
        self.assertIn(cp.MARKETPLACE, dane["extraKnownMarketplaces"])
        self.assertTrue(any("/plugin install" in r for r in raport))

    def test_zepsuty_json_nie_jest_nadpisywany(self):
        with tempfile.TemporaryDirectory() as d:
            plik = Path(d) / "settings.json"
            plik.write_text("{ nie json", encoding="utf-8")
            zdanie = cp.dopisz_ustawienia(plik)
            self.assertEqual(plik.read_text(encoding="utf-8"), "{ nie json")
        self.assertIn("NIE zmieniam", zdanie)

    def test_odswiez_tylko_gdy_zainstalowany(self):
        with mock.patch.object(cp, "_claude", return_value="/usr/bin/claude"):
            a = Atrapa(zainstalowany=False)
            self.assertEqual(cp.odswiez(uruchom=a), [])
            self.assertFalse(any(w[:2] == ["plugin", "update"] for w in a.wolania))
            a = Atrapa(zainstalowany=True)
            self.assertTrue(cp.odswiez(uruchom=a))
            self.assertTrue(any(w[:3] == ["plugin", "update", cp.ID] for w in a.wolania))


if __name__ == "__main__":
    unittest.main()
