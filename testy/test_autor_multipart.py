"""Profil AUTOR: składanie multipart i wysyłka paczki plików (v0.3, warstwa biblioteki).

v0.3 (15.09.2026) - APro Agents / borys-sf

Multipart składany ręcznie jest jedynym miejscem w Kicie, gdzie literówka nie daje wyjątku,
tylko **cichy błąd po drugiej stronie**: serwer dostaje ciało, którego nie umie rozebrać, albo
rozbiera je inaczej, niż myśleliśmy. Dlatego te testy rozbierają złożone ciało z powrotem
i sprawdzają, co w nim naprawdę jest.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import multipart  # noqa: E402
from sf_kit.api import Klient  # noqa: E402


def _plik(katalog: Path, nazwa: str, tresc: bytes = b"tresc") -> Path:
    p = katalog / nazwa
    p.write_bytes(tresc)
    return p


class TestTypPliku(unittest.TestCase):

    def test_rozpoznaje_typowe_pliki_makiety(self):
        self.assertEqual(multipart.typ_pliku("makieta.html"), "text/html")
        self.assertEqual(multipart.typ_pliku("zrzut.png"), "image/png")
        self.assertEqual(multipart.typ_pliku("notatka.md"), "text/markdown")

    def test_nieznane_rozszerzenie_NIE_jest_zgadywane(self):
        """Zgadnięty typ myli odbiorcę bardziej niż uczciwe „strumień bajtów”."""
        self.assertEqual(multipart.typ_pliku("cos.qwertyz"), multipart.TYP_NIEZNANY)


class TestNazwaPliku(unittest.TestCase):

    def test_spacje_ZOSTAJA(self):
        """Człowiek nie ma zmieniać nazw swoich plików, żeby dało się je wysłać."""
        self.assertEqual(multipart.bezpieczna_nazwa("makieta strony głównej.html"),
                         "makieta strony głównej.html")

    def test_cudzyslow_i_nowa_linia_wypadaja(self):
        """Cudzysłów kończy pole nagłówka w połowie, nowa linia pozwala dopisać własne nagłówki.

        To jest ta sama klasa błędu co wstrzyknięcie do zapytania, tylko w innym protokole —
        więc znak wycinamy, zamiast go „poprawiać”.
        """
        zle = 'plik".html\r\nX-Wstrzykniety: 1'
        czysta = multipart.bezpieczna_nazwa(zle)
        self.assertNotIn('"', czysta)
        self.assertNotIn("\n", czysta)
        self.assertNotIn("\r", czysta)

    def test_nazwa_z_samych_zlych_znakow_nie_znika(self):
        self.assertEqual(multipart.bezpieczna_nazwa('"""'), "plik")


class TestSkladanieCiala(unittest.TestCase):

    def test_wszystkie_pliki_ida_pod_TYM_SAMYM_polem(self):
        """Sedno: jedno żądanie = jeden wpis = jedno powiadomienie.

        Pliki wysłane osobno dały kiedyś dwanaście wpisów i dwanaście maili w piętnaście
        sekund. Nazwa pola (`files`) jest tym, co trzyma je razem.
        """
        with tempfile.TemporaryDirectory() as k:
            kat = Path(k)
            pliki = [_plik(kat, "a.html"), _plik(kat, "b.png")]
            cialo, typ = multipart.zloz({"content": "opis"}, pliki)

        tekst = cialo.decode("utf-8", errors="replace")
        self.assertEqual(tekst.count('name="files"'), 2)
        self.assertIn('filename="a.html"', tekst)
        self.assertIn('filename="b.png"', tekst)
        self.assertTrue(typ.startswith("multipart/form-data; boundary="))

    def test_granica_NIE_wystepuje_w_tresci_pliku(self):
        """Granica trafiona wewnątrz pliku rozcina żądanie w przypadkowym miejscu.

        Losowana kryptograficznie, więc kolizja jest nierealna — ale test pilnuje, żeby nikt
        nie zamienił jej na coś przewidywalnego (znacznik czasu, stały napis).
        """
        with tempfile.TemporaryDirectory() as k:
            plik = _plik(Path(k), "x.txt", b"tresc")
            cialo, typ = multipart.zloz({}, [plik])
        granica = typ.split("boundary=")[1]
        self.assertGreater(len(granica), 24, "granica ma być nie do zgadnięcia")
        # Jedna część (plik) + zamknięcie = dwa wystąpienia. Gdyby granica trafiła się
        # w treści pliku, wystąpień byłoby więcej i serwer rozebrałby ciało w złym miejscu.
        self.assertEqual(cialo.count(granica.encode()), 2)

    def test_tresc_binarna_przechodzi_BEZ_ZMIAN(self):
        """Plik nie jest tekstem. Bajt zmieniony po drodze psuje zrzut ekranu po cichu."""
        surowe = bytes(range(256))
        with tempfile.TemporaryDirectory() as k:
            plik = _plik(Path(k), "obraz.png", surowe)
            cialo, _ = multipart.zloz({}, [plik])
        self.assertIn(surowe, cialo)

    def test_puste_pola_nie_wchodza_do_ciala(self):
        cialo, _ = multipart.zloz({"content": "a", "pomin": None}, [])
        self.assertNotIn(b"pomin", cialo)


class TestSprawdzaniePrzedWyslaniem(unittest.TestCase):

    def test_brakujacy_plik_zatrzymuje_CALA_paczke(self):
        """Paczka odrzucona w połowie zostawia sprawę z częścią plików — lepiej nie zacząć."""
        with tempfile.TemporaryDirectory() as k:
            istniejacy = _plik(Path(k), "jest.html")
            with self.assertRaises(FileNotFoundError) as p:
                multipart.sprawdz_pliki([str(istniejacy), str(Path(k) / "nie-ma.png")])
        self.assertIn("nie-ma.png", str(p.exception))

    def test_pusty_plik_tez_zatrzymuje(self):
        """Pusty załącznik wygląda na wysłany i nie niesie nic — gorszy od braku."""
        with tempfile.TemporaryDirectory() as k:
            pusty = _plik(Path(k), "pusty.html", b"")
            with self.assertRaises(FileNotFoundError):
                multipart.sprawdz_pliki([str(pusty)])


class TestWysylkaPrzezKlienta(unittest.TestCase):
    """Warstwa `Klient` — z podmienioną siecią, bez wychodzenia na zewnątrz."""

    def test_wpis_z_plikami_idzie_na_trase_paczkowa(self):
        zlapane = {}

        class Atrapa(Klient):
            def _wywolaj_surowo(self, metoda, sciezka, *, dane, typ_tresci):
                zlapane.update(metoda=metoda, sciezka=sciezka, dane=dane, typ=typ_tresci)
                return {"id": "wpis-1"}

        k = Atrapa(baza="https://x", klucz="sk_live_x", organizacja="org")
        with tempfile.TemporaryDirectory() as kat:
            plik = _plik(Path(kat), "makieta.html", b"<html>")
            k.wpis_z_plikami("sprawa-1", "gotowe", [plik])

        self.assertEqual(zlapane["metoda"], "POST")
        self.assertIn("entries/with-attachments", zlapane["sciezka"],
                      "paczka ma iść trasą dającą JEDEN wpis i jedno powiadomienie")
        self.assertIn(b"gotowe", zlapane["dane"])
        self.assertIn(b"<html>", zlapane["dane"])

    def test_widocznosc_przechodzi_do_pola_formularza(self):
        zlapane = {}

        class Atrapa(Klient):
            def _wywolaj_surowo(self, metoda, sciezka, *, dane, typ_tresci):
                zlapane["dane"] = dane
                return {}

        k = Atrapa(baza="https://x", klucz="sk_live_x", organizacja="org")
        with tempfile.TemporaryDirectory() as kat:
            plik = _plik(Path(kat), "a.txt")
            k.wpis_z_plikami("s", "t", [plik], widocznosc="external")
        self.assertIn(b"false", zlapane["dane"], "`external` = wpis NIE jest wewnętrzny")

    def test_zaloz_sprawe_podaje_obserwujacych(self):
        zlapane = {}

        class Atrapa(Klient):
            def _wywolaj(self, metoda, sciezka, *, cialo=None):
                zlapane.update(sciezka=sciezka, cialo=cialo)
                return {"ticket_id": "abc"}

        k = Atrapa(baza="https://x", klucz="sk_live_x", organizacja="org")
        k.zaloz_sprawe(tytul="Makieta gotowa", opis="…", obserwatorzy=["u1", "u2"])

        self.assertEqual(zlapane["sciezka"], "tickets")
        self.assertEqual(zlapane["cialo"]["watcher_user_ids"], ["u1", "u2"])

    def test_bez_obserwujacych_pole_NIE_idzie_puste(self):
        """Puste pole i brak pola to dla serwera to samo, ale ciało ma mówić, co zamierzamy."""
        zlapane = {}

        class Atrapa(Klient):
            def _wywolaj(self, metoda, sciezka, *, cialo=None):
                zlapane["cialo"] = cialo
                return {}

        Atrapa(baza="https://x", klucz="k", organizacja="o").zaloz_sprawe(tytul="T", opis="O")
        self.assertNotIn("watcher_user_ids", zlapane["cialo"])


if __name__ == "__main__":
    unittest.main()
