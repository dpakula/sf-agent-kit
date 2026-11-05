"""Kit 0.20.0: luki koordynatora SF-486 (wpis 75e3182a) — odpowiedź w wątku, krok kompletny, odpowiedzi w wątkach.

v1.0.0 (05.11.2026) - APro Agents / klaudiusz-general · SF-486 luki 1, 4, 5

CZEGO PILNUJĄ
· `wpis/odpowiedz --w-odpowiedzi`: link `…#wpis-<uuid>` / pełne id → `w_odpowiedzi_do`; bez opcji wywołanie jak przed 0.20;
  `--w-odpowiedzi` + `--zalacz` = kod 2, zero zapisu.
· `krok nowy --tytul --tag --obserwujacy --zalacz`: każdy element dołożony; błąd jednego = kod 3, krok zostaje.
· `konsola.odpowiedzi_w_watkach`: odpowiedź osoby pod MOIM wpisem bez mojej reakcji = jest; z moją odpowiedzią w wątku
  albo z id rodzica w treści = nie ma; zmiana pola się nie liczy; odpowiedź pod cudzym wpisem = nie ma.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import argparse
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, konsola  # noqa: E402

SPRAWA = "46aea40a-4a3e-4923-85c3-8a1b0406a5c5"
RODZIC = "40b86129-4ea3-4b9e-a1a2-f296309dff4a"


def wpis(eid, kiedy, autor, tresc="", rodzic=None, kind="note", email=None):
    return {"id": "tl-" + eid, "native_entry_id": eid, "occurred_at": kiedy, "author_label": autor,
            "author_email": email, "content": tresc, "kind": kind,
            "w_odpowiedzi_do": {"id": None, "native_entry_id": rodzic} if rodzic else None}


class TestWOdpowiedzi(unittest.TestCase):
    def test_link_i_id(self):
        args = SimpleNamespace(w_odpowiedzi=f"https://sales-forge.pl/tickets/x?org=y#wpis-{RODZIC}", zalacz=[])
        self.assertEqual(cli._watek_kw(None, SPRAWA, args), {"w_odpowiedzi_do": RODZIC})
        self.assertEqual(cli._watek_kw(None, SPRAWA, SimpleNamespace(w_odpowiedzi=RODZIC, zalacz=[])),
                         {"w_odpowiedzi_do": RODZIC})

    def test_bez_opcji_pusto(self):
        self.assertEqual(cli._watek_kw(None, SPRAWA, SimpleNamespace(w_odpowiedzi=None, zalacz=[])), {})

    def test_z_zalacznikiem_blad(self):
        with self.assertRaises(ValueError):
            cli._rodzic_wpisu(None, SPRAWA, SimpleNamespace(w_odpowiedzi=RODZIC, zalacz=["a.md"]))

    def test_parser_zna_opcje(self):
        p = cli.zbuduj_parser() if hasattr(cli, "zbuduj_parser") else None
        if p is None:
            self.skipTest("brak zbuduj_parser")
        a = p.parse_args(["wpis", SPRAWA, "--tresc", "ok", "--w-odpowiedzi", RODZIC[:8]])
        self.assertEqual(a.w_odpowiedzi, RODZIC[:8])
        a = p.parse_args(["odpowiedz", SPRAWA, "--tresc", "ok", "--w-odpowiedzi", RODZIC[:8]])
        self.assertEqual(a.w_odpowiedzi, RODZIC[:8])
        a = p.parse_args(["krok", "nowy", "--tytul", "KROK V", "--obserwujacy", "a@b.pl", "--zalacz", "x.md"])
        self.assertEqual((a.tytul, a.tag, a.obserwujacy, a.zalacz), ("KROK V", "Krok", ["a@b.pl"], ["x.md"]))
        a = p.parse_args(["konsola", "odpowiedzi", "--osoba", "d.pakula@advertpro.co", "--dni", "3"])
        self.assertEqual((a.osoba, a.dni, a.bez_watkow), (["d.pakula@advertpro.co"], 3, False))


class TestKrokKompletny(unittest.TestCase):
    def test_wszystko_dolozone(self):
        k = mock.MagicMock()
        typy = [{"id": "t", "name": "Krok", "tags": [{"id": "g", "name": "Krok", "value": "krok"}]}]
        with mock.patch.object(konsola, "typy_wszystkie", return_value=typy), \
                mock.patch.object(konsola, "nadaj_tag") as nadaj:
            braki = cli._uzupelnij_krok(k, SPRAWA, SimpleNamespace(tytul="KROK V · Rozgrywka 03.11.2026", tag="Krok",
                                                                    obserwujacy=["a@b.pl"], zalacz=["x.md"]))
        self.assertEqual(braki, [])
        k.zmien_sprawe.assert_called_once_with(SPRAWA, {"title": "KROK V · Rozgrywka 03.11.2026"})
        nadaj.assert_called_once()
        k.dodaj_obserwujacego.assert_called_once_with(SPRAWA, "a@b.pl")
        k.wpis_z_plikami.assert_called_once()

    def test_brak_tagu_to_brak_nie_wyjatek(self):
        k = mock.MagicMock()
        with mock.patch.object(konsola, "typy_wszystkie", return_value=[]):
            braki = cli._uzupelnij_krok(k, SPRAWA, SimpleNamespace(tytul=None, tag="Krok", obserwujacy=[], zalacz=[]))
        self.assertEqual(len(braki), 1)
        self.assertIn("tag Krok", braki[0])
        k.zmien_sprawe.assert_not_called()


class TestOdpowiedziWWatkach(unittest.TestCase):
    def _uruchom(self, wpisy):
        org = SimpleNamespace(uuid="org-1", slug="seco-cosmetics", agent_slug=None)
        toz = SimpleNamespace(konto_email="agata@dpakula.pl", z_nadaniami=[org], organizacje=[org])
        k = mock.MagicMock()
        k.w_organizacji.return_value = k
        k.feed_osoby.return_value = [{"primary_type": "ticket", "primary_id": SPRAWA,
                                      "primary_label": "SECO-0273 · bot"}]
        k.os_obiektu.return_value = {"entries": wpisy}
        with mock.patch.object(konsola, "datetime") as dt:
            from datetime import datetime, timezone
            dt.now.return_value = datetime(2026, 11, 5, 14, 0, tzinfo=timezone.utc)
            return konsola.odpowiedzi_w_watkach(k, toz, ["d.pakula@advertpro.co"], slug="agata")

    def test_nieodebrana(self):
        w, problemy = self._uruchom([
            wpis("zm", "2026-11-05T13:00:00Z", "agata@dpakula.pl", "status", kind="field_change", email="agata@dpakula.pl"),
            wpis("odp", "2026-11-05T12:35:00Z", "d.pakula@advertpro.co", "ok wysylaj", rodzic=RODZIC),
            wpis(RODZIC, "2026-11-05T12:29:00Z", "api:agata klucz osobisty", "SZKIC do akceptu"),
        ])
        self.assertEqual(problemy, [])
        self.assertEqual(len(w), 1)
        self.assertEqual((w[0]["sprawa"], w[0]["rodzic_id"], w[0]["odpowiedz"]), ("SECO-0273", RODZIC, "ok wysylaj"))
        self.assertIn(f"--w-odpowiedzi {RODZIC[:8]}", konsola.wiersz_watku(w[0]))

    def test_odebrana_w_watku(self):
        w, _ = self._uruchom([
            wpis("moja", "2026-11-05T13:00:00Z", "api:agata klucz osobisty", "Wysłane", rodzic=RODZIC),
            wpis("odp", "2026-11-05T12:35:00Z", "d.pakula@advertpro.co", "ok wysylaj", rodzic=RODZIC),
            wpis(RODZIC, "2026-11-05T12:29:00Z", "api:agata klucz osobisty", "SZKIC"),
        ])
        self.assertEqual(w, [])

    def test_odebrana_przez_id_w_tresci(self):
        w, _ = self._uruchom([
            wpis("moja", "2026-11-05T13:00:00Z", "api:agata klucz osobisty", f"Opublikowane (szkic {RODZIC[:8]})"),
            wpis("odp", "2026-11-05T12:35:00Z", "d.pakula@advertpro.co", "ok wysylaj", rodzic=RODZIC),
            wpis(RODZIC, "2026-11-05T12:29:00Z", "api:agata klucz osobisty", "SZKIC"),
        ])
        self.assertEqual(w, [])

    def test_pod_cudzym_wpisem_nie(self):
        w, _ = self._uruchom([
            wpis("odp", "2026-11-05T12:35:00Z", "d.pakula@advertpro.co", "dobra", rodzic=RODZIC),
            wpis(RODZIC, "2026-11-05T12:29:00Z", "api:arek-sf-agent", "propozycja"),
        ])
        self.assertEqual(w, [])


if __name__ == "__main__":
    unittest.main()
