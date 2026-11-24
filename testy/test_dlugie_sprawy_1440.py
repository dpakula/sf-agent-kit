"""Długa sprawa: oś stronami, pełna treść w `os --json` i `blok --json`, `sprawa --wpis` (ADVERTPR-1440, Kit 0.21.2).

v0.1 (24.11.2026) - APro Agents / borys-sf

USTERKI, KTÓRYCH TO PILNUJE (zgłoszenie klaudiusza-radziborza 24.11, ADVERTPR-1420 z 473 wpisami)
1. `os --limit 500` → 422 z API (limit ≤ 200), a jedna strona nie sięgała początku osi.
2. `os --json` i `blok --json` oddawały treść uciętą przez SF do 400 znaków.
3. Brak odczytu JEDNEGO wpisu w całości po id/skrócie — zostawało `--wszystkie` na setki ekranów.
4. `sprawa --ostatnie N` — N najnowszych także w `--json`.

Atrapy podmieniają klienta; sieci nie ma.
Uruchomienie: `python3 -m unittest testy.test_dlugie_sprawy_1440` (albo `discover -s testy`)
"""
import io
import json
import sys
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, kontekst  # noqa: E402

SPRAWA = "e4dfb4a0-d4e9-450c-95a7-f355f9b8c5eb"
DLUGA = "x" * 2759


def _id(n: int) -> str:
    return f"{n:08d}-0000-4000-8000-000000000000"


def _wpis(n: int) -> dict:
    return {"id": _id(n), "entry_type": "note", "created_at": f"2026-11-{1 + n // 24:02d}T{n % 24:02d}:00:00Z",
            "content": DLUGA if n % 3 == 0 else f"wpis {n}", "visibility": "internal", "attachments": []}


class AtrapaSF:
    """Sprawa z `ile` wpisami: oś od najnowszych z kursorem (limit ≤ 200, treść ucięta do 400),
    dziennik od najstarszych z offsetem (treść pełna) — kształty jak SF 24.11."""

    def __init__(self, ile: int):
        self.wpisy = [_wpis(n) for n in range(ile)]
        self.osie: list[tuple[int, str]] = []
        self.dzienniki: list[tuple[int, int]] = []

    def sprawa(self, ticket_id):
        return {"id": SPRAWA, "ticket_prefix": "ADVERTPR", "ticket_number": 1420,
                "status": "open", "priority": "medium", "entries": self.wpisy[:200]}

    def wpisy_sprawy(self, ticket_id, *, limit=100, offset=0):
        self.dzienniki.append((limit, offset))
        return {"razem": len(self.wpisy), "pozycje": self.wpisy[offset:offset + limit]}

    def wpis_sprawy(self, ticket_id, entry_id):
        return next(dict(w) for w in self.wpisy if w["id"] == entry_id)

    def os_obiektu(self, typ, sprawa_id, *, pelna=True, rozwin="", limit=50, kursor=""):
        if limit > 200:
            raise AssertionError("SF odpowiada 422 na limit > 200")
        self.osie.append((limit, kursor))
        od_najnowszych = list(reversed(self.wpisy))
        start = int(kursor or 0)
        strona = od_najnowszych[start:start + limit]
        dalej = str(start + limit) if start + limit < len(od_najnowszych) else None
        return {"entity_type": "ticket", "entity_id": sprawa_id, "next_cursor": dalej,
                "entries": [{"typ": "blok", "id": f"os-{w['id']}", "native_entry_id": w["id"],
                             "content": w["content"][:400]} for w in strona]}

    def blok(self, blok_id):
        w = self.wpisy[0]
        return {"id": blok_id, "rodzaj": "note", "tresc": w["content"][:400], "kotwica_typ": "ticket",
                "kotwica_id": SPRAWA, "natywny_id": w["id"], "z_rdzenia": True}


def _uruchom(klient, argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with ExitStack() as stos:
        stos.enter_context(mock.patch.object(cli.konfiguracja, "wczytaj", lambda: object()))
        stos.enter_context(mock.patch.object(cli, "_klient", lambda konf, a: klient))
        stos.enter_context(mock.patch.object(cli.asystent, "znajdz_sprawe",
                                              lambda k, w: k.sprawa(w)))
        stos.enter_context(mock.patch.object(cli, "_pokaz_do_ciebie", lambda *a, **k: None))
        args = cli.zbuduj_parser().parse_args(argv)
        with redirect_stdout(out), redirect_stderr(err):
            kod = args.funkcja(args)
    return kod, out.getvalue(), err.getvalue()


class OsStronami(unittest.TestCase):
    def test_limit_ponad_200_idzie_kursorem_bez_422(self):
        sf = AtrapaSF(473)
        kod, out, _ = _uruchom(sf, ["os", "ADVERTPR-1420", "--limit", "450", "--json"])
        self.assertEqual(kod, 0)
        dane = json.loads(out)
        self.assertEqual(len(dane["entries"]), 450)
        self.assertEqual([l for l, _ in sf.osie], [200, 200, 50])
        self.assertTrue(dane["next_cursor"])

    def test_wszystkie_do_konca_osi(self):
        sf = AtrapaSF(473)
        kod, out, _ = _uruchom(sf, ["os", "ADVERTPR-1420", "--wszystkie", "--json"])
        dane = json.loads(out)
        self.assertEqual(len(dane["entries"]), 473)
        self.assertIsNone(dane["next_cursor"])
        self.assertEqual(dane["entries"][-1]["native_entry_id"], _id(0))

    def test_json_uzupelnia_tresc_z_dziennika_jednym_przebiegiem(self):
        sf = AtrapaSF(473)
        _, out, _ = _uruchom(sf, ["os", "ADVERTPR-1420", "--limit", "200", "--json"])
        dlugie = [e for e in json.loads(out)["entries"] if e.get("tresc_z_dziennika")]
        self.assertTrue(dlugie)
        self.assertTrue(all(len(e["content"]) == len(DLUGA) for e in dlugie))
        self.assertEqual(sf.dzienniki, [(200, 0), (200, 200), (200, 400)])

    def test_bez_dlugich_wierszy_dziennik_nie_jest_czytany(self):
        sf = AtrapaSF(5)
        for w in sf.wpisy:
            w["content"] = "krótko"
        _uruchom(sf, ["os", "ADVERTPR-1420", "--json"])
        self.assertEqual(sf.dzienniki, [])

    def test_odmowa_dziennika_nie_psuje_osi(self):
        sf = AtrapaSF(10)

        def odmowa(*a, **k):
            raise cli.BladAPI("brak dostępu", kod=403)
        sf.wpisy_sprawy = odmowa
        kod, out, _ = _uruchom(sf, ["os", "ADVERTPR-1420", "--json"])
        self.assertEqual(kod, 0)
        self.assertEqual(len(json.loads(out)["entries"]), 10)

    def test_limit_zero_odmawia(self):
        kod, _, err = _uruchom(AtrapaSF(3), ["os", "ADVERTPR-1420", "--limit", "0"])
        self.assertEqual(kod, 2)
        self.assertIn("co najmniej 1", err)


class BlokJson(unittest.TestCase):
    def test_json_ma_pelna_tresc_wpisu_sprawy(self):
        sf = AtrapaSF(3)
        kod, out, _ = _uruchom(sf, ["blok", "eb7d8ad7-4890-4543-b948-ec5f54548d66", "--json"])
        self.assertEqual(kod, 0)
        dane = json.loads(out)
        self.assertEqual(len(dane["tresc"]), len(DLUGA))
        self.assertTrue(dane["tresc_z_dziennika"])


class JedenWpis(unittest.TestCase):
    def test_skrot_z_nawiasu_daje_caly_wpis(self):
        sf = AtrapaSF(473)
        kod, out, _ = _uruchom(sf, ["sprawa", "ADVERTPR-1420", "--wpis", _id(471)[:8]])
        self.assertEqual(kod, 0)
        self.assertIn(DLUGA, out)
        self.assertIn(f"{len(DLUGA)} znaków", out)

    def test_json_to_sam_wpis(self):
        sf = AtrapaSF(10)
        _, out, _ = _uruchom(sf, ["sprawa", "ADVERTPR-1420", "--wpis", _id(9), "--json"])
        self.assertEqual(json.loads(out)["id"], _id(9))

    def test_nieznany_skrot_to_komunikat_nie_traceback(self):
        kod, _, err = _uruchom(AtrapaSF(10), ["sprawa", "ADVERTPR-1420", "--wpis", "ffffffff"])
        self.assertEqual(kod, 1)
        self.assertIn("ffffffff", err)


class Ostatnie(unittest.TestCase):
    def test_json_ostatnie_n_najnowszych(self):
        sf = AtrapaSF(473)
        _, out, _ = _uruchom(sf, ["sprawa", "ADVERTPR-1420", "--ostatnie", "3", "--json"])
        self.assertEqual([e["id"] for e in json.loads(out)["entries"]], [_id(470), _id(471), _id(472)])

    def test_tekst_ostatnie_n_i_podpowiedz_wszystkie(self):
        _, out, _ = _uruchom(AtrapaSF(473), ["sprawa", "ADVERTPR-1420", "--ostatnie", "2"])
        self.assertIn("Ostatnie wpisy (2 z 473", out)
        self.assertIn("--wszystkie`", out)

    def test_dziennik_po_200_bez_zmian(self):
        self.assertEqual(kontekst.WPISOW_W_KARCIE, 200)


if __name__ == "__main__":
    unittest.main()
