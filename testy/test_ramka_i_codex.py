"""Ramka promptu i sposób wołania Codexa (A2, A3).

v0.2 (14.09.2026) - APro Agents / borys-sf

DWIE RZECZY, KTÓRE BEZ TESTU WYGLĄDAJĄ TAK SAMO JAK DZIAŁAJĄCE
1. Ramka: model, którego nie poprosi się o sprawozdanie, oddaje dziennik pracy — a wpis na
   sprawie wygląda wtedy na zrobiony, tylko nikt go nie rozumie.
2. Wołanie Codexa: zła pozycja flagi kończy się kodem 2, a brak flagi — czekaniem na zgodę,
   której nikt nie kliknie, i komunikatem „przekroczony limit czasu" wskazującym nie tam,
   gdzie trzeba.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import ramka  # noqa: E402
from sf_kit.worker import czy_sprawozdanie, wpis_sukces  # noqa: E402
from sf_kit.wykonawcy import (  # noqa: E402
    FLAGA_BEZ_PYTAN, WykonawcaCodex, WykonawcaShell, _w_repozytorium_git,
)

ZADANIE = {
    "id": "8a1f",
    "external_id": "ADVERTPR-901",
    "title": "Uporządkuj katalog raportów",
    "ticket_ref": "ADVERTPR-777",
    "body_md": "Usuń pliki starsze niż 30 dni z katalogu raporty/.",
}


class _KlientNiemowa:
    """Klient, który wszystko przyjmuje i nic nie robi — tu chodzi wyłącznie o prompt."""

    def ustaw_status(self, *_a, **_k):
        return {}

    def wpis(self, *_a, **_k):
        return {}

    # Dołożone w v0.4: worker sprawozdaje też załącznikami i — przy zadaniu bez sprawy —
    # komentarzem zadania. Ta atrapa mierzy WYŁĄCZNIE prompt, więc przyjmuje wszystko.
    def wpis_z_plikami(self, *_a, **_k):
        return {}

    def zadanie(self, *_a, **_k):
        return {"comments": []}

    def kim_jestem(self, *_a, **_k):
        return {"user": {"email": "codex-fm@advertpro.co"}}

    def komentarz_zadania(self, *_a, **_k):
        return {}


class TestRamka(unittest.TestCase):

    def test_tresc_zadania_idzie_BEZ_ZMIAN(self):
        """Zmieniona treść to zmienione zadanie — człowiek zobaczyłby pracę, której nie zlecił."""
        tekst = ramka.zbuduj(ZADANIE, slug="codex-fm", katalog="/praca")
        self.assertIn(ZADANIE["body_md"], tekst)

    def test_mowi_KIM_jest_GDZIE_pracuje_i_SKAD_zadanie(self):
        tekst = ramka.zbuduj(ZADANIE, slug="codex-fm", katalog="/praca")
        self.assertIn("codex-fm", tekst)
        self.assertIn("/praca", tekst)
        self.assertIn("ADVERTPR-901", tekst)
        self.assertIn("ADVERTPR-777", tekst, "sprawa, przy której stoi zadanie")

    def test_zabrania_sekretow_i_wyjscia_poza_katalog(self):
        tekst = ramka.zbuduj(ZADANIE, slug="codex-fm", katalog="/praca")
        self.assertIn(".env", tekst)
        self.assertIn("poza katalog", tekst)

    def test_prosi_o_UKLAD_sprawozdania(self):
        """Bez tego cała zmiana A2 jest ozdobą: worker prosiłby o sprawozdanie nikogo.

        Sprawdzamy nagłówki NA POCZĄTKU LINII, a nie gdziekolwiek w tekście. Pierwsza wersja
        tego testu przepuściła mutację, która wycięła całe polecenie „**Sedno** — jedno zdanie:
        …", bo słowo `**Sedno**` padało jeszcze raz w zdaniu niżej. Wzmianka o sekcji to nie
        to samo, co prośba o nią.
        """
        linie = ramka.zbuduj(ZADANIE, slug="codex-fm", katalog="/praca").splitlines()
        for naglowek in ramka.UKLAD_SPRAWOZDANIA:
            self.assertTrue(
                any(l.startswith(naglowek) for l in linie),
                f"prompt nie prosi o sekcję {naglowek} — wymienia ją najwyżej mimochodem")

    def test_zadanie_bez_sprawy_nie_zostawia_dziury_w_zdaniu(self):
        """`ticket_ref` bywa pusty — ramka ma być wtedy krótsza, a nie wybrakowana."""
        tekst = ramka.zbuduj({"id": "x", "title": "T", "body_md": "zrób"},
                             slug="a", katalog="/k")
        self.assertNotIn("None", tekst)
        self.assertNotIn("Sprawa, przy której", tekst)


class TestWpisSukcesu(unittest.TestCase):

    def test_sprawozdanie_wykonawcy_idzie_JAKO_WPIS(self):
        """Sedno zmiany: wpis to sprawozdanie, nie sprawozdanie o sprawozdaniu.

        Wersja 0.1 zawijała każde wyjście w blok kodu ze zdaniem „poniżej wyjście wykonawcy,
        bez zmian" — czyli człowiek dostawał na sprawie zrzut konsoli z obwódką.
        """
        wyjscie = ("**Sedno** — katalog raportów uporządkowany.\n\n"
                   "**Co zrobiono** — usunięto stare raporty.\n\n"
                   "**Szczegóły techniczne** — 14 plików.")

        wpis = wpis_sukces(ZADANIE, wyjscie, wykonawca="codex")

        self.assertTrue(wpis.startswith("**Sedno** — katalog raportów"))
        self.assertNotIn("```", wpis, "sprawozdanie nie jest zrzutem konsoli")
        self.assertNotIn("bez zmian", wpis)
        self.assertIn("ADVERTPR-901", wpis, "stopka nadal mówi, z czego to sprawozdanie")

    def test_surowe_wyjscie_jest_opakowane_i_POWIEDZIANE_wprost(self):
        """Gdy układu brakuje, wpis ma to przyznać — a nie udawać sprawozdania."""
        wpis = wpis_sukces(ZADANIE, "rm raporty/*.csv\nDone.", wykonawca="codex")

        self.assertIn("nie oddał sprawozdania", wpis)
        self.assertIn("```", wpis)

    def test_samo_slowo_Sedno_nie_wystarczy(self):
        """Model potrafi przepisać nagłówek z promptu, nie pisząc sprawozdania."""
        self.assertFalse(czy_sprawozdanie("Mam napisać **Sedno**, ale najpierw zrobię X."))
        self.assertFalse(czy_sprawozdanie(""))


class TestWolanieCodexa(unittest.TestCase):

    def test_flaga_zgody_idzie_PRZED_podkomenda(self):
        """`codex exec --ask-for-approval never` kończy się kodem 2 (openai/codex#26602).

        Kolejność argumentów jest tu treścią, nie stylem — dlatego pilnuje jej test, a nie
        komentarz.
        """
        wykonawca = WykonawcaCodex()
        wykonawca._flagi = FLAGA_BEZ_PYTAN
        polecenia = self._zlap(wykonawca, katalog="/nie/repozytorium")

        self.assertEqual(polecenia[0], "codex")
        self.assertEqual(tuple(polecenia[1:3]), FLAGA_BEZ_PYTAN)
        self.assertEqual(polecenia[3], "exec")
        self.assertLess(polecenia.index("--ask-for-approval"), polecenia.index("exec"))

    def test_bez_przyjetej_flagi_wolamy_Codexa_i_tak(self):
        """Instalacja, która flagi nie zna, ma dalej pracować — bez flagi, ale ma."""
        wykonawca = WykonawcaCodex()
        wykonawca._flagi = ()
        polecenia = self._zlap(wykonawca, katalog="/nie/repozytorium")

        self.assertEqual(polecenia[:2], ["codex", "exec"])
        self.assertIn("--sandbox", polecenia)

    def test_poza_repozytorium_dokladamy_skip_git_repo_check(self):
        """Katalog roboczy agenta zwykle nie jest repozytorium — bez tego KAŻDE zadanie odpada."""
        wykonawca = WykonawcaCodex()
        wykonawca._flagi = ()
        self.assertIn("--skip-git-repo-check",
                      self._zlap(wykonawca, katalog="/nie/repozytorium"))

    def test_w_repozytorium_NIE_zdejmujemy_cudzego_zabezpieczenia(self):
        """W repozytorium zmiany Codexa da się cofnąć — niech ta ochrona zostanie."""
        wykonawca = WykonawcaCodex()
        wykonawca._flagi = ()
        korzen = str(Path(__file__).resolve().parents[1])
        self.assertTrue(_w_repozytorium_git(korzen), "Kit sam jest repozytorium git")
        self.assertNotIn("--skip-git-repo-check", self._zlap(wykonawca, katalog=korzen))

    def test_prompt_idzie_wejsciem_a_nie_argumentem(self):
        """Treść zadania w `argv` widzi każdy przez `ps` — ta sama zasada, co przy kluczu."""
        wykonawca = WykonawcaCodex()
        wykonawca._flagi = ()
        polecenia = self._zlap(wykonawca, katalog="/nie/repozytorium")
        self.assertEqual(polecenia[-1], "-")
        self.assertNotIn("Usuń pliki", " ".join(polecenia))

    def test_shell_NIE_dostaje_ramki(self):
        """Powłoka WYKONUJE to, co dostaje — ramka po polsku jest dla niej błędem składni."""
        self.assertFalse(WykonawcaShell().chce_ramke)
        self.assertTrue(WykonawcaCodex().chce_ramke)

    def test_worker_NAPRAWDE_podaje_ramke_wykonawcy_ktory_jej_chce(self):
        """Luka wykryta mutacją: nic nie pilnowało, że ramka w ogóle dochodzi do wykonawcy.

        Testy wyżej sprawdzały `ramka.zbuduj` osobno, a testy workera chodzą po `shell`,
        który ramki nie chce — więc całe wpięcie było nieobsadzone. Usunięcie go nie zapalało
        niczego, a worker wołałby Codexa samą treścią zadania, tak jak w 0.1.
        """
        from sf_kit.config import Konfiguracja
        from sf_kit.worker import obsluz_zadanie
        from sf_kit import wykonawcy

        class WykonawcaProbny(wykonawcy.Wykonawca):
            nazwa = "probny"
            chce_ramke = True

            def __init__(self):
                self.dostal = None

            def dostepny(self):
                return True, ""

            def wykonaj(self, polecenie, *, katalog, limit_s):
                self.dostal = polecenie
                return wykonawcy.Wynik(True, "**Sedno** — ok\n\n**Co zrobiono** — nic")

        probny = WykonawcaProbny()
        stare = dict(wykonawcy._WYKONAWCY)
        wykonawcy._WYKONAWCY["probny"] = probny
        try:
            obsluz_zadanie(_KlientNiemowa(), Konfiguracja(slug="codex-fm", runtime="probny",
                                                          katalog_roboczy="/tmp"), ZADANIE)
        finally:
            wykonawcy._WYKONAWCY.clear()
            wykonawcy._WYKONAWCY.update(stare)

        self.assertIsNotNone(probny.dostal, "wykonawca nie został w ogóle zawołany")
        self.assertIn("codex-fm", probny.dostal, "w promptzie brakuje ramki")
        self.assertIn("**Sedno**", probny.dostal, "prompt nie prosi o sprawozdanie")
        self.assertIn(ZADANIE["body_md"], probny.dostal, "…ale treść zadania ma w nim być")

    def _zlap(self, wykonawca, *, katalog: str) -> list:
        """Uruchamia `wykonaj` z podmienionym podprocesem i oddaje zbudowaną listę argumentów."""
        zlapane = {}

        def podstawiony(argumenty, **reszta):
            zlapane["argumenty"] = argumenty
            raise FileNotFoundError("test nie uruchamia Codexa")

        oryginal = subprocess.run
        subprocess.run = podstawiony
        try:
            wykonawca.wykonaj("treść", katalog=katalog, limit_s=5)
        finally:
            subprocess.run = oryginal
        return zlapane["argumenty"]


class _Doszlo(Exception):
    """Znacznik: sterowanie doszło do pętli workera, czyli bramka `shell` przepuściła."""


class TestBramkiWersjiIShell(unittest.TestCase):
    """A5 i A6 — wersja z jednego miejsca, `shell` za jawnym zezwoleniem.

    Podmianki cofamy w `tearDown`. Test, który zostawia po sobie podmienioną funkcję modułu,
    psuje sąsiadów i robi to w sposób zależny od kolejności — czyli najtrudniejszy do
    zdiagnozowania z możliwych.
    """

    def setUp(self):
        from sf_kit import cli
        import sf_kit.worker as worker

        self._cli = cli
        self._worker = worker
        self._stare = (cli.konfiguracja.wczytaj, cli._klient, worker.uruchom)

    def tearDown(self):
        (self._cli.konfiguracja.wczytaj, self._cli._klient,
         self._worker.uruchom) = self._stare

    def test_wersja_jest_w_JEDNYM_miejscu(self):
        """`--version`, `User-Agent` i tag gita mają mówić to samo.

        Trzy kopie rozjeżdżają się przy pierwszym wydaniu, a wtedy „która wersja u ciebie
        stoi" przestaje być pytaniem z odpowiedzią.
        """
        from sf_kit import WERSJA
        from sf_kit.api import Klient

        naglowki = Klient(baza="https://x", klucz="k", organizacja="o")._naglowki()
        self.assertEqual(naglowki["User-Agent"], f"sf-agent-kit/{WERSJA}")

    def test_shell_bez_zezwolenia_ODMAWIA_z_wyjasnieniem(self):
        """Sama flaga `--runtime shell` wystarczała w 0.1.

        Czyli każdy, kto zobaczył ją w `--help`, mógł zamienić dowolne zadanie z kolejki
        w polecenie powłoki na swojej maszynie — bez żadnego drugiego kroku.
        """
        with self.assertRaises(SystemExit) as pulapka:
            self._cli.polecenie_worker(self._argumenty(zezwol_shell=False))

        tresc = str(pulapka.exception)
        self.assertIn("zezwol_shell", tresc)
        self.assertIn("--runtime codex", tresc, "komunikat ma mówić, co zrobić zamiast")

    def test_shell_z_zezwoleniem_przechodzi_bramke(self):
        """Druga strona bramki: administrator, który świadomie ją otworzył, ma móc pracować."""
        with self.assertRaises(_Doszlo):
            self._cli.polecenie_worker(self._argumenty(zezwol_shell=True))

    def test_codex_bramki_shella_nie_dotyka(self):
        """Domyślny wykonawca nie ma nic wspólnego z tym zezwoleniem."""
        with self.assertRaises(_Doszlo):
            self._cli.polecenie_worker(
                self._argumenty(zezwol_shell=False, runtime="codex"))

    def _argumenty(self, *, zezwol_shell: bool, runtime: str = "shell"):
        """Konfiguracja + podmiana klienta i pętli — testujemy samą bramkę, nie pracę."""
        from sf_kit import config

        konf = config.Konfiguracja(adres="https://x", organizacja="o", slug="s",
                                   runtime=runtime, zezwol_shell=zezwol_shell)

        class Argumenty:
            pass

        a = Argumenty()
        a.runtime = runtime
        a.interval = None
        a.once = True

        self._cli.konfiguracja.wczytaj = lambda: konf
        # `*_` zamiast jednego parametru: od v0.4 `_klient` przyjmuje też `args` (stamtąd
        # bierze `--org`). Atrapa o sztywnej liczbie parametrów wywracała się na zmianie
        # sygnatury, choć mierzy coś zupełnie innego — bramkę wykonawcy `shell`.
        self._cli._klient = lambda *_a, **_k: object()
        self._worker.uruchom = _podniesc
        return a


def _podniesc(*_a, **_k):
    raise _Doszlo()


if __name__ == "__main__":
    unittest.main()


class TestOchronaRepozytorium(unittest.TestCase):
    """`sf-kit init` NAPRAWDĘ włącza ochronę przed zapisaniem klucza (B11).

    README obiecywał to od wersji 0.1, a `init` tego nie robił: instalator haka istniał jako
    skrypt, który trzeba było uruchomić samemu. Nieprawdziwe zdanie o zabezpieczeniu jest
    gorsze od braku zabezpieczenia, bo zdejmuje czujność — i dlatego obietnicy pilnuje odtąd
    test, a nie akapit.
    """

    def test_init_instaluje_hak_w_repozytorium(self):
        import shutil
        import subprocess
        import tempfile

        korzen = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tymczasowy:
            kopia = Path(tymczasowy) / "kit"
            # `.git` WYKLUCZONY: kopiowanie go przeniosłoby razem z repozytorium hak,
            # który jest tu przedmiotem badania — test zaczynałby od stanu końcowego.
            shutil.copytree(korzen, kopia,
                            ignore=shutil.ignore_patterns("__pycache__", ".git"))
            subprocess.run(["git", "init", "-q"], cwd=kopia, check=True,
                           env={"PATH": "/usr/bin:/bin", "HOME": tymczasowy})
            hak = kopia / ".git" / "hooks" / "pre-commit"
            self.assertFalse(hak.exists(), "świeże repozytorium nie ma jeszcze haka")

            wynik = subprocess.run(
                ["bash", str(kopia / "hooks" / "install.sh")], cwd=kopia,
                capture_output=True, text=True,
                env={"PATH": "/usr/bin:/bin", "HOME": tymczasowy})

            self.assertEqual(wynik.returncode, 0, wynik.stderr)
            self.assertTrue(hak.exists(), "hak nie został zainstalowany")

    def test_init_wola_instalator(self):
        """Sama obecność instalatora nic nie daje, dopóki `init` go nie uruchamia."""
        import inspect

        from sf_kit import cli

        zrodlo = inspect.getsource(cli.polecenie_init)
        self.assertIn("_wlacz_ochrone_repozytorium", zrodlo,
                      "`init` nie włącza ochrony — README obiecuje coś, czego nie robi")
