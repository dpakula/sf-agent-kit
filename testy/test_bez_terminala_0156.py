"""Kit 0.15.6 (SF-175): sesja bez terminala — Claude Code z telefonu albo w chmurze.

v1.0.0 (01.10.2026) - APro Agents / borys-sf

CZEGO PILNUJĄ
· Bez klucza i bez terminala `whoami`/`init` mówią wprost o `SF_KIT_KEY` (a przy terminalu — nie
  dokładają szumu do zwykłego „uruchom init”).
· Klucz ze `SF_KIT_KEY` NIE jest odnawiany — i to przed jakimkolwiek wywołaniem SF: odnowienie
  zabiłoby stary sekret, a nowego nie ma gdzie oddać (zmienna zostaje ze starym → 401 w następnej sesji).
· `install.sh`: gdy archiwum z codeload nie przychodzi (proxy chmury: 403), instalator pobiera to samo
  wydanie gitem i instaluje działającego Kita; bez gita — czytelna odmowa z radą.
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

KORZEN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KORZEN))

from sf_kit import WERSJA, klucz, rotacja  # noqa: E402


def _czyste_srodowisko(dom: str, **dodatki) -> dict:
    env = {"PATH": "/usr/bin:/bin", "HOME": dom, "XDG_CONFIG_HOME": f"{dom}/.config",
           "XDG_DATA_HOME": f"{dom}/.local/share", "LANG": "C.UTF-8"}
    env.update(dodatki)
    return env


class KomunikatBezKlucza(unittest.TestCase):
    def test_bez_terminala_mowi_o_zmiennej(self):
        with mock.patch.object(klucz, "czy_macos", return_value=False):
            zdanie = klucz.powod_braku_klucza(ma_terminal=False)
        self.assertIn("sf-kit init", zdanie)
        self.assertIn("SF_KIT_KEY", zdanie)
        self.assertIn("NIE w rozmowie", zdanie)
        self.assertIn("nową sesję", zdanie)

    def test_przy_terminalu_bez_dopisku(self):
        with mock.patch.object(klucz, "czy_macos", return_value=False):
            zdanie = klucz.powod_braku_klucza(ma_terminal=True)
        self.assertNotIn("SF_KIT_KEY", zdanie)

    def test_whoami_bez_klucza_ze_stdin_z_devnull(self):
        with tempfile.TemporaryDirectory() as dom:
            wynik = subprocess.run([sys.executable, str(KORZEN / "sf-kit"), "whoami"],
                                   stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   env=_czyste_srodowisko(dom), timeout=30)
        tekst = wynik.stdout + wynik.stderr
        self.assertIn("Nie mam klucza", tekst)
        self.assertIn("SF_KIT_KEY", tekst)

    def test_init_bez_wejscia_mowi_o_zmiennej(self):
        with tempfile.TemporaryDirectory() as dom:
            wynik = subprocess.run([sys.executable, str(KORZEN / "sf-kit"), "init"],
                                   stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   env=_czyste_srodowisko(dom), timeout=30)
        self.assertEqual(wynik.returncode, 2)
        self.assertIn("Brak wejścia", wynik.stderr)
        self.assertIn("SF_KIT_KEY", wynik.stderr)


class ZeSrodowiska(unittest.TestCase):
    def test_ustawiona(self):
        with mock.patch.dict(os.environ, {"SF_KIT_KEY": "sk_test_x"}):
            self.assertTrue(klucz.z_srodowiska())

    def test_pusta_albo_same_spacje_to_nie_zmienna(self):
        for wartosc in ("", "   "):
            with mock.patch.dict(os.environ, {"SF_KIT_KEY": wartosc}):
                self.assertFalse(klucz.z_srodowiska(), repr(wartosc))

    def test_brak(self):
        env = {k: v for k, v in os.environ.items() if k != "SF_KIT_KEY"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(klucz.z_srodowiska())


class _KlientNieDoRuszenia:
    """Każde wywołanie SF jest błędem testu — odmowa ma zapaść przed siecią."""

    def __getattr__(self, nazwa):
        raise AssertionError(f"rotacja przy kluczu ze zmiennej zawołała SF: {nazwa}")


class _KlientOdnawiajacy:
    def __init__(self):
        self.odnowiono = False

    def kim_jestem(self):
        return {"api_key": {"id": "k1"}, "user": {"name": "agent"}, "memberships": []}

    def odnow_klucz(self, key_id):
        self.odnowiono = True
        return {"api_key": "sk_nowy_sekret_0000", "expires_at": "2026-10-31T00:00:00Z"}


class RotacjaKluczaZeZmiennej(unittest.TestCase):
    def test_zmienna_to_odmowa_bez_sieci_i_bez_zapisu(self):
        zapisane = []
        with mock.patch.dict(os.environ, {"SF_KIT_KEY": "sk_test_x"}):
            wynik = rotacja.rotuj(_KlientNieDoRuszenia(), zapis=zapisane.append)
        self.assertFalse(wynik.odnowiony)
        self.assertEqual(zapisane, [])
        self.assertIn("SF_KIT_KEY", wynik.zdanie)
        self.assertIn("ustawieniach środowiska", wynik.zdanie)

    def test_bez_zmiennej_odnowienie_idzie_jak_dotad(self):
        """Strażnik nie może zgasić zwykłej ścieżki (mutacja: warunek zawsze prawdziwy)."""
        env = {k: v for k, v in os.environ.items() if k != "SF_KIT_KEY"}
        klient = _KlientOdnawiajacy()
        zapisane = []
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(rotacja.mod_tozsamosc, "z_odpowiedzi",
                                  return_value=mock.Mock(klucz_id="k1")):
            wynik = rotacja.rotuj(klient, zapis=lambda s: zapisane.append(s) or "plik")
        self.assertTrue(klient.odnowiono)
        self.assertTrue(wynik.odnowiony, wynik.zdanie)
        self.assertEqual(zapisane, ["sk_nowy_sekret_0000"])


def _wykonywalny(sciezka: Path, tresc: str) -> None:
    sciezka.write_text(tresc, encoding="utf-8")
    sciezka.chmod(sciezka.stat().st_mode | stat.S_IXUSR)


@unittest.skipIf(os.name != "posix", "install.sh jest dla macOS/Linuksa")
class InstallShZapasGitem(unittest.TestCase):
    """`install.sh` z atrapami: `curl` zawsze pada (jak 403 z proxy), `git clone` kopiuje ten checkout."""

    def _uruchom(self, *, z_gitem: bool):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        bin_ = tmp / "bin"
        bin_.mkdir()
        _wykonywalny(bin_ / "curl", "#!/bin/sh\necho 'curl: (22) The requested URL returned error: 403' >&2\nexit 22\n")
        slad = tmp / "git-wolany"
        if z_gitem:
            # clone … <repo> <cel> → kopia tego checkoutu (bez sieci); rev-parse → stały SHA.
            _wykonywalny(bin_ / "git", f"""#!/bin/sh
echo "$@" >> "{slad}"
case "$1" in
  clone) for a; do cel="$a"; done; cp -R "{KORZEN}" "$cel" ;;
  -C) echo 0123456789abcdef0123456789abcdef01234567 ;;
esac
""")
        dom = tmp / "dom"
        dom.mkdir()
        # PATH bez systemowego gita: tylko atrapy + to, czego install.sh potrzebuje (sh, find, mktemp…).
        narzedzia = tmp / "narzedzia"
        narzedzia.mkdir()
        for nazwa in ("sh", "find", "head", "mktemp", "rm", "cp", "printf", "dirname", "uname",
                      "cat", "mkdir", "ln", "chmod", "env", "basename"):
            sciezka = shutil.which(nazwa)
            if sciezka:
                (narzedzia / nazwa).symlink_to(sciezka)
        (narzedzia / "python3").symlink_to(sys.executable)
        env = _czyste_srodowisko(str(dom), PATH=f"{bin_}:{narzedzia}", SHELL="/bin/sh")
        wynik = subprocess.run(["sh", str(KORZEN / "install.sh")], capture_output=True, text=True,
                               env=env, timeout=120, stdin=subprocess.DEVNULL)
        return wynik, dom, slad

    def test_403_z_codeload_i_git_dostepny_instaluje_z_klonu(self):
        wynik, dom, slad = self._uruchom(z_gitem=True)
        self.assertEqual(wynik.returncode, 0, wynik.stdout + wynik.stderr)
        self.assertIn("pobieram to samo wydanie gitem", wynik.stdout)
        wolania = slad.read_text(encoding="utf-8")
        self.assertIn("clone", wolania)
        self.assertIn(f"--branch v{WERSJA}", wolania)   # tag = wersja tego wydania
        polecenie = dom / ".local" / "bin" / "sf-kit"          # instalacja.katalog poleceń (macOS/Linux)
        self.assertTrue(polecenie.exists(), wynik.stdout + wynik.stderr)
        self.assertFalse((dom / ".local" / "share" / "sf-kit" / "app" / ".git").exists(),
                         "klon gita nie może wnieść .git do instalacji — ma być jak z ZIP")
        wersja = subprocess.run([str(polecenie), "--version"], capture_output=True, text=True,
                                env=_czyste_srodowisko(str(dom)), timeout=30)
        self.assertIn(WERSJA, wersja.stdout + wersja.stderr)

    def test_403_bez_gita_to_odmowa_z_rada(self):
        wynik, _, slad = self._uruchom(z_gitem=False)
        self.assertNotEqual(wynik.returncode, 0)
        self.assertIn("Nie udało się pobrać Kita", wynik.stderr)
        self.assertIn("zainstaluj git", wynik.stderr)
        self.assertFalse(slad.exists())


class WersjaWydania(unittest.TestCase):
    def test_instalatory_wskazuja_ten_tag(self):
        self.assertIn(f'REF="${{SF_KIT_REF:-v{WERSJA}}}"', (KORZEN / "install.sh").read_text(encoding="utf-8"))
        self.assertIn(f"'v{WERSJA}'", (KORZEN / "install.ps1").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
