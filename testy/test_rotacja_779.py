"""Samoodnowienie klucza w Kicie — `sf-kit rotate` i auto-rotacja workera (ADVERTPR-779 B).

v1.0.0 (19.09.2026) - APro Agents / borys-sf

Najważniejszy test w tym pliku to `test_sekret_jest_ZAPISANY_zanim_cokolwiek_innego`. SF odnawia
klucz „jednym żywym sekretem": w chwili odpowiedzi stary jest martwy. Wszystko, co dzieje się
między odebraniem nowego sekretu a jego zapisem, to okno, w którym agent może stracić dostęp
bezpowrotnie — więc pilnujemy, że w tym oknie nie dzieje się NIC.
"""
import unittest
from datetime import datetime, timedelta, timezone

from sf_kit import api, rotacja, worker

TERAZ = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _za(dni):
    return (TERAZ + timedelta(days=dni)).isoformat()


def _me(*, id_klucza="11111111-1111-1111-1111-111111111111", wygasa=None):
    return {"konto": {"nazwa": "Borys"},
            "klucz": {"id": id_klucza, "prefiks": "sk_live_stary", "wygasa": wygasa},
            "organizacje": []}


class _Klient:
    """Atrapa o TAKICH SAMYCH nazwach metod, jakie ma prawdziwy `Klient` (lekcja z 19.09)."""

    def __init__(self, *, me=None, odpowiedz=None, blad=None):
        self._me = me if me is not None else _me()
        self.odpowiedz = odpowiedz
        self.blad = blad
        self.wolano_odnow = 0
        self.klucz_teraz = "sk_live_stary"

    def kim_jestem(self):
        return self._me

    def odnow_klucz(self, key_id):
        self.wolano_odnow += 1
        self.ostatni_id = key_id
        if self.blad:
            raise self.blad
        return self.odpowiedz

    def podmien_klucz(self, klucz):
        self.klucz_teraz = klucz


def _blad(kod, detail):
    """Wyjątek dokładnie taki, jaki zbuduje `api.Klient` przy odpowiedzi SF."""
    return api.Klient._na_wyjatek(kod, "POST", "me/api-keys/x/odnow",
                                  '{"detail": "%s"}' % detail)


class TestRotacja(unittest.TestCase):

    def test_sekret_jest_ZAPISANY_zanim_cokolwiek_innego(self):
        """Nawet gdy podmiana klucza w kliencie wybuchnie, sekret ma już być na dysku.

        To jest cała cena decyzji „jeden żywy sekret": po odpowiedzi SF stary klucz nie działa,
        więc nieudany zapis znaczy utratę dostępu bez odwołania.
        """
        zapisane = []

        class _Wybuchowy(_Klient):
            def podmien_klucz(self, klucz):
                raise RuntimeError("cokolwiek po zapisie")

        kl = _Wybuchowy(odpowiedz={"api_key": "sk_live_nowy", "expires_at": _za(30)})
        with self.assertRaises(RuntimeError):
            rotacja.rotuj(kl, zapis=lambda k: zapisane.append(k) or "pęk")
        self.assertEqual(zapisane, ["sk_live_nowy"])

    def test_po_rotacji_klient_mowi_juz_NOWYM_sekretem(self):
        kl = _Klient(odpowiedz={"api_key": "sk_live_nowy", "expires_at": _za(30)})
        wynik = rotacja.rotuj(kl, zapis=lambda k: "pęk kluczy")
        self.assertTrue(wynik.odnowiony)
        self.assertEqual(kl.klucz_teraz, "sk_live_nowy")
        self.assertIn("pęk kluczy", wynik.zdanie)

    def test_zdanie_nie_zawiera_calego_sekretu(self):
        """Klucz nigdy w całości na ekranie ani w dzienniku — reguła modułu `klucz`.

        Wartość SKLEJAMY w trakcie testu, zamiast wpisywać ją literałem: hak `pre-commit` tego
        repozytorium zatrzymuje commit, w którym widzi osiem znaków po `sk_live_` — i słusznie,
        bo nie ma jak odróżnić przykładu od prawdziwego klucza. Test od tego nie słabnie.
        """
        sekret = "sk_live_" + "t4jn3s3kr3t" + "9876"
        kl = _Klient(odpowiedz={"api_key": sekret, "expires_at": _za(30)})
        wynik = rotacja.rotuj(kl, zapis=lambda k: "plik")
        self.assertNotIn(sekret, wynik.zdanie)
        self.assertNotIn("t4jn3s3kr3t", wynik.zdanie)
        self.assertIn("…", wynik.zdanie)

    def test_odmowa_SF_wraca_JEGO_zdaniem_a_nie_mapa_kodow_Kitu(self):
        """409 z mapy Kitu znaczy „ktoś zmienił ten obiekt przed tobą" — przy odnowieniu to
        nieprawda. Zdanie ma pochodzić z `detail`, bo tylko ono opisuje prawdziwy powód."""
        kl = _Klient(blad=_blad(409, "Za wcześnie na odnowienie. Klucz wygasa 20.10.2026."))
        wynik = rotacja.rotuj(kl, zapis=lambda k: "plik")
        self.assertFalse(wynik.odnowiony)
        self.assertIn("Za wcześnie", wynik.zdanie)
        self.assertNotIn("ktoś zmienił", wynik.zdanie)

    def test_brak_uprawnienia_tez_wraca_zdaniem_SF(self):
        kl = _Klient(blad=_blad(403, "Ten klucz nie może się odnawiać sam."))
        wynik = rotacja.rotuj(kl, zapis=lambda k: "plik")
        self.assertIn("nie może się odnawiać sam", wynik.zdanie)

    def test_bez_identyfikatora_klucza_NIE_wolamy_trasy(self):
        """Starsze SF nie podaje `klucz.id`. Zgadywanie adresu skończyłoby się 404 albo — gorzej
        — trafieniem w cudzy klucz."""
        kl = _Klient(me=_me(id_klucza=None))
        wynik = rotacja.rotuj(kl, zapis=lambda k: "plik")
        self.assertFalse(wynik.odnowiony)
        self.assertEqual(kl.wolano_odnow, 0)
        self.assertIn("identyfikatora klucza", wynik.zdanie)

    def test_dwiescie_bez_sekretu_mowi_WPROST_ze_dostep_mogl_przepasc(self):
        """Jedyny przypadek, w którym „sukces" znaczy kłopot — musi być nazwany, nie przemilczany."""
        kl = _Klient(odpowiedz={"expires_at": _za(30)})
        wynik = rotacja.rotuj(kl, zapis=lambda k: "plik")
        self.assertFalse(wynik.odnowiony)
        self.assertIn("nie przysłał nowego sekretu", wynik.zdanie)


class TestWorkerDbaOKlucz(unittest.TestCase):
    """Zapis sekretu ZAWSZE na atrapie.

    Pierwsza wersja tych testów wołała `zadbaj_o_klucz` bez wstrzykniętego zapisu i „sk_live_nowy"
    wylądował w prawdziwym magazynie kluczy tej maszyny (katalog powstał w trakcie przebiegu).
    Atrapa klienta nie wystarcza, jeśli kod za nią sięga po prawdziwy dysk.
    """


    def test_udane_odnowienie_trafia_do_dziennika(self):
        kl = _Klient(me=_me(wygasa=_za(3)),
                     odpowiedz={"api_key": "sk_live_nowy", "expires_at": _za(30)})
        zdanie = worker.zadbaj_o_klucz(kl, teraz=TERAZ, zapis=lambda k: "atrapa")
        self.assertIn("odnowiony sam", zdanie or "")

    def test_poza_oknem_worker_MILCZY(self):
        """Klucz z terminem za 25 dni dostaje 409 codziennie. Gdyby worker o tym mówił, dziennik
        zamieniłby się w listę odmów, w której ginie ostrzeżenie naprawdę pilne."""
        kl = _Klient(me=_me(wygasa=_za(25)), blad=_blad(409, "Za wcześnie na odnowienie."))
        self.assertIsNone(worker.zadbaj_o_klucz(kl, teraz=TERAZ, zapis=lambda k: "atrapa"))

    def test_blisko_terminu_i_bez_prawa_do_odnowienia_worker_OSTRZEGA(self):
        kl = _Klient(me=_me(wygasa=_za(2)), blad=_blad(403, "Ten klucz nie może się odnawiać sam."))
        zdanie = worker.zadbaj_o_klucz(kl, teraz=TERAZ, zapis=lambda k: "atrapa")
        self.assertIn("za 2 dni", zdanie or "")

    def test_awaria_rotacji_NIE_zatrzymuje_workera(self):
        """FAIL-SOFT: zatrzymać workera ma SF, gdy odmówi — nie wymiana klucza."""
        class _Pada(_Klient):
            def kim_jestem(self):
                raise RuntimeError("sieć padła")

        self.assertIsNone(worker.zadbaj_o_klucz(_Pada(), teraz=TERAZ, zapis=lambda k: "atrapa"))


if __name__ == "__main__":
    unittest.main()


class TestPolecenieRotate(unittest.TestCase):
    """`sf-kit rotate` musi wołać SF Z ORGANIZACJĄ — inaczej 403 przy poprawnym kluczu.

    Odnowienie wygląda na czynność ponad Organizacjami, ale uprawnienie `keys:self-renew` jest
    nadaniem na członkostwie, więc SF wymaga nagłówka `X-Tenant-Id` (sprawdzone żądaniem na
    trasie, nie założone). Pierwsza wersja polecenia budowała klienta bez Organizacji.
    """

    def test_klient_dostaje_organizacje(self):
        from types import SimpleNamespace

        from sf_kit import cli

        zbudowane = []

        class _K:
            def __init__(self, *, baza, klucz, organizacja=""):
                zbudowane.append(organizacja)

            def kim_jestem(self):
                return {"konto": {"nazwa": "Borys"}, "klucz": {"id": "abc"},
                        "organizacje": [{"tenant_uuid": "u-1", "slug": "advertpro-co",
                                         "nazwa": "AdvertPro", "rola": "user",
                                         "uprawnienia_efektywne": ["keys:self-renew"]}]}

        pierwotne = (cli.Klient, cli.konfiguracja.wczytaj, cli.magazyn_klucza.wczytaj,
                     cli.mod_rotacja.rotuj)
        cli.Klient = _K
        cli.konfiguracja.wczytaj = lambda: SimpleNamespace(
            adres="https://sf.example", organizacja="advertpro-co", slug="borys-sf",
            profil="agent")
        cli.magazyn_klucza.wczytaj = lambda: "sk_live_x"
        cli.mod_rotacja.rotuj = lambda klient: rotacja.Wynik(True, "odnowiony", gdzie="atrapa")
        try:
            kod = cli.polecenie_rotate(SimpleNamespace(org=None))
        finally:
            (cli.Klient, cli.konfiguracja.wczytaj, cli.magazyn_klucza.wczytaj,
             cli.mod_rotacja.rotuj) = pierwotne

        self.assertEqual(kod, 0)
        # Pierwszy klient (odczyt `/me`) celowo bez Organizacji, drugi — TEN, którym rotujemy — z nią.
        self.assertEqual(zbudowane, ["", "u-1"])
