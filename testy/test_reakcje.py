"""Reakcje z komentarzy zadania — rozpoznawanie i granice (ADVERTPR-807 C1).

v0.1 (16.09.2026) - APro Agents / borys-sf

TESTY OD STRONY PRZERWANIA I OD STRONY ODMOWY (wymóg zadania). Najmocniej pilnowane:
worker NIE reaguje na to, co nie było do niego — ani na własną telemetrię, ani na komentarze
sprzed wzięcia zadania. Fałszywe „przerwij" kosztuje tyle samo co przeoczone.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import reakcje  # noqa: E402

START = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)


def _k(tresc, *, minut=1, autor="Damian", mail="d.pakula@advertpro.co"):
    return {"content": tresc, "author_name": autor, "author_email": mail,
            "created_at": (START + timedelta(minutes=minut)).isoformat()}


class TestPrzerwanie(unittest.TestCase):

    def test_przerwij_rozpoznane_z_autorem(self):
        r = reakcje.rozpoznaj([_k("przerwij")], po=START)
        self.assertEqual(r.przerwal, "Damian")

    def test_przerwij_dziala_bez_wzgledu_na_wielkosc_liter_i_ogon(self):
        r = reakcje.rozpoznaj([_k("Przerwij, to idzie w złą stronę")], po=START)
        self.assertEqual(r.przerwal, "Damian")

    def test_pierwsze_przerwij_wygrywa(self):
        """Kto podjął decyzję, idzie potem do wpisu — nadpisanie gubiłoby tę informację."""
        r = reakcje.rozpoznaj(
            [_k("przerwij", minut=1, autor="Damian"),
             _k("przerwij", minut=2, autor="Agata", mail="agata@dpakula.pl")], po=START)
        self.assertEqual(r.przerwal, "Damian")

    def test_slowo_przerwij_w_srodku_zdania_NIE_przerywa(self):
        """„Nie przerywaj" i „jak przerwiesz, to…" to zdania o pracy, nie polecenia."""
        r = reakcje.rozpoznaj([_k("nie przerywaj tego, dokończ")], po=START)
        self.assertIsNone(r.przerwal)
        self.assertEqual(r.nierozpoznane, 1)


class TestUwagi(unittest.TestCase):

    def test_doprecyzuj_i_kontekst_zbierane_w_kolejnosci(self):
        r = reakcje.rozpoznaj(
            [_k("doprecyzuj: tylko faktury z września", minut=1),
             _k("kontekst: klient zmienił NIP", minut=2)], po=START)
        self.assertEqual(r.uwagi, ["tylko faktury z września", "klient zmienił NIP"])
        self.assertIsNone(r.przerwal)

    def test_przedrostek_BEZ_tresci_nie_jest_uwaga(self):
        r = reakcje.rozpoznaj([_k("doprecyzuj:")], po=START)
        self.assertEqual(r.uwagi, [])
        self.assertEqual(r.nierozpoznane, 1)

    def test_uwagi_maja_PIERWSZENSTWO_w_ramce(self):
        """Model musi wiedzieć, że to dopisek późniejszy niż treść zadania, a nie jej część."""
        opis = reakcje.opis_uwag(["tylko faktury z września"])
        self.assertIn("pierwszeństwo", opis)
        self.assertIn("tylko faktury z września", opis)

    def test_uwagi_trafiaja_do_sprawozdania(self):
        """Czytający wpis ma wiedzieć, że zadanie zmieniło się w locie."""
        opis = reakcje.opis_do_wpisu(["klient zmienił NIP"])
        self.assertIn("Uwzględnione uwagi", opis)
        self.assertIn("klient zmienił NIP", opis)

    def test_brak_uwag_nie_doklada_pustej_sekcji(self):
        self.assertEqual(reakcje.opis_uwag([]), "")
        self.assertEqual(reakcje.opis_do_wpisu([]), "")


class TestCoNIEjestReakcja(unittest.TestCase):

    def test_komentarz_SPRZED_startu_kroku_jest_pomijany(self):
        """To część zlecenia, nie reakcja na pracę — worker już ją ma w treści zadania."""
        stary = _k("przerwij", minut=-5)
        r = reakcje.rozpoznaj([stary], po=START)
        self.assertIsNone(r.przerwal)
        self.assertEqual(r.nierozpoznane, 0)

    def test_komentarz_DOKLADNIE_w_momencie_startu_tez_pomijany(self):
        r = reakcje.rozpoznaj([_k("przerwij", minut=0)], po=START)
        self.assertIsNone(r.przerwal)

    def test_WLASNA_telemetria_workera_nie_liczy_sie_jako_glos_czlowieka(self):
        """Bez tego pierwszy komentarz „krok 1 z 3" worker policzyłby jako cudzą wypowiedź
        i meldowałby, że ktoś do niego mówi — sam do siebie, w kółko."""
        moj = _k("krok 1 z 3: czytam pliki", autor="Kodeks", mail="kodeks@advertpro.co")
        r = reakcje.rozpoznaj([moj], po=START, autor_wlasny="kodeks@advertpro.co")
        self.assertEqual(r.nierozpoznane, 0)
        self.assertFalse(r.cos_jest)

    def test_wlasny_autor_porownywany_bez_wzgledu_na_wielkosc_liter(self):
        moj = _k("krok 2 z 3", mail="Kodeks@AdvertPro.co")
        r = reakcje.rozpoznaj([moj], po=START, autor_wlasny="kodeks@advertpro.co")
        self.assertEqual(r.nierozpoznane, 0)

    def test_nierozpoznane_sa_LICZONE_a_nie_przemilczane(self):
        """Cisza o nich znaczyłaby, że człowiek pisze do workera i nie wie, że ten nie czyta."""
        r = reakcje.rozpoznaj(
            [_k("swietna robota", minut=1), _k("@michal zerknij", minut=2)], po=START)
        self.assertEqual(r.nierozpoznane, 2)
        self.assertTrue(r.cos_jest)

    def test_zly_format_czasu_nie_wywraca_przebiegu(self):
        """Komentarz z nieczytelną datą pomijamy — awaria workera z powodu cudzego wpisu
        byłaby gorsza niż przeoczenie jednego komentarza."""
        zepsuty = {"content": "przerwij", "created_at": "wczoraj", "author_name": "X"}
        r = reakcje.rozpoznaj([zepsuty], po=START)
        self.assertIsNone(r.przerwal)

    def test_czas_jako_datetime_tez_dziala(self):
        k = {"content": "przerwij", "created_at": START + timedelta(minutes=1),
             "author_name": "Damian"}
        self.assertEqual(reakcje.rozpoznaj([k], po=START).przerwal, "Damian")


class TestWpisPrzerwania(unittest.TestCase):

    def test_wpis_mowi_KTO_i_W_JAKIM_STANIE(self):
        """„Przerwane" bez stanu jest gorsze od milczenia: następna osoba nie wie,
        czy zaczynać od zera, czy sprzątać po połowie."""
        wpis = reakcje.wpis_przerwania({"id": "x"}, "Damian", stan="po odbiorze, przed wykonaniem")
        self.assertIn("Damian", wpis)
        self.assertIn("po odbiorze, przed wykonaniem", wpis)
        self.assertIn("Katalog roboczy zostaje", wpis)


if __name__ == "__main__":
    unittest.main()
