"""Profil `autor` → `asystent` (ADVERTPR-959): stara nazwa w konfiguracji działa dalej.

Aktualizacja Kita nie może nikomu nic zepsuć: plik z `profil: autor` (Kimi, Wójt, Codex FM)
wczytuje się jako `asystent` i Kit mówi, żeby nazwę zmienić — nie odmawia.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, klucz  # noqa: E402
from sf_kit import config as konfiguracja  # noqa: E402


class _Katalog:
    """Własny katalog konfiguracji na czas testu (jak w `test_wielu_agentow`)."""

    def __init__(self, profil: str):
        self.katalog = tempfile.TemporaryDirectory()
        korzen = Path(self.katalog.name) / "sf-kit"
        korzen.mkdir(parents=True)
        (korzen / "config.json").write_text(json.dumps({"slug": "wojt", "profil": profil}),
                                            encoding="utf-8")

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


class ProfilAsystent(unittest.TestCase):
    def test_stara_nazwa_w_pliku_dziala_jako_asystent_z_ostrzezeniem(self):
        with _Katalog("autor"):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                konf = konfiguracja.wczytaj()
        self.assertEqual(konf.profil, "asystent")
        self.assertIn("stara nazwa", err.getvalue())
        self.assertIn("asystent", err.getvalue())

    def test_nowa_nazwa_bez_ostrzezenia(self):
        with _Katalog("asystent"):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                konf = konfiguracja.wczytaj()
        self.assertEqual(konf.profil, "asystent")
        self.assertEqual(err.getvalue(), "")

    def test_lista_profili_nie_zna_juz_autora(self):
        self.assertEqual(cli.PROFILE, ("worker", "asystent", "koordynator"))
        self.assertEqual(konfiguracja.PROFIL_ALIASY, {"autor": "asystent"})


if __name__ == "__main__":
    unittest.main()
