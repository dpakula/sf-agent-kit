"""Kit 0.22.0: `zadania <sprawa>`, `zlec --json`, `sprawa --wpis` po id bloku z osi (ADVERTPR-1420).

v1.0.0 (24.11.2026) - APro Agents / klaudiusz-general

CZEGO PILNUJĄ
· lista zadań sprawy czyta WSZYSTKIE strony (290 zadań = 2 strony), bez dubli, nigdy `limit` > 200;
· rozjazd liczby z `total` → drugi przebieg, dalej rozjazd → `kompletne: false` i kod 3 (kawałek nie udaje całości);
· literówka w `--status` to błąd przed zapytaniem, nie „zero zadań”;
· bramka rozwiązania sprawy widzi otwarte zadanie spoza pierwszych 200;
· `zlec --json` oddaje `task_id`, stdout jest czystym JSON-em, nieudane doręczenie to uwaga przy kodzie 0.

Uruchomienie: `python3 -m unittest testy.test_zadania_sprawy_1420`
"""
import io
import json
import sys
import unittest
import urllib.parse
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, koordynacja, koordynator, wpisy  # noqa: E402
from sf_kit.api import BladAPI, Klient  # noqa: E402

SPRAWA = "e4dfb4a0-d4e9-450c-95a7-f355f9b8c5eb"
BLOK = "5d122e78-3d60-48ff-a5f9-50c66fd8c7b3"
WPIS = "6393f0a6-92e1-419a-a4bd-acdbffaaa02a"


def _zadanie(n: int, status: str = "queued", agent: str = "arek-localhost") -> dict:
    return {"id": f"{n:08d}-0000-4000-8000-000000000000", "external_id": f"z-{n}", "title": f"E{n}", "status": status,
            "assigned_agent_slug": agent, "ticket_ref": "ADVERTPR-1420", "body_md": "treść", "updated_at": "2026-11-24T19:00:00Z"}


def klient_z(zadania, *, total=None, totale=None):
    """Prawdziwy Klient z podmienionym transportem. `totale` = total kolejnych żądań (rozjazd w trakcie)."""
    k = Klient(baza="https://sf.test", klucz="sk_live_x")
    k.zapytania = []

    def wywolaj(metoda, sciezka, **_):
        q = dict(urllib.parse.parse_qsl(sciezka.split("?", 1)[1]))
        limit, offset = int(q["limit"]), int(q["offset"])
        if limit > 200:
            raise AssertionError("SF odpowiada 422 na limit > 200")
        k.zapytania.append(offset)
        t = totale[min(len(k.zapytania), len(totale)) - 1] if totale else (len(zadania) if total is None else total)
        return {"items": zadania[offset:offset + limit], "total": t, "limit": limit, "offset": offset}

    k._wywolaj = wywolaj
    return k


def uruchom(argv, klient):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(cli, "_klient", return_value=klient), \
            mock.patch.object(cli.konfiguracja, "wczytaj", return_value=SimpleNamespace(adres="https://sf.test")), \
            redirect_stdout(out), redirect_stderr(err):
        args = cli.zbuduj_parser().parse_args(argv)
        kod = args.funkcja(args)
    return kod, out.getvalue(), err.getvalue()


class TestStrony(unittest.TestCase):
    def test_wszystkie_strony(self):
        k = klient_z([_zadanie(n) for n in range(290)])
        w = k.zadania_sprawy_stronami(SPRAWA)
        self.assertEqual((len(w["zadania"]), w["razem"], w["kompletne"]), (290, 290, True))
        self.assertEqual(k.zapytania, [0, 200])

    def test_rowno_200_bez_drugiej_strony(self):
        k = klient_z([_zadanie(n) for n in range(200)])
        self.assertEqual(len(k.zadania_sprawy(SPRAWA)), 200)
        self.assertEqual(k.zapytania, [0])

    def test_zero(self):
        self.assertTrue(klient_z([]).zadania_sprawy_stronami(SPRAWA)["kompletne"])

    def test_rozjazd_naprawia_drugi_przebieg(self):
        k = klient_z([_zadanie(n) for n in range(250)], totale=[251, 251, 250, 250])
        w = k.zadania_sprawy_stronami(SPRAWA)
        self.assertTrue(w["kompletne"])
        self.assertEqual(len(w["zadania"]), 250)

    def test_duble_miedzy_stronami_zdjete_i_zgloszone(self):
        lista = [_zadanie(n) for n in range(200)] + [_zadanie(199), _zadanie(200)]
        w = klient_z(lista).zadania_sprawy_stronami(SPRAWA)
        self.assertEqual(len(w["zadania"]), 201)
        self.assertFalse(w["kompletne"])

    def test_bramka_sprawy_widzi_zadanie_z_drugiej_strony(self):
        k = klient_z([_zadanie(n, "completed") for n in range(230)] + [_zadanie(230, "in_progress")])
        k.tagi_sprawy = lambda _: []
        self.assertEqual(len(koordynacja.przeszkody_rozwiazania(k, SPRAWA)), 1)


class TestPolecenie(unittest.TestCase):
    ZAD = [_zadanie(n, "completed" if n % 3 == 0 else "queued", "dariusz" if n % 2 else "arek") for n in range(290)]

    def test_json(self):
        kod, out, _ = uruchom(["zadania", SPRAWA, "--json"], klient_z(self.ZAD))
        d = json.loads(out)
        self.assertEqual(kod, 0)
        self.assertTrue(d["ok"])
        self.assertEqual(d["razem"], 290)
        self.assertEqual(len(d["zadania"]), 290)
        self.assertEqual(d["sprawa"], {"id": SPRAWA, "numer": "ADVERTPR-1420"})
        self.assertEqual(d["zadania"][0]["agent"], "arek")
        self.assertNotIn("body_md", d["zadania"][0])

    def test_filtry_zawezaja_liste_nie_liczby(self):
        kod, out, _ = uruchom(["zadania", SPRAWA, "--status", "completed,in_progress", "--agent-slug", "arek", "--json"],
                              klient_z(self.ZAD))
        d = json.loads(out)
        self.assertEqual({z["status"] for z in d["zadania"]}, {"completed"})
        self.assertEqual({z["agent"] for z in d["zadania"]}, {"arek"})
        self.assertEqual(d["pokazano"], len(d["zadania"]))
        self.assertEqual(sum(d["liczby"].values()), 290)

    def test_literowka_w_statusie(self):
        k = klient_z(self.ZAD)
        kod, out, err = uruchom(["zadania", SPRAWA, "--status", "done", "--json"], k)
        self.assertEqual(kod, 2)
        self.assertFalse(json.loads(out)["ok"])
        self.assertIn("completed", err)
        self.assertEqual(k.zapytania, [])

    def test_niekompletna_lista_kod_3(self):
        kod, out, err = uruchom(["zadania", SPRAWA, "--json"], klient_z(self.ZAD, total=999))
        d = json.loads(out)
        self.assertEqual(kod, 3)
        self.assertFalse(d["ok"])
        self.assertFalse(d["kompletne"])
        self.assertIn("Ponów", err)

    def test_pelne_niesie_rekord_sf(self):
        _, out, _ = uruchom(["zadania", SPRAWA, "--pelne", "--json"], klient_z(self.ZAD[:2]))
        self.assertEqual(json.loads(out)["zadania"][0]["body_md"], "treść")

    def test_tekst(self):
        kod, out, _ = uruchom(["zadania", SPRAWA, "--status", "completed"], klient_z(self.ZAD[:6]))
        self.assertEqual(kod, 0)
        self.assertIn("Zadania sprawy ADVERTPR-1420: 6 (queued 4 · completed 2)", out)
        self.assertIn(self.ZAD[0]["id"], out)
        self.assertNotIn(self.ZAD[1]["id"], out)


class TestZlecJson(unittest.TestCase):
    def _zlec(self, *dodatkowe, doreczenie=None, zalozenie=None):
        k = mock.Mock()
        k.sprawa.return_value = {"ticket_prefix": "AUT", "ticket_number": 12}
        k.zaloz_zadanie.return_value = {"id": "uuid-zadania", "external_id": "SF-T-1", "status": "queued", "title": "T"}
        k.zaloz_zadanie.side_effect = zalozenie
        k.wiadomosc_do.side_effect = doreczenie
        agent = SimpleNamespace(slug="kodeks", user_id="u")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli, "_koordynator", return_value=(k, SimpleNamespace(slug="autera"))), \
                mock.patch.object(cli.konfiguracja, "wczytaj", return_value=SimpleNamespace(adres="https://sf.test")), \
                mock.patch.object(koordynator, "flota", return_value=[]), \
                mock.patch.object(koordynator, "znajdz_agenta", return_value=agent), \
                mock.patch.object(koordynator, "sprawdz_sprawe_dla_wykonawcy"), \
                redirect_stdout(out), redirect_stderr(err):
            args = cli.zbuduj_parser().parse_args(
                ["zlec", "--tytul", "T", "--agent-slug", "kodeks", "--sprawa", SPRAWA, "--tresc", "x", *dodatkowe])
            kod = args.funkcja(args)
        return kod, out.getvalue(), err.getvalue(), k

    def test_json_ma_task_id(self):
        kod, out, _, k = self._zlec("--json", "--dostarcz")
        d = json.loads(out)
        self.assertEqual(kod, 0)
        self.assertEqual((d["ok"], d["task_id"], d["external_id"]), (True, "uuid-zadania", "SF-T-1"))
        self.assertTrue(d["doreczone"])
        self.assertEqual(d["uwagi"], [])

    def test_nieudane_doreczenie_to_uwaga_nie_blad(self):
        kod, out, err, k = self._zlec("--json", "--dostarcz", doreczenie=BladAPI("404"))
        d = json.loads(out)
        self.assertEqual((kod, d["ok"], d["task_id"], d["doreczone"]), (0, True, "uuid-zadania", False))
        self.assertEqual(len(d["uwagi"]), 1)
        self.assertEqual(k.zaloz_zadanie.call_count, 1)

    def test_nieudane_zalozenie_json_na_stdout(self):
        kod, out, _, _ = self._zlec("--json", zalozenie=BladAPI("403"))
        self.assertEqual(kod, 1)
        self.assertFalse(json.loads(out)["ok"])

    def test_tekst_tez_pokazuje_id(self):
        _, out, _, _ = self._zlec()
        self.assertIn("id zadania: uuid-zadania", out)
        self.assertIn("Zlecone: SF-T-1 → kodeks", out)


class TestWpisPoIdBloku(unittest.TestCase):
    def _klient(self):
        k = mock.Mock()
        k.wpisy_sprawy.return_value = {"pozycje": [{"id": WPIS}]}
        k.os_obiektu.return_value = {"entries": [{"id": BLOK, "native_entry_id": WPIS}], "next_cursor": None}

        def wpis(_, wid):
            if wid != WPIS:
                raise BladAPI("nie ma", kod=404)
            return {"id": WPIS}
        k.wpis_sprawy.side_effect = wpis
        return k

    def test_skrot_i_pelny_id_bloku(self):
        for wskazanie in ("5d122e78", BLOK):
            self.assertEqual(cli._wpis_albo_blok(self._klient(), SPRAWA, wskazanie)[0], WPIS)

    def test_id_dziennika_nie_pyta_osi(self):
        k = self._klient()
        self.assertEqual(cli._wpis_albo_blok(k, SPRAWA, WPIS[:8])[0], WPIS)
        k.os_obiektu.assert_not_called()

    def test_nieznany_zostaje_bledem(self):
        with self.assertRaises(wpisy.ZlyWpis):
            cli._wpis_albo_blok(self._klient(), SPRAWA, "deadbeef")

    def test_niejednoznaczny_skrot_nie_schodzi_do_osi(self):
        k = self._klient()
        k.wpisy_sprawy.return_value = {"pozycje": [{"id": BLOK}, {"id": BLOK[:-1] + "4"}]}
        with self.assertRaises(wpisy.ZlyWpis):
            cli._wpis_albo_blok(k, SPRAWA, "5d122e78")
        k.os_obiektu.assert_not_called()


if __name__ == "__main__":
    unittest.main()
