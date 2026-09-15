"""Reakcje człowieka W PEŁNEJ PĘTLI workera (ADVERTPR-807 C1).

v0.1 (16.09.2026) - APro Agents / borys-sf

`test_reakcje.py` sprawdza rozpoznawanie słów. Ten plik sprawdza, co worker Z TYM ROBI —
bo to są dwie różne rzeczy i psują się osobno. Rozpoznanie „przerwij" bez oddania zadania
do kolejki wygląda w testach jednostkowych na działające.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit.worker import obsluz_zadanie  # noqa: E402
from testy.test_worker import AtrapaKlienta, konfiguracja, zadanie  # noqa: E402


def komentarz(tresc, *, za_ile_minut=1, autor="Damian", mail="d.pakula@advertpro.co"):
    """Komentarz z przyszłości — worker bierze tylko te nowsze niż moment wzięcia zadania."""
    return {"content": tresc, "author_name": autor, "author_email": mail,
            "created_at": (datetime.now(timezone.utc)
                           + timedelta(minutes=za_ile_minut)).isoformat()}


class TestPrzerwanie(unittest.TestCase):

    def test_przerwij_przed_wykonaniem_ODDAJE_zadanie_i_NIE_wykonuje(self):
        klient = AtrapaKlienta(komentarze_zadania=[komentarz("przerwij")])
        wynik = obsluz_zadanie(klient, konfiguracja(), zadanie(body_md="echo NIE_POWINNO_BYC"))

        self.assertIn("przerwane", wynik)
        self.assertIn("Damian", wynik)
        # Zadanie przyjęte, a potem oddane — i ANI RAZU nie zamknięte.
        statusy = [s for _, s in klient.statusy]
        self.assertEqual(statusy, ["in_progress", "queued"])
        self.assertNotIn("completed", statusy)

    def test_wpis_o_przerwaniu_mowi_KTO_i_W_JAKIM_STANIE(self):
        """Bez stanu następna osoba nie wie, czy zaczynać od zera, czy sprzątać po połowie."""
        klient = AtrapaKlienta(komentarze_zadania=[komentarz("przerwij")])
        obsluz_zadanie(klient, konfiguracja(), zadanie())

        self.assertEqual(len(klient.wpisy), 1)
        tresc = klient.wpisy[0][1]
        self.assertIn("Damian", tresc)
        self.assertIn("przed wykonaniem", tresc)
        self.assertIn("Katalog roboczy zostaje", tresc)

    def test_przerwij_PO_wykonaniu_NIE_kasuje_pracy_ale_nie_zamyka(self):
        """Praca już jest — skasowanie jej byłoby gorsze niż zignorowanie polecenia.

        Worker ma oddać wynik i NIE zamykać zadania, żeby człowiek zobaczył, co powstało,
        i sam zdecydował, co dalej.
        """
        klient = AtrapaKlienta()
        # Komentarz pojawia się dopiero przy DRUGIM zajrzeniu (po wykonaniu). Liczymy
        # wywołania, a nie statusy: `in_progress` jest ustawiane PRZED pierwszym punktem
        # kontrolnym, więc po statusie nie da się tych dwóch chwil odróżnić.
        pierwotne = klient.zadanie
        zajrzenia = {"ile": 0}

        def zadanie_z_opoznionym_komentarzem(task_id):
            zajrzenia["ile"] += 1
            odpowiedz = dict(pierwotne(task_id))
            if zajrzenia["ile"] >= 2:
                odpowiedz["comments"] = [komentarz("przerwij")]
            return odpowiedz

        klient.zadanie = zadanie_z_opoznionym_komentarzem
        wynik = obsluz_zadanie(klient, konfiguracja(), zadanie(body_md="echo zrobione"))

        self.assertIn("przerwał", wynik)
        statusy = [s for _, s in klient.statusy]
        self.assertNotIn("completed", statusy, "przerwane zadanie NIE ma być zamknięte")
        self.assertEqual(statusy[-1], "queued")
        # Wynik pracy jednak jest opisany — nie kasujemy tego, co powstało.
        self.assertEqual(len(klient.wpisy), 1)
        self.assertIn("zrobione", klient.wpisy[0][1])
        self.assertIn("poprosił(a) o przerwanie", klient.wpisy[0][1])


class TestUwagi(unittest.TestCase):

    def test_uwagi_trafiaja_do_SPRAWOZDANIA(self):
        klient = AtrapaKlienta(komentarze_zadania=[
            komentarz("doprecyzuj: tylko faktury z września")])
        obsluz_zadanie(klient, konfiguracja(), zadanie(body_md="echo ok"))

        tresc = klient.wpisy[0][1]
        self.assertIn("Uwzględnione uwagi", tresc)
        self.assertIn("tylko faktury z września", tresc)

    def test_uwagi_NIE_ida_do_powloki_bo_ona_je_WYKONA(self):
        """`shell` wykonuje to, co dostaje. Polski akapit doklejony do skryptu to błąd składni,
        a nie wskazówka — dlatego uwagi dokleja się wyłącznie do RAMKI."""
        klient = AtrapaKlienta(komentarze_zadania=[komentarz("kontekst: klient zmienił NIP")])
        wynik = obsluz_zadanie(klient, konfiguracja(runtime="shell"),
                               zadanie(body_md="echo ok"))

        self.assertEqual(wynik, "zrobione", "uwagi nie mogą wywrócić wykonania przez powłokę")
        # Do wpisu i tak trafiają — człowiek ma wiedzieć, że je widziano.
        self.assertIn("klient zmienił NIP", klient.wpisy[0][1])

    def test_zadanie_bez_reakcji_przechodzi_jak_dotad(self):
        """Kanał reakcji jest dodatkiem; jego obecność nie może zmienić zwykłego przebiegu."""
        klient = AtrapaKlienta()
        wynik = obsluz_zadanie(klient, konfiguracja(), zadanie(body_md="echo ok"))

        self.assertEqual(wynik, "zrobione")
        self.assertEqual([s for _, s in klient.statusy], ["in_progress", "completed"])
        self.assertNotIn("Uwzględnione uwagi", klient.wpisy[0][1])


class TestOdpornosc(unittest.TestCase):

    def test_awaria_odczytu_komentarzy_NIE_zatrzymuje_zadania(self):
        """Kanał reakcji jest dodatkiem do pracy, nie jej warunkiem."""
        from sf_kit.api import BladAPI

        klient = AtrapaKlienta()
        klient.zadanie = lambda *_a, **_k: (_ for _ in ()).throw(BladAPI("atrapa: 503"))
        wynik = obsluz_zadanie(klient, konfiguracja(), zadanie(body_md="echo ok"))

        self.assertEqual(wynik, "zrobione")
        self.assertEqual([s for _, s in klient.statusy], ["in_progress", "completed"])


if __name__ == "__main__":
    unittest.main()
