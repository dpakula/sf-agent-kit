"""Pełna treść świeżego wpisu na dużej sprawie + link po numerze (ADVERTPR-1395, Kit 0.20.3).

v0.1 (23.11.2026) - APro Agents / borys-sf

USTERKI, KTÓRYCH TO PILNUJE (zgłoszenie klaudiusza-seco 20.11, ADVERTPR-1362 z 243 wpisami)
1. Karta sprawy (`GET /tickets/{id}`) oddaje 200 NAJSTARSZYCH wpisów. `sprawa`, `sprawa --json`
   i kontekst workera pokazywały „ostatnie wpisy” z 19.11, a wpis z 20.11 nie istniał.
2. `blok <id>` drukował `tresc` z rdzenia, ucinaną przez SF do 400 znaków (wpis miał 5290).
3. `wpis-wersje --pelne` spłaszczał meldunek z 38 wierszy do jednej linii.
4. Link `https://…/tickets/numer/SECO-329?org=…` kończył się „nie rozumiem”.

Atrapy podmieniają klienta; sieci nie ma.
Uruchomienie: `python3 -m unittest testy.test_pelna_tresc_1395` (albo `discover -s testy`)
"""
import argparse
import io
import sys
import unittest
from contextlib import ExitStack
from unittest import mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, flow, kontekst, wpisy  # noqa: E402
from sf_kit.api import BladAPI  # noqa: E402

SPRAWA = "d6bcfa35-f4a9-493d-b917-b029dc6d1e7f"


def _podmiany(klient) -> ExitStack:
    stos = ExitStack()
    stos.enter_context(mock.patch.object(cli.konfiguracja, "wczytaj", lambda: object()))
    stos.enter_context(mock.patch.object(cli, "_klient", lambda konf, a: klient))
    return stos


def _wpis(n: int) -> dict:
    return {"id": f"{n:08d}-0000-4000-8000-000000000000", "entry_type": "note",
            "created_at": f"2026-11-{1 + n // 20:02d}T{n % 20:02d}:00:00Z",
            "content": f"wpis {n}", "visibility": "internal", "attachments": []}


class AtrapaDziennika:
    """Karta z 200 najstarszymi wpisami, dziennik ze wszystkimi — jak SF 23.11."""

    def __init__(self, ile: int):
        self.wszystkie = [_wpis(n) for n in range(ile)]
        self.pytania: list[tuple[int, int]] = []

    def sprawa(self, ticket_id):
        return {"id": SPRAWA, "ticket_prefix": "ADVERTPR", "ticket_number": 1362,
                "status": "open", "priority": "medium", "entries": self.wszystkie[:200]}

    def wpisy_sprawy(self, ticket_id, *, limit=100, offset=0):
        self.pytania.append((limit, offset))
        return {"razem": len(self.wszystkie), "limit": limit, "offset": offset,
                "pozycje": self.wszystkie[offset:offset + limit]}


# ── 1. dziennik dociągany ponad 200 ────────────────────────────────────────────────────

def test_karta_z_200_wpisami_dostaje_pelny_dziennik():
    klient = AtrapaDziennika(243)
    karta = klient.sprawa(SPRAWA)
    assert kontekst.uzupelnij_dziennik(klient, karta) == 243
    assert len(karta["entries"]) == 243
    assert karta["entries"][-1]["content"] == "wpis 242"
    assert klient.pytania == [(200, 0), (200, 200)]


def test_mala_sprawa_nie_pyta_dziennika():
    klient = AtrapaDziennika(12)
    karta = klient.sprawa(SPRAWA)
    assert kontekst.uzupelnij_dziennik(klient, karta) is None
    assert klient.pytania == []


def test_blad_dziennika_zostawia_karte():
    class Pada(AtrapaDziennika):
        def wpisy_sprawy(self, *a, **k):
            raise BladAPI("x", kod=500)

    klient = Pada(243)
    karta = klient.sprawa(SPRAWA)
    assert kontekst.uzupelnij_dziennik(klient, karta) is None
    assert len(karta["entries"]) == 200


def test_ostatnie_wpisy_w_kontekscie_sa_najswiezsze_i_maja_id():
    klient = AtrapaDziennika(243)
    karta = klient.sprawa(SPRAWA)
    kontekst.uzupelnij_dziennik(klient, karta)
    tekst = kontekst._tekst(karta, kontekst.Pakiet(), Path.cwd())
    assert "wpis 242" in tekst and "wpis 199" not in tekst
    assert "[00000242]" in tekst


def test_polecenie_sprawa_json_ma_pelny_dziennik():
    klient = AtrapaDziennika(243)
    args = argparse.Namespace(sprawa="ADVERTPR-1362", org=None, status=None, kind=None,
                              tylko_id=False, json=True, wszystkie=False)
    wy, err = io.StringIO(), io.StringIO()
    with _podmiany(klient), \
            mock.patch.object(cli, "_sprawa_dla_zapisu", lambda k, w: ({"id": SPRAWA}, "")), \
            redirect_stdout(wy), redirect_stderr(err):
        assert cli.polecenie_sprawa(args) == 0
    import json
    assert len(json.loads(wy.getvalue())["entries"]) == 243
    assert "243 wpisów" in err.getvalue()


# ── 2. blok: pełna treść z dziennika ───────────────────────────────────────────────────

class AtrapaBloku:
    def __init__(self, blok: dict, pelna: str | None = None, blad: Exception | None = None):
        self._blok, self._pelna, self._blad = blok, pelna, blad
        self.wolania: list[tuple] = []

    def blok(self, blok_id):
        return self._blok

    def wpis_sprawy(self, ticket_id, entry_id):
        self.wolania.append((ticket_id, entry_id))
        if self._blad:
            raise self._blad
        return {"id": entry_id, "content": self._pelna}


BLOK = "374b3be5-562c-4410-b498-3003be52fb24"
NATYWNY = "3bf3d863-c7b5-4ae8-bf41-6b561b237afa"


def _blok(tresc: str, **nadpisz) -> dict:
    b = {"id": BLOK, "natywny_id": NATYWNY, "kotwica_typ": "ticket", "kotwica_id": SPRAWA,
         "rodzaj": "notatka", "widocznosc": "internal", "tresc": tresc, "z_rdzenia": True}
    b.update(nadpisz)
    return b


def _blok_uruchom(klient) -> str:
    wy = io.StringIO()
    with _podmiany(klient), redirect_stdout(wy), redirect_stderr(io.StringIO()):
        assert cli.polecenie_blok(argparse.Namespace(co=BLOK, json=False)) == 0
    return wy.getvalue()


def test_blok_uciety_przez_rdzen_dociaga_pelna_tresc():
    pelna = "## Nagłówek\n\n" + "x" * 5000 + "\nOSTATNI WIERSZ"
    klient = AtrapaBloku(_blok(pelna[:400]), pelna=pelna)
    wynik = _blok_uruchom(klient)
    assert "OSTATNI WIERSZ" in wynik
    assert klient.wolania == [(SPRAWA, NATYWNY)]


def test_krotki_blok_nie_pyta_dziennika():
    klient = AtrapaBloku(_blok("krótko"), pelna="nie to")
    assert "krótko" in _blok_uruchom(klient)
    assert klient.wolania == []


def test_blok_spoza_sprawy_mowi_o_limicie():
    klient = AtrapaBloku(_blok("y" * 400, kotwica_typ="deal"), pelna="nie to")
    wynik = _blok_uruchom(klient)
    assert "najwyżej 400 znaków" in wynik and klient.wolania == []


def test_odmowa_dziennika_zostawia_tresc_rdzenia():
    klient = AtrapaBloku(_blok("z" * 400), blad=BladAPI("nie", kod=404))
    wynik = _blok_uruchom(klient)
    assert "z" * 400 in wynik and "najwyżej 400 znaków" in wynik


# ── 3. wpis-wersje --pelne zachowuje wiersze ───────────────────────────────────────────

def test_pelne_zachowuje_wiersze_a_skrot_splaszcza():
    wpis = {"id": NATYWNY, "content": "pierwszy\n\n- punkt\n- drugi", "edited_count": 0}
    pelne = wpisy.historia_do_pokazania(wpis, [], skrot=0)
    assert "  pierwszy\n  \n  - punkt\n  - drugi" in pelne
    assert "pierwszy - punkt - drugi" in wpisy.historia_do_pokazania(wpis, [], skrot=160)


# ── 4. link po numerze ─────────────────────────────────────────────────────────────────

def test_link_po_numerze_daje_numer_i_organizacje():
    link = "https://sales-forge.pl/tickets/numer/SECO-329?org=58a67774-c077-4d2a-9fbd-e7a05da569e4"
    assert flow.numer_z_linku(link) == "SECO-329"
    assert flow.organizacja_z_linku(link) == "58a67774-c077-4d2a-9fbd-e7a05da569e4"
    assert flow.sprawa_z_linku(link) is None       # to nie uuid — nie udajemy identyfikatora


def test_rozwin_link_numeru_ustawia_org_gdy_nie_podano():
    args = argparse.Namespace(sprawa="https://sales-forge.pl/tickets/numer/seco-329?org=seco", org=None)
    flow.rozwin_link_numeru(args)
    assert (args.sprawa, args.org) == ("seco-329", "seco")


def test_jawne_org_wygrywa_z_linkiem():
    args = argparse.Namespace(sprawa="https://x.test/tickets/numer/FM-12?org=inna", org="advertpro-co")
    flow.rozwin_link_numeru(args)
    assert (args.sprawa, args.org) == ("FM-12", "advertpro-co")


def test_numer_i_link_z_uuid_bez_zmian():
    uuid_link = f"https://x.test/tickets/{SPRAWA}?org=sf"
    for wartosc in ("FM-12", uuid_link, "https://x.test/tickets/numer/FM-12 i coś dalej"):
        args = argparse.Namespace(sprawa=wartosc, org=None)
        flow.rozwin_link_numeru(args)
        assert args.sprawa == wartosc and args.org is None


class TestyADVERTPR1395(unittest.TestCase):
    """Funkcje `test_*` modułu jako przypadki unittest — pakiet Kita biegnie przez `unittest discover`."""


for _nazwa, _f in list(globals().items()):
    if _nazwa.startswith("test_") and callable(_f):
        setattr(TestyADVERTPR1395, _nazwa, staticmethod(_f))

if __name__ == "__main__":
    unittest.main()
