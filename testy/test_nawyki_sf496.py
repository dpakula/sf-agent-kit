"""Kit 0.19.0: nawyki koordynatorki — `blok nowy`, `--tresc`, krok z rozgrywki, bloki z kotwicą, zamknięcie z notką,
`nowa-sprawa` jedną komendą, `sprawa --rodzaj/--id`, `--json` i kody wyjścia.

v1.0.0 (04.11.2026) - APro Agents / klaudiusz-general · SF-496 (pkt 1–5 i 11)

CZEGO PILNUJĄ
· `--tresc`: tekst wprost, plik, `-`; napis wyglądający na plik, którego nie ma = kod 2, ZERO wywołań SF.
· `blok nowy …` = `konsola blok …` (także po `--org X`); `blok <id>` (SF-7) bez zmian.
· Krok bloku z `tracking/rozgrywka.json` (jak sf_box_sprawa); „null” = brak; `--krok` wygrywa, `--bez-kroku` wyłącza.
· `--zastepuje #N`: po założeniu nowego stary otwarty zostaje zamknięty; dubel (blok nie nowy) nie zamyka nic.
· `konsola zamknij --odpowiedz`: status + reply_seen + wpis WEWNĘTRZNY na sprawie kotwicy w jej Organizacji.
· `nowa-sprawa`: --przypisz → assignee_user_id, --prio med → medium, obserwujący „a,b”, --tag z taksonomii → nadany,
  spoza → kategoria; --json = jeden obiekt na stdout.
· `sprawa --rodzaj` = `--kind`; `sprawa --id` = uuid, numer, Organizacja.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, konsola, nawyki  # noqa: E402

ORG_A = "289cef06-b8b9-4a0c-967f-2533b08e82c4"
ORG_K = "58a67774-c077-4d2a-9fbd-e7a05da569e4"
SPRAWA = "46aea40a-4a3e-4923-85c3-8a1b0406a5c5"
KROK = "cdc7af07-435a-4874-8660-456d423c685c"


def uruchom(funkcja, args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            kod = funkcja(args)
        except SystemExit as e:
            kod = e.code
    return kod, out.getvalue(), err.getvalue()


class TestTresc(unittest.TestCase):
    def test_tekst_plik_stdin(self):
        self.assertEqual(nawyki.tresc(tresc_arg="Zrobione, dzięki."), "Zrobione, dzięki.")
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("z pliku")
        self.addCleanup(os.unlink, f.name)
        self.assertEqual(nawyki.tresc(tresc_arg=f.name), "z pliku")
        self.assertEqual(nawyki.tresc(opis=f.name), "z pliku")
        self.assertEqual(nawyki.tresc(tresc_arg="-", stdin=io.StringIO("ze stdin")), "ze stdin")
        self.assertIsNone(nawyki.tresc())

    def test_zla_sciezka_to_blad_nie_tresc(self):
        for zla in ("raport.md", "/tmp/nie-ma-takiego-pliku-496", "~/brak.txt", "katalog/plik"):
            with self.assertRaises(nawyki.ZleWejscie, msg=zla):
                nawyki.tresc(tresc_arg=zla)
        with self.assertRaises(nawyki.ZleWejscie):
            nawyki.tresc(opis="/tmp/nie-ma-opisu-496.md")
        self.assertEqual(nawyki.tresc(tresc_arg="zrobione w raport.md"), "zrobione w raport.md")   # spacja = tekst

    def test_sprzeczne_i_wymagana(self):
        with self.assertRaises(nawyki.ZleWejscie):
            nawyki.tresc(opis="-", tresc_arg="x")
        self.assertEqual(nawyki.tresc(tresc_arg="-", stdin=io.StringIO("")), "")      # decyduje wołający
        with self.assertRaises(nawyki.ZleWejscie):
            nawyki.tresc(tresc_arg="-", stdin=io.StringIO("  "), wymagana=True)


class TestArgv(unittest.TestCase):
    def test_blok_nowy(self):
        self.assertEqual(nawyki.przetlumacz_argv(["blok", "nowy", "--rodzaj", "info"]),
                         ["konsola", "blok", "--rodzaj", "info"])
        self.assertEqual(nawyki.przetlumacz_argv(["--org", "advertpro-co", "blok", "nowy", "--tresc", "x"]),
                         ["--org", "advertpro-co", "konsola", "blok", "--tresc", "x"])
        for bez_zmian in (["blok", "abc123"], ["blok"], ["wpis", "SF-1", "--tresc", "blok nowy"], []):
            self.assertEqual(nawyki.przetlumacz_argv(bez_zmian), bez_zmian)

    def test_parser_przyjmuje_paczke(self):
        p = cli.zbuduj_parser()
        a = p.parse_args(nawyki.przetlumacz_argv(
            ["--org", "advertpro-co", "blok", "nowy", "--sprawa", "SF-1", "--rodzaj", "action", "--prio", "high",
             "--effort", "15min", "--tresc", "Decyzja: A) tak · B) nie", "--zastepuje", "#2364"]))
        self.assertIs(a.funkcja, cli.polecenie_konsola_blok)
        self.assertEqual((a.tresc, a.zastepuje, a.opis), ("Decyzja: A) tak · B) nie", "#2364", None))
        a = p.parse_args(["konsola", "bloki", "--otwarte", "--sprawa", "SF-1", "--json"])
        self.assertIs(a.funkcja, cli.polecenie_konsola_bloki)
        a = p.parse_args(["konsola", "zamknij", "#1", "#2", "--odpowiedz", "wdrożone"])
        self.assertEqual((a.bloki, a.odpowiedz), (["#1", "#2"], "wdrożone"))
        a = p.parse_args(["nowa-sprawa", "--tytul", "T", "--prio", "med", "--przypisz", "a@b.pl",
                          "--obserwujacy", "a@b.pl,c@d.pl", "--tag", "Krok", "--tag", "Rdzeń", "--json"])
        self.assertEqual((a.priorytet, a.przypisz, a.tag, a.json), ("med", "a@b.pl", ["Krok", "Rdzeń"], True))
        a = p.parse_args(["sprawa", "SF-1", "--rodzaj", "message"])
        self.assertEqual(a.kind, "message")
        a = p.parse_args(["konsola", "odpowiedzi", "--odebrane", "#5", "--notka", "zrobione"])
        self.assertEqual(a.notka, "zrobione")
        a = p.parse_args(["krok", "zamknij", "SF-9", "--wpis", "domknięte"])
        self.assertEqual(a.tresc, "domknięte")


class TestRozgrywka(unittest.TestCase):
    def _plik(self, tresc):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        f.write(tresc)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_ostatni_ticket(self):
        self.assertEqual(nawyki.krok_z_rozgrywki(self._plik(json.dumps({"ostatni_ticket_id": KROK}))), KROK)
        for pusty in ('{"ostatni_ticket_id": null}', '{"ostatni_ticket_id": "null"}', "{}", "zepsuty"):
            self.assertIsNone(nawyki.krok_z_rozgrywki(self._plik(pusty)), pusty)
        self.assertIsNone(nawyki.krok_z_rozgrywki("/tmp/nie-ma-rozgrywki-496.json"))
        with mock.patch.dict(os.environ, {"SF_KIT_ROZGRYWKA": self._plik(json.dumps({"ostatni_ticket_id": KROK}))}):
            self.assertEqual(nawyki.krok_z_rozgrywki(), KROK)

    def test_drobne(self):
        self.assertEqual(nawyki.priorytet_sprawy("med"), "medium")
        self.assertEqual(nawyki.priorytet_sprawy(None), "medium")
        with self.assertRaises(nawyki.ZleWejscie):
            nawyki.priorytet_sprawy("pilne")
        self.assertEqual(nawyki.adresy(["a@b.pl,c@d.pl", "e@f.pl", "a@b.pl"]), ["a@b.pl", "c@d.pl", "e@f.pl"])


class AtrapaBlokow:
    def __init__(self, organizacja=ORG_K, wspolne=None):
        self.organizacja = organizacja
        self.w = wspolne if wspolne is not None else {"patche": [], "wpisy": [], "bloki": []}

    def w_organizacji(self, org):
        return AtrapaBlokow(org, self.w)

    def zmien_blok(self, bid, cialo):
        self.w["patche"].append((bid, cialo))

    def wpis(self, sid, tresc, *, widocznosc="internal"):
        self.w["wpisy"].append((self.organizacja, sid, widocznosc, tresc))
        return {"id": "e1"}

    def bloki(self, **f):
        return [b for b in self.w["bloki"] if f.get("numer") is None or b["numer"] == f"#{f['numer']}"]


class TestBloki(unittest.TestCase):
    BLOK = {"id": "b1", "numer": "#2364", "status": "open", "kind": "action", "priority": "high",
            "effort_tag": "15min", "created_at": "2026-11-04T18:00:00Z", "replied_at": "2026-11-04T19:00:00Z",
            "context_anchor": {"type": "ticket", "id": SPRAWA, "tenant": ORG_A}, "body": "Decyzja o wdrożeniu"}

    def test_wiersz_z_kotwica_wysilkiem_wiekiem(self):
        from datetime import datetime, timezone
        w = nawyki.wiersz_bloku(self.BLOK, datetime(2026, 11, 4, 21, 0, tzinfo=timezone.utc))
        for kawalek in ("#2364", "action", "high", "15min", "3 h", "NIEODEBRANA", "kotwica 46aea40a", "Decyzja"):
            self.assertIn(kawalek, w)

    def test_zamknij_z_notka_na_sprawie_kotwicy(self):
        k = AtrapaBlokow()
        linie = nawyki.zamknij_blok(k, dict(self.BLOK), notka="wdrożone na PROD", org_kotwicy=ORG_A)
        self.assertEqual(k.w["patche"], [("b1", {"status": "closed", "reply_seen": True})])
        org, sid, widocznosc, tresc = k.w["wpisy"][0]
        self.assertEqual((org, sid, widocznosc), (ORG_A, SPRAWA, "internal"))
        self.assertIn("#2364 zamknięty", tresc)
        self.assertEqual(len(linie), 2)

    def test_zamkniety_bez_patcha_i_bez_kotwicy_blad(self):
        k = AtrapaBlokow()
        nawyki.zamknij_blok(k, {"id": "b2", "numer": "#1", "status": "closed"})
        self.assertEqual(k.w["patche"], [])
        with self.assertRaises(ValueError):
            nawyki.zamknij_blok(k, {"id": "b3", "numer": "#2", "status": "open"}, notka="x")


class TestKomendy(unittest.TestCase):
    def setUp(self):
        self.konf = mock.Mock(adres="https://sf.example", obserwatorzy_domyslni=[])
        for p in (mock.patch.object(cli.konfiguracja, "wczytaj", return_value=self.konf),
                  mock.patch.object(cli, "_tozsamosc", return_value=mock.Mock())):
            p.start()
            self.addCleanup(p.stop)

    def _blok_args(self, **kw):
        d = dict(rodzaj="info", prio="med", effort=None, opis=None, tresc="Stan: wszystko zielone",
                 sprawa=SPRAWA, sprawa_org=None, krok=None, bez_kroku=False, do=None, tytul=None, zastepuje=None,
                 opcja=[], rekomendowana=None, bez_dedupu=False, dedup_h=2.0, json=True)
        d.update(kw)
        return argparse.Namespace(**d)

    def test_blok_krok_z_rozgrywki_i_zastapienie(self):
        klient = mock.Mock(organizacja=ORG_K)
        with mock.patch.object(cli, "_klient_dla_zapisu", return_value=(klient, "")), \
                mock.patch.object(cli, "_adresat_bloku", return_value="u1"), \
                mock.patch.object(nawyki, "krok_z_rozgrywki", return_value=KROK), \
                mock.patch.object(konsola, "zaloz_blok", return_value=({"id": "n1", "numer": "#9001"}, True)) as zb, \
                mock.patch.object(konsola, "znajdz_blok", return_value={"id": "s1", "numer": "#2364", "status": "open"}):
            kod, out, err = uruchom(cli.polecenie_konsola_blok, self._blok_args(zastepuje="#2364"))
        self.assertEqual(kod, 0, err)
        self.assertEqual(zb.call_args.kwargs["krok"], KROK)
        self.assertEqual(zb.call_args.kwargs["tresc"], "Stan: wszystko zielone")
        klient.zmien_blok.assert_called_once_with("s1", {"status": "closed"})
        d = json.loads(out)
        self.assertEqual((d["ok"], d["numer"], d["nowy"], d["zastapiony_zamkniety"]), (True, "#9001", True, "#2364"))

    def test_blok_dubel_nie_zamyka_zastepowanego_i_bez_kroku(self):
        klient = mock.Mock(organizacja=ORG_K)
        with mock.patch.object(cli, "_klient_dla_zapisu", return_value=(klient, "")), \
                mock.patch.object(cli, "_adresat_bloku", return_value="u1"), \
                mock.patch.object(nawyki, "krok_z_rozgrywki", return_value=KROK), \
                mock.patch.object(konsola, "zaloz_blok", return_value=({"id": "o", "numer": "#9"}, False)) as zb:
            kod, out, _ = uruchom(cli.polecenie_konsola_blok, self._blok_args(zastepuje="#2364", bez_kroku=True))
        self.assertEqual(kod, 0)
        self.assertIsNone(zb.call_args.kwargs["krok"])
        klient.zmien_blok.assert_not_called()
        self.assertFalse(json.loads(out)["nowy"])

    def test_blok_zla_sciezka_tresci_kod_2_bez_sf(self):
        klient = mock.Mock(organizacja=ORG_K)
        with mock.patch.object(cli, "_klient_dla_zapisu", return_value=(klient, "")), \
                mock.patch.object(konsola, "zaloz_blok") as zb:
            kod, out, err = uruchom(cli.polecenie_konsola_blok, self._blok_args(tresc="nie-ma-bloku-496.md"))
        self.assertEqual(kod, 2)
        zb.assert_not_called()
        self.assertFalse(json.loads(out.strip().splitlines()[-1])["ok"])
        self.assertIn("Błąd:", err)

    def test_wpis_tresc_inline_i_zla_sciezka(self):
        klient = mock.Mock(organizacja=ORG_A)
        klient.wpis.return_value = {"id": "e9"}
        a = argparse.Namespace(sprawa="SF-1", do=None, opis=None, tresc="Krótki postęp", zalacz=[],
                               widocznosc="internal", json=True)
        with mock.patch.object(cli, "_klient_dla_zapisu", return_value=(klient, "")), \
                mock.patch.object(cli, "_sprawa_dla_zapisu", return_value=({"id": SPRAWA, "number": 1}, "")), \
                mock.patch.object(cli, "_ostrzez_o_szkicu"):
            kod, out, _ = uruchom(cli.polecenie_wpis, a)
            self.assertEqual(kod, 0)
            klient.wpis.assert_called_once_with(SPRAWA, "Krótki postęp", widocznosc="internal")
            self.assertEqual(json.loads(out)["wpis_id"], "e9")
            klient.reset_mock()
            a.tresc = "notatka-z-literowka.md"
            kod, _, err = uruchom(cli.polecenie_wpis, a)
        self.assertEqual(kod, 2)
        klient.wpis.assert_not_called()

    def test_nowa_sprawa_jedna_komenda_json(self):
        klient = mock.Mock(organizacja=ORG_A)
        klient.czlonek.return_value = {"user_id": "u-damian"}
        klient.zaloz_sprawe.return_value = {"ticket_id": SPRAWA, "ticket_number": 497, "ticket_prefix": "SF"}
        typy = [{"id": "t1", "name": "Krok", "is_multi": True, "tags": [{"id": "g1", "name": "Krok"}]}]
        a = argparse.Namespace(tytul="Kit 0.20", opis=None, tresc="Opis wprost", tag=["Krok", "makieta"],
                               zalacz=[], priorytet="med", termin=None, rodzaj=None,
                               obserwujacy=["a@b.pl,c@d.pl"], szkic=False, kontekst="", przypisz="d@advertpro.co",
                               json=True)
        with mock.patch.object(cli, "_klient_dla_zapisu", return_value=(klient, "")), \
                mock.patch.object(konsola, "typy_wszystkie", return_value=typy), \
                mock.patch.object(konsola, "nadaj_tag", return_value=["nadany Krok: Krok"]) as nt, \
                mock.patch.object(cli, "_dodaj_obserwujacych", return_value=[]) as do, \
                mock.patch.object(cli.asystent, "adres_sprawy", return_value="https://sf.example/s"):
            kod, out, err = uruchom(cli.polecenie_nowa_sprawa, a)
        self.assertEqual(kod, 0, err)
        kw = klient.zaloz_sprawe.call_args.kwargs
        self.assertEqual((kw["priorytet"], kw["przypisany"], kw["kategoria"], kw["opis"]),
                         ("medium", "u-damian", "makieta", "Opis wprost"))
        nt.assert_called_once()
        do.assert_called_once_with(klient, SPRAWA, ["a@b.pl", "c@d.pl"])
        d = json.loads(out)
        self.assertEqual((d["ok"], d["ticket_id"], d["tagi"], d["obserwujacy"]),
                         (True, SPRAWA, ["Krok"], ["a@b.pl", "c@d.pl"]))

    def test_nowa_sprawa_przypisz_spoza_org_kod_2_bez_sprawy(self):
        from sf_kit.api import BladAPI
        klient = mock.Mock(organizacja=ORG_A)
        klient.czlonek.side_effect = BladAPI("404", kod=404)
        a = argparse.Namespace(tytul="T", opis=None, tresc="x", tag=[], zalacz=[], priorytet="medium", termin=None,
                               rodzaj=None, obserwujacy=[], szkic=False, kontekst="", przypisz="obcy@x.pl", json=True)
        with mock.patch.object(cli, "_klient_dla_zapisu", return_value=(klient, "")):
            kod, out, _ = uruchom(cli.polecenie_nowa_sprawa, a)
        self.assertEqual(kod, 2)
        klient.zaloz_sprawe.assert_not_called()
        self.assertFalse(json.loads(out)["ok"])

    def test_sprawa_id_i_rodzaj(self):
        klient = mock.Mock(organizacja=ORG_A)
        klient.sprawa.return_value = {"id": SPRAWA, "ticket_number": 496, "ticket_prefix": "SF", "kind": "case",
                                      "status": "in_progress"}
        a = argparse.Namespace(sprawa="SF-496", org=None, status=None, kind=None, tylko_id=True, json=False,
                               wszystkie=False, mimo_to=False)
        with mock.patch.object(cli, "_klient", return_value=klient), \
                mock.patch.object(cli, "_sprawa_dla_zapisu", return_value=({"id": SPRAWA}, "")):
            kod, out, _ = uruchom(cli.polecenie_sprawa, a)
        self.assertEqual(kod, 0)
        self.assertEqual(out.strip().split("\t")[0::2], [SPRAWA, ORG_A])
        a = argparse.Namespace(sprawa="SF-496", org=None, status=None, kind="message", tylko_id=False, json=True,
                               wszystkie=False, mimo_to=False)
        with mock.patch.object(cli, "_klient_dla_zapisu", return_value=(klient, "")), \
                mock.patch.object(cli, "_sprawa_dla_zapisu", return_value=({"id": SPRAWA}, "")):
            kod, out, _ = uruchom(cli.polecenie_sprawa, a)
        self.assertEqual(kod, 0)
        klient.zmien_rodzaj_sprawy.assert_called_once_with(SPRAWA, "message")
        self.assertIn("case → message", json.loads(out)["zrobione"][0])


if __name__ == "__main__":
    unittest.main()
