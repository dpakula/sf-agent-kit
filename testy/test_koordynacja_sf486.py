"""Kit 0.18.0: luki 4–6 koordynatora — status/rodzaj sprawy, rodzaj pracy, sweep kolejki, doręczenie, reguła rozwiązywania.

v1.0.0 (03.11.2026) - APro Agents / klaudiusz-general · SF-486 krok 3

CZEGO PILNUJĄ
· `--status resolved/closed` odmawia przy otwartym zadaniu albo tagu „czeka na wdrożenie / bramkę / klienta”
  (bez ogonków i wielkości liter); nieczytelne zadania/tagi = odmowa; `--mimo-to` obchodzi; ten sam status = noop.
· `kolejka --stare`: 14d / 36h, liczone od updated_at (zapas created_at), najstarsze pierwsze.
· `odbierz --hurt`: tylko cancelled/on_hold, z notką; completed hurtem nie istnieje.
· Treść doręczenia ma link sprawy z ?org= i polecenie odczytu kontekstu.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import argparse
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, koordynacja  # noqa: E402
from sf_kit.api import BladAPI  # noqa: E402


class Atrapa:
    def __init__(self, *, zadania=(), tagi=(), blad_zadan=False):
        self._zadania, self._tagi, self.blad_zadan = list(zadania), list(tagi), blad_zadan
        self.patche = []

    def zadania_sprawy(self, tid):
        if self.blad_zadan:
            raise BladAPI("sieć")
        return self._zadania

    def tagi_sprawy(self, tid):
        return [{"tag_id": f"t{i}", "tag": {"name": n}} for i, n in enumerate(self._tagi)]

    def zmien_sprawe(self, tid, cialo):
        self.patche.append(cialo)


SPRAWA = {"id": "s1", "status": "in_progress"}


class TestStatus(unittest.TestCase):
    def test_otwarte_zadanie_innego_blokuje(self):
        k = Atrapa(zadania=[{"id": "z1", "status": "queued", "assigned_agent_slug": "arek-sf"}])
        with self.assertRaises(ValueError) as e:
            koordynacja.zmien_status(k, SPRAWA, "resolved")
        self.assertIn("arek-sf", str(e.exception))
        self.assertEqual(k.patche, [])

    def test_tag_blokuje_bez_ogonkow(self):
        k = Atrapa(tagi=["CZEKA NA WDROZENIE"])
        with self.assertRaises(ValueError):
            koordynacja.zmien_status(k, SPRAWA, "closed")

    def test_nieczytelne_zadania_to_odmowa(self):
        with self.assertRaises(ValueError):
            koordynacja.zmien_status(Atrapa(blad_zadan=True), SPRAWA, "resolved")

    def test_mimo_to_i_czysta_sprawa(self):
        k = Atrapa(zadania=[{"id": "z1", "status": "queued"}])
        koordynacja.zmien_status(k, SPRAWA, "resolved", mimo_to=True)
        k2 = Atrapa(zadania=[{"id": "z2", "status": "completed"}], tagi=["Rdzeń"])
        koordynacja.zmien_status(k2, SPRAWA, "resolved")
        self.assertEqual(k.patche + k2.patche, [{"status": "resolved"}] * 2)

    def test_ten_sam_status_noop_i_inne_bez_kontroli(self):
        k = Atrapa(blad_zadan=True)
        self.assertIn("nic nie zmieniam", koordynacja.zmien_status(k, SPRAWA, "in_progress"))
        koordynacja.zmien_status(k, SPRAWA, "waiting_for_customer")
        self.assertEqual(k.patche, [{"status": "waiting_for_customer"}])

    def test_wlasne_zadanie_nie_blokuje_przy_odbiorze(self):
        k = Atrapa(zadania=[{"id": "moje", "status": "in_progress"}])
        self.assertEqual(koordynacja.przeszkody_rozwiazania(k, "s1", poza_zadaniem="moje"), [])


class TestKolejka(unittest.TestCase):
    def test_wiek_i_stare(self):
        self.assertEqual(koordynacja.wiek_w_dniach("14d"), 14)
        self.assertEqual(koordynacja.wiek_w_dniach("36h"), 1.5)
        with self.assertRaises(ValueError):
            koordynacja.wiek_w_dniach("dwa tygodnie")
        t = datetime(2026, 11, 3, tzinfo=timezone.utc)
        z = [{"id": "a", "updated_at": (t - timedelta(days=20)).isoformat()},
             {"id": "b", "updated_at": (t - timedelta(days=2)).isoformat(), "created_at": "2026-08-01T00:00:00Z"},
             {"id": "c", "created_at": (t - timedelta(days=30)).isoformat()}]
        self.assertEqual([x["id"] for x in koordynacja.stare(z, 14, teraz=t)], ["c", "a"])

    def test_hurt_tylko_sprzatanie_z_notka(self):
        k = mock.Mock()
        a = argparse.Namespace(status="cancelled", notka=None, zadanie=["x"])
        self.assertEqual(cli._odbierz_hurt(k, a), 2)
        with mock.patch.object(cli.koordynator, "znajdz_zadanie") as zn:
            zn.return_value = mock.Mock(zadanie={"id": "z1", "external_id": "e1", "status": "queued"})
            a = argparse.Namespace(status="cancelled", notka="martwe od sierpnia", zadanie=["e1"])
            self.assertEqual(cli._odbierz_hurt(k, a), 0)
        k.komentarz_zadania.assert_called_once_with("z1", "martwe od sierpnia")
        k.ustaw_status.assert_called_once_with("z1", "cancelled")


class TestDostarczenie(unittest.TestCase):
    def test_tresc_z_linkiem_i_kontekstem(self):
        t = koordynacja.tresc_dostarczenia({"external_id": "x-1", "title": "Zrób to"},
                                           {"id": "s1", "ticket_prefix": "SF", "ticket_number": 7},
                                           baza="https://sales-forge.pl/", org_slug="sf")
        self.assertIn("SF-7", t)
        self.assertIn("https://sales-forge.pl/tickets/s1?org=sf", t)
        self.assertIn("sf-kit sprawa", t)


if __name__ == "__main__":
    unittest.main()
