"""Warstwa administracyjna profilu koordynatora (ADVERTPR-879).

v0.6 (18.09.2026) - APro Agents / borys-sf

CZEGO TE TESTY PILNUJĄ — I DLACZEGO AKURAT TEGO
════════════════════════════════════════════════
Sprawa powstała z jednej doby, w której koordynatorka trzy razy ogłosiła „tego się nie da",
a funkcja istniała pod adresem, w który akurat nie strzeliła. Wspólny mianownik wszystkich
trzech wpadek nie brzmi „brakowało funkcji", tylko: **system odpowiedział czymś, co wyglądało
na sukces albo na brak trasy, a znaczyło co innego.**

Dlatego mierzymy tu ciszę, nie funkcje:

· pole, którego trasa nie obsługuje, ma być ZATRZYMANE przed wysyłką — bo po wysyłce
  serwer albo je cicho pominie (potwierdzona usterka `PATCH …/agents/{uuid}`), albo odpowie
  422, nie mówiąc, gdzie to pole naprawdę mieszka;
· numer Organizacji w ścieżce ma być TŁUMACZONY ze sluga, a nie wpisywany — pułapki, którą
  da się usunąć, nie opisuje się w tabeli;
· żądanie o nieistniejącą Organizację ma być ODMOWĄ z listą, nigdy „pierwszą z brzegu";
· `ustaw_domyslne` i lista uprawnień nie mogą pojechać razem, bo serwer rozstrzyga to po cichu
  na korzyść jednego z nich, a suma — której człowiek się spodziewa — nie istnieje;
· „tego nie ma" musi nieść POWÓD, bo bez powodu wraca nazajutrz jako to samo pytanie.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import kontrakt  # noqa: E402
from sf_kit.api import BladAPI, Klient  # noqa: E402


class AtrapaTras(Klient):
    """Klient, który nie rusza sieci — zapamiętuje, CO by wysłał i dokąd.

    Podstawiamy `_wywolaj`, a nie całą klasę: chodzi o to, żeby przez test przeszła prawdziwa
    składanka ścieżki (`tenants/{numer}/…`) i prawdziwe ciało żądania. Atrapa, która udaje
    także składanie adresu, sprawdzałaby wyłącznie samą siebie.
    """

    def __init__(self, organizacje=None):
        super().__init__(baza="https://przyklad.test", klucz="sf_test", organizacja="uuid-7")
        self.wywolania: list[tuple[str, str, dict | None]] = []
        self._organizacje = organizacje if organizacje is not None else [
            {"id": 7, "uuid": "uuid-7", "slug": "advertpro-co"},
            {"id": 6, "uuid": "uuid-6", "slug": "sf"},
        ]

    def _wywolaj(self, metoda, sciezka, *, cialo=None):
        self.wywolania.append((metoda, sciezka, cialo))
        if sciezka == "tenants":
            return list(self._organizacje)
        return {}


class NumerOrganizacji(unittest.TestCase):
    """Pułapka z wymagania 2 sprawy: numer w ścieżce to `tenants.id`, nagłówek niesie `uuid`."""

    def test_slug_tlumaczy_sie_na_numer_porzadkowy(self):
        klient = AtrapaTras()
        self.assertEqual(klient.numer_organizacji("advertpro-co"), 7)

    def test_uuid_tez_dziala_bo_czlowiek_ma_go_pod_reka(self):
        klient = AtrapaTras()
        self.assertEqual(klient.numer_organizacji("uuid-6"), 6)

    def test_bez_wskazania_bierze_organizacje_biezaca_klienta(self):
        klient = AtrapaTras()
        self.assertEqual(klient.numer_organizacji(), 7)

    def test_nieznana_organizacja_to_odmowa_z_lista_a_nie_pierwsza_z_brzegu(self):
        klient = AtrapaTras()
        with self.assertRaises(BladAPI) as pulapka:
            klient.numer_organizacji("cudza-firma")
        tresc = str(pulapka.exception)
        self.assertIn("advertpro-co", tresc)
        self.assertIn("sf", tresc)

    def test_brak_numeru_w_odpowiedzi_to_zmiana_kontraktu_nie_cisza(self):
        """Gdyby `GET /tenants` przestało oddawać `id`, Kit ma o tym POWIEDZIEĆ.

        To jest jedyne miejsce, z którego zwykły członek bierze numer porządkowy. Ciche
        `None` w ścieżce dałoby `tenants/None/...` i 404 wyglądający jak brak trasy — czyli
        dokładnie ten rodzaj fałszywej diagnozy, od którego zaczęła się ta sprawa.
        """
        klient = AtrapaTras(organizacje=[{"uuid": "uuid-7", "slug": "advertpro-co"}])
        with self.assertRaises(BladAPI) as pulapka:
            klient.numer_organizacji("advertpro-co")
        self.assertIn("kontrakt", str(pulapka.exception))

    def test_sciezka_niesie_numer_a_nie_uuid(self):
        klient = AtrapaTras()
        klient.nadania(7, "konto-uuid")
        metoda, sciezka, _ = klient.wywolania[-1]
        self.assertEqual(metoda, "GET")
        self.assertEqual(sciezka, "tenants/7/users/konto-uuid/permissions")
        self.assertNotIn("uuid-7", sciezka)


class PolaKtorychTrasaNieZna(unittest.TestCase):
    """Wymaganie 3 ze sprawy: odrzucać, zamiast cicho połykać."""

    def test_permissions_przy_naprawie_agenta_jest_rozpoznane_z_adresem_wlasciwej_trasy(self):
        """To jest potwierdzona usterka po stronie API — serwer oddaje 200 i zero skutku."""
        op = kontrakt.znajdz("agent-napraw")
        nieznane = dict(kontrakt.nieznane_pola(op, {"kind": "agent", "permissions": ["x"]}))
        self.assertIn("permissions", nieznane)
        self.assertIn("permissions", nieznane["permissions"])
        self.assertIn("sf-kit nadaj", nieznane["permissions"])

    def test_scope_przy_nadaniach_wskazuje_ze_zakres_ma_klucz_nie_nadanie(self):
        op = kontrakt.znajdz("nadaj")
        nieznane = dict(kontrakt.nieznane_pola(op, {"permissions": [], "scope": "user"}))
        self.assertIn("api-keys", nieznane["scope"])

    def test_pole_znane_trasie_przechodzi_bez_slowa(self):
        op = kontrakt.znajdz("klucz-wystaw")
        self.assertEqual(
            kontrakt.nieznane_pola(op, {"source_name": "x", "scope": "user",
                                        "user_email": "a@b.pl", "permissions": None}),
            [])

    def test_pole_zupelnie_obce_tez_jest_zglaszane_ostrozniejszym_zdaniem(self):
        """Cisza jest gorsza od fałszywego alarmu: alarm kosztuje spojrzenie, cisza — noc."""
        op = kontrakt.znajdz("nadaj")
        nieznane = dict(kontrakt.nieznane_pola(op, {"permissions": [], "wymyslone_pole": 1}))
        self.assertIn("wymyslone_pole", nieznane)
        self.assertIn("zignorowane", nieznane["wymyslone_pole"])


class CzegoNieMa(unittest.TestCase):
    """„Nie da się" bez powodu wraca nazajutrz jako to samo pytanie."""

    def test_opinie_maja_powod_a_nie_samo_nie_znam(self):
        powod = kontrakt.podpowiedz_nie_ma("opinie")
        self.assertIsNotNone(powod)
        self.assertIn("panel", powod)

    def test_niezobaczone_mowia_ze_403_jest_zamierzone(self):
        """Bo inaczej koordynatorka zgłosi to jako usterkę — i będzie to trzecia fałszywa diagnoza."""
        powod = kontrakt.podpowiedz_nie_ma("niezobaczone sprawy")
        self.assertIn("403", powod)
        self.assertIn("zamierzone", powod)

    def test_konsola_i_plany_mowia_ze_to_swiadomy_brak_kitu_a_nie_brak_trasy(self):
        for haslo in ("konsola", "plany"):
            with self.subTest(haslo=haslo):
                self.assertIn("ADVERTPR-879", kontrakt.podpowiedz_nie_ma(haslo))

    def test_operacja_ktorej_nie_znamy_wcale_nie_udaje_ze_wie(self):
        self.assertIsNone(kontrakt.znajdz("wymyslona-operacja"))
        self.assertIsNone(kontrakt.podpowiedz_nie_ma("wymyslona-operacja"))


class KatalogOperacji(unittest.TestCase):
    """Katalog jest KOPIĄ kształtu, który żyje po drugiej stronie — ma o tym mówić."""

    def test_kazda_operacja_ma_sposob_weryfikacji_a_nie_sam_kod_odpowiedzi(self):
        """201 na konfigurację, która nie działa, kosztowało 18.09 pół nocy."""
        for op in kontrakt.KATALOG:
            with self.subTest(op=op.nazwa):
                self.assertTrue(op.weryfikacja, f"{op.nazwa} nie mówi, czym się domyka")

    def test_kazda_trasa_z_numerem_ostrzega_o_liczbie_porzadkowej(self):
        for op in kontrakt.KATALOG:
            if "{numer}" not in op.trasa:
                continue
            with self.subTest(op=op.nazwa):
                self.assertIn(kontrakt.PULAPKA_NUMERU, op.pulapki)

    def test_opis_niesie_pola_pulapki_i_to_czego_trasa_nie_obsluguje(self):
        tekst = kontrakt.znajdz("klucz-wystaw").opis()
        self.assertIn("source_name", tekst)
        self.assertIn("pułapki", tekst)
        self.assertIn("agent_slug", tekst)   # pole ODRZUCANE — ma być widoczne w opisie

    def test_spis_wymienia_takze_to_czego_nie_ma(self):
        tekst = kontrakt.spis()
        for op in kontrakt.KATALOG:
            self.assertIn(op.nazwa, tekst)
        self.assertIn("opinie", tekst)


class WystawianieKlucza(unittest.TestCase):
    """`null` i `[]` to po tamtej stronie dwie różne rzeczy (kontrakt 545 §4.3)."""

    def test_brak_zawezenia_jedzie_jako_jawny_null_a_nie_pusta_lista(self):
        """`[]` to klucz, który nie może NIC — 201 przy wystawieniu i 403 na każdym żądaniu."""
        klient = AtrapaTras()
        klient.wystaw_klucz(nazwa="test", uprawnienia=None)
        _, sciezka, cialo = klient.wywolania[-1]
        self.assertEqual(sciezka, "api-keys")
        self.assertIn("permissions", cialo)
        self.assertIsNone(cialo["permissions"])

    def test_pusta_lista_zostaje_pusta_lista_bo_to_swiadomy_wybor(self):
        klient = AtrapaTras()
        klient.wystaw_klucz(nazwa="test", uprawnienia=[])
        self.assertEqual(klient.wywolania[-1][2]["permissions"], [])


class UstawianieNadan(unittest.TestCase):
    def test_domyslne_jedzie_samo_bo_serwer_i_tak_odrzucilby_liste_po_cichu(self):
        klient = AtrapaTras()
        klient.ustaw_nadania(7, "konto", uprawnienia=["tickets:write"], domyslne=True)
        cialo = klient.wywolania[-1][2]
        self.assertEqual(cialo, {"ustaw_domyslne": True})
        self.assertNotIn("permissions", cialo)

    def test_lista_idzie_bez_powtorzen_i_posortowana(self):
        klient = AtrapaTras()
        klient.ustaw_nadania(7, "konto", uprawnienia=["b", "a", "b"])
        self.assertEqual(klient.wywolania[-1][2], {"permissions": ["a", "b"]})


class ProbneWywolanie(unittest.TestCase):
    """Weryfikacja idzie NOWYM kluczem — inaczej sprawdzamy klucz wołającego, nie wystawiony."""

    def test_probny_klient_nie_niesie_naglowka_organizacji(self):
        """`GET /me` działa bez niego (ADVERTPR-796), a pusty nagłówek to 403 zamiast odpowiedzi."""
        klient = AtrapaTras()
        uchwycone = {}

        class Podglad(Klient):
            def kim_jestem(self):
                uchwycone["organizacja"] = self.organizacja
                uchwycone["klucz"] = self._klucz
                return {"konto": {"email": "nowy@x.pl"}, "organizacje": []}

        import sf_kit.api as modul
        stary = modul.Klient
        modul.Klient = Podglad
        try:
            klient.probne_wywolanie("sf_nowy_klucz")
        finally:
            modul.Klient = stary

        self.assertEqual(uchwycone["organizacja"], "")
        self.assertEqual(uchwycone["klucz"], "sf_nowy_klucz")


if __name__ == "__main__":
    unittest.main()


class BramkaPolWCLI(unittest.TestCase):
    """Bramka ma ZAPALAĆ, a nie stać. Testy wołają warstwę CLI, nie sam katalog.

    Pierwsza wersja tej warstwy miała bramkę, która nie miała czego łapać: argparse przepuszcza
    wyłącznie flagi, które sam zna, więc ciało żądania nigdy nie zawierało nieznanego pola.
    Sprawdzenie stało w kodzie i nie mogło zapalić ANI RAZU. Stąd `--pole nazwa=wartość`
    i stąd te testy — kod, którego nikt nie woła, wygląda w przeglądzie identycznie jak
    zabezpieczenie, które działa.
    """

    def test_pole_nieznane_trasie_zatrzymuje_polecenie_z_adresem_wlasciwej(self):
        from sf_kit import cli
        op = kontrakt.znajdz("agent-napraw")
        with self.assertRaises(SystemExit) as pulapka:
            cli._sprawdz_pola(op, {"kind": "agent", "permissions": ["tickets:write"]})
        tresc = str(pulapka.exception)
        self.assertIn("permissions", tresc)
        self.assertIn("sf-kit nadaj", tresc)
        self.assertIn("kontrakt agent-napraw", tresc)

    def test_pole_znane_trasie_przechodzi_przez_bramke(self):
        from sf_kit import cli
        cli._sprawdz_pola(kontrakt.znajdz("klucz-wystaw"),
                          {"source_name": "x", "expires_at": "2026-12-31T00:00:00Z"})

    def test_pole_surowe_rozpoznaje_wartosci_a_nie_robi_ze_wszystkiego_tekstu(self):
        from sf_kit import cli

        class Args:
            pola = ["licz=7", "flaga=true", "nic=null", "tekst=abc", "ujemna=-3"]

        self.assertEqual(cli._pola_surowe(Args()),
                         {"licz": 7, "flaga": True, "nic": None, "tekst": "abc", "ujemna": -3})

    def test_pole_bez_znaku_rownosci_to_odmowa_a_nie_ciche_pominiecie(self):
        from sf_kit import cli

        class Args:
            pola = ["permissions"]

        with self.assertRaises(SystemExit) as pulapka:
            cli._pola_surowe(Args())
        self.assertIn("=", str(pulapka.exception))

    def test_pole_ktore_przeszlo_bramke_NAPRAWDE_jedzie_do_serwera(self):
        """Druga połowa bramki: zgubienie pola w Kicie to to samo ciche połknięcie."""
        klient = AtrapaTras()
        klient.wystaw_klucz(nazwa="x", dodatkowe={"expires_at": "2026-12-31T00:00:00Z"})
        self.assertEqual(klient.wywolania[-1][2]["expires_at"], "2026-12-31T00:00:00Z")

    def test_naprawa_agenta_nie_niesie_uprawnien_nawet_gdyby_ktos_je_podal(self):
        """Trasa, na której siedziała usterka — Kit nie ma prawa jej karmić tym polem."""
        klient = AtrapaTras()
        klient.napraw_agenta(7, "konto", slug="arek-sf", rodzaj="agent")
        _, sciezka, cialo = klient.wywolania[-1]
        self.assertEqual(sciezka, "tenants/7/agents/konto")
        self.assertNotIn("permissions", cialo)


class BramkaStoiPrzedSiecia(unittest.TestCase):
    """Błąd kształtu żądania ma być widoczny ZAWSZE — także gdy nie wolno go wykonać.

    Pierwsza wersja `nadaj` sprawdzała pola dopiero przed zapisem, czyli po odczycie stanu.
    Dla kogoś, kto nie jest ownerem, odczyt kończy się 403 — i człowiek dostawał komunikat
    o uprawnieniach, nie dowiadując się, że w dodatku wysyłał pole, którego ta trasa nie zna.
    Złapane w smoke'u na żywym API 18.09, nie w przeglądzie kodu.
    """

    def _uruchom_nadaj(self, **nadpisz):
        from sf_kit import cli

        class KlientBezSieci:
            def __getattr__(self, nazwa):
                def _(*a, **k):
                    raise AssertionError(f"bramka przepuściła — poszło `{nazwa}` do sieci")
                return _

        class Args:
            konto = "11111111-1111-1111-1111-111111111111"
            uprawnienia = ["tickets:read"]
            domyslne = False
            pokaz = False
            pola = ["scope=user"]
            org = None

        for k, v in nadpisz.items():
            setattr(Args, k, v)

        stary_klient, stara_konf = cli._klient, cli.konfiguracja.wczytaj
        cli._klient = lambda konf, args: KlientBezSieci()
        cli.konfiguracja.wczytaj = lambda: None
        try:
            return cli.polecenie_nadaj(Args())
        finally:
            cli._klient, cli.konfiguracja.wczytaj = stary_klient, stara_konf

    def test_zle_pole_zatrzymuje_polecenie_zanim_ruszy_siec(self):
        with self.assertRaises(SystemExit) as pulapka:
            self._uruchom_nadaj()
        self.assertIn("scope", str(pulapka.exception))

    def test_sprzeczne_flagi_tez_zatrzymuja_przed_siecia(self):
        """`--domyslne` z listą: serwer bierze sam zestaw domyślny, lista przepada bez słowa."""
        self.assertEqual(self._uruchom_nadaj(pola=[], domyslne=True), 2)
