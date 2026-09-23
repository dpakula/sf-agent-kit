"""Adapter Kimi — składnia wołania i odmowy (ADVERTPR-807 C3; SF-32 od 24.09).

v0.2 (24.09.2026) - APro Agents / borys-sf

CZEGO TU PILNUJEMY I DLACZEGO AKURAT TEGO
1. **Składnia rozpoznana z pomocy tej instalacji.** Kimi Code (0.43.1 i 2.x) przyjmuje
   `--prompt` i ODRZUCA `--print`, `--yolo`, `--auto` w trybie promptu; stary `kimi-cli` chce
   `--print` + `--yolo`. Do 0.8.0 atrapa przyjmowała każdą flagę, więc test „wołamy z
   `--print`" był zielony, a na macu każde zadanie kończyło się „unknown option '--print'"
   (ADVERTPR-918). Atrapa Kimi Code poniżej odrzuca to, co odrzuca prawdziwy.
2. **Odmowa PRZED wzięciem zadania.** Zepsuta instalacja albo nierozpoznana składnia
   wywala się inaczej dopiero na pierwszym zadaniu — po tym, jak worker zdążył je przypisać.

Atrapa `kimi` jest skryptem powłoki na `PATH`: sprawdzamy to, co Kit naprawdę uruchamia,
a nie to, co uruchomiłby, gdyby `subprocess` działał tak, jak podstawiliśmy w teście.

Test z PRAWDZIWĄ binarką (`TestPrawdziwyKimi`) biegnie, gdy `SF_KIT_KIMI` wskazuje plik
`kimi` — bez tego jest pomijany i mówi o tym w wyniku (`skipped`), nie udaje zieleni.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit.wykonawcy import (  # noqa: E402
    SKLADNIA_KIMI_CLI, SKLADNIA_KIMI_CODE, WykonawcaKimi, rozpoznaj_skladnie_kimi, wybierz)


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
        # Do 0.8.0 katalog zostawał w /tmp — po każdym przebiegu pakietu kilka `kimi-atrapa-*`.
        shutil.rmtree(self.katalog, ignore_errors=True)


#: Wycinek PRAWDZIWEJ pomocy Kimi Code 2.0.1 (0.43.1 ma identyczną), zdjęty 24.09.
POMOC_KIMI_CODE = """Usage: kimi [options] [command]

Options:
  -V, --version                 output the version number
  -y, --yolo                    Start in Ask When Needed mode: routine edits and commands run
  --auto                        Start in Never Ask mode: never interrupts you; everything runs and
  -p, --prompt <prompt>         Run one prompt non-interactively and print the response.
  --output-format <format>      Output format for prompt mode. Defaults to text. (choices: "text",
"""

#: Atrapa Kimi Code: odrzuca dokładnie to, co odrzuca prawdziwy (komunikaty przepisane z 2.0.1).
ATRAPA_KIMI_CODE = """#!/bin/sh
if [ "$1" = "--version" ]; then echo "2.0.1"; exit 0; fi
if [ "$1" = "--help" ]; then cat <<'POMOC'
""" + POMOC_KIMI_CODE + """POMOC
exit 0; fi
printf '%s\\n' "$@" > "${KIMI_ARGV_PLIK:-/dev/null}"
for a in "$@"; do
  case "$a" in
    --print|--afk) echo "error: unknown option '$a'" >&2; echo "(Did you mean --prompt?)" >&2; exit 1;;
    --yolo) echo "error: Cannot combine --prompt with --yolo." >&2; exit 1;;
    --auto) echo "error: Cannot combine --prompt with --auto." >&2; exit 1;;
  esac
done
echo "Sedno: zrobione."
exit 0
"""

#: Atrapa starego `kimi-cli`: w pomocy ma `--print`.
ATRAPA_KIMI_CLI = """#!/bin/sh
if [ "$1" = "--version" ]; then echo "kimi 0.9.0-atrapa"; exit 0; fi
if [ "$1" = "--help" ]; then echo "  --print   tryb nieinteraktywny"; echo "  --prompt TEXT"; exit 0; fi
printf '%s\\n' "$@" > "${KIMI_ARGV_PLIK:-/dev/null}"
echo "Sedno: zrobione."
exit 0
"""

ATRAPA_DZIALAJACA = ATRAPA_KIMI_CODE

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

    def _zawolaj(self, atrapa: str) -> tuple:
        with ZAtrapaNaPath(atrapa):
            with tempfile.TemporaryDirectory() as katalog:
                plik_argv = os.path.join(katalog, "argv.txt")
                os.environ["KIMI_ARGV_PLIK"] = plik_argv
                try:
                    wynik = WykonawcaKimi().wykonaj(
                        "Zrób porządek", katalog=katalog, limit_s=30)
                finally:
                    os.environ.pop("KIMI_ARGV_PLIK", None)
                argv = (Path(plik_argv).read_text(encoding="utf-8").splitlines()
                        if os.path.exists(plik_argv) else [])
        return wynik, argv

    def test_kimi_code_wola_prompt_BEZ_print_i_yolo(self):
        """SF-32: `--print` i `--yolo` to dla Kimi Code błąd, nie tryb bezobsługowy."""
        wynik, argv = self._zawolaj(ATRAPA_KIMI_CODE)
        self.assertTrue(wynik.udalo_sie, wynik.powod_niepowodzenia)
        self.assertIn("Sedno", wynik.wyjscie)
        self.assertEqual(argv, ["--prompt", "Zrób porządek", "--output-format", "text"])

    def test_stary_kimi_cli_dostaje_print_i_yolo(self):
        wynik, argv = self._zawolaj(ATRAPA_KIMI_CLI)
        self.assertTrue(wynik.udalo_sie, wynik.powod_niepowodzenia)
        self.assertIn("--print", argv)
        self.assertIn("--yolo", argv)
        self.assertEqual(argv[argv.index("--output-format") + 1], "text")
        self.assertEqual(argv[argv.index("--prompt") + 1], "Zrób porządek")

    def test_skladnia_starego_produktu_na_kimi_code_PADA(self):
        """Kontrola atrapy: bez tego testu atrapa mogłaby znowu przyjmować wszystko."""
        wykonawca = WykonawcaKimi()
        with ZAtrapaNaPath(ATRAPA_KIMI_CODE):
            self.assertTrue(wykonawca.dostepny()[0])
            wykonawca.skladnia = SKLADNIA_KIMI_CLI          # wymuszona pomyłka sprzed SF-32
            with tempfile.TemporaryDirectory() as katalog:
                wynik = wykonawca.wykonaj("x", katalog=katalog, limit_s=30)
        self.assertFalse(wynik.udalo_sie)
        self.assertIn("unknown option '--print'", wynik.powod_niepowodzenia)

    def test_pracuje_w_KATALOGU_ZADANIA(self):
        """Wykonawca ma pracować tam, gdzie worker przygotował zadanie, nie w swoim cwd."""
        with ZAtrapaNaPath("""#!/bin/sh
if [ "$1" = "--version" ]; then echo ok; exit 0; fi
if [ "$1" = "--help" ]; then echo "  -p, --prompt <prompt>"; exit 0; fi
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


class TestRozpoznanieSkladni(unittest.TestCase):

    def test_prawdziwa_pomoc_kimi_code_to_skladnia_kimi_code(self):
        self.assertEqual(rozpoznaj_skladnie_kimi(POMOC_KIMI_CODE), SKLADNIA_KIMI_CODE)

    def test_pomoc_z_print_to_stary_kimi_cli(self):
        self.assertEqual(rozpoznaj_skladnie_kimi("  --print  \n  --prompt TEXT"),
                         SKLADNIA_KIMI_CLI)

    def test_flaga_zawierajaca_print_w_nazwie_nie_przelacza(self):
        self.assertEqual(rozpoznaj_skladnie_kimi("--print-config\n-p, --prompt <p>"),
                         SKLADNIA_KIMI_CODE)

    def test_nierozpoznana_pomoc_to_odmowa_przed_zadaniem(self):
        with ZAtrapaNaPath("""#!/bin/sh
if [ "$1" = "--version" ]; then echo "9.9.9"; exit 0; fi
echo "Usage: kimi [--cos-nowego]"
"""):
            da_sie, powod = WykonawcaKimi().dostepny()
        self.assertFalse(da_sie)
        self.assertIn("9.9.9", powod)
        self.assertIn("--runtime codex", powod)


@unittest.skipUnless(os.environ.get("SF_KIT_KIMI"), "SF_KIT_KIMI nie wskazuje binarki `kimi`")
class TestPrawdziwyKimi(unittest.TestCase):
    """Kit przeciw PRAWDZIWEJ binarce. Bez modelu i bez logowania: sprawdzamy, że parser
    Kimi przyjmuje nasz wiersz polecenia — czyli że błąd przychodzi DOPIERO z braku modelu,
    a nie z „unknown option" ani „Cannot combine"."""

    def test_prawdziwy_kimi_przyjmuje_nasza_skladnie(self):
        binarka = os.environ["SF_KIT_KIMI"]
        with tempfile.TemporaryDirectory() as dom:
            stary = dict(os.environ)
            os.environ["PATH"] = os.path.dirname(binarka) + os.pathsep + stary["PATH"]
            os.environ["HOME"] = dom             # czysty profil: bez modelu, bez sesji
            try:
                wykonawca = WykonawcaKimi()
                da_sie, powod = wykonawca.dostepny()
                self.assertTrue(da_sie, powod)
                self.assertEqual(wykonawca.skladnia, SKLADNIA_KIMI_CODE)
                wynik = wykonawca.wykonaj("Odpowiedz: OK", katalog=dom, limit_s=60)
            finally:
                os.environ.clear()
                os.environ.update(stary)
        tresc = wynik.powod_niepowodzenia + wynik.wyjscie
        self.assertNotIn("unknown option", tresc)
        self.assertNotIn("Cannot combine", tresc)


if __name__ == "__main__":
    unittest.main()
