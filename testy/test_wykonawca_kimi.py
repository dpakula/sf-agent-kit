"""Adapter Kimi Code CLI — składnia wołania i odmowy (ADVERTPR-807 C3).

v0.1 (15.09.2026) - APro Agents / borys-sf

CZEGO TU PILNUJEMY I DLACZEGO AKURAT TEGO
1. **Flagi trybu bezobsługowego.** Bez `--print` i `--yolo` Kimi czeka na zgodę człowieka,
   której przy workerze nikt nie kliknie — przebieg wisi do limitu czasu i melduje
   „przekroczony limit czasu", czyli diagnozę wskazującą na wolny model zamiast na brak flagi.
2. **Odmowa PRZED wzięciem zadania.** Zepsuta instalacja, która przechodzi `which`, wywala się
   dopiero na pierwszym zadaniu — po tym, jak worker zdążył je sobie przypisać.

Atrapa `kimi` jest skryptem powłoki na `PATH`: sprawdzamy to, co Kit naprawdę uruchamia,
a nie to, co uruchomiłby, gdyby `subprocess` działał tak, jak podstawiliśmy w teście.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit.wykonawcy import WykonawcaKimi, wybierz  # noqa: E402


def _atrapa(katalog: str, *, tresc: str) -> str:
    """Postaw wykonywalny plik `kimi` w podanym katalogu i oddaj ten katalog."""
    sciezka = os.path.join(katalog, "kimi")
    with open(sciezka, "w", encoding="utf-8") as plik:
        plik.write(tresc)
    os.chmod(sciezka, os.stat(sciezka).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return katalog


class ZAtrapaNaPath:
    """Kontekst: `PATH` z podstawionym katalogiem na początku."""

    def __init__(self, tresc: str):
        self.tresc = tresc

    def __enter__(self):
        self.katalog = tempfile.mkdtemp(prefix="kimi-atrapa-")
        _atrapa(self.katalog, tresc=self.tresc)
        self.stary_path = os.environ["PATH"]
        os.environ["PATH"] = self.katalog + os.pathsep + self.stary_path
        return self.katalog

    def __exit__(self, *_):
        os.environ["PATH"] = self.stary_path


ATRAPA_DZIALAJACA = """#!/bin/sh
if [ "$1" = "--version" ]; then echo "kimi 0.9.0-atrapa"; exit 0; fi
# Zapisz argumenty, żeby test mógł sprawdzić, JAK zostaliśmy zawołani.
printf '%s\\n' "$@" > "$KIMI_ARGV_PLIK"
echo "Sedno: zrobione."
exit 0
"""

ATRAPA_ZEPSUTA = """#!/bin/sh
echo "ImportError: brak zaleznosci" >&2
exit 1
"""


class TestDostepnosc(unittest.TestCase):

    def test_brak_kimi_w_path_to_czytelna_odmowa(self):
        wykonawca = WykonawcaKimi()
        sciezka = os.environ["PATH"]
        os.environ["PATH"] = tempfile.mkdtemp(prefix="pusty-")
        try:
            da_sie, powod = wykonawca.dostepny()
        finally:
            os.environ["PATH"] = sciezka
        self.assertFalse(da_sie)
        self.assertIn("kimi", powod)
        # Odmowa ma powiedzieć, CO ZROBIĆ — inaczej człowiek zostaje z samym „nie da się".
        self.assertIn("--runtime", powod)

    def test_zepsuta_instalacja_NIE_przechodzi_mimo_obecnosci_w_path(self):
        """Sam `which` przepuściłby ten przypadek do pierwszego zadania."""
        with ZAtrapaNaPath(ATRAPA_ZEPSUTA):
            da_sie, powod = WykonawcaKimi().dostepny()
        self.assertFalse(da_sie)
        self.assertIn("niesprawna", powod)
        self.assertIn("brak zaleznosci", powod)

    def test_dzialajaca_instalacja_przechodzi(self):
        with ZAtrapaNaPath(ATRAPA_DZIALAJACA):
            da_sie, powod = WykonawcaKimi().dostepny()
        self.assertTrue(da_sie)
        self.assertEqual(powod, "")

    def test_wynik_sondy_jest_pamietany(self):
        """Pętla workera pyta o dostępność co takt; sondowanie za każdym razem to koszt bez pożytku."""
        wykonawca = WykonawcaKimi()
        with ZAtrapaNaPath(ATRAPA_DZIALAJACA):
            self.assertTrue(wykonawca.dostepny()[0])
        # Po wyjściu z kontekstu `kimi` nie ma już w PATH, a odpowiedź ma zostać ta sama.
        self.assertTrue(wykonawca.dostepny()[0])


class TestWolanie(unittest.TestCase):

    def test_wola_kimi_z_kompletem_flag_trybu_bezobslugowego(self):
        with ZAtrapaNaPath(ATRAPA_DZIALAJACA):
            with tempfile.TemporaryDirectory() as katalog:
                plik_argv = os.path.join(katalog, "argv.txt")
                os.environ["KIMI_ARGV_PLIK"] = plik_argv
                try:
                    wynik = WykonawcaKimi().wykonaj(
                        "Zrób porządek", katalog=katalog, limit_s=30)
                finally:
                    os.environ.pop("KIMI_ARGV_PLIK", None)

                argv = Path(plik_argv).read_text(encoding="utf-8").splitlines()

        self.assertTrue(wynik.udalo_sie, wynik.powod_niepowodzenia)
        self.assertIn("Sedno", wynik.wyjscie)
        # Bez `--print` Kimi pyta człowieka; bez `--yolo` czeka na zgodę na każde polecenie.
        self.assertIn("--print", argv)
        self.assertIn("--yolo", argv)
        self.assertEqual(argv[argv.index("--output-format") + 1], "text")
        self.assertEqual(argv[argv.index("--prompt") + 1], "Zrób porządek")

    def test_pracuje_w_KATALOGU_ZADANIA(self):
        """Wykonawca ma pracować tam, gdzie worker przygotował zadanie, nie w swoim cwd."""
        with ZAtrapaNaPath("""#!/bin/sh
if [ "$1" = "--version" ]; then echo ok; exit 0; fi
pwd
"""):
            with tempfile.TemporaryDirectory() as katalog:
                wynik = WykonawcaKimi().wykonaj("cokolwiek", katalog=katalog, limit_s=30)
        self.assertTrue(wynik.udalo_sie, wynik.powod_niepowodzenia)
        self.assertIn(os.path.realpath(katalog), os.path.realpath(wynik.wyjscie.strip()))


class TestRejestracja(unittest.TestCase):

    def test_kimi_jest_do_wybrania_po_nazwie(self):
        self.assertIsInstance(wybierz("kimi"), WykonawcaKimi)

    def test_kimi_dostaje_RAMKE_bo_czyta_a_nie_wykonuje(self):
        """Powłoka wykonuje to, co dostaje — model to czyta. Ramka po polsku dla `shell`
        jest błędem składni, dla Kimi jest instrukcją."""
        self.assertTrue(wybierz("kimi").chce_ramke)

    def test_nieznany_wykonawca_wymienia_dostepnych_wraz_z_kimi(self):
        with self.assertRaises(ValueError) as blad:
            wybierz("wojt")
        self.assertIn("kimi", str(blad.exception))


if __name__ == "__main__":
    unittest.main()
