"""Kilku agentów na jednej maszynie (v0.3, dopisek Damiana 15.09 03:3x).

v0.3 (15.09.2026) - APro Agents / borys-sf

CO SIĘ ZMIENIŁO I DLACZEGO TERAZ
Do 0.2.2 Kit trzymał konfigurację i klucz PER UŻYTKOWNIK SYSTEMU: jeden `config.json`, jeden
wpis w pęku pod kontem `api-key`. To znaczyło **jeden agent na maszynę**. Damian planuje
kilku w jednym Codeksie, a to jest układ konfiguracji, którego potem nie da się ruszyć bez
migracji u ludzi, którzy już pracują.

DWIE RZECZY, KTÓRYCH TE TESTY PILNUJĄ NAJMOCNIEJ
1. Pojedynczy użytkownik ma NIE zauważyć zmiany — żadnej nowej flagi, gdy agent jest jeden.
2. Przy kilku agentach Kit ma ODMÓWIĆ, a nie wybrać któregoś. Wybranie „pierwszego z brzegu"
   znaczy pisanie do cudzej Organizacji cudzym kluczem — błąd niewidoczny ani w wyniku,
   ani w logu.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import klucz  # noqa: E402


class _Swiat:
    """Tymczasowy `~/.config` z zadanym układem agentów."""

    def __init__(self, agenci=(), stary_uklad=False):
        self.katalog = tempfile.TemporaryDirectory()
        korzen = Path(self.katalog.name) / "sf-kit"
        korzen.mkdir(parents=True)
        for slug in agenci:
            (korzen / slug).mkdir()
            (korzen / slug / "config.json").write_text(
                json.dumps({"slug": slug}), encoding="utf-8")
        if stary_uklad:
            (korzen / "config.json").write_text(json.dumps({"slug": "stary"}), encoding="utf-8")
        self.korzen = korzen

    def __enter__(self):
        self._stare = os.environ.get("XDG_CONFIG_HOME")
        self._stary_dom = os.environ.pop(klucz.ZMIENNA_DOMU, None)
        os.environ["XDG_CONFIG_HOME"] = self.katalog.name
        klucz.ustaw_agenta(None)
        return self

    def __exit__(self, *_):
        klucz.ustaw_agenta(None)
        if self._stare is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._stare
        if self._stary_dom is not None:
            os.environ[klucz.ZMIENNA_DOMU] = self._stary_dom
        self.katalog.cleanup()


class TestJedenAgentDzialaJakDotad(unittest.TestCase):

    def test_jeden_agent_NIE_wymaga_flagi(self):
        """Sedno: nie karzemy pojedynczego użytkownika za to, że ktoś inny ma kilku agentów."""
        with _Swiat(agenci=["codex-fm"]) as s:
            self.assertEqual(klucz.sciezka_konfiguracji(), s.korzen / "codex-fm")

    def test_uklad_sprzed_podzialu_dziala_bez_przenosin(self):
        """Ludzie, którzy skonfigurowali Kit wcześniej, nie mają obowiązku niczego przenosić.

        Aktualizacja, która każe im zaczynać od nowa, jest aktualizacją, której nie zrobią.
        """
        with _Swiat(stary_uklad=True) as s:
            self.assertEqual(klucz.sciezka_konfiguracji(), s.korzen)
            self.assertEqual(klucz.konto_w_peku(), klucz.KONTO_JEDNEGO_AGENTA)

    def test_pusta_maszyna_daje_katalog_bazowy(self):
        """`init` musi mieć gdzie zacząć, zanim jakikolwiek agent istnieje."""
        with _Swiat() as s:
            self.assertEqual(klucz.sciezka_konfiguracji(), s.korzen)


class TestKilkuAgentow(unittest.TestCase):

    def test_kilku_agentow_bez_flagi_ODMAWIA(self):
        with _Swiat(agenci=["codex-fm", "kodeks-dpakula"]):
            with self.assertRaises(klucz.WieluAgentow) as p:
                klucz.sciezka_konfiguracji()
        tresc = str(p.exception)
        self.assertIn("codex-fm", tresc)
        self.assertIn("kodeks-dpakula", tresc)
        self.assertIn("--agent", tresc, "komunikat ma mówić, co zrobić")

    def test_flaga_agent_rozstrzyga(self):
        with _Swiat(agenci=["codex-fm", "kodeks-dpakula"]) as s:
            klucz.ustaw_agenta("kodeks-dpakula")
            self.assertEqual(klucz.sciezka_konfiguracji(), s.korzen / "kodeks-dpakula")

    def test_stary_uklad_OBOK_nowych_tez_odmawia(self):
        """Ktoś w połowie przenosin — najgorszy moment na zgadywanie."""
        with _Swiat(agenci=["a", "b"], stary_uklad=True):
            with self.assertRaises(klucz.WieluAgentow) as p:
                klucz.sciezka_konfiguracji()
        self.assertIn("sprzed podziału", str(p.exception))

    def test_katalog_bez_konfiguracji_NIE_jest_agentem(self):
        """Śmieć po nieudanym `init` nie ma prawa uczestniczyć w wyborze."""
        with _Swiat(agenci=["prawdziwy"]) as s:
            (s.korzen / "smiec-po-nieudanym-init").mkdir()
            self.assertEqual(klucz.agenci(), ["prawdziwy"])
            self.assertEqual(klucz.sciezka_konfiguracji(), s.korzen / "prawdziwy")


class TestKluczPerAgent(unittest.TestCase):

    def test_konto_w_peku_to_SLUG_agenta(self):
        """Jeden wpis „api-key" na maszynę znaczył jeden agent na maszynę."""
        with _Swiat(agenci=["codex-fm", "kodeks-dpakula"]):
            klucz.ustaw_agenta("codex-fm")
            self.assertEqual(klucz.konto_w_peku(), "codex-fm")
            klucz.ustaw_agenta("kodeks-dpakula")
            self.assertEqual(klucz.konto_w_peku(), "kodeks-dpakula")

    def test_klucze_dwoch_agentow_NIE_mieszaja_sie_w_pliku(self):
        """Na Linuksie klucz leży w pliku — ma leżeć w katalogu SWOJEGO agenta."""
        with _Swiat(agenci=["a", "b"]) as s:
            klucz.ustaw_agenta("a")
            klucz._zapisz_plik("sk_live_aaa")
            klucz.ustaw_agenta("b")
            klucz._zapisz_plik("sk_live_bbb")

            self.assertEqual((s.korzen / "a" / "credentials").read_text().strip(), "sk_live_aaa")
            self.assertEqual((s.korzen / "b" / "credentials").read_text().strip(), "sk_live_bbb")

    def test_zmienna_domu_wygrywa_ze_wszystkim(self):
        """Powiedziane wprost — nie zgadujemy niczego dalej (kontener, wspólna maszyna)."""
        with _Swiat(agenci=["a", "b"]) as s:
            wskazany = Path(s.katalog.name) / "gdzie-indziej"
            os.environ[klucz.ZMIENNA_DOMU] = str(wskazany)
            try:
                klucz.ustaw_agenta("a")
                self.assertEqual(klucz.sciezka_konfiguracji(), wskazany)
            finally:
                os.environ.pop(klucz.ZMIENNA_DOMU, None)


if __name__ == "__main__":
    unittest.main()
