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
        dokładnie wtedy, gdy sieć wróci za dziesięć minut."""
        self.assertIn("StartLimitIntervalSec=0", self._unit())

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
