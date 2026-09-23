"""Tętno workera i jednostka systemd (ADVERTPR-807 C6).

v0.1 (16.09.2026) - APro Agents / borys-sf

Tętno ma dokładnie dwa sposoby zawieść i oba są kosztowne:
1. **Fałszywe „martwy"** — czujka restartuje workera w połowie pracy modelu, czyli robi tę
   szkodę, przed którą miała chronić.
2. **Fałszywe „żywy"** — worker padł, a nikt się nie dowiaduje, bo brak workera wygląda tak
   samo jak brak zadań.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import usluga  # noqa: E402


class TestTetno(unittest.TestCase):

    def setUp(self):
        self.katalog = tempfile.TemporaryDirectory()
        self.plik = Path(self.katalog.name) / "heartbeat"

    def tearDown(self):
        self.katalog.cleanup()

    def test_swieze_tetno_znaczy_zywy(self):
        usluga.zapisz_tetno(slug="kodeks", stan="czekam", plik=self.plik)
        zywy, co = usluga.czy_zywy(self.plik)
        self.assertTrue(zywy)
        self.assertIn("kodeks", co)

    def test_brak_pliku_znaczy_MARTWY_i_mowi_dlaczego(self):
        zywy, co = usluga.czy_zywy(self.plik)
        self.assertFalse(zywy)
        self.assertIn("nigdy nie wystartował", co)

    def test_uszkodzony_plik_znaczy_martwy_a_nie_wyjatek(self):
        """Czujka ma zaraportować, a nie paść — awaria czujki to cisza, czyli fałszywe OK."""
        self.plik.write_text("to nie jest json", encoding="utf-8")
        zywy, co = usluga.czy_zywy(self.plik)
        self.assertFalse(zywy)
        self.assertIn("nieczytelny", co)

    def test_stare_tetno_znaczy_martwy(self):
        usluga.zapisz_tetno(slug="kodeks", wazne_przez_s=60, plik=self.plik)
        dane = json.loads(self.plik.read_text(encoding="utf-8"))
        zywy, co = usluga.czy_zywy(self.plik, teraz=dane["kiedy"] + 61)
        self.assertFalse(zywy)
        self.assertIn("nie odpowiada", co)

    def test_DLUGIE_zadanie_NIE_jest_uznane_za_martwe(self):
        """Sedno C6: zadanie z limitem 30 min nie odświeża tętna w trakcie wykonania.

        Stały próg dwóch minut kazałby czujce zrestartować workera w połowie pracy modelu.
        Worker deklaruje więc, jak długo ten stan może legalnie trwać.
        """
        usluga.zapisz_tetno(slug="kodeks", stan="pracuję", wazne_przez_s=1800 + 120,
                            plik=self.plik)
        dane = json.loads(self.plik.read_text(encoding="utf-8"))

        # Dwadzieścia minut później — dla stałego progu to dawno martwy.
        zywy, _ = usluga.czy_zywy(self.plik, teraz=dane["kiedy"] + 20 * 60)
        self.assertTrue(zywy, "worker w trakcie długiego zadania ma być uznany za żywego")

        # Ale po deklarowanym oknie już nie.
        zywy, _ = usluga.czy_zywy(self.plik, teraz=dane["kiedy"] + 1800 + 121)
        self.assertFalse(zywy)

    def test_tetno_BEZ_pola_wazne_do_wraca_do_stalego_progu(self):
        """Tętno zapisane starszą wersją Kitu nie może ogłosić workera martwym po aktualizacji."""
        self.plik.write_text(json.dumps({"slug": "kodeks", "stan": "czekam", "kiedy": 1000}),
                             encoding="utf-8")
        zywy, _ = usluga.czy_zywy(self.plik, teraz=1000 + 60)
        self.assertTrue(zywy)
        zywy, _ = usluga.czy_zywy(self.plik, teraz=1000 + 121)
        self.assertFalse(zywy)

    def test_zapis_tetna_NIE_wywraca_sie_na_niedostepnym_katalogu(self):
        """Worker, który przestaje pracować przez plik diagnostyczny, zamienia usterkę w awarię."""
        niemozliwy = Path("/nie-ma-takiego-katalogu-807/heartbeat")
        usluga.zapisz_tetno(slug="kodeks", plik=niemozliwy)      # ma nie rzucić

    def test_zapis_jest_ATOMOWY(self):
        """Czujka czytająca w trakcie zapisu dostałaby inaczej połowę linii."""
        usluga.zapisz_tetno(slug="kodeks", plik=self.plik)
        usluga.zapisz_tetno(slug="kodeks", plik=self.plik)
        self.assertEqual(json.loads(self.plik.read_text(encoding="utf-8"))["slug"], "kodeks")
        self.assertFalse(self.plik.with_suffix(".tmp").exists(),
                         "plik tymczasowy ma zniknąć po podmianie")


class TestJednostka(unittest.TestCase):

    def _unit(self):
        return usluga.tresc_unitu(slug="kodeks", polecenie="/opt/sf-kit/sf-kit",
                                  katalog_domowy="/home/kodeks",
                                  plik_srodowiska="/home/kodeks/.config/sf-kit/kodeks.env")

    def test_jednostka_wstaje_po_awarii(self):
        unit = self._unit()
        self.assertIn("Restart=always", unit)
        self.assertIn("RestartSec=30", unit)

    def test_jednostka_NIE_poddaje_sie_po_kilku_probach(self):
        """Worker pada najczęściej na sieci; domyślny limit startów wyłączyłby go na dobre
        dokładnie wtedy, gdy sieć wróci za dziesięć minut.

        W SEKCJI [Unit]: do 0.9.0 linia stała w [Service], systemd ją ignorował („Unknown
        key … ignoring"), a ten test — sprawdzający samą obecność linii — był zielony."""
        unit = self._unit()
        sekcja_unit = unit.split("\n[Service]\n")[0]
        self.assertIn("StartLimitIntervalSec=0", sekcja_unit)
        self.assertNotIn("StartLimitIntervalSec", unit.split("\n[Service]\n")[1])

    def test_klucz_NIE_stoi_w_jednostce(self):
        """Jednostkę czyta się szerzej niż katalog agenta, a `systemctl cat` pokazuje ją każdemu.

        Sekret przepisany do opisu usługi zostaje tam na zawsze.
        """
        unit = self._unit()
        self.assertIn("EnvironmentFile=", unit)
        for podejrzane in ("sk_live", "Environment=SF_KLUCZ", "--klucz"):
            self.assertNotIn(podejrzane, unit)

    def test_jednostka_czeka_na_siec(self):
        unit = self._unit()
        self.assertIn("After=network-online.target", unit)

    def test_nazwa_jednostki_zawiera_slug(self):
        """Kilku agentów na jednej maszynie to norma — jednostka bez sluga byłaby jedna."""
        self.assertEqual(usluga.nazwa_unitu("kodeks"), "sf-kit-worker@kodeks.service")

    def test_domyslnie_jednostka_UZYTKOWNIKA_a_nie_systemowa(self):
        """Instalacja ma się udać bez proszenia administratora o cokolwiek."""
        sciezka = usluga.sciezka_unitu("kodeks")
        self.assertIn(".config/systemd/user", str(sciezka))


if __name__ == "__main__":
    unittest.main()


class TestTetnoPerSlug(unittest.TestCase):
    """Tętno jednego workera, nie jednego konta systemowego (v0.5.3, ADVERTPR-850).

    Decyzja z 17.09 daje DWA konta na wykonawcę (`kodeks-worker` + `kodeks`, jak Kimi), więc
    dwa workery chodzą na tym samym koncie systemowym. Do v0.5.2 pisały do jednego pliku
    `~/.sf-kit/heartbeat` — czujka widziała jedno tętno, uznawała oba za żywe i nie zauważała,
    że jeden leży. Przy jednym workerze na maszynę to działało i dlatego nikt tego nie widział.
    """

    def test_dwa_slugi_maja_dwa_pliki(self):
        a = usluga.plik_tetna("kodeks-worker")
        b = usluga.plik_tetna("kodeks")
        self.assertNotEqual(a, b, "dwa workery na jednym koncie nadpisują sobie tętno")
        self.assertIn("kodeks-worker", a.name)

    def test_slug_ze_znakami_specjalnymi_nie_wychodzi_z_katalogu(self):
        """Slug idzie do NAZWY PLIKU, więc `../` w nim byłoby zapisem poza katalogiem."""
        plik = usluga.plik_tetna("../../etc/passwd")
        self.assertEqual(plik.parent, usluga.KATALOG_TETNA)
        self.assertNotIn("/", plik.name)

    def test_pusty_slug_nie_daje_pliku_bez_nazwy(self):
        self.assertTrue(usluga.plik_tetna("").name.endswith("bez-slugu"))

    def test_zapis_trafia_do_pliku_ze_slugiem(self):
        import tempfile

        with tempfile.TemporaryDirectory() as katalog:
            with unittest.mock.patch.object(usluga, "KATALOG_TETNA", Path(katalog)):
                usluga.zapisz_tetno(slug="kimi-worker", stan="czekam")
                self.assertTrue((Path(katalog) / "heartbeat-kimi-worker").exists(),
                                "tętno nie trafiło do pliku ze slugiem")

    def test_czujka_spada_na_STARY_plik_gdy_nowego_nie_ma(self):
        """Zapas na czas aktualizacji: czujka z v0.5.3 odpytuje workera z v0.5.2.

        Bez tego pierwszy przebieg czujki po aktualizacji ogłosiłby martwymi wszystkich
        workerów, którzy jeszcze nie dostali nowej wersji — czyli awarię tam, gdzie jej nie ma.
        """
        import json as _json
        import tempfile
        import time as _time

        with tempfile.TemporaryDirectory() as katalog:
            stary = Path(katalog) / "heartbeat"
            stary.write_text(_json.dumps({
                "slug": "stary-worker", "stan": "czekam",
                "kiedy": int(_time.time()), "wazne_do": int(_time.time()) + 120,
            }), encoding="utf-8")
            with unittest.mock.patch.object(usluga, "KATALOG_TETNA", Path(katalog)), \
                 unittest.mock.patch.object(usluga, "PLIK_TETNA_STARY", stary):
                zywy, co = usluga.czy_zywy(slug="stary-worker")
                self.assertTrue(zywy, co)


class TestLaunchd(unittest.TestCase):
    """Agent launchd dla macOS (v0.5.3, ADVERTPR-850) — Kodeks chodzi na macu Damiana."""

    def test_plist_ma_KeepAlive_i_odstep_po_padzie(self):
        """`KeepAlive` to odpowiednik `Restart=always`; bez `ThrottleInterval` awaria sieci
        daje setki startów na minutę i log, w którym nie da się znaleźć przyczyny."""
        tresc = usluga.tresc_plist(slug="kodeks-worker", polecenie="/usr/local/bin/sf-kit",
                                   katalog_domowy="/Users/damian")
        self.assertIn("<key>KeepAlive</key><true/>", tresc)
        self.assertIn("ThrottleInterval", tresc)

    def test_plist_podaje_PATH_bo_launchd_nie_czyta_profilu(self):
        """Najczęstsza przyczyna „usługa wstała i nic nie robi" na macOS: goły PATH
        i proces, który nie znajduje ani `codex`, ani `kimi`, ani samego `sf-kit`."""
        tresc = usluga.tresc_plist(slug="k", polecenie="/usr/local/bin/sf-kit",
                                   katalog_domowy="/Users/damian")
        self.assertIn("<key>PATH</key>", tresc)
        self.assertIn("/opt/homebrew/bin", tresc, "brak ścieżki Homebrew z Apple Silicon")

    def test_plist_ma_osobny_log_bledow(self):
        tresc = usluga.tresc_plist(slug="k", polecenie="/x/sf-kit", katalog_domowy="/Users/d")
        self.assertIn("StandardOutPath", tresc)
        self.assertIn(".err.log", tresc, "błędy w tym samym pliku co wyjście — przy KeepAlive "
                                         "to one mówią, dlaczego worker wstaje w kółko")

    def test_plist_jest_poprawnym_XML(self):
        """Plik, którego launchd nie sparsuje, kończy się milczącym brakiem usługi."""
        import xml.etree.ElementTree as ET

        tresc = usluga.tresc_plist(slug="kodeks-worker", polecenie="/usr/local/bin/sf-kit",
                                   katalog_domowy="/Users/damian")
        ET.fromstring(tresc)   # rzuci, gdy XML jest zepsuty

    def test_polecenie_workera_niesie_slug(self):
        tresc = usluga.tresc_plist(slug="kodeks-worker", polecenie="/x/sf-kit",
                                   katalog_domowy="/Users/d")
        self.assertIn("<string>--agent</string><string>kodeks-worker</string>",
                      tresc.replace("\n    ", "").replace("\n", ""))

    def test_sciezka_plist_w_LaunchAgents_uzytkownika(self):
        """Agent użytkownika, nie demon systemowy — instalacja bez `sudo`."""
        sciezka = usluga.sciezka_plist("kodeks-worker")
        self.assertIn("LaunchAgents", str(sciezka))
        self.assertTrue(sciezka.name.endswith(".plist"))


class TestDrogaDoWykonawcy(unittest.TestCase):
    """Czy da się WYBRAĆ wykonawcę, którego Kit ma (v0.5.3, ADVERTPR-850).

    `WykonawcaKimi` był w rejestrze od 807 C3 i działał — `wybierz("kimi")` zwracało go bez
    mrugnięcia. Ale parser CLI miał `choices=["codex", "shell"]`, więc jedyną drogą do niego
    było obejście `sf-kit` własnym skryptem. **Mechanizm bez drogi do siebie jest mechanizmem,
    którego nie ma** — i ten test pilnuje właśnie drogi, nie mechanizmu.

    Wykryte MUTACJĄ: usunięcie „kimi" z `choices` nie zapalało niczego, bo cała reszta testów
    sprawdzała rejestr wykonawców, do którego CLI nie musi mieć dostępu.
    """

    def _runtime_choices(self):
        import argparse
        import io
        import contextlib
        from sf_kit import cli

        # Parser powstaje w `main()`, więc pytamy o pomoc podkomendy — to jedyne wyjście,
        # które nie wymaga refaktoru produkcyjnego kodu na potrzeby testu.
        bufor = io.StringIO()
        with contextlib.redirect_stdout(bufor), self.assertRaises(SystemExit):
            cli.main(["worker", "--help"])
        return bufor.getvalue()

    def test_CLI_przyjmuje_kazdego_wykonawce_z_rejestru(self):
        from sf_kit import wykonawcy

        pomoc = self._runtime_choices()
        for nazwa in wykonawcy._WYKONAWCY:
            self.assertIn(nazwa, pomoc,
                          f"wykonawca {nazwa} jest w Kicie, ale --runtime go nie przyjmuje "
                          f"- jedyna droga do niego to obejscie CLI")
