"""Kit 0.16.0 (SF-203): `sf-kit mcp` — serwer MCP stdio nad tym samym kodem co CLI; rejestracja w Codexie.

v1.0.0 (02.10.2026) - APro Agents / borys-sf · Agata 14:36

Na żywo sprawdzone 02.10: mały klient stdio (initialize → tools/list → tools/call `status` = whoami na
prawdziwym SF, isError false); `claude --plugin-dir ./plugin mcp list` → `plugin:sf-kit:sf-kit ✔ Connected`.
Tu pilnujemy protokołu i granic bez sieci (podproces podmieniony).

CZEGO PILNUJĄ
· Narzędzia = komendy manifestu z `mcp: true`; `update` NIE jest narzędziem; `readOnlyHint` z `tylko_odczyt`.
· Wywołanie = `sf-kit <cli> <argumenty>` jako LISTA (bez powłoki), stdin zamknięty, limit czasu.
· Powiadomienia bez odpowiedzi; zły JSON / nieznane narzędzie / złe argumenty → błąd JSON-RPC, nie wywrotka.
· Codex: `codex mcp add` gdy jest; inaczej tabela w config.toml, raz, reszta pliku zostaje.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import codex_pakiet, mcp_serwer, pakiet  # noqa: E402


class Podproces:
    def __init__(self, kod=0, wyjscie="ok"):
        self.wolania, self.kod, self.wyjscie = [], kod, wyjscie

    def __call__(self, argv, **kw):
        self.wolania.append((argv, kw))
        return SimpleNamespace(returncode=self.kod, stdout=self.wyjscie, stderr="")


def _rozmowa(wiadomosci, uruchom=None):
    wejscie = io.StringIO("".join(json.dumps(w) + "\n" for w in wiadomosci))
    wyjscie = io.StringIO()
    mcp_serwer.petla(wejscie, wyjscie, manifest=pakiet.wczytaj(), uruchom=uruchom or Podproces())
    return [json.loads(l) for l in wyjscie.getvalue().splitlines()]


class TestProtokol(unittest.TestCase):
    def test_initialize_i_powiadomienie_bez_odpowiedzi(self):
        odp = _rozmowa([{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-06-18"}},
                        {"jsonrpc": "2.0", "method": "notifications/initialized"}])
        self.assertEqual(len(odp), 1)
        self.assertEqual(odp[0]["result"]["serverInfo"]["name"], "sf-kit")
        self.assertIn("tools", odp[0]["result"]["capabilities"])

    def test_lista_z_manifestu_bez_update_z_adnotacjami(self):
        narz = {t["name"]: t for t in _rozmowa([{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])[0]["result"]["tools"]}
        m = pakiet.wczytaj()
        oczekiwane = {k["id"].replace("-", "_") for k in m["komendy"] if k["mcp"] and k["rola"] == "wszyscy"}
        self.assertEqual(set(narz), oczekiwane)
        self.assertNotIn("update", narz)
        self.assertTrue(narz["cases"]["annotations"]["readOnlyHint"])
        self.assertFalse(narz["reply"]["annotations"]["readOnlyHint"])
        self.assertIn("argumenty", narz["report_work"]["inputSchema"]["properties"])

    def test_wywolanie_lista_argumentow_bez_powloki_stdin_zamkniety(self):
        pp = Podproces(wyjscie="SF-1 Sprawa")
        odp = _rozmowa([{"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                         "params": {"name": "case", "arguments": {"argumenty": ["SF-1; rm -rf /"]}}}], pp)
        argv, kw = pp.wolania[0]
        self.assertEqual(argv[-2:], ["sprawa", "SF-1; rm -rf /"], "argument idzie jako jeden element listy")
        self.assertNotIn("shell", kw)
        self.assertEqual(kw["stdin"], subprocess.DEVNULL)
        self.assertEqual(odp[0]["result"], {"content": [{"type": "text", "text": "SF-1 Sprawa"}], "isError": False})

    def test_kod_wyjscia_to_iserror(self):
        odp = _rozmowa([{"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                         "params": {"name": "status", "arguments": {}}}], Podproces(kod=1, wyjscie=""))
        self.assertTrue(odp[0]["result"]["isError"])

    def test_bledy_zamiast_wywrotki(self):
        wejscie = io.StringIO("nie json\n" + json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                                                          "params": {"name": "update"}}) + "\n"
                              + json.dumps({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                                            "params": {"name": "case", "arguments": {"argumenty": "SF-1"}}}) + "\n"
                              + json.dumps({"jsonrpc": "2.0", "id": 7, "method": "resources/list"}) + "\n")
        wyjscie = io.StringIO()
        mcp_serwer.petla(wejscie, wyjscie, manifest=pakiet.wczytaj(), uruchom=Podproces())
        kody = [json.loads(l)["error"]["code"] for l in wyjscie.getvalue().splitlines()]
        self.assertEqual(kody, [-32700, -32602, -32602, -32601])


class TestStraznikMcp(unittest.TestCase):
    def test_update_jako_narzedzie_zapala_straznika(self):
        m = pakiet.wczytaj()
        for k in m["komendy"]:
            if k["id"] == "update":
                k["mcp"] = True
        self.assertTrue(any("nie może być narzędziem MCP" in b for b in pakiet.waliduj(m, pakiet._podkomendy())))

    def test_plugin_ma_mcp_json(self):
        pliki = pakiet.generuj(pakiet.wczytaj(), "0.0.0")
        self.assertEqual(json.loads(pliki[Path("plugin/.mcp.json")]), pakiet.MCP_SERWER)


class TestRejestracjaCodex(unittest.TestCase):
    def test_z_codex_wola_mcp_add(self):
        pp = Podproces()
        with mock.patch.object(codex_pakiet.shutil, "which", return_value="/usr/bin/codex"):
            raport = codex_pakiet.zarejestruj_mcp(uruchom=pp)
        self.assertEqual(pp.wolania[0][0][1:], ["mcp", "add", "sf-kit", "--", "sf-kit", "mcp"])
        self.assertIn("zarejestrowany", raport[0])

    def test_bez_codex_tabela_raz_reszta_zostaje(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict("os.environ", {"CODEX_HOME": d}), \
                mock.patch.object(codex_pakiet.shutil, "which", return_value=None):
            plik = Path(d) / "config.toml"
            plik.write_text('model = "gpt-5"\n', encoding="utf-8")
            codex_pakiet.zarejestruj_mcp()
            codex_pakiet.zarejestruj_mcp()
            tresc = plik.read_text(encoding="utf-8")
        self.assertTrue(tresc.startswith('model = "gpt-5"\n'))
        self.assertEqual(tresc.count(codex_pakiet.TABELA_MCP), 1)
        self.assertIn('args = ["mcp"]', tresc)


if __name__ == "__main__":
    unittest.main()
