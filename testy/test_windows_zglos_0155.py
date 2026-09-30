"""Kit 0.15.5: poprawki z pierwszej instalacji na Windows (JULIAPAK-11) + `zglos --priorytet/--termin`.

v1.0.0 (30.09.2026) - APro Agents / borys-sf

CZEGO PILNUJĄ
· Instalator w kontenerze aplikacji (MSIX, terminal Claude) NIE kończy się sukcesem w miejscu,
  którego człowiek nie widzi: kod ≠ 0 i instrukcja „zrób to we własnym oknie”.
· Ochrona przed kluczem w repozytorium: poza repozytorium gita / bez `bash` — cisza, nie „UWAGA”.
· `zglos --priorytet` idzie do SF; `--termin` na górę opisu, po ludzku; termin w przeszłości albo
  nieczytelny → odmowa PRZED założeniem sprawy.
· Sprawa bez obserwujących → jawna informacja, że nikt poza autorem nie dostanie powiadomienia.
"""
import datetime as dt
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, instalacja  # noqa: E402

DZIS = dt.date(2026, 9, 30)          # środa


class TestTermin(unittest.TestCase):

    def test_formaty(self):
        self.assertEqual(cli._termin_po_ludzku("jutro", dzis=DZIS), "czwartek, 1 października 2026")
        self.assertEqual(cli._termin_po_ludzku("dziś", dzis=DZIS), "środa, 30 września 2026")
        self.assertEqual(cli._termin_po_ludzku("2026-10-02 14:00", dzis=DZIS), "piątek, 2 października 2026, 14:00")
        self.assertEqual(cli._termin_po_ludzku("2026-10-05", dzis=DZIS), "poniedziałek, 5 października 2026")

    def test_przeszlosc_i_smieci(self):
        with self.assertRaises(ValueError):
            cli._termin_po_ludzku("2026-09-01", dzis=DZIS)
        with self.assertRaises(ValueError) as b:
            cli._termin_po_ludzku("na wczoraj", dzis=DZIS)
        self.assertIn("jutro", str(b.exception))


class Atrapa:
    def __init__(self):
        self.zalozona = None

    def zaloz_sprawe(self, **kw):
        self.zalozona = kw
        return {"ticket_id": "t-1", "ticket_prefix": "JULIAPAK", "ticket_number": 12}


def _zglos(argv, *, obserwatorzy_domyslni=()):
    a = Atrapa()
    konf = mock.Mock(obserwatorzy_domyslni=list(obserwatorzy_domyslni), adres="https://sf")
    with mock.patch.object(cli.konfiguracja, "wczytaj", return_value=konf), \
            mock.patch.object(cli.konfiguracja, "wczytaj_jesli_jest", return_value=None), \
            mock.patch.object(cli, "_klient_dla_zapisu", return_value=(a, None)), \
            mock.patch.object(cli, "_opis_z_wejscia", return_value="Opis sprawy"), \
            mock.patch.object(cli, "_pokaz_sprawe"):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            kod = cli.main(["--org", "jp", "zglos", "--tytul", "Ankieta", *argv])
    return kod, a, out.getvalue(), err.getvalue()


class TestZglos(unittest.TestCase):

    def test_priorytet_idzie_do_sf(self):
        kod, a, _, _ = _zglos(["--priorytet", "high"])
        self.assertEqual((kod, a.zalozona["priorytet"]), (0, "high"))

    def test_domyslny_priorytet_medium(self):
        _, a, _, _ = _zglos([])
        self.assertEqual(a.zalozona["priorytet"], "medium")

    def test_termin_na_gorze_opisu_i_uczciwa_uwaga(self):
        with mock.patch.object(cli, "_termin_po_ludzku", return_value="czwartek, 1 października 2026"):
            kod, a, out, _ = _zglos(["--termin", "jutro"])
        self.assertEqual(kod, 0)
        self.assertTrue(a.zalozona["opis"].startswith("**Termin:** czwartek, 1 października 2026\n\nOpis sprawy"))
        self.assertIn("nie ma dziś osobnego pola terminu", out)

    def test_zly_termin_nie_zaklada_sprawy(self):
        kod, a, _, err = _zglos(["--termin", "2020-01-01"])
        self.assertEqual(kod, 2)
        self.assertIsNone(a.zalozona)
        self.assertIn("przeszłości", err)

    def test_bez_obserwujacych_jawna_informacja(self):
        _, _, out, _ = _zglos([])
        self.assertIn("nikt nie dostanie powiadomienia", out)
        _, _, out, _ = _zglos([], obserwatorzy_domyslni=["u-1"])
        self.assertNotIn("nikt nie dostanie powiadomienia", out)


class TestKontenerAplikacji(unittest.TestCase):

    def test_poza_windows_nigdy(self):
        with mock.patch.object(instalacja, "czy_windows", return_value=False):
            self.assertFalse(instalacja.w_kontenerze_aplikacji())

    def test_instaluj_w_kontenerze_odmawia_kodem_3(self):
        with mock.patch.object(instalacja, "w_kontenerze_aplikacji", return_value=True), \
                mock.patch.object(instalacja, "zainstaluj") as zainstaluj:
            err = io.StringIO()
            with redirect_stderr(err):
                kod = cli.main(["instaluj", "--ref", "v0.15.5"])
        self.assertEqual(kod, 3)
        zainstaluj.assert_not_called()
        self.assertIn("we własnym oknie", err.getvalue())


class TestOchronaBezGita(unittest.TestCase):

    def test_poza_repozytorium_cisza(self):
        with tempfile.TemporaryDirectory() as k:
            kat = Path(k)
            (kat / "hooks").mkdir()
            (kat / "hooks" / "install.sh").write_text("exit 1\n")
            (kat / "sf_kit").mkdir()
            with mock.patch.object(cli, "__file__", str(kat / "sf_kit" / "cli.py")), \
                    mock.patch("subprocess.run") as run:
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    cli._wlacz_ochrone_repozytorium()
            run.assert_not_called()
            self.assertEqual((out.getvalue(), err.getvalue()), ("", ""))


if __name__ == "__main__":
    unittest.main()
