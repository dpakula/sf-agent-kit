"""Cztery poprawki z pierwszego uruchomienia u Damiana (0.2.2).

v0.2.2 (15.09.2026) - APro Agents / borys-sf

Wszystkie cztery to KOMUNIKATY, nie zachowanie — i dlatego łatwo je zepsuć z powrotem bez
żadnego objawu. Każda wyszła z jednego przebiegu z prawdziwym człowiekiem przy terminalu,
więc każda ma tu test.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, klucz  # noqa: E402


class _Wynik:
    """Atrapa `WynikSzukania` — liczniki bez chodzenia do sieci."""

    def __init__(self, ile, przejrzano, wszystkich):
        self.zadania = [{"id": i} for i in range(ile)]
        self.przejrzano = przejrzano
        self.wszystkich = wszystkich

    @property
    def urwane(self):
        return self.przejrzano < self.wszystkich

    def __len__(self):
        return len(self.zadania)


class TestKomunikatOKluczu(unittest.TestCase):
    """Punkt 1: „nie zapisałeś klucza" ≠ „nie mam dostępu do pęku"."""

    def setUp(self):
        self._stare = (klucz.czy_macos, klucz._wczytaj_keychain)

    def tearDown(self):
        klucz.czy_macos, klucz._wczytaj_keychain = self._stare

    def test_brak_dostepu_do_peku_NIE_kaze_uruchamiac_init(self):
        """Sedno: klucz JEST, wszystko działa, a komunikat kazał naprawiać niezepsute.

        Tak wygląda `sf-kit` uruchomiony przez model w piaskownicy — i to jest zachowanie
        zamierzone, bo klucz należy do człowieka i do workera, nie do modelu.
        """
        klucz.czy_macos = lambda: True
        klucz._wczytaj_keychain = lambda: (None, klucz.BRAK_DOSTEPU)

        tresc = klucz.powod_braku_klucza()

        self.assertIn("JEST zapisany", tresc)
        self.assertIn("piaskownic", tresc.lower())
        self.assertNotIn("init", tresc, "to nie jest sytuacja do naprawy przez `init`")

    def test_brak_wpisu_kaze_uruchomic_init(self):
        """Druga strona rozróżnienia — tu `init` jest właściwą odpowiedzią."""
        klucz.czy_macos = lambda: True
        klucz._wczytaj_keychain = lambda: (None, klucz.BRAK_WPISU)

        self.assertIn("init", klucz.powod_braku_klucza())

    def test_poza_macos_zostaje_zwykly_komunikat(self):
        klucz.czy_macos = lambda: False
        self.assertIn("init", klucz.powod_braku_klucza())

    def test_KOD_WYJSCIA_rozstrzyga_ktory_to_przypadek(self):
        """Luka wykryta mutacją: testy wyżej podstawiały całą funkcję, więc sama reguła
        („44 = nie ma wpisu, cokolwiek innego = nie mam dostępu") nie była sprawdzana wcale.

        To jest miejsce, w którym rozróżnienie żyje — i jedyne, w którym da się je zepsuć
        tak, żeby komunikat dalej wyglądał poprawnie w pozostałych testach.
        """
        import subprocess

        class Odpowiedz:
            def __init__(self, kod, tekst=""):
                self.returncode, self.stdout, self.stderr = kod, tekst, ""

        stare = subprocess.run
        try:
            subprocess.run = lambda *a, **k: Odpowiedz(44)
            self.assertEqual(klucz._wczytaj_keychain(), (None, klucz.BRAK_WPISU))

            subprocess.run = lambda *a, **k: Odpowiedz(51)
            self.assertEqual(klucz._wczytaj_keychain(), (None, klucz.BRAK_DOSTEPU),
                             "kod inny niż 44 znaczy „jest, ale nie mogę otworzyć”")

            subprocess.run = lambda *a, **k: Odpowiedz(0, "sk_live_abc\n")
            self.assertEqual(klucz._wczytaj_keychain(), ("sk_live_abc", klucz.ZNALEZIONY))

            subprocess.run = lambda *a, **k: Odpowiedz(0, "   \n")
            self.assertEqual(klucz._wczytaj_keychain(), (None, klucz.BRAK_WPISU),
                             "pusty wpis to brak wpisu, nie klucz o pustej treści")
        finally:
            subprocess.run = stare


class TestLicznikZadan(unittest.TestCase):
    """Punkt 2: „zadania: 524" było całą kolejką Organizacji i myliło."""

    def test_obie_liczby_sa_NAZWANE(self):
        tekst = cli._licznik(_Wynik(1, 525, 525))
        self.assertIn("Twoje w kolejce: 1", tekst)
        self.assertIn("525", tekst)
        self.assertNotRegex(tekst, r"^\s*\d+\s*$")

    def test_ta_sama_formula_w_whoami_i_w_tasks(self):
        """Dwa polecenia mówiące o tym samym różnymi słowami to ta sama pomyłka od nowa."""
        import inspect

        for funkcja in (cli.polecenie_whoami, cli.polecenie_tasks):
            self.assertIn("_licznik", inspect.getsource(funkcja),
                          f"{funkcja.__name__} nie używa wspólnej formuły licznika")

    def test_obciecie_bezpiecznikiem_jest_widoczne(self):
        """Gdy przejrzano mniej niż całość, liczba całości ma zostać na ekranie."""
        self.assertIn("z 9000", cli._licznik(_Wynik(0, 4000, 9000)))
        self.assertNotIn("z 525", cli._licznik(_Wynik(1, 525, 525)))


class TestPodpowiedzWywolania(unittest.TestCase):
    """Punkt 4: `sf-kit whoami` bez dowiązania w PATH daje „command not found"."""

    def setUp(self):
        import shutil

        self._stare = shutil.which

    def tearDown(self):
        import shutil

        shutil.which = self._stare

    def test_bez_dowiazania_podpowiadamy_z_kropka(self):
        import shutil

        shutil.which = lambda _n: None
        self.assertEqual(cli._jak_wolac(), "./sf-kit")

    def test_z_dowiazaniem_podpowiadamy_krotko(self):
        import shutil

        shutil.which = lambda _n: "/usr/local/bin/sf-kit"
        self.assertEqual(cli._jak_wolac(), "sf-kit")


class TestMonityPekuKluczy(unittest.TestCase):
    """Punkt 3: `security` pyta o hasło dwa razy, a człowiek nie wie, czy ma coś wpisać."""

    def test_haslo_idzie_na_OBA_pytania(self):
        import inspect

        zrodlo = inspect.getsource(klucz._zapisz_keychain)
        self.assertIn("{klucz}\\n{klucz}", zrodlo,
                      "drugie pytanie `security` zostaje bez odpowiedzi i widać je na ekranie")

    def test_init_uprzedza_o_monitach(self):
        """Podanie hasła dwa razy może nie wystarczyć (security bywa czyta z terminala),
        więc `init` mówi o tym WCZEŚNIEJ — to jest część, która działa zawsze."""
        import inspect

        zrodlo = inspect.getsource(klucz.zapytaj_i_zapisz)
        self.assertIn("pęku kluczy", zrodlo)
        self.assertIn("nic nie wpisuj", zrodlo.lower())


if __name__ == "__main__":
    unittest.main()
