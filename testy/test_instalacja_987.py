"""Instalacja bez gita, aktualizacja z ZIP-a, klucz w Menedżerze poświadczeń (ADVERTPR-987).

v0.1 (29.09.2026) - APro Agents / borys-sf

Bez sieci i bez Windows: archiwum budujemy z TEGO repo (z komentarzem = SHA, jak GitHub),
pobieranie i Menedżer poświadczeń są atrapami. Prawdziwy Windows sprawdza przebieg
end-to-end na maszynie z Windows 11 (wpis na ADVERTPR-987).

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

KOD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOD))

from sf_kit import aktualizacje, instalacja, klucz  # noqa: E402

SHA = "a" * 40
INNY_SHA = "b" * 40


def zbuduj_zip(cel: Path, *, komentarz: str = SHA, prefiks: str | None = None,
               dodatkowe: dict | None = None) -> Path:
    """ZIP jak z `codeload`: jeden katalog `sf-agent-kit-<ref>/…`, komentarz = SHA."""
    prefiks = prefiks or f"sf-agent-kit-{komentarz[:12] or 'x'}/"
    with zipfile.ZipFile(cel, "w") as z:
        z.write(KOD / "sf-kit", prefiks + "sf-kit")
        for plik in (KOD / "sf_kit").glob("*.py"):
            z.write(plik, prefiks + "sf_kit/" + plik.name)
        for nazwa, tresc in (dodatkowe or {}).items():
            z.writestr(nazwa, tresc)
        z.comment = komentarz.encode()
    return cel


class Rozpakowanie(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_komentarz_archiwum_to_commit(self):
        zrodlo, commit = instalacja.rozpakuj(zbuduj_zip(self.tmp / "k.zip"), self.tmp / "r")
        self.assertEqual(commit, SHA)
        self.assertTrue((zrodlo / "sf-kit").is_file())

    def test_inny_commit_niz_wymaga_sf_to_odmowa_przed_rozpakowaniem(self):
        with self.assertRaises(instalacja.BladInstalacji) as ctx:
            instalacja.rozpakuj(zbuduj_zip(self.tmp / "k.zip"), self.tmp / "r",
                                oczekiwany_commit=INNY_SHA)
        self.assertIn("WERYFIKACJA NIE PRZESZŁA", str(ctx.exception))
        self.assertFalse((self.tmp / "r").exists())

    def test_sciezka_spoza_katalogu_to_odmowa(self):
        arch = zbuduj_zip(self.tmp / "k.zip", dodatkowe={"../../poza.txt": "x"})
        with self.assertRaises(instalacja.BladInstalacji):
            instalacja.rozpakuj(arch, self.tmp / "r")
        self.assertFalse((self.tmp / "poza.txt").exists())

    def test_archiwum_bez_kita_to_odmowa(self):
        arch = self.tmp / "k.zip"
        with zipfile.ZipFile(arch, "w") as z:
            z.writestr("cos-innego/README.md", "nie Kit")
        with self.assertRaises(instalacja.BladInstalacji):
            instalacja.rozpakuj(arch, self.tmp / "r")

    def test_uszkodzony_plik_to_czytelna_odmowa(self):
        arch = self.tmp / "k.zip"
        arch.write_bytes(b"<html>rate limit</html>")
        with self.assertRaises(instalacja.BladInstalacji):
            instalacja.rozpakuj(arch, self.tmp / "r")


@unittest.skipIf(os.name == "nt", "uruchamiacz POSIX")
class Instalacja(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.baza, self.bin = self.tmp / "share" / "sf-kit", self.tmp / "bin"
        self.zrodlo, _ = instalacja.rozpakuj(zbuduj_zip(self.tmp / "k.zip"), self.tmp / "r")

    def _instaluj(self, zrodlo=None, commit=SHA):
        with redirect_stdout(io.StringIO()):
            return instalacja.zainstaluj(zrodlo or self.zrodlo, commit=commit, ref="v9.9.9",
                                         baza=self.baza, bin_=self.bin, dopisz_path=False)

    def test_polecenie_uruchamia_zainstalowany_kod(self):
        polecenie = self._instaluj()
        wynik = subprocess.run([str(polecenie), "--version"], capture_output=True, text=True)
        self.assertEqual(wynik.returncode, 0, wynik.stderr)
        self.assertIn(aktualizacje.WERSJA, wynik.stdout)
        znacznik = json.loads((self.baza / "app" / instalacja.PLIK_ZNACZNIKA).read_text("utf-8"))
        self.assertEqual((znacznik["sposob"], znacznik["commit"], znacznik["ref"]), ("zip", SHA, "v9.9.9"))

    def test_ponowna_instalacja_podmienia_kod_i_sprzata(self):
        self._instaluj()
        (self.baza / "app" / "stary-plik.txt").write_text("z poprzedniej wersji")
        self._instaluj(commit=INNY_SHA)
        self.assertFalse((self.baza / "app" / "stary-plik.txt").exists())
        self.assertFalse((self.baza / "app.stary").exists())
        self.assertFalse((self.baza / "app.nowy").exists())
        znacznik = json.loads((self.baza / "app" / instalacja.PLIK_ZNACZNIKA).read_text("utf-8"))
        self.assertEqual(znacznik["commit"], INNY_SHA)

    def test_aktualizacja_z_zip_sprawdza_commit_i_nie_rusza_przy_rozjezdzie(self):
        self._instaluj()
        przed = (self.baza / "app" / instalacja.PLIK_ZNACZNIKA).read_text("utf-8")

        def zle_pobieranie(adres, plik):
            self.assertIn(INNY_SHA, adres)                      # pobieramy DOKŁADNIE commit z SF
            zbuduj_zip(plik, komentarz=SHA)                     # …a przychodzi inny

        with redirect_stdout(io.StringIO()), self.assertRaises(instalacja.BladInstalacji):
            instalacja.aktualizuj_z_zip(tag="v9.9.10", commit=INNY_SHA, baza=self.baza,
                                        pobieranie=zle_pobieranie)
        self.assertEqual((self.baza / "app" / instalacja.PLIK_ZNACZNIKA).read_text("utf-8"), przed)

        with redirect_stdout(io.StringIO()), mock.patch.object(instalacja, "katalog_polecenia",
                                                               return_value=self.bin):
            instalacja.aktualizuj_z_zip(tag="v9.9.10", commit=INNY_SHA, baza=self.baza,
                                        pobieranie=lambda a, p: zbuduj_zip(p, komentarz=INNY_SHA))
        znacznik = json.loads((self.baza / "app" / instalacja.PLIK_ZNACZNIKA).read_text("utf-8"))
        self.assertEqual((znacznik["commit"], znacznik["ref"]), (INNY_SHA, "v9.9.10"))

    def test_commit_z_sf_niebedacy_sha_to_odmowa_bez_pobierania(self):
        with self.assertRaises(instalacja.BladInstalacji):
            instalacja.aktualizuj_z_zip(tag="v1", commit="--upload-pack=zlo", baza=self.baza,
                                        pobieranie=lambda a, p: self.fail("nie wolno pobierać"))


class AktualizujWybieraDroge(unittest.TestCase):
    INFO = {"latest": "99.0.0", "min": "0.1.0", "tag": "v99.0.0", "commit": SHA, "breaking": False}

    def test_instalacja_z_zip_idzie_droga_zip(self):
        with mock.patch.object(aktualizacje, "pobierz_info", return_value=self.INFO), \
             mock.patch.object(aktualizacje.Repo, "znajdz", return_value=None), \
             mock.patch.object(instalacja, "ta_instalacja", return_value={"sposob": "zip"}), \
             mock.patch.object(instalacja, "aktualizuj_z_zip") as zip_:
            self.assertTrue(aktualizacje.aktualizuj(object(), mow=lambda *_: None))
        zip_.assert_called_once()
        self.assertEqual(zip_.call_args.kwargs["commit"], SHA)

    def test_blad_zip_to_blad_aktualizacji_z_informacja_ze_nic_nie_zmieniono(self):
        with mock.patch.object(aktualizacje, "pobierz_info", return_value=self.INFO), \
             mock.patch.object(aktualizacje.Repo, "znajdz", return_value=None), \
             mock.patch.object(instalacja, "ta_instalacja", return_value={"sposob": "zip"}), \
             mock.patch.object(instalacja, "aktualizuj_z_zip",
                               side_effect=instalacja.BladInstalacji("WERYFIKACJA NIE PRZESZŁA")):
            with self.assertRaises(aktualizacje.BladAktualizacji) as ctx:
                aktualizacje.aktualizuj(object(), mow=lambda *_: None)
        self.assertIn("Zostałeś przy", str(ctx.exception))

    def test_ani_klon_ani_instalator_to_odmowa(self):
        with mock.patch.object(aktualizacje.Repo, "znajdz", return_value=None), \
             mock.patch.object(instalacja, "ta_instalacja", return_value=None):
            with self.assertRaises(aktualizacje.OdmowaAktualizacji):
                aktualizacje.aktualizuj(object(), mow=lambda *_: None)


class PathPowloki(unittest.TestCase):
    def test_plik_startowy_wg_powloki(self):
        dom = Path.home()
        self.assertEqual(instalacja.plik_startowy_powloki("/bin/zsh", macos=True), dom / ".zshrc")
        self.assertEqual(instalacja.plik_startowy_powloki("/bin/bash", macos=True), dom / ".bash_profile")
        self.assertEqual(instalacja.plik_startowy_powloki("/bin/bash", macos=False), dom / ".bashrc")
        self.assertEqual(instalacja.plik_startowy_powloki("/usr/bin/fish", macos=False), dom / ".profile")

    @unittest.skipIf(os.name == "nt", "POSIX")
    def test_dopisanie_path_raz(self):
        with tempfile.TemporaryDirectory() as dom, \
             mock.patch.dict(os.environ, {"HOME": dom, "SHELL": "/bin/zsh", "PATH": "/usr/bin"}), \
             redirect_stdout(io.StringIO()):
            bin_ = Path(dom) / ".local" / "bin"
            instalacja._path_posix(bin_)
            instalacja._path_posix(bin_)
            tresc = (Path(dom) / ".zshrc").read_text("utf-8")
        self.assertEqual(tresc.count(instalacja.ZNACZNIK_PATH), 1)
        self.assertIn(f'export PATH="{bin_}:$PATH"', tresc)

    def test_katalog_juz_w_path_nic_nie_dopisuje(self):
        self.assertTrue(instalacja._w_path(Path("/opt/x/bin"), os.pathsep.join(["/usr/bin", "/opt/x/bin/"])))


class KluczNaWindows(unittest.TestCase):
    """Droga Windows w `klucz.py` z atrapą Menedżera — prawdziwe `advapi32` sprawdza Windows 11."""

    def setUp(self):
        self.magazyn = {}
        self.tmp = tempfile.TemporaryDirectory()
        from sf_kit import klucz_windows
        self.latki = [
            mock.patch.object(klucz, "czy_windows", return_value=True),
            mock.patch.object(klucz, "czy_macos", return_value=False),
            mock.patch.dict(os.environ, {"SF_KIT_HOME": self.tmp.name}, clear=False),
            mock.patch.object(klucz_windows, "zapisz",
                              side_effect=lambda cel, konto, k: self.magazyn.__setitem__(cel, k)),
            mock.patch.object(klucz_windows, "wczytaj", side_effect=lambda cel: self.magazyn.get(cel)),
            mock.patch.object(klucz_windows, "usun", side_effect=lambda cel: self.magazyn.pop(cel, None) is not None),
        ]
        os.environ.pop("SF_KIT_KEY", None)
        for l in self.latki:
            l.start()

    def tearDown(self):
        for l in reversed(self.latki):
            l.stop()
        self.tmp.cleanup()

    def test_klucz_idzie_do_menedzera_a_nie_do_pliku(self):
        gdzie = klucz.zapisz("sk_live_XXXX")
        self.assertIn("Menedżer poświadczeń", gdzie)
        self.assertEqual(klucz.wczytaj(), "sk_live_XXXX")
        self.assertFalse((Path(self.tmp.name) / "credentials").exists())
        self.assertEqual(list(self.magazyn), [f"{klucz.USLUGA}:{klucz.konto_w_peku()}"])

    def test_blad_menedzera_to_blad_a_nie_cichy_plik(self):
        from sf_kit import klucz_windows
        with mock.patch.object(klucz_windows, "zapisz", side_effect=klucz_windows.BladMenedzera("kod 5")):
            with self.assertRaises(RuntimeError):
                klucz.zapisz("sk_live_XXXX")
        self.assertFalse((Path(self.tmp.name) / "credentials").exists())


class Cli(unittest.TestCase):
    def test_aktualizuj_to_update(self):
        from sf_kit import cli
        # `set_defaults(funkcja=…)` wiąże funkcję przy budowie parsera, czyli w `main` — łatka przed.
        with mock.patch.object(cli, "polecenie_update", return_value=0) as up:
            self.assertEqual(cli.main(["aktualizuj", "--check"]), 0)
        up.assert_called_once()
        self.assertTrue(up.call_args.args[0].check)


if __name__ == "__main__":
    unittest.main()
