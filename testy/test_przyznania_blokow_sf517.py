"""Przyznania bloków stron per Organizacja z Kitu (SF-517 R5, kontrakt K4).

v0.1 (25.11.2026) - APro Agents / arek-sf

CZEGO TE TESTY PILNUJĄ
══════════════════════
· zapis idzie pod UUID Organizacji DOCELOWEJ (`--dla`), a nagłówek zostaje przy Organizacji
  roboczej — superadmin przyznaje blok tam, gdzie nie jest członkiem;
· ten sam stan drugi raz NIE wysyła PUT, blok spoza listy `granted` zatrzymuje się przed zapisem;
· sukces = stan z odpowiedzi, nie kod 200;
· trasa nieznana serwerowi (PROD przed wydaniem R5) mówi o wydaniu, nie o uprawnieniach;
· zapis nie trafia pod narzędzie MCP `block`, które pakiet ogłasza jako tylko do odczytu.

Uruchomienie: `python3 -m unittest testy.test_przyznania_blokow_sf517`
"""
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, kontrakt, pakiet  # noqa: E402
from sf_kit.api import Klient  # noqa: E402

UUID_FF = "0b7e2f0c-1111-4a2b-9c3d-222222222222"
UUID_OBCA = "9f9f9f9f-3333-4a2b-9c3d-444444444444"


class AtrapaSF(Klient):
    """Klient bez sieci, ze stanem przyznań po stronie „serwera”. Ścieżki i ciała są prawdziwe."""

    def __init__(self, *, przyznane=(), odmowa=None, klamie=False):
        super().__init__(baza="https://przyklad.test", klucz="sf_test", organizacja="uuid-robocza")
        self.wywolania: list[tuple[str, str, dict | None]] = []
        self.przyznane = set(przyznane)
        self.odmowa = odmowa          # (kod, treść) — każde żądanie pod /super-admin/ kończy się tym
        self.klamie = klamie          # PUT oddaje 200, ale stanu nie zmienia

    def _stan(self):
        return {"bloki": [
            {"referencja": "lib/vehicle_list", "nazwa": "Lista aut", "opis": "", "przyznany": "lib/vehicle_list" in self.przyznane},
            {"referencja": "lib/cennik_serwisu", "nazwa": "Cennik", "opis": "", "przyznany": "lib/cennik_serwisu" in self.przyznane},
        ]}

    def _wywolaj(self, metoda, sciezka, *, cialo=None):
        self.wywolania.append((metoda, sciezka, cialo))
        if sciezka == "tenants":
            return [{"id": 6, "uuid": "uuid-robocza", "slug": "sf", "name": "SF"},
                    {"id": 31, "uuid": UUID_FF, "slug": "fixforum", "name": "FixForum"}]
        if self.odmowa and sciezka.startswith("super-admin/"):
            kod, tresc = self.odmowa
            raise self._na_wyjatek(kod, metoda, sciezka, tresc, self.organizacja)
        if metoda == "PUT" and not self.klamie:
            ref = sciezka.split("/bloki/", 1)[1]
            (self.przyznane.add if cialo["przyznany"] else self.przyznane.discard)(ref)
        return self._stan()

    def zapisy(self):
        return [w for w in self.wywolania if w[0] == "PUT"]


def uruchom(argv, klient):
    """Polecenie przez prawdziwy parser, z klientem-atrapą zamiast konfiguracji i klucza."""
    args = cli.zbuduj_parser().parse_args(argv)
    wyjscie, bledy = io.StringIO(), io.StringIO()
    with mock.patch.object(cli, "_klient", return_value=klient), \
            mock.patch.object(cli.konfiguracja, "wczytaj", return_value=object()), \
            redirect_stdout(wyjscie), redirect_stderr(bledy):
        kod = args.funkcja(args)
    return kod, wyjscie.getvalue(), bledy.getvalue()


class Przyznaj(unittest.TestCase):
    def test_zapis_pod_uuid_docelowej_a_naglowek_przy_roboczej(self):
        sf = AtrapaSF()
        kod, out, _ = uruchom(["blok-przyznaj", "lib/vehicle_list", "--dla", "fixforum"], sf)
        self.assertEqual(kod, 0)
        self.assertEqual(sf.zapisy(), [("PUT", f"super-admin/tenants/{UUID_FF}/bloki/lib/vehicle_list",
                                         {"przyznany": True})])
        self.assertEqual(sf.organizacja, "uuid-robocza")
        self.assertIn("Przyznany: lib/vehicle_list", out)
        self.assertIn("fixforum", out)

    def test_ten_sam_stan_drugi_raz_nie_wysyla_zapisu(self):
        sf = AtrapaSF(przyznane={"lib/vehicle_list"})
        kod, out, _ = uruchom(["blok-przyznaj", "lib/vehicle_list", "--dla", "fixforum"], sf)
        self.assertEqual(kod, 0)
        self.assertEqual(sf.zapisy(), [])
        self.assertIn("Bez zmian", out)

    def test_blok_spoza_listy_granted_to_kod_2_bez_zapisu_z_lista_dostepnych(self):
        sf = AtrapaSF()
        kod, _, err = uruchom(["blok-przyznaj", "core/hero", "--dla", "fixforum"], sf)
        self.assertEqual(kod, 2)
        self.assertEqual(sf.zapisy(), [])
        self.assertIn("universal", err)
        self.assertIn("lib/vehicle_list", err)

    def test_wersja_w_referencji_jest_zdejmowana_z_uwaga(self):
        sf = AtrapaSF()
        kod, _, err = uruchom(["blok-przyznaj", "lib/vehicle_list@1", "--dla", "fixforum"], sf)
        self.assertEqual(kod, 0)
        self.assertTrue(sf.zapisy()[0][1].endswith("/bloki/lib/vehicle_list"))
        self.assertIn("@1", err)

    def test_zly_ksztalt_referencji_to_kod_2_bez_sieci(self):
        for zla in ("vehicle_list", "lib/", "Lib/X", "lib/a/b", "../x"):
            sf = AtrapaSF()
            kod, _, _ = uruchom(["blok-przyznaj", zla, "--dla", "fixforum"], sf)
            self.assertEqual(kod, 2, zla)
            self.assertEqual(sf.wywolania, [], zla)

    def test_bez_dla_to_kod_2_bez_sieci_i_z_wyjasnieniem_org(self):
        sf = AtrapaSF()
        kod, _, err = uruchom(["blok-przyznaj", "lib/vehicle_list"], sf)
        self.assertEqual(kod, 2)
        self.assertEqual(sf.wywolania, [])
        self.assertIn("--org", err)

    def test_nieznany_slug_to_kod_2_a_uuid_spoza_listy_jedzie_do_serwera(self):
        sf = AtrapaSF()
        kod, _, err = uruchom(["blok-przyznaj", "lib/vehicle_list", "--dla", "fixforun"], sf)
        self.assertEqual(kod, 2)
        self.assertEqual(sf.zapisy(), [])
        self.assertIn("fixforun", err)

        sf = AtrapaSF()
        kod, _, _ = uruchom(["blok-przyznaj", "lib/vehicle_list", "--dla", UUID_OBCA], sf)
        self.assertEqual(kod, 0)
        self.assertEqual(sf.zapisy()[0][1], f"super-admin/tenants/{UUID_OBCA}/bloki/lib/vehicle_list")

    def test_200_bez_zmiany_stanu_to_kod_1(self):
        sf = AtrapaSF(klamie=True)
        kod, _, err = uruchom(["blok-przyznaj", "lib/vehicle_list", "--dla", "fixforum"], sf)
        self.assertEqual(kod, 1)
        self.assertIn("NIE weszło", err)

    def test_json_mowi_przed_i_czy_byla_zmiana(self):
        sf = AtrapaSF()
        kod, out, _ = uruchom(["blok-przyznaj", "lib/vehicle_list", "--dla", "fixforum", "--json"], sf)
        self.assertEqual(kod, 0)
        dane = json.loads(out)
        self.assertEqual((dane["przed"], dane["przyznany"], dane["zmiana"]), (False, True, True))
        self.assertEqual(dane["organizacja"]["uuid"], UUID_FF)


class Odbierz(unittest.TestCase):
    def test_odebranie_wysyla_false_i_mowi_ze_sekcje_zostaja(self):
        sf = AtrapaSF(przyznane={"lib/vehicle_list"})
        kod, out, _ = uruchom(["blok-odbierz", "lib/vehicle_list", "--dla", "fixforum"], sf)
        self.assertEqual(kod, 0)
        self.assertEqual(sf.zapisy()[0][2], {"przyznany": False})
        self.assertNotIn("lib/vehicle_list", sf.przyznane)
        self.assertIn("ZOSTAJĄ", out)

    def test_odebranie_nieprzyznanego_to_bez_zmian(self):
        sf = AtrapaSF()
        kod, _, _ = uruchom(["blok-odbierz", "lib/vehicle_list", "--dla", "fixforum"], sf)
        self.assertEqual(kod, 0)
        self.assertEqual(sf.zapisy(), [])


class Przyznane(unittest.TestCase):
    def test_lista_pokazuje_kto_ma_co(self):
        sf = AtrapaSF(przyznane={"lib/cennik_serwisu"})
        kod, out, _ = uruchom(["blok-przyznane", "--dla", "fixforum"], sf)
        self.assertEqual(kod, 0)
        self.assertEqual(sf.wywolania[-1], ("GET", f"super-admin/tenants/{UUID_FF}/bloki", None))
        linia_cennika = next(l for l in out.splitlines() if "lib/cennik_serwisu" in l)
        linia_aut = next(l for l in out.splitlines() if "lib/vehicle_list" in l)
        self.assertIn("✓ ma", linia_cennika)
        self.assertIn("nie ma", linia_aut)

    def test_json(self):
        kod, out, _ = uruchom(["blok-przyznane", "--dla", "fixforum", "--json"], AtrapaSF())
        self.assertEqual(kod, 0)
        self.assertEqual(len(json.loads(out)["bloki"]), 2)


class OdmowySerwera(unittest.TestCase):
    def test_trasa_nieznana_mowi_o_wydaniu_r5_a_nie_o_uprawnieniach(self):
        sf = AtrapaSF(odmowa=(404, '{"detail": "Not Found"}'))
        kod, _, err = uruchom(["blok-przyznane", "--dla", "fixforum"], sf)
        self.assertEqual(kod, 1)
        self.assertIn("R5", err)
        self.assertNotIn("superadmin", err)

    def test_brak_organizacji_404_z_powodem_serwera(self):
        sf = AtrapaSF(odmowa=(404, '{"detail": "Nie ma takiej Organizacji."}'))
        kod, _, err = uruchom(["blok-przyznaj", "lib/vehicle_list", "--dla", UUID_OBCA], sf)
        self.assertEqual(kod, 1)
        self.assertIn("Nie ma takiej Organizacji", err)

    def test_403_mowi_kto_moze(self):
        sf = AtrapaSF(odmowa=(403, '{"detail": "Przyznania bloków zmienia superadmin SalesForge."}'))
        kod, _, err = uruchom(["blok-przyznaj", "lib/vehicle_list", "--dla", "fixforum"], sf)
        self.assertEqual(kod, 1)
        self.assertIn("wyłącznie superadmin", err)
        self.assertEqual(sf.zapisy(), [])


class PozaNarzedziemTylkoDoOdczytu(unittest.TestCase):
    def test_blok_przyznaj_ze_spacja_odsyla_do_osobnego_polecenia(self):
        sf = AtrapaSF()
        kod, _, err = uruchom(["blok", "przyznaj"], sf)
        self.assertEqual(kod, 2)
        self.assertIn("blok-przyznaj", err)
        self.assertEqual(sf.wywolania, [])

    def test_manifest_pakietu_nie_wystawia_przyznan(self):
        polecenia = {k["cli"] for k in pakiet.wczytaj()["komendy"]}
        self.assertTrue(polecenia.isdisjoint({"blok-przyznaj", "blok-odbierz", "blok-przyznane"}))


class Kontrakt(unittest.TestCase):
    def test_katalog_zna_obie_trasy_z_uuid_w_sciezce(self):
        put = kontrakt.znajdz("blok-przyznaj")
        self.assertEqual((put.metoda, put.wymagane), ("PUT", ("przyznany",)))
        self.assertIn("{tenant_uuid}", put.trasa)
        self.assertEqual(kontrakt.znajdz("blok-przyznane").metoda, "GET")


if __name__ == "__main__":
    unittest.main()
