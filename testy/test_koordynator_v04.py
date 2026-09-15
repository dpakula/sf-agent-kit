"""Profil KOORDYNATOR — v0.4 zakres C (ADVERTPR-777).

v0.4 (15.09.2026) - APro Agents / borys-sf

TESTY OD STRONY ODMOWY — I TO JEST POLECENIE Z `task.yml`, NIE MOJA PREFERENCJA
Koordynator jest jedynym z trzech profili, który działa na CUDZYCH zadaniach. Pomyłka kosztuje
tu czyjś dzień pracy, nie własny, więc mierzymy przede wszystkim to, czego narzędzie ma NIE
zrobić:

· zlecić bez sprawy (wynik nie miałby gdzie wylądować),
· zlecić agentowi, którego nie ma albo który nie ma sluga (zadanie wygląda na wysłane),
· zlecić na sprawie, której wykonawca nie zobaczy (zadanie niewykonalne, a wygląda na wysłane),
· odebrać zadanie, po którym na sprawie nic nie ma (`completed` przestaje cokolwiek znaczyć),
· pokazać polecenia komuś, kto nie ma do nich prawa (403 w środku pracy zamiast odmowy na wejściu).

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import koordynator  # noqa: E402
from sf_kit.api import BladAPI  # noqa: E402

AGENCI = [
    {"user_id": "aaa", "agent_slug": "kodeks", "full_name": "Kodeks", "email": "kodeks@x.pl"},
    {"user_id": "bbb", "agent_slug": None, "full_name": "Stare członkostwo", "email": "s@x.pl"},
    {"user_id": "ccc", "agent_slug": "redaktor", "full_name": "Redaktor", "email": "r@x.pl"},
]


class AtrapaKlienta:
    """Zapamiętuje wywołania. Może udawać brak dostępu do sprawy i pusty dziennik."""

    def __init__(self, *, dziennik=None, sprawa_niedostepna=False):
        self.zalozone: list[dict] = []
        self._dziennik = dziennik if dziennik is not None else {"pozycje": [], "ukryte": 0}
        self._sprawa_niedostepna = sprawa_niedostepna

    def agenci(self):
        return list(AGENCI)

    def wpisy_sprawy(self, ticket_id, *, limit=100):
        if self._sprawa_niedostepna:
            raise BladAPI("atrapa: 404 na sprawie")
        return self._dziennik

    def zaloz_zadanie(self, **kwargs):
        self.zalozone.append(kwargs)
        return {"external_id": "zadanie-1", "id": "zzz"}


class TestGatingu(unittest.TestCase):
    """Widoczność poleceń rozstrzyga UPRAWNIENIE z `/me`, nie pole `profil` w pliku."""

    def test_uprawnienie_jest_tym_ktore_naprawde_gatuje_SF(self):
        """`plans:write` — sprawdzone w kodzie SF, nie zgadnięte.

        `task.yml` przewidywał `tasks:write`/`tasks:assign`; takich uprawnień w SF NIE MA.
        Gating po nieistniejącej nazwie ukrywałby polecenia przed wszystkimi — łącznie z tymi,
        którzy mają do nich pełne prawo.
        """
        self.assertEqual(koordynator.UPRAWNIENIE_ZLECANIA, "plans:write")

    def test_bez_uprawnienia_nie_wolno(self):
        self.assertFalse(koordynator.czy_wolno_zlecac(["tickets:read", "tickets:comment"]))
        self.assertFalse(koordynator.czy_wolno_zlecac([]))
        self.assertFalse(koordynator.czy_wolno_zlecac(None))

    def test_z_uprawnieniem_wolno(self):
        self.assertTrue(koordynator.czy_wolno_zlecac(["tickets:read", "plans:write"]))


class TestFloty(unittest.TestCase):

    def test_agenci_bez_sluga_sa_POKAZANI_a_nie_ukryci(self):
        """Ukryty agent wygląda jak nieistniejący — nikt nie wie, że jest co naprawić."""
        flota = koordynator.flota(AtrapaKlienta())
        self.assertEqual(len(flota), 3)
        self.assertIn("nie da się zlecić", next(a.opis() for a in flota if not a.wolalny))

    def test_wolalni_sa_na_wierzchu(self):
        flota = koordynator.flota(AtrapaKlienta())
        self.assertEqual([a.slug for a in flota], ["kodeks", "redaktor", None])


class TestOdmowPrzyZlecaniu(unittest.TestCase):

    def test_agent_ktorego_nie_ma_to_odmowa_z_lista(self):
        with self.assertRaises(koordynator.Odmowa) as e:
            koordynator.znajdz_agenta(koordynator.flota(AtrapaKlienta()), "nie-ma-takiego")
        tresc = str(e.exception)
        self.assertIn("nie-ma-takiego", tresc)
        self.assertIn("kodeks", tresc)

    def test_agent_bez_sluga_to_odmowa_a_nie_ciche_zlecenie(self):
        """Bez sluga nie ma jak wskazać boardu — zadanie „wysłane" nie dotarłoby nigdzie."""
        with self.assertRaises(koordynator.Odmowa) as e:
            koordynator.znajdz_agenta(koordynator.flota(AtrapaKlienta()), "bbb")
        self.assertIn("nie ma ustawionego sluga", str(e.exception))

    def test_puste_wskazanie_agenta(self):
        with self.assertRaises(koordynator.Odmowa):
            koordynator.znajdz_agenta(koordynator.flota(AtrapaKlienta()), "")

    def test_sprawa_niedostepna_to_odmowa_z_PODPOWIEDZIA(self):
        """Odmowa ma mówić, co zrobić: założyć sprawę pomocniczą w Organizacji wykonawcy."""
        agent = koordynator.znajdz_agenta(koordynator.flota(AtrapaKlienta()), "kodeks")
        with self.assertRaises(koordynator.Odmowa) as e:
            koordynator.sprawdz_sprawe_dla_wykonawcy(
                AtrapaKlienta(sprawa_niedostepna=True), ticket_id="t-1", agent=agent)
        self.assertIn("sprawę pomocniczą", str(e.exception))

    def test_sprawa_dostepna_przechodzi(self):
        agent = koordynator.znajdz_agenta(koordynator.flota(AtrapaKlienta()), "kodeks")
        koordynator.sprawdz_sprawe_dla_wykonawcy(
            AtrapaKlienta(), ticket_id="t-1", agent=agent)     # brak wyjątku = zdane


class TestOdbioru(unittest.TestCase):
    """`odbierz` sprawdza, czy wynik JEST — zamknięcie na słowo unieważnia status `completed`."""

    def test_pusta_sprawa_to_brak_wyniku(self):
        jest, co = koordynator.wynik_jest_na_sprawie(
            AtrapaKlienta(), ticket_id="t-1", external_id="zadanie-1")
        self.assertFalse(jest)
        self.assertIn("nie ma wpisu wskazującego zadanie-1", co)

    def test_wpis_ze_sladem_zadania_wystarcza(self):
        dziennik = {"pozycje": [{"content": "Zrobione — zadanie-1", "attachments": []}],
                    "ukryte": 0}
        jest, co = koordynator.wynik_jest_na_sprawie(
            AtrapaKlienta(dziennik=dziennik), ticket_id="t-1", external_id="zadanie-1")
        self.assertTrue(jest)
        self.assertIn("bez załączników", co)

    def test_wpis_z_zalacznikami_jest_nazwany(self):
        dziennik = {"pozycje": [{"content": "zadanie-1 gotowe",
                                 "attachments": [{"id": 1}, {"id": 2}]}], "ukryte": 0}
        jest, co = koordynator.wynik_jest_na_sprawie(
            AtrapaKlienta(dziennik=dziennik), ticket_id="t-1", external_id="zadanie-1")
        self.assertTrue(jest)
        self.assertIn("2 załącznikami", co)

    def test_cudze_zalaczniki_NIE_sa_dowodem_na_ten_wynik(self):
        """Na sprawie bywa wiele zadań. Załącznik po kimś innym nie znaczy, że TO jest zrobione."""
        dziennik = {"pozycje": [{"content": "inne zadanie-99", "attachments": [{"id": 1}]}],
                    "ukryte": 0}
        jest, co = koordynator.wynik_jest_na_sprawie(
            AtrapaKlienta(dziennik=dziennik), ticket_id="t-1", external_id="zadanie-1")
        self.assertFalse(jest)
        self.assertIn("żaden wpis nie wskazuje", co)

    def test_ukryte_wpisy_nie_pozwalaja_twierdzic_ze_wyniku_NIE_MA(self):
        """Wpisy poza moim poziomem widoczności mogą zawierać wynik — mówimy to wprost.

        Bez tego rozróżnienia koordynator o węższym poziomie widoczności odmawiałby odbioru
        pracy, która jest zrobiona — i nie dowiedziałby się dlaczego.
        """
        jest, co = koordynator.wynik_jest_na_sprawie(
            AtrapaKlienta(dziennik={"pozycje": [], "ukryte": 3}),
            ticket_id="t-1", external_id="zadanie-1")
        self.assertFalse(jest)
        self.assertIn("poza moim poziomem widoczności", co)

    def test_nieodczytany_dziennik_to_brak_dowodu_a_nie_dowod_braku(self):
        jest, co = koordynator.wynik_jest_na_sprawie(
            AtrapaKlienta(sprawa_niedostepna=True), ticket_id="t-1", external_id="zadanie-1")
        self.assertFalse(jest)
        self.assertIn("nie udało się odczytać", co)


if __name__ == "__main__":
    unittest.main()
