"""Kit 0.15.4: obserwujący sprawy — `sf-kit obserwujacy` i `zglos --obserwujacy`.

v1.0.0 (30.09.2026) - APro Agents / borys-sf · Damian 10:1x: „kiedy Kit będzie mógł dodawać obserwatorów?”

CZEGO PILNUJĄ
· SF przyjmuje obserwującego po ADRESIE (`{email}`); identyfikator/imię zamiast adresu Kit
  odrzuca sam, zanim cokolwiek wyśle (API dałoby 422).
· Sprawa założona, a obserwujący nie wszedł → kod 1 i polecenie na dołożenie brakujących,
  zamiast sukcesu, który udaje, że powiadomienia pójdą.
· Link do sprawy niesie Organizację; lista bez `--dodaj`/`--usun` to odczyt.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli  # noqa: E402
from sf_kit.api import BladAPI  # noqa: E402

UUID = "d70a914b-3b44-406a-964c-ea4f8a3ac78b"


class Atrapa:
    def __init__(self, odmowa: set[str] = frozenset()):
        self.dodane: list[str] = []
        self.usuniete: list[str] = []
        self.odmowa = set(odmowa)

    def dodaj_obserwujacego(self, sid, email):
        if email in self.odmowa:
            raise BladAPI("Twój klucz nie ma uprawnienia `tickets:watchers`")
        self.dodane.append(email)
        return {"email": email}

    def usun_obserwujacego(self, sid, wskazanie):
        self.usuniete.append(wskazanie)

    def obserwujacy(self, sid):
        return [{"email": e, "name": None} for e in self.dodane]

    def zaloz_sprawe(self, **kw):
        self.zalozona = kw
        return {"ticket_id": UUID, "ticket_prefix": "JULIAPAK", "ticket_number": 10}


def _uruchom(argv, atrapa, org_z=None):
    widziane_org = []

    def zapis(konf, args, org_z_linku=""):
        widziane_org.append(getattr(args, "org", None))
        return atrapa, None

    with mock.patch.object(cli.konfiguracja, "wczytaj",
                           return_value=mock.Mock(obserwatorzy_domyslni=[], adres="https://sf")), \
            mock.patch.object(cli.konfiguracja, "wczytaj_jesli_jest", return_value=None), \
            mock.patch.object(cli, "_klient_dla_zapisu", side_effect=zapis), \
            mock.patch.object(cli, "_klient", side_effect=lambda konf, args=None: atrapa), \
            mock.patch.object(cli, "_pokaz_sprawe"):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            kod = cli.main(argv)
    return kod, out.getvalue(), err.getvalue(), widziane_org


class TestPolecenieObserwujacy(unittest.TestCase):

    def test_dodaj_po_adresie_i_lista(self):
        a = Atrapa()
        kod, out, _, org = _uruchom(["obserwujacy", f"https://sf.dpakula.pl/tickets/{UUID}?org=juliapak",
                                     "--dodaj", "julia@pak.pl", "anna@pak.pl"], a)
        self.assertEqual(kod, 0)
        self.assertEqual(a.dodane, ["julia@pak.pl", "anna@pak.pl"])
        self.assertIn("Obserwujący (2)", out)
        self.assertEqual(org, ["juliapak"])                          # Organizacja z linku

    def test_nie_adres_odrzucony_bez_wywolania(self):
        a = Atrapa()
        kod, _, err, _ = _uruchom(["--org", "jp", "obserwujacy", UUID, "--dodaj", "Julia Pak"], a)
        self.assertEqual(kod, 1)
        self.assertEqual(a.dodane, [])
        self.assertIn("to nie jest adres e-mail", err)

    def test_odmowa_sf_to_kod_1_z_powodem(self):
        a = Atrapa(odmowa={"anna@pak.pl"})
        kod, _, err, _ = _uruchom(["--org", "jp", "obserwujacy", UUID,
                                   "--dodaj", "julia@pak.pl", "anna@pak.pl"], a)
        self.assertEqual(kod, 1)
        self.assertEqual(a.dodane, ["julia@pak.pl"])
        self.assertIn("tickets:watchers", err)

    def test_usun(self):
        a = Atrapa()
        kod, out, _, _ = _uruchom(["--org", "jp", "obserwujacy", UUID, "--usun", "anna@pak.pl"], a)
        self.assertEqual((kod, a.usuniete), (0, ["anna@pak.pl"]))


class TestZglosZObserwujacymi(unittest.TestCase):

    def test_sprawa_powstaje_obserwujacy_dodani(self):
        a = Atrapa()
        with mock.patch.object(cli, "_opis_z_wejscia", return_value="opis"):
            kod, out, _, _ = _uruchom(["--org", "jp", "zglos", "--tytul", "Ankieta",
                                       "--obserwujacy", "julia@pak.pl"], a)
        self.assertEqual(kod, 0)
        self.assertEqual(a.dodane, ["julia@pak.pl"])

    def test_nieudany_obserwujacy_nie_udaje_sukcesu(self):
        a = Atrapa(odmowa={"julia@pak.pl"})
        with mock.patch.object(cli, "_opis_z_wejscia", return_value="opis"):
            kod, _, err, _ = _uruchom(["--org", "jp", "zglos", "--tytul", "Ankieta",
                                       "--obserwujacy", "julia@pak.pl"], a)
        self.assertEqual(kod, 1)
        self.assertTrue(hasattr(a, "zalozona"))                      # sprawa powstała mimo to
        self.assertIn("julia@pak.pl", err)


ZADANIE = {"id": "9f1c2d3e-4b5a-4c6d-8e7f-001122334455", "external_id": "JULIAPAK-13-t1",
           "title": "Ankieta po szkoleniu", "short_desc": "wyślij ankietę",
           "body_md": "## Co zrobić\n1. Przygotuj 5 pytań\n2. Wyślij do uczestników",
           "status": "queued", "priority": "high", "urgent": False, "deadline": "2026-10-02T10:00:00Z",
           "ticket_ref": "JULIAPAK-13", "ticket_id": UUID}


class AtrapaZadan:
    def __init__(self):
        self.statusy = []

    def zadanie(self, tid):
        return dict(ZADANIE)

    def moje_zadania(self, *, slug, status="queued"):
        self.statusy.append(status)
        return [dict(ZADANIE)] if status == "queued" else []


def _uruchom_zadania(argv):
    a = AtrapaZadan()
    with mock.patch.object(cli.konfiguracja, "wczytaj", return_value=mock.Mock(slug="asystent-julii")), \
            mock.patch.object(cli.konfiguracja, "wczytaj_jesli_jest", return_value=None), \
            mock.patch.object(cli, "_klient", side_effect=lambda konf, args=None: a):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            kod = cli.main(argv)
    return kod, out.getvalue(), err.getvalue()


class TestTrescZadania(unittest.TestCase):

    def test_zadanie_po_id_pokazuje_tresc_termin_sprawe(self):
        kod, out, _ = _uruchom_zadania(["zadanie", ZADANIE["id"]])
        self.assertEqual(kod, 0)
        for fragment in ("Przygotuj 5 pytań", "termin: 2026-10-02", "sprawa: JULIAPAK-13", "priorytet: high"):
            self.assertIn(fragment, out)

    def test_zadanie_po_external_id(self):
        kod, out, _ = _uruchom_zadania(["zadanie", "juliapak-13-t1"])
        self.assertEqual(kod, 0)
        self.assertIn("Wyślij do uczestników", out)

    def test_nieznane_zadanie_mowi_co_zrobic(self):
        kod, _, err = _uruchom_zadania(["zadanie", "NIE-MA-1"])
        self.assertEqual(kod, 1)
        self.assertIn("sf-kit tasks", err)

    def test_tasks_pelne_drukuje_tresc_a_bez_flagi_nie(self):
        with mock.patch.object(cli, "_licznik", return_value="1 zadanie"):
            a = AtrapaZadan()
            wynik = mock.MagicMock()
            wynik.__iter__.return_value = iter([dict(ZADANIE)])
            wynik.__bool__.return_value = True
            a.moje_zadania = lambda **kw: wynik
            for argv, jest in ((["tasks", "--pelne"], True), (["tasks"], False)):
                wynik.__iter__.return_value = iter([dict(ZADANIE)])
                with mock.patch.object(cli.konfiguracja, "wczytaj", return_value=mock.Mock(slug="s")), \
                        mock.patch.object(cli.konfiguracja, "wczytaj_jesli_jest", return_value=None), \
                        mock.patch.object(cli, "_klient", side_effect=lambda konf, args=None: a):
                    out = io.StringIO()
                    with redirect_stdout(out):
                        cli.main(argv)
                self.assertEqual("Przygotuj 5 pytań" in out.getvalue(), jest, argv)


if __name__ == "__main__":
    unittest.main()
