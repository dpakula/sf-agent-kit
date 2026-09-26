"""`sf-kit init` — lista agentów, tryby dodawania i edycji, klucz → `/me` (ADVERTPR-960, runda 2).

v0.1 (26.09.2026) - APro Agents / kimi-autor · decyzje Damiana 26.09

CZEGO TU PILNUJEMY
1. Ekran startowy to LISTA agentów (numer = edycja, `n` = dodawanie, `q` = wyjście); pusta
   maszyna wchodzi w tryb dodawania od razu.
2. Tryb dodawania zaczyna się od klucza: `GET /me` ustala nazwę (slug z członkostw; klucz
   osobisty bez sluga → część adresu przed `@`), domyślną Organizację i profil Z UPRAWNIEŃ
   (`plans:write` → koordynator, `tickets:write` → asystent, inaczej worker). O nazwę NIE pyta.
3. Klucz agenta, który już jest na liście, prowadzi do pytania „przejść do edycji?".
4. Tryb edycji: Enter zostawia, pusty klucz = bez zmian; nowy klucz MUSI należeć do tego
   samego agenta (ten sam slug z `/me`) — obcy klucz = odmowa bez zapisu.
5. Stary układ (jeden `config.json` w korzeniu) widnieje na liście i da się go przenieść
   do podkatalogu razem z kluczem.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import builtins
import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sf_kit import klucz, onboarding  # noqa: E402
from test_slug_z_sf_32 import MaszynaTestowa, _me, _org  # noqa: E402


class _AtrapaKlienta:
    """Klient zwracający przygotowaną odpowiedź `/me` (i nic więcej nie potrzebujemy)."""

    def __init__(self, odpowiedz):
        self.odpowiedz = odpowiedz

    def kim_jestem(self):
        return self.odpowiedz


class _Inicjator:
    """`onboarding.polecenie` z podmienionym wejściem, klientem SF i pytaniem o klucz."""

    def __init__(self, odpowiedzi: list[str], me: dict, klucz_z_flagi=None,
                 wartosc_klucza="sk_live_nowy-abcd"):
        self.odpowiedzi = odpowiedzi
        self.me = me
        self.agent_z_flagi = klucz_z_flagi
        self.wartosc_klucza = wartosc_klucza

    def __call__(self) -> tuple[int, str]:
        from sf_kit import onboarding
        wejscia = iter(self.odpowiedzi)

        class Argumenty:
            agent = self.agent_z_flagi

        stare = (builtins.input, onboarding.Klient, klucz.zapytaj)
        builtins.input = lambda _p="": next(wejscia)
        onboarding.Klient = lambda **_k: _AtrapaKlienta(self.me)
        klucz.zapytaj = lambda **_k: self.wartosc_klucza
        wyswietlone = io.StringIO()
        bledy = io.StringIO()
        try:
            with contextlib.redirect_stdout(wyswietlone), contextlib.redirect_stderr(bledy):
                kod = onboarding.polecenie(Argumenty(), ochrona=lambda: None,
                                           jak_wolac=lambda: "./sf-kit")
        finally:
            (builtins.input, onboarding.Klient, klucz.zapytaj) = stare
        return kod, wyswietlone.getvalue() + bledy.getvalue()


class TestProfilZUprawnien(unittest.TestCase):
    def test_plans_write_to_koordynator(self):
        self.assertEqual(onboarding._profil_z_uprawnien(["tickets:write", "plans:write"]),
                         "koordynator")

    def test_tickets_write_to_asystent(self):
        self.assertEqual(onboarding._profil_z_uprawnien(["tickets:read", "tickets:write"]),
                         "asystent")

    def test_bez_praw_do_zapisu_to_worker(self):
        self.assertEqual(onboarding._profil_z_uprawnien(["tickets:read", "tasks:own"]),
                         "worker")
        self.assertEqual(onboarding._profil_z_uprawnien([]), "worker")


class TestNazwaZMe(unittest.TestCase):
    def test_slug_z_czlonkostw(self):
        toz = onboarding.tozsamosc.z_odpowiedzi(_me(_org("sf", "claude-jkowalski")))
        self.assertEqual(onboarding._nazwa_z_me(toz), "claude-jkowalski")

    def test_klucz_osobisty_bez_sluga_to_czesc_adresu(self):
        """Decyzja Damiana 26.09: klucz osobisty bez `agent_slug` → adres przed `@`."""
        me = {"konto": {"nazwa": "Jan Kowalski", "email": "jkowalski@dpakula.pl"},
              "organizacje": [{"tenant_uuid": "uuid-advertpro", "slug": "advertpro",
                               "nazwa": "ADVERTpro", "agent_slug": None,
                               "uprawnienia_efektywne": ["tickets:read"]}]}
        toz = onboarding.tozsamosc.z_odpowiedzi(me)
        self.assertEqual(onboarding._nazwa_z_me(toz), "jkowalski")

    def test_dwie_rozne_nazwy_to_brak_odpowiedzi(self):
        toz = onboarding.tozsamosc.z_odpowiedzi(
            _me(_org("sf", "claude-jkowalski"), _org("inna", "claude-inny")))
        self.assertIsNone(onboarding._nazwa_z_me(toz))


class TestDodawanie(unittest.TestCase):
    def test_profil_z_uprawnien_trafia_do_ustawien(self):
        """`plans:write` w SF → profil „koordynator" w zapisanych ustawieniach — bez pytania."""
        with MaszynaTestowa() as m:
            me = _me(_org("advertpro", "claude-jkowalski",
                          prawa=("tickets:read", "tickets:write", "plans:write")))
            kod, wyswietlone = _Inicjator(["", "t"], me)()
            self.assertEqual(kod, 0)
            ustawienia = m.ustawienia("claude-jkowalski")
        self.assertEqual(ustawienia["profil"], "koordynator")
        self.assertEqual(ustawienia["slug"], "claude-jkowalski")
        self.assertIn("koordynator", wyswietlone, "Kit pokazuje rozpoznany profil zwykłym językiem")

    def test_jeden_agent_za_drugim_przez_liste(self):
        """Drugi agent powstaje z ekranu listy: `[n]` → tryb dodawania → zapis."""
        with MaszynaTestowa(agent="claude-jkowalski") as m:
            me = _me(_org("advertpro", "kodeks-dpakula", prawa=("tickets:read",)))
            kod, _ = _Inicjator(["n", "", "t"], me)()
            self.assertEqual(kod, 0)
            self.assertEqual(klucz.agenci(), ["claude-jkowalski", "kodeks-dpakula"])
            self.assertEqual(m.ustawienia("kodeks-dpakula")["profil"], "worker")

    def test_klucz_istniejacego_agenta_proponuje_edycje(self):
        with MaszynaTestowa(agent="claude-jkowalski", slug="claude-jkowalski") as m:
            me = _me(_org("advertpro", "claude-jkowalski", prawa=("tickets:read",)))
            # `[n]` z listy → tryb dodawania; klucz należy do agenta z listy;
            # „n" na pytanie „przejść do edycji?" → nic nie rusza.
            kod, wyswietlone = _Inicjator(["n", "", "n"], me)()
            self.assertEqual(kod, 0)
            self.assertIn("już jest na tej maszynie", wyswietlone)
            self.assertEqual(klucz.agenci(), ["claude-jkowalski"])
            self.assertEqual(m.ustawienia("claude-jkowalski")["slug"], "claude-jkowalski")


class TestEdycja(unittest.TestCase):
    def test_samymi_Enterami_nic_sie_nie_zmienia(self):
        with MaszynaTestowa(agent="claude-jkowalski") as m:
            m.korzen.joinpath("claude-jkowalski", "credentials").write_text(
                "sk_live_stary-1234", encoding="utf-8")
            przed = m.ustawienia("claude-jkowalski")
            me = _me(_org("advertpro", "claude-jkowalski"))
            # pusty klucz, potem Enter przy Organizacji, profilu i adresie
            kod, _ = _Inicjator(["", "", "", ""], me, klucz_z_flagi="claude-jkowalski",
                                wartosc_klucza="")()
            self.assertEqual(kod, 0)
            po = m.ustawienia("claude-jkowalski")
            for pole in przed:
                self.assertEqual(po[pole], przed[pole],
                                 f"Enter zostawia pole „{pole}” bez zmian")
            self.assertEqual(m.korzen.joinpath("claude-jkowalski", "credentials")
                             .read_text(encoding="utf-8").strip(), "sk_live_stary-1234",
                             "pusty klucz = obecny zostaje nietknięty")

    def test_nowy_klucz_innego_agenta_odmowa_bez_zapisu(self):
        """Decyzja Damiana 26.09: nowy klucz w edycji musi należeć do TEGO SAMEGO agenta."""
        with MaszynaTestowa(agent="claude-jkowalski") as m:
            m.korzen.joinpath("claude-jkowalski", "credentials").write_text(
                "sk_live_stary-1234", encoding="utf-8")
            me_obcego = _me(_org("advertpro", "kodeks-dpakula"))
            kod, wyswietlone = _Inicjator([""], me_obcego,
                                          klucz_z_flagi="claude-jkowalski")()
            self.assertEqual(kod, 2)
            self.assertIn("innego agenta", wyswietlone)
            self.assertEqual(m.korzen.joinpath("claude-jkowalski", "credentials")
                             .read_text(encoding="utf-8").strip(), "sk_live_stary-1234",
                             "odmowa = stary klucz nietknięty")

    def test_nowy_klucz_tego_samego_agenta_przyjmowany(self):
        with MaszynaTestowa(agent="claude-jkowalski") as m:
            me = _me(_org("advertpro", "claude-jkowalski"))
            kod, _ = _Inicjator(["", "", "", ""], me,
                                klucz_z_flagi="claude-jkowalski")()
            self.assertEqual(kod, 0)
            self.assertEqual(m.korzen.joinpath("claude-jkowalski", "credentials")
                             .read_text(encoding="utf-8").strip(), "sk_live_nowy-abcd")

    def test_nieznany_agent_z_flagi_to_zrozumiala_odmowa(self):
        with MaszynaTestowa(agent="claude-jkowalski"):
            kod, wyswietlone = _Inicjator([], _me(_org("sf", "x")),
                                          klucz_z_flagi="nie-ma-go")()
            self.assertEqual(kod, 2)
            self.assertIn("Nie ma agenta „nie-ma-go”", wyswietlone)


class TestStaryUklad(unittest.TestCase):
    def test_stary_uklad_widnieje_na_liscie(self):
        with MaszynaTestowa() as m:
            m.korzen.mkdir(parents=True, exist_ok=True)
            m.korzen.joinpath("config.json").write_text(
                json.dumps({"slug": "kodeks-dpakula", "profil": "worker"}),
                encoding="utf-8")
            wiersze = onboarding._wiersze_agentow()
        self.assertEqual(len(wiersze), 1)
        self.assertTrue(wiersze[0].stary_uklad)
        self.assertEqual(wiersze[0].nazwa, "kodeks-dpakula")

    def test_przeniesienie_zabiera_config_i_klucz(self):
        """Wybór starego układu z listy + zgoda → config i klucz w podkatalogu, korzeń czysty."""
        with MaszynaTestowa() as m:
            m.korzen.mkdir(parents=True, exist_ok=True)
            m.korzen.joinpath("config.json").write_text(
                json.dumps({"slug": "kodeks-dpakula", "profil": "worker"}),
                encoding="utf-8")
            m.korzen.joinpath("credentials").write_text("sk_live_stary-1234",
                                                        encoding="utf-8")
            me = _me(_org("advertpro", "kodeks-dpakula"))
            # „1" wybiera stary układ, „t" potwierdza przeniesienie; po odświeżeniu listy „q".
            kod, wyswietlone = _Inicjator(["1", "t", "q"], me)()
            self.assertEqual(kod, 0)
            self.assertFalse(m.korzen.joinpath("config.json").exists())
            self.assertFalse(m.korzen.joinpath("credentials").exists())
            self.assertEqual(json.loads(m.korzen.joinpath("kodeks-dpakula", "config.json")
                                        .read_text(encoding="utf-8"))["slug"],
                             "kodeks-dpakula")
            self.assertEqual(m.korzen.joinpath("kodeks-dpakula", "credentials")
                             .read_text(encoding="utf-8").strip(), "sk_live_stary-1234")
            self.assertIn("usluga", wyswietlone,
                          "po przenosinach Kit mówi o przegenerowaniu jednostki usługi")


if __name__ == "__main__":
    unittest.main()
