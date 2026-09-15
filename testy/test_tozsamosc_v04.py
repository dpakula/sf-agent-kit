"""Wybór Organizacji przez `GET /me` — v0.4 (ADVERTPR-777, część A).

v0.4 (15.09.2026) - APro Agents / borys-sf

CO TU JEST MIERZONE I DLACZEGO AKURAT TO
════════════════════════════════════════
Cała ta warstwa istnieje po to, żeby **nie zgadywać Organizacji**. Damian (15.09): „nie
najlepsze, żeby kodować Organizację w init". Koszt pomyłki jest asymetryczny i nieodwracalny:
wpis Michała, który wyląduje w cudzej Organizacji, jest wyciekiem do klienta, a nie
niedogodnością — dlatego przy każdej wątpliwości Kit ODMAWIA, zamiast wybierać.

Testy chodzą na odpowiedzi `/me` przepisanej z PRODUKCJI (kluczem borys-sf, 15.09): cztery
Organizacje, dwie z nadaniami, dwie bez. To nie jest wymyślony kształt — to dokładnie ten,
na którym „pierwsza z brzegu" podjęłaby złą decyzję.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import tozsamosc  # noqa: E402

#: Odpowiedź `/me` w kształcie zmierzonym na produkcji 15.09 (adresy i identyfikatory zmienione).
ODPOWIEDZ = {
    "konto": {"id": "b1f1dcf2-0fb9-4a23-878e-14c456a10b08", "email": "agent@example",
              "nazwa": "Borys (agent SF, backend)", "kind": "agent"},
    "klucz": {"prefiks": "sk_live_86c7", "scope": "member", "zawezony": True, "wygasa": None},
    "organizacje": [
        {"tenant_uuid": "11111111-1111-1111-1111-111111111111", "slug": "advertpro-co",
         "nazwa": "AdvertPro", "rola": "user", "kind": "agent", "agent_slug": "borys-sf",
         "uprawnienia_efektywne": ["tickets:read", "tickets:write", "tasks:read"]},
        {"tenant_uuid": "22222222-2222-2222-2222-222222222222", "slug": "autera",
         "nazwa": "Autera", "rola": "member", "kind": "agent", "agent_slug": "borys-sf",
         "uprawnienia_efektywne": []},
        {"tenant_uuid": "33333333-3333-3333-3333-333333333333", "slug": "sf",
         "nazwa": "SalesForge", "rola": "user", "kind": "agent", "agent_slug": "borys-sf",
         "uprawnienia_efektywne": ["tickets:read", "tickets:write", "tasks:read"]},
        {"tenant_uuid": "44444444-4444-4444-4444-444444444444", "slug": "szarlotka",
         "nazwa": "Szarlotka", "rola": "member", "kind": "agent", "agent_slug": "borys-sf",
         "uprawnienia_efektywne": []},
    ],
}

ADVERTPRO = "11111111-1111-1111-1111-111111111111"
SF = "33333333-3333-3333-3333-333333333333"


def _toz(organizacje=None):
    dane = dict(ODPOWIEDZ)
    if organizacje is not None:
        dane = {**ODPOWIEDZ, "organizacje": organizacje}
    return tozsamosc.z_odpowiedzi(dane)


class TestOdczytu(unittest.TestCase):
    def test_czyta_konto_klucz_i_organizacje(self):
        t = _toz()
        self.assertEqual(t.konto_kind, "agent")
        self.assertEqual(t.klucz_prefiks, "sk_live_86c7")
        self.assertTrue(t.klucz_zawezony)
        self.assertEqual(len(t.organizacje), 4)

    def test_brak_terminu_to_brak_terminu_a_nie_niewiedza(self):
        """`wygasa: null` znaczy klucz BEZTERMINOWY. Rozróżnienie jest po stronie SF."""
        self.assertIsNone(_toz().klucz_wygasa)

    def test_nadania_licza_sie_z_uprawnien_efektywnych(self):
        t = _toz()
        self.assertEqual([o.slug for o in t.z_nadaniami], ["advertpro-co", "sf"])

    def test_nieznane_pola_nie_wywracaja_odczytu(self):
        """Kontrakt `/me` może urosnąć — Kit ma wtedy działać, a nie odmawiać startu."""
        dane = {**ODPOWIEDZ, "cos_nowego": 1,
                "organizacje": [{**ODPOWIEDZ["organizacje"][0], "nowe_pole": "x"}]}
        self.assertEqual(len(tozsamosc.z_odpowiedzi(dane).organizacje), 1)

    def test_pusta_odpowiedz_nie_wybucha(self):
        t = tozsamosc.z_odpowiedzi({})
        self.assertEqual(t.organizacje, [])
        self.assertIsNone(t.konto_nazwa)


class TestWyboru(unittest.TestCase):
    def test_org_wskazana_slugiem_wygrywa_z_plikiem(self):
        wybrana = tozsamosc.wybierz(_toz(), wskazana="sf", z_pliku=ADVERTPRO)
        self.assertEqual(wybrana.slug, "sf")

    def test_org_wskazana_uuidem_tez_dziala(self):
        self.assertEqual(tozsamosc.wybierz(_toz(), wskazana=SF).slug, "sf")

    def test_wielkosc_liter_nie_ma_znaczenia(self):
        self.assertEqual(tozsamosc.wybierz(_toz(), wskazana="SF").slug, "sf")

    def test_bez_wskazania_i_bez_pliku_przy_dwoch_kandydatach_ODMAWIA(self):
        """SEDNO: dwie Organizacje z nadaniami to sytuacja, w której nie wolno wybrać za człowieka."""
        with self.assertRaises(tozsamosc.BrakWyboru) as e:
            tozsamosc.wybierz(_toz())
        tresc = str(e.exception)
        self.assertIn("--org", tresc)
        self.assertIn("advertpro-co", tresc)
        self.assertIn("sf", tresc)

    def test_dokladnie_jedna_z_nadaniami_jest_wybierana_sama(self):
        """Gdy nie ma czego zgadywać, pytanie byłoby tylko utrudnieniem."""
        jedna = [ODPOWIEDZ["organizacje"][0], ODPOWIEDZ["organizacje"][1]]
        self.assertEqual(tozsamosc.wybierz(_toz(jedna)).slug, "advertpro-co")

    def test_plik_z_03_dziala_dalej(self):
        """Migracja: Organizacja wpisana w konfiguracji 0.3 jest po prostu domyślną."""
        self.assertEqual(tozsamosc.wybierz(_toz(), z_pliku=ADVERTPRO).slug, "advertpro-co")


class TestOdmow(unittest.TestCase):
    """Cztery drogi do odmowy. Każda mówi, CO zrobić dalej — nie „błąd"."""

    def test_org_bez_nadan_wskazana_wprost_to_odmowa(self):
        """Nawet wskazana palcem: praca bez nadań kończy się odmową serwera W POŁOWIE."""
        with self.assertRaises(tozsamosc.BrakWyboru) as e:
            tozsamosc.wybierz(_toz(), wskazana="autera")
        tresc = str(e.exception)
        self.assertIn("autera", tresc)
        self.assertIn("nie masz żadnych uprawnień", tresc)
        # Odmowa ma pokazać, GDZIE agent prawa ma — inaczej człowiek zgaduje dalej.
        self.assertIn("advertpro-co", tresc)

    def test_org_bez_nadan_z_pliku_tez_jest_odmowa(self):
        with self.assertRaises(tozsamosc.BrakWyboru):
            tozsamosc.wybierz(_toz(), z_pliku="22222222-2222-2222-2222-222222222222")

    def test_org_spoza_listy_to_odmowa_z_lista(self):
        with self.assertRaises(tozsamosc.BrakWyboru) as e:
            tozsamosc.wybierz(_toz(), wskazana="cudza-firma")
        self.assertIn("cudza-firma", str(e.exception))
        self.assertIn("advertpro-co", str(e.exception))

    def test_org_z_pliku_ktorej_juz_nie_ma_zatrzymuje_prace(self):
        """Odebrane członkostwo ma ZATRZYMAĆ pracę, a nie przenieść ją gdzie indziej.

        Ciche przejście na inną Organizację byłoby najgorszym możliwym zachowaniem: agent
        pracuje dalej, a jego wpisy lądują u kogoś, kto o nich nie wie.
        """
        with self.assertRaises(tozsamosc.BrakWyboru) as e:
            tozsamosc.wybierz(_toz(), z_pliku="99999999-9999-9999-9999-999999999999")
        self.assertIn("członkostwo mogło zostać odebrane", str(e.exception))

    def test_zero_nadan_wszedzie_mowi_o_administratorze(self):
        bez = [{**o, "uprawnienia_efektywne": []} for o in ODPOWIEDZ["organizacje"]]
        with self.assertRaises(tozsamosc.BrakWyboru) as e:
            tozsamosc.wybierz(_toz(bez))
        self.assertIn("administratora", str(e.exception))

    def test_brak_organizacji_w_ogole(self):
        with self.assertRaises(tozsamosc.BrakWyboru) as e:
            tozsamosc.wybierz(_toz([]))
        self.assertIn("nie ma gdzie pracować", str(e.exception))


class TestListy(unittest.TestCase):
    def test_organizacje_z_nadaniami_sa_na_wierzchu(self):
        """Człowiek przy terminalu ma zobaczyć najpierw te, w których może pracować."""
        lista = tozsamosc.lista_do_pokazania(_toz().organizacje).splitlines()
        self.assertIn("advertpro-co", lista[0])
        self.assertIn("sf", lista[1])
        self.assertIn("bez nadań", lista[2])

    def test_pusta_lista_ma_swoj_napis(self):
        self.assertIn("żadnej", tozsamosc.lista_do_pokazania([]))


if __name__ == "__main__":
    unittest.main()
