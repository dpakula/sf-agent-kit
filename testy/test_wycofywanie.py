"""Worker wycofuje się, gdy SalesForge nie odpowiada (uzupełnienie v0.2).

v0.2 (14.09.2026) - APro Agents / borys-sf

CZEGO BRAKOWAŁO
Worker pytał co minutę niezależnie od tego, czy serwer ma chwilową czkawkę, czy leży od trzech
godzin. Przy kilku agentach na jednej instalacji to stały ostrzał maszyny, która właśnie ma
awarię. README opisywał zwiększanie odstępu (30 s, 60 s, 120 s) jako instrukcję dla człowieka
wołającego API ręcznie — worker sam tego nie robił, a dokument nie mówił, że nie robi.

Testujemy SAMĄ REGUŁĘ odstępu (funkcja czysta), a nie pętlę z prawdziwym czekaniem: test,
który śpi dwie sekundy, żeby sprawdzić arytmetykę, jest gorszy od testu tej arytmetyki.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit.worker import MAX_ODSTEP_AWARII_S, odstep_po_awarii  # noqa: E402

BAZOWY = 60


class TestWycofywanie(unittest.TestCase):

    def test_bez_awarii_odstep_sie_nie_zmienia(self):
        """Praca normalna ma wyglądać dokładnie tak, jak dotąd."""
        self.assertEqual(odstep_po_awarii(BAZOWY, 0), BAZOWY)

    def test_odstep_rosnie_z_kazda_nieudana_proba(self):
        """Sedno: serwer w awarii ma dostawać coraz mniej pytań, nie tyle samo."""
        odstepy = [odstep_po_awarii(BAZOWY, n) for n in (1, 2, 3)]
        self.assertEqual(odstepy, [120, 240, 480])
        self.assertTrue(all(a < b for a, b in zip(odstepy, odstepy[1:])))

    def test_odstep_ma_sufit(self):
        """Bez sufitu po dobie awarii worker obudziłby się za kilka lat.

        `2 ** nieudanych` rośnie szybciej, niż podpowiada intuicja: przy 20 próbach to już
        ponad 60 lat czekania. Sufit sprawia, że po ustaniu awarii worker wraca sam.
        """
        self.assertEqual(odstep_po_awarii(BAZOWY, 50), MAX_ODSTEP_AWARII_S)
        self.assertLessEqual(odstep_po_awarii(BAZOWY, 8), MAX_ODSTEP_AWARII_S)

    def test_powrot_do_bazowego_jest_NATYCHMIASTOWY(self):
        """Awaria, która minęła, nie ma prawa spowalniać pracy przez następne pół godziny.

        Licznik zeruje się po pierwszej udanej próbie — gdyby opadał stopniowo, worker po
        krótkiej przerwie w sieci pracowałby wolniej jeszcze długo po jej ustaniu, a nikt by
        nie wiedział dlaczego.
        """
        self.assertEqual(odstep_po_awarii(BAZOWY, 0), BAZOWY)

    def test_krotszy_odstep_bazowy_daje_krotsze_wycofanie(self):
        """Reguła skaluje się od ustawienia użytkownika, a nie od zaszytej liczby."""
        self.assertEqual(odstep_po_awarii(10, 1), 20)
        self.assertEqual(odstep_po_awarii(10, 2), 40)


class TestPetlaUzywaReguly(unittest.TestCase):
    """Sama funkcja może być poprawna i nieużywana — to jest test drugiej połowy."""

    def test_petla_wola_odstep_po_awarii_przy_bledzie_pobrania(self):
        import inspect

        from sf_kit import worker

        zrodlo = inspect.getsource(worker.uruchom)
        self.assertIn("odstep_po_awarii", zrodlo,
                      "pętla nie korzysta z wycofywania — reguła byłaby martwym kodem")
        self.assertIn("nieudanych = 0", zrodlo, "licznik nie zeruje się po udanej próbie")


if __name__ == "__main__":
    unittest.main()


class TestPrawdaOSystemie(unittest.TestCase):
    """Kit mówi PRAWDĘ o tym, czy prawa pliku chronią klucz (uzupełnienie v0.2).

    Na Windows `chmod` ustawia tylko atrybut „tylko do odczytu" — nie to, kto plik przeczyta.
    Komunikat „prawa 600" byłby tam nieprawdą o zabezpieczeniu, a nieprawda o zabezpieczeniu
    zdejmuje czujność skuteczniej, niż brak zabezpieczenia ją podnosi (ta sama lekcja, co przy
    haku, który README obiecywał, a `init` nie włączał).
    """

    def test_na_uniksie_prawa_chronia(self):
        import os

        from sf_kit.klucz import czy_prawa_chronia

        self.assertEqual(czy_prawa_chronia(), os.name == "posix")

    def test_komunikat_zapisu_NIE_obiecuje_praw_tam_gdzie_ich_nie_ma(self):
        """Podmieniamy `os.name` na windowsowy i żądamy, żeby komunikat się zmienił."""
        import os
        import tempfile

        from sf_kit import klucz as k

        with tempfile.TemporaryDirectory() as katalog:
            stare_xdg = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_CONFIG_HOME"] = katalog
            stare_czy = k.czy_prawa_chronia
            try:
                k.czy_prawa_chronia = lambda: False
                komunikat = k._zapisz_plik("sk_live_testowy")
            finally:
                k.czy_prawa_chronia = stare_czy
                if stare_xdg is None:
                    os.environ.pop("XDG_CONFIG_HOME", None)
                else:
                    os.environ["XDG_CONFIG_HOME"] = stare_xdg

        self.assertIn("NIE ograniczają dostępu", komunikat)
        self.assertNotIn("prawa 600", komunikat)
        self.assertNotIn("sk_live_testowy", komunikat, "komunikat nie powtarza klucza")
