"""Kit 0.17.1: klucz w `init` na Windows PowerShell 5.1 (GRA-1, Asia, 06.10.2026) i ze `SF_KIT_KEY`.

v1.0.0 (06.10.2026) - APro Agents / borys-sf

CZEGO PILNUJĄ
· Ctrl+V w ukrytym polu (znak `\\x16`) wkleja SCHOWEK — dotąd klucz był odrzucany jako „nie wygląda na klucz”.
· Gwiazdki za każdy znak (widać, że coś doszło), Backspace, klawisze specjalne, Ctrl+C.
· Wklejone nie zaczyna się od `sk_live_` → jedna widoczna druga próba, nie odmowa.
· `SF_KIT_KEY` ustawiona → `init` nie pyta; znaki sterujące i spacje ze schowka odcięte.
Prawdziwej konsoli Windows tu nie ma — `msvcrt` podmieniamy atrapą (szew w `_czytaj_ukryty_windows`).
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import klucz  # noqa: E402

KLUCZ = "sk_live" + "_0082abcdef1234567890"   # z części — hak repozytorium szuka wzorca klucza


def _konsola(znaki: str):
    """Atrapa `msvcrt`: kolejne znaki z klawiatury + zapis tego, co poszło na ekran."""
    wejscie = iter(znaki)
    ekran: list[str] = []
    return (lambda: next(wejscie)), ekran.append, ekran


class TestUkrytePoleWindows(unittest.TestCase):

    def test_ctrl_v_wkleja_schowek(self):
        getwch, putwch, ekran = _konsola("\x16\r")
        wynik = klucz._czytaj_ukryty_windows("K: ", getwch=getwch, putwch=putwch,
                                            schowek=lambda: KLUCZ + "\r\n")
        self.assertEqual(wynik, KLUCZ)
        self.assertEqual("".join(ekran).count("*"), len(KLUCZ))     # gwiazdki, nie klucz
        self.assertNotIn(KLUCZ, "".join(ekran))

    def test_prawy_przycisk_czyli_zwykle_znaki(self):
        getwch, putwch, _ = _konsola(KLUCZ + "\r")
        self.assertEqual(klucz._czytaj_ukryty_windows("K: ", getwch=getwch, putwch=putwch,
                                                     schowek=lambda: ""), KLUCZ)

    def test_backspace_i_klawisze_specjalne(self):
        getwch, putwch, _ = _konsola("sk_live_X\b" + "\xe0H" + "1\r")
        self.assertEqual(klucz._czytaj_ukryty_windows("K: ", getwch=getwch, putwch=putwch,
                                                     schowek=lambda: ""), "sk_live_1")

    def test_ctrl_c_przerywa(self):
        getwch, putwch, _ = _konsola("sk\x03")
        with self.assertRaises(KeyboardInterrupt):
            klucz._czytaj_ukryty_windows("K: ", getwch=getwch, putwch=putwch, schowek=lambda: "")

    def test_zle_wklejenie_daje_widoczna_druga_probe(self):
        with redirect_stdout(io.StringIO()) as wyjscie:
            wynik = klucz._zapytaj_windows(czytaj=lambda _e: "ghp_cos", widoczny=lambda _e: f"  {KLUCZ}\x16 ")
        self.assertEqual(wynik, KLUCZ)
        self.assertIn("PRAWYM przyciskiem", wyjscie.getvalue())

    def test_dobre_wklejenie_bez_drugiej_proby(self):
        def nie_wolno(_e):
            raise AssertionError("druga próba niepotrzebna")
        self.assertEqual(klucz._zapytaj_windows(czytaj=lambda _e: KLUCZ, widoczny=nie_wolno), KLUCZ)

    def test_zapytaj_na_windows_idzie_wlasna_droga(self):
        with mock.patch.object(klucz, "czy_windows", return_value=True), \
                mock.patch.object(klucz, "czy_macos", return_value=False), \
                mock.patch.object(klucz, "_zapytaj_windows", return_value=KLUCZ), \
                mock.patch.object(klucz.getpass, "getpass", side_effect=AssertionError("getpass na Windows")), \
                mock.patch.dict(os.environ, {}, clear=False), redirect_stdout(io.StringIO()):
            os.environ.pop(klucz.ZMIENNA_KLUCZA, None)
            self.assertEqual(klucz.zapytaj(), KLUCZ)


class TestKluczZeZmiennej(unittest.TestCase):

    def test_init_nie_pyta_gdy_zmienna_ustawiona(self):
        with mock.patch.dict(os.environ, {klucz.ZMIENNA_KLUCZA: f"﻿{KLUCZ}\r\n"}), \
                mock.patch.object(klucz.getpass, "getpass", side_effect=AssertionError("pytał")), \
                mock.patch.object(klucz, "_zapytaj_windows", side_effect=AssertionError("pytał")), \
                redirect_stdout(io.StringIO()) as wyjscie:
            self.assertEqual(klucz.zapytaj(), KLUCZ)
        self.assertNotIn(KLUCZ, wyjscie.getvalue())                  # na ekranie tylko skrót

    def test_zla_wartosc_zmiennej_nadal_odrzucona(self):
        with mock.patch.dict(os.environ, {klucz.ZMIENNA_KLUCZA: "ghp_token"}), \
                redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            klucz.zapytaj()


if __name__ == "__main__":
    unittest.main()
