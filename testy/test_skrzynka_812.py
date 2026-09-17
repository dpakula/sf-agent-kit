"""Skrzynka wiadomości w Kicie: moduł, worker, odporność (ADVERTPR-812, zakres D).

v0.1 (16.09.2026) - APro Agents / borys-sf

CZEGO TU PILNUJĘ, POZA TYM ŻE „DZIAŁA"
══════════════════════════════════════
1. **KOLEJNOŚĆ: pokaż, potem potwierdź.** Ack przy samym odczycie znaczyłby „odebrane" dla
   treści, która poszła w powietrze razem z procesem. Test sprawdza, że w chwili wywołania
   wykonawcy potwierdzenia JESZCZE NIE MA — a nie tylko, że kiedyś poszło.
2. **Skrzynka nie zatrzymuje pracy.** Klient bez metody, 503 przed rewizją, padający ack —
   każde z nich znaczy „dziś bez skrzynki", nie „nie pracuj". To nie jest hipoteza: pierwsza
   wersja łapała tylko `BladAPI` i `AttributeError` ze starszego klienta zatrzymywał worker
   w połowie zadania (16 testów kitu zapaliło się od razu).
3. **Fail-soft nie połyka literówki.** Powód braku niesie NAZWĘ wyjątku, więc `NameError`
   w kodzie skrzynki nie wygląda jak „skrzynka pusta".

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import skrzynka  # noqa: E402
from sf_kit.api import BladAPI, Klient  # noqa: E402
from sf_kit.worker import obsluz_zadanie  # noqa: E402
from testy.test_worker import AtrapaKlienta, konfiguracja, zadanie  # noqa: E402


def wiadomosc(*, mid="m1", status="new", tresc="treść wiadomości", nadawca="agata@dpakula.pl",
              zalega=False):
    return {"id": f"r-{mid}", "message_id": mid, "status": status, "body": tresc,
            "nadawca": nadawca, "utworzono": "2026-09-16T01:12:44Z", "kind": "entry",
            "adresat_glowny": "borys-sf", "zalega": zalega}


class KlientZeSkrzynka:
    """Atrapa z osobnym licznikiem potwierdzeń — po nim sprawdzamy KOLEJNOŚĆ."""

    def __init__(self, dane=None, *, odczyt_pada=None, ack_pada=False):
        self._dane = dane if dane is not None else {"wiadomosci": [], "nieodebrane": 0,
                                                    "zalegle": 0}
        self._odczyt_pada = odczyt_pada
        self._ack_pada = ack_pada
        self.potwierdzone: list[str] = []
        self.zapytania = 0

    def skrzynka(self, *, session_target="", dni=None, limit=None, tylko_nieodebrane=False):
        self.zapytania += 1
        if self._odczyt_pada:
            raise self._odczyt_pada
        return self._dane

    def potwierdz_odbior(self, message_id, *, status="consumed", powod=None):
        if self._ack_pada:
            raise BladAPI("atrapa: ack nie przeszedł", kod=500)
        self.potwierdzone.append(str(message_id))
        return {}


class TestPobieranie(unittest.TestCase):

    def test_klient_uzywa_listy_z_filtrem_sluga_a_nie_kolizyjnego_inbox(self):
        class KlientSzpieg(Klient):
            def __init__(self):
                super().__init__(baza="https://atrapa.test", klucz="x", organizacja="org")
                self.zapytanie = None

            def _wywolaj(self, metoda, sciezka, *, cialo=None):
                self.zapytanie = (metoda, sciezka)
                return {"wiadomosci": []}

        klient = KlientSzpieg()
        klient.skrzynka(session_target="kodeks-dpakula", limit=5,
                        tylko_nieodebrane=True)
        metoda, sciezka = klient.zapytanie
        adres = urlparse(sciezka)
        parametry = parse_qs(adres.query)

        self.assertEqual(metoda, "GET")
        self.assertEqual(adres.path, "console/messages")
        self.assertEqual(parametry["session_target"], ["kodeks-dpakula"])
        self.assertEqual(parametry["status"], ["new"])
        self.assertNotIn("/inbox", adres.path)

    def test_bierze_tylko_to_co_CZEKA_na_agenta(self):
        klient = KlientZeSkrzynka({"wiadomosci": [
            wiadomosc(mid="a", status="new"),
            wiadomosc(mid="b", status="delivered"),
            wiadomosc(mid="c", status="failed"),
            wiadomosc(mid="d", status="consumed"),   # już odebrana — nie moja robota
            wiadomosc(mid="e", status="replied"),     # już odpowiedziana
        ], "nieodebrane": 3, "zalegle": 1})
        odebrane = skrzynka.pobierz(klient)

        self.assertEqual([w["message_id"] for w in odebrane.wiadomosci], ["a", "b", "c"])
        self.assertEqual(odebrane.zalegle, 1)
        self.assertTrue(odebrane.cos_jest)

    def test_ile_dalej_mowi_ile_zostalo_w_skrzynce(self):
        """Limit taktu jest po to, żeby nie utopić prompta setką treści — ale agent MA WIEDZIEĆ,
        że reszta istnieje. Cisza o niej wyglądałaby jak pusta skrzynka."""
        klient = KlientZeSkrzynka({"wiadomosci": [wiadomosc(mid="a")], "nieodebrane": 48,
                                   "zalegle": 12})
        odebrane = skrzynka.pobierz(klient, limit=1)
        self.assertEqual(odebrane.ile_dalej, 47)
        self.assertIn("47 dalej", skrzynka.opis(odebrane))

    def test_pusta_skrzynka_to_nie_brak_skrzynki(self):
        odebrane = skrzynka.pobierz(KlientZeSkrzynka())
        self.assertFalse(odebrane.cos_jest)
        self.assertIsNone(odebrane.powod_braku, "pusto ≠ niedostępna — to dwa różne stany")


class TestOdpornosc(unittest.TestCase):

    def test_503_przed_rewizja_to_STAN_a_nie_awaria(self):
        klient = KlientZeSkrzynka(odczyt_pada=BladAPI("czeka na rewizję bazy", kod=503))
        odebrane = skrzynka.pobierz(klient)
        self.assertFalse(odebrane.cos_jest)
        self.assertIn("rewizję", odebrane.powod_braku)

    def test_klient_BEZ_metody_skrzynki_nie_wywraca_odczytu(self):
        """Starszy klient (albo atrapa) nie ma `skrzynka()`. To musi być „dziś bez skrzynki",
        a nie wyjątek — inaczej podniesienie samego SF zatrzymuje workery."""
        class Staruszek:
            pass

        odebrane = skrzynka.pobierz(Staruszek())
        self.assertFalse(odebrane.cos_jest)
        self.assertIn("AttributeError", odebrane.powod_braku,
                      "powód ma nieść NAZWĘ wyjątku — inaczej literówka wygląda jak pusta skrzynka")

    def test_padajacy_ack_zapisuje_sie_i_NIE_przerywa_reszty(self):
        klient = KlientZeSkrzynka({"wiadomosci": [wiadomosc(mid="a"), wiadomosc(mid="b")],
                                   "nieodebrane": 2, "zalegle": 0}, ack_pada=True)
        odebrane = skrzynka.potwierdz(klient, skrzynka.pobierz(klient))
        self.assertEqual(sorted(odebrane.niepotwierdzone), ["a", "b"],
                         "porażka pierwszego nie ma prawa zatrzymać potwierdzania drugiego")


class TestOpis(unittest.TestCase):

    def test_tresc_jest_doslowna_a_zaleglosc_widoczna(self):
        """Nagłówek kontekstu skleja SF, żeby ta sama wiadomość wyglądała identycznie
        w tmuxie, w API i tutaj. Kit nie dokleja nic do cudzej treści i nic nie skraca."""
        dlugie = "x" * 500
        odebrane = skrzynka.pobierz(KlientZeSkrzynka(
            {"wiadomosci": [wiadomosc(tresc=dlugie, zalega=True)], "nieodebrane": 1,
             "zalegle": 1}))
        tekst = skrzynka.opis(odebrane)
        self.assertIn(dlugie, tekst, "treści nie skracamy")
        self.assertIn("[ZALEGA]", tekst)
        self.assertIn("agata@dpakula.pl", tekst)

    def test_pusta_skrzynka_nie_ma_opisu(self):
        self.assertEqual(skrzynka.opis(skrzynka.Odebrane()), "")


class KlientWorkera(AtrapaKlienta):
    """Atrapa workera + skrzynka. Zapisuje, ILE potwierdzeń było w chwili wykonania."""

    def __init__(self, dane=None, **kw):
        super().__init__(**kw)
        self._dane = dane or {"wiadomosci": [wiadomosc(tresc="Przypisano Cię do sprawy X.")],
                              "nieodebrane": 1, "zalegle": 0}
        self.potwierdzone: list[str] = []
        self.ack_przy_wykonaniu: int | None = None

    def skrzynka(self, *, session_target="", dni=None, limit=None, tylko_nieodebrane=False):
        return self._dane

    def potwierdz_odbior(self, message_id, *, status="consumed", powod=None):
        self.potwierdzone.append(str(message_id))
        return {}


class TestWorker(unittest.TestCase):

    def test_skrzynka_wchodzi_do_POLECENIA_i_ack_idzie_DOPIERO_POTEM(self):
        """Najważniejszy test tego pliku: kolejność.

        Potwierdzenie odbioru przed przekazaniem treści agentowi znaczyłoby „odebrane" dla
        wiadomości, którą proces mógł zgubić. Ta sama zasada, co przy bramce floty:
        najpierw zapis, potem ack.
        """
        from sf_kit import wykonawcy

        klient = KlientWorkera()
        widziane = {}

        class WykonawcaSzpieg(wykonawcy.Wykonawca):
            """Wykonawca, który CHCE RAMKI — tylko tacy dostają treść skrzynki."""

            nazwa = "szpieg"
            chce_ramke = True

            def dostepny(self):
                return True, ""

            def wykonaj(self, polecenie, *, katalog, limit_s):
                widziane["polecenie"] = polecenie
                # Migawka potwierdzeń Z CHWILI wykonania — po niej sprawdzamy kolejność.
                widziane["ack_do_tej_pory"] = list(klient.potwierdzone)
                return wykonawcy.Wynik(True, "**Sedno** — ok")

        stare_wykonawcy = dict(wykonawcy._WYKONAWCY)
        wykonawcy._WYKONAWCY["szpieg"] = WykonawcaSzpieg()
        try:
            obsluz_zadanie(klient, konfiguracja(runtime="szpieg"),
                           zadanie(body_md="zrób coś"))
        finally:
            wykonawcy._WYKONAWCY.clear()
            wykonawcy._WYKONAWCY.update(stare_wykonawcy)

        self.assertIn("Przypisano Cię do sprawy X.", widziane["polecenie"],
                      "treść skrzynki ma dojść do agenta, a nie tylko do logu")
        self.assertEqual(widziane["ack_do_tej_pory"], [],
                         "w chwili wykonania odbiór NIE może być jeszcze potwierdzony")
        self.assertEqual(klient.potwierdzone, ["m1"], "…ale po przekazaniu treści — tak")

    def test_niedostepna_skrzynka_NIE_zatrzymuje_zadania(self):
        class KlientBezSkrzynki(AtrapaKlienta):
            def skrzynka(self, **_):
                raise BladAPI("czeka na rewizję bazy", kod=503)

        klient = KlientBezSkrzynki()
        wynik = obsluz_zadanie(klient, konfiguracja(), zadanie(body_md="echo ok"))
        self.assertNotIn("przerwane", wynik)
        self.assertIn("completed", [s for _, s in klient.statusy])

    def test_wiadomosci_NIE_ida_do_powloki_bo_ona_je_WYKONA(self):
        """Ta sama reguła, co przy uwagach z 807 C1: wykonawca powłokowy dostaje skrypt,
        więc polski akapit jest dla niego błędem składni, a nie wskazówką.

        Skutek uboczny jest zamierzony: skoro treść NIE dotarła do agenta, odbioru też NIE
        potwierdzamy — wiadomość wraca w następnym takcie, zamiast zginąć jako „odebrana".
        """
        klient = KlientWorkera()
        obsluz_zadanie(klient, konfiguracja(), zadanie(body_md="echo ok"))
        self.assertEqual(klient.potwierdzone, [],
                         "nie pokazaliśmy — nie potwierdzamy")


if __name__ == "__main__":
    unittest.main()
