"""Kit 0.18.0: konsola koordynatora, wiadomości ze wszystkich Organizacji, tagi, dziennik audytu.

v1.0.0 (03.11.2026) - APro Agents / klaudiusz-general · SF-486 krok 2 (Agata alfa-testerką koordynatora)

CZEGO PILNUJĄ
· Blok: brak sprawy źródłowej („null”) = brak bloku; dubel z tą samą kotwicą < 2 h = stary blok,
  zero POST; opcje „A) … · B) …” z treści (etykieta ≤ 80); „Zastępuje …” bez istniejącego #N odcięte.
· Lustro: kanał konsoli Organizacji sprawy wyłączony → kotwica na kroku + wpis `konsola`; bez kroku odmowa.
· Odbiór wiadomości: `/recipients/me`, a przy 404 dyspozycja bez adresata → `PATCH /console/messages/{id}`.
· Tag typu jednokrotnego: odmowa przy innym tagu tego typu, `--zamien` zdejmuje stary.
· Dziennik audytu: wiersz w formacie `sf_audit.log` floty, czytelny dla parsera `tematy.py`; tylko zapisy.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import audyt, konsola  # noqa: E402
from sf_kit.api import BladAPI  # noqa: E402

ORG_A = "289cef06-b8b9-4a0c-967f-2533b08e82c4"
ORG_K = "58a67774-c077-4d2a-9fbd-e7a05da569e4"
SPRAWA = "46aea40a-4a3e-4923-85c3-8a1b0406a5c5"
KROK = "cdc7af07-435a-4874-8660-456d423c685c"


class Toz:
    organizacje: list = []
    z_nadaniami: list = []

    def znajdz(self, w):
        return None


class AtrapaKonsoli:
    """Klient z pamięcią: bloki, kanał, wpisy, wiadomości, tagi — bez sieci."""

    def __init__(self, organizacja=ORG_A, *, bloki=None, kanal=True, odrzuc_obca=False, wspolne=None):
        self.organizacja = organizacja
        self.w = wspolne if wspolne is not None else {
            "bloki": list(bloki or []), "posty": [], "wpisy": [], "kanal": kanal,
            "odrzuc_obca": odrzuc_obca, "patch_wiad": [], "ack": [], "tagi": [], "zdjete": [], "nadane": []}

    def w_organizacji(self, org):
        return AtrapaKonsoli(org, wspolne=self.w)

    def bloki(self, **f):
        out = list(self.w["bloki"])
        if f.get("numer") is not None:
            out = [b for b in out if b.get("numer") == f"#{f['numer']}"]
        if f.get("anchor_id"):
            out = [b for b in out if (b.get("context_anchor") or {}).get("id") == f["anchor_id"]]
        return out

    def blok_konsoli(self, bid):
        return next(b for b in self.w["bloki"] if b["id"] == bid)

    def kanal_konsoli(self):
        return self.w["kanal"]

    def zaloz_blok(self, cialo):
        kotwica = cialo.get("context_anchor") or {}
        if self.w["odrzuc_obca"] and kotwica.get("tenant") not in (None, self.organizacja):
            raise BladAPI("autor nie jest członkiem", kod=422)
        self.w["posty"].append(cialo)
        b = {"id": f"b{len(self.w['posty'])}", "numer": f"#{9000 + len(self.w['posty'])}", **cialo}
        self.w["bloki"].append(b)
        return b

    def wpis(self, sid, tresc, *, widocznosc="internal"):
        self.w["wpisy"].append((self.organizacja, sid, widocznosc, tresc))
        return {"id": "e1"}

    def potwierdz_odbior(self, mid, *, status, powod=None):
        if mid.startswith("dysp"):
            raise BladAPI("brak adresata", kod=404)
        self.w["ack"].append((self.organizacja, mid, powod))

    def zmien_wiadomosc(self, mid, *, status, notka=None):
        self.w["patch_wiad"].append((self.organizacja, mid, status, notka))

    def tagi_sprawy(self, sid):
        return self.w["tagi"]

    def zdejmij_tag(self, sid, tid):
        self.w["zdjete"].append(tid)

    def nadaj_tag(self, sid, tid):
        self.w["nadane"].append(tid)


def _blok(numer, *, kind="action", kotwica=SPRAWA, minut=10, status="open"):
    kiedy = (datetime.now(timezone.utc) - timedelta(minutes=minut)).isoformat()
    return {"id": f"id{numer}", "numer": f"#{numer}", "kind": kind, "status": status,
            "context_anchor": {"type": "ticket", "id": kotwica}, "created_at": kiedy}


def _zaloz(k, **kw):
    domyslne = dict(rodzaj="action", tresc="Decyzja: A) wdrażaj · B) czekaj", sprawa=SPRAWA, log=lambda s: None)
    domyslne.update(kw)
    return konsola.zaloz_blok(k, Toz(), **domyslne)


class TestBlok(unittest.TestCase):
    def test_null_to_brak_bloku(self):
        k = AtrapaKonsoli()
        for zle in ("null", "None", ""):
            with self.assertRaises(ValueError):
                _zaloz(k, sprawa=zle)
        self.assertEqual(k.w["posty"], [])

    def test_dubel_oddaje_stary_bez_post(self):
        k = AtrapaKonsoli(bloki=[_blok(2364)])
        blok, nowy = _zaloz(k)
        self.assertFalse(nowy)
        self.assertEqual(blok["numer"], "#2364")
        self.assertEqual(k.w["posty"], [])

    def test_stary_blok_poza_oknem_i_inny_rodzaj_to_nie_dubel(self):
        k = AtrapaKonsoli(bloki=[_blok(1, minut=180), _blok(2, kind="info")])
        _, nowy = _zaloz(k)
        self.assertTrue(nowy)
        self.assertEqual(len(k.w["posty"]), 1)

    def test_bez_dedupu_swiadomie_drugi(self):
        k = AtrapaKonsoli(bloki=[_blok(2364)])
        _, nowy = _zaloz(k, bez_dedupu=True)
        self.assertTrue(nowy)

    def test_opcje_z_tresci_i_kotwica(self):
        k = AtrapaKonsoli()
        _zaloz(k, tresc="Co robimy? A) wdrażaj teraz (rekomendowana) · B) " + "x" * 120,
               krok=KROK, effort="2min", adresat_id="u1")
        cialo = k.w["posty"][0]
        self.assertEqual([o["klucz"] for o in cialo["opcje"]], ["A", "B"])
        self.assertTrue(cialo["opcje"][0]["rekomendowana"])
        self.assertLessEqual(len(cialo["opcje"][1]["etykieta"]), konsola.ETYKIETA_MAX)
        self.assertEqual(cialo["context_anchor"], {"type": "ticket", "id": SPRAWA, "tenant": ORG_A,
                                                   "krok_id": KROK})
        self.assertEqual(cialo["effort_tag"], "2min")
        self.assertEqual(cialo["assignee_user_id"], "u1")

    def test_effort_tylko_przy_action(self):
        k = AtrapaKonsoli()
        _zaloz(k, rodzaj="info", effort="2min")
        self.assertNotIn("effort_tag", k.w["posty"][0])

    def test_zastepuje_bez_numeru_odciete_z_numerem_zostaje(self):
        k = AtrapaKonsoli(bloki=[_blok(100, kotwica="inna", minut=600)])
        _zaloz(k, tresc="Nowa wersja. Zastępuje wczorajszy blok o hasłach. Zastępuje #100.", bez_dedupu=True)
        body = k.w["posty"][0]["body"]
        self.assertNotIn("wczorajszy", body)
        self.assertIn("Zastępuje #100", body)

    def test_lustro_gdy_kanal_wylaczony(self):
        k = AtrapaKonsoli(kanal=False)
        _zaloz(k, sprawa_org=ORG_K, krok=KROK, sprawa=SPRAWA)
        self.assertEqual(k.w["posty"][0]["context_anchor"]["id"], KROK)
        org, sid, poziom, tresc = k.w["wpisy"][0]
        self.assertEqual((org, sid, poziom), (ORG_K, SPRAWA, "konsola"))
        self.assertIn("#9001", tresc)

    def test_lustro_bez_kroku_odmowa(self):
        k = AtrapaKonsoli(kanal=False)
        with self.assertRaises(ValueError):
            _zaloz(k, sprawa_org=ORG_K)
        self.assertEqual(k.w["posty"], [])

    def test_obca_kotwica_odrzucona_przechodzi_na_lustro(self):
        k = AtrapaKonsoli(odrzuc_obca=True)
        _zaloz(k, sprawa_org=ORG_K, krok=KROK)
        self.assertEqual(k.w["posty"][0]["context_anchor"]["id"], KROK)

    def test_opcje_z_argumentow(self):
        o = konsola.opcje_z_argumentow(["A=tak", "B=nie"], "A")
        self.assertEqual(o[0], {"klucz": "A", "etykieta": "tak", "rekomendowana": True})
        with self.assertRaises(ValueError):
            konsola.opcje_z_argumentow(["A"], None)
        with self.assertRaises(ValueError):
            konsola.opcje_z_argumentow(["A=tak"], None)


class TestWiadomosci(unittest.TestCase):
    def test_odbior_z_adresatem_i_dyspozycja(self):
        k = AtrapaKonsoli()
        mapa = {"m1": ORG_K, "dysp1": ORG_A}
        self.assertEqual(konsola.odbierz_wiadomosc(k, Toz(), "m1", notka="zrobione", mapa=mapa), ORG_K)
        self.assertEqual(k.w["ack"], [(ORG_K, "m1", "zrobione")])
        konsola.odbierz_wiadomosc(k, Toz(), "dysp1", notka="odp. na SF-1", mapa=mapa)
        self.assertEqual(k.w["patch_wiad"], [(ORG_A, "dysp1", "consumed", "odp. na SF-1")])

    def test_nieznane_id_bez_org_to_blad(self):
        toz = Toz()
        with mock.patch.object(konsola, "ThreadPoolExecutor") as pula:
            pula.return_value.__enter__.return_value.map.return_value = []
            with self.assertRaises(ValueError):
                konsola.odbierz_wiadomosc(AtrapaKonsoli(), toz, "x", notka="n", mapa={})

    def test_kiedy_z_obu_drog(self):
        self.assertEqual(konsola._kiedy({"utworzono": "2026-11-03T10:00"}), "2026-11-03T10:00")
        self.assertEqual(konsola._kiedy({"created_at": "2026-11-03T09:00"}), "2026-11-03T09:00")


TYP = {"id": "t1", "name": "Rodzaj pracy", "slug": "rodzaj_pracy", "is_multi": False,
       "tags": [{"id": "g1", "name": "Rdzeń", "value": "rodzaj_pracy:rdzen"},
                {"id": "g2", "name": "Rozwojowe", "value": "rodzaj_pracy:rozwojowe"}]}
PROJEKT = {"id": "t2", "name": "Projekt", "slug": "project", "is_multi": True,
           "tags": [{"id": "p1", "name": "Rdzeń"}]}


class TestTagi(unittest.TestCase):
    def test_znajdz_bez_ogonkow_i_wieloznacznosc(self):
        tag, typ = konsola.znajdz_tag([TYP], "rdzen")
        self.assertEqual(tag["id"], "g1")
        with self.assertRaises(ValueError):
            konsola.znajdz_tag([TYP, PROJEKT], "Rdzeń")
        self.assertEqual(konsola.znajdz_tag([TYP, PROJEKT], "Rdzeń", typ="rodzaj pracy")[0]["id"], "g1")

    def test_jednokrotny_typ_odmowa_i_zamiana(self):
        k = AtrapaKonsoli()
        k.w["tagi"] = [{"id": "przyp1", "tag_id": "g2", "tag": {"id": "g2", "tag_type_id": "t1", "name": "Rozwojowe"}}]
        with self.assertRaises(ValueError):
            konsola.nadaj_tag(k, SPRAWA, TYP["tags"][0], TYP)
        self.assertEqual(k.w["nadane"], [])
        zrobione = konsola.nadaj_tag(k, SPRAWA, TYP["tags"][0], TYP, zamien=True)
        self.assertEqual(k.w["zdjete"], ["g2"])
        self.assertEqual(k.w["nadane"], ["g1"])
        self.assertEqual(len(zrobione), 2)

    def test_juz_ma_tag_nic_nie_robi(self):
        k = AtrapaKonsoli()
        k.w["tagi"] = [{"id": "przyp1", "tag_id": "g1", "tag": {"id": "g1", "tag_type_id": "t1"}}]
        konsola.nadaj_tag(k, SPRAWA, TYP["tags"][0], TYP)
        self.assertEqual(k.w["nadane"], [])

    def test_bez_tagu_typu_filtr_serwera(self):
        k = mock.Mock()
        k.sprawy_filtrem.return_value = ([], 0)
        konsola.sprawy_bez_tagu_typu(k, TYP)
        filtry = k.sprawy_filtrem.call_args.kwargs
        self.assertEqual(filtry["exclude_tags"], "g1,g2")
        self.assertEqual(filtry["exclude_status"], "resolved,closed")


class TestDziennik(unittest.TestCase):
    def _linie(self, plik):
        return Path(plik).read_text(encoding="utf-8").splitlines()

    def test_wiersz_zgodny_z_parserem_tematow(self):
        with tempfile.TemporaryDirectory() as kat:
            plik = Path(kat) / "sf_audit.log"
            d = audyt.Dziennik(plik, aktor="agata")
            with mock.patch.dict(os.environ, {"SF_KIT_SESJA": "", "AGATA_ROLA": ""}):
                d.zapisz("POST", f"tickets/{SPRAWA}/entries", cialo={"content": "a | b"}, organizacja=ORG_A, kod=201)
                d.zapisz("GET", f"tickets/{SPRAWA}", cialo=None, organizacja=ORG_A, kod=200)
            with mock.patch.dict(os.environ, {"AGATA_ROLA": "zaplecze"}):
                d.zapisz("POST", "console/boxes", cialo={"context_anchor": {"id": KROK}}, organizacja=ORG_A, kod=201)
            linie = self._linie(plik)
        self.assertEqual(len(linie), 2)                  # GET nie trafia do dziennika
        # parser tematy.py: split(" | "), pola k=v, `sesja`, `ticket`, `tenant`
        pola = [p.strip() for p in linie[0].split(" | ")]
        kv = dict(p.split("=", 1) for p in pola[1:])
        self.assertEqual(kv["ticket"], SPRAWA)
        self.assertEqual(kv["tenant"], ORG_A)
        self.assertEqual(kv["sesja"], "jawny")
        self.assertEqual(kv["hook"], "kit")
        self.assertEqual(kv["result"], "HTTP 201")
        kv2 = dict(p.split("=", 1) for p in [x.strip() for x in linie[1].split(" | ")][1:])
        self.assertEqual((kv2["ticket"], kv2["sesja"]), (KROK, "zaplecze"))

    def test_bez_pliku_nic(self):
        with mock.patch.dict(os.environ, {audyt.ZMIENNA_PLIKU: ""}):
            self.assertIsNone(audyt.z_ustawien(mock.Mock(dziennik_audytu=""), "x"))

    def test_klient_pisze_tylko_zapisy_i_klon_dziedziczy(self):
        from sf_kit.api import Klient
        k = Klient(baza="https://x", klucz="sk_test", organizacja=ORG_A)
        k.dziennik = mock.Mock()
        self.assertIs(k.w_organizacji(ORG_K).dziennik, k.dziennik)
        k._zapisz_w_dzienniku("PATCH", "console/boxes/1", {"status": "closed"}, 200)
        k.dziennik.zapisz.assert_called_once()


if __name__ == "__main__":
    unittest.main()
