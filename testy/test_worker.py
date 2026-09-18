"""Testy pętli workera — na atrapie SF, bez sieci i bez produkcji.

v0.1 (14.09.2026) - APro Agents / borys-sf

DLACZEGO ATRAPA, A NIE ŻYWE SF
Bo pierwszy test workera puściłem na żywym SF własnym slugiem i worker — zachowując się
poprawnie — napisał wpis na prawdziwej sprawie klienta (ADVERTPR-695, sprostowane). Kod był
w porządku; złe było to, na czym go uruchomiłem.

Logika workera to decyzje: co odrzucić, co przyjąć, kiedy NIE zamykać zadania. Wszystkie dają
się sprawdzić na atrapie, która zapamiętuje, co zostało wywołane — i tylko tak da się
sprawdzić te, których na produkcji wywołać nie wolno (np. „co się stanie, gdy wpis padnie").

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit.api import BladAPI, BrakUprawnienia  # noqa: E402
from sf_kit.config import Konfiguracja  # noqa: E402
from sf_kit.worker import obsluz_zadanie  # noqa: E402
from sf_kit.stan_workera import StanProb  # noqa: E402


class AtrapaKlienta:
    """Zapamiętuje, co worker wywołał. Może udawać awarię wybranej operacji."""

    def __init__(self, *, wpis_pada=False, status_pada_na=None, brak_uprawnienia=False,
                 komentarz_pada=False, komentarze_zadania=None):
        #: Komentarze, ktore `zadanie()` odda workerowi (807 C1). Domyslnie brak — czyli
        #: zachowanie sprzed kanalu reakcji.
        self._komentarze_zadania = list(komentarze_zadania or [])
        self.wpisy: list[tuple[str, str]] = []
        self.wpisy_z_plikami: list[tuple[str, str, list]] = []
        self.komentarze: list[tuple[str, str]] = []
        self.statusy: list[tuple[str, str]] = []
        self._wpis_pada = wpis_pada
        self._status_pada_na = status_pada_na
        self._brak_uprawnienia = brak_uprawnienia
        self._komentarz_pada = komentarz_pada

    def wpis(self, ticket_id, tresc, *, widocznosc="internal"):
        if self._wpis_pada:
            raise BladAPI("atrapa: wpis nie przeszedł")
        self.wpisy.append((str(ticket_id), tresc))
        return {}

    def wpis_z_plikami(self, ticket_id, tresc, pliki, **_):
        if self._wpis_pada:
            raise BladAPI("atrapa: wpis z plikami nie przeszedł")
        self.wpisy_z_plikami.append((str(ticket_id), tresc, list(pliki)))
        self.wpisy.append((str(ticket_id), tresc))
        return {}

    def komentarz_zadania(self, task_id, tresc, *, wewnetrzny=True):
        if self._komentarz_pada:
            raise BladAPI("atrapa: komentarz nie przeszedł")
        self.komentarze.append((str(task_id), tresc))
        return {}

    def zadanie(self, task_id):
        """Szczegoly zadania — worker czyta stad komentarze miedzy krokami (807 C1)."""
        return {"id": str(task_id), "comments": self._komentarze_zadania}

    def kim_jestem(self):
        return {"user": {"email": "kodeks@advertpro.co"}}

    def ustaw_status(self, task_id, status, *, wersja=None):
        if self._brak_uprawnienia:
            raise BrakUprawnienia("atrapa: brak plans:write")
        if status == self._status_pada_na:
            raise BladAPI(f"atrapa: nie mogę ustawić {status}")
        self.statusy.append((str(task_id), status))
        return {}


def zadanie(**nadpisz):
    z = {
        "id": "11111111-1111-1111-1111-111111111111",
        "external_id": "zadanie-testowe-20260914",
        "title": "Zadanie testowe",
        "body_md": "echo 'zrobione'",
        "ticket_id": "22222222-2222-2222-2222-222222222222",
        "version": 1,
    }
    z.update(nadpisz)
    return z


def konfiguracja(**nadpisz):
    k = Konfiguracja(adres="https://x", organizacja="org", slug="agent-testowy",
                     katalog_roboczy="/tmp", runtime="shell", limit_zadania_s=10)
    for pole, wartosc in nadpisz.items():
        setattr(k, pole, wartosc)
    return k


class TestOdrzucanie(unittest.TestCase):
    """Zadanie bez kontekstu ma być ODRZUCONE, a nie wykonane „mniej więcej".

    ZMIANA KONTRAKTU W ADVERTPR-850 — ŚWIADOMA, NIE PRZEOCZENIE
    ═════════════════════════════════════════════════════════════
    Do v0.5.1 te testy wymagały `klient.statusy == []`: odrzucenie NIE ruszało statusu, żeby
    nie zostawiać śladu „ktoś to wziął i oddał". Uzasadnienie było dobre i przestało wystarczać,
    gdy policzyłem skutek: worker bierze PIERWSZE zadanie z kolejki, więc zadanie odrzucone
    i pozostawione jako `queued` wraca przy następnym takcie — i przy następnym, i przy każdym.
    Przy takcie minutowym (design Bita, 17.09) to jest ten sam wpis o odrzuceniu co minutę,
    w nieskończoność, na tej samej sprawie.

    Nowy kontrakt: odrzucone zadanie ląduje na **`on_hold`**. To jedyny status w enumie SF
    (`queued`, `in_progress`, `on_hold`, `completed` — sprawdzone w modelu, `rejected` NIE MA),
    który mówi prawdę: czeka na człowieka. `completed` byłoby kłamstwem i zawyżałoby domknięcia.
    """

    def test_puste_zadanie_nie_jest_przyjmowane(self):
        klient = AtrapaKlienta()
        wynik = obsluz_zadanie(klient, konfiguracja(), zadanie(body_md=""))

        self.assertIn("odrzucone", wynik)
        self.assertNotIn("in_progress", [s for _, s in klient.statusy],
                         "zadania bez treści NIE przyjmujemy — odkładamy je nietknięte")
        self.assertEqual([s for _, s in klient.statusy], ["on_hold"],
                         "odrzucone zadanie ma czekać na człowieka, a nie wracać w pętli")
        self.assertEqual(len(klient.wpisy), 1, "odrzucenie ma zostawić wpis, nie ciszę")
        self.assertIn("nie mam czego wykonać", klient.wpisy[0][1])

    def test_brak_katalogu_roboczego_odrzuca_zamiast_zgadywac(self):
        klient = AtrapaKlienta()
        wynik = obsluz_zadanie(klient, konfiguracja(katalog_roboczy=""), zadanie())

        self.assertIn("odrzucone", wynik)
        self.assertEqual([s for _, s in klient.statusy], ["on_hold"])
        self.assertIn("Nie zgaduję", klient.wpisy[0][1])

    def test_nieistniejacy_katalog_tez_odrzuca(self):
        klient = AtrapaKlienta()
        wynik = obsluz_zadanie(
            klient, konfiguracja(katalog_roboczy="/nie/ma/takiego/katalogu"), zadanie())
        self.assertIn("odrzucone", wynik)
        self.assertEqual([s for _, s in klient.statusy], ["on_hold"])

    def test_odrzucone_zadanie_NIE_wraca_do_kolejki(self):
        """Sedno zmiany z 850: `queued` znaczyłoby „weź mnie znowu za minutę"."""
        klient = AtrapaKlienta()
        obsluz_zadanie(klient, konfiguracja(), zadanie(body_md=""))

        self.assertNotIn("queued", [s for _, s in klient.statusy],
                         "zadanie odrzucone wróciło do kolejki — worker weźmie je przy "
                         "następnym takcie i dopisze ten sam wpis")


class TestSciezkaUdana(unittest.TestCase):

    def test_kolejnosc_przyjmij_wpis_zamknij(self):
        klient = AtrapaKlienta()
        wynik = obsluz_zadanie(klient, konfiguracja(), zadanie())

        self.assertEqual(wynik, "zrobione")
        self.assertEqual([s for _, s in klient.statusy], ["in_progress", "completed"])
        self.assertEqual(len(klient.wpisy), 1)
        self.assertIn("zrobione", klient.wpisy[0][1], "wyjście wykonawcy ma wejść do wpisu")

    def test_wpis_idzie_na_sprawe_a_nie_na_zadanie(self):
        klient = AtrapaKlienta()
        obsluz_zadanie(klient, konfiguracja(), zadanie())
        self.assertEqual(klient.wpisy[0][0], "22222222-2222-2222-2222-222222222222")


class TestNiepowodzenia(unittest.TestCase):
    """Najważniejsza grupa: kiedy NIE wolno zamknąć zadania."""

    def test_nieudane_wykonanie_wraca_do_kolejki(self):
        klient = AtrapaKlienta()
        wynik = obsluz_zadanie(klient, konfiguracja(), zadanie(body_md="exit 7"))

        self.assertIn("niepowodzenie", wynik)
        self.assertEqual([s for _, s in klient.statusy], ["in_progress", "queued"],
                         "zadanie, które się nie udało, ma WRÓCIĆ do kolejki")
        self.assertNotIn("completed", [s for _, s in klient.statusy])
        self.assertIn("utknąłem", klient.wpisy[0][1])

    def test_trzy_bledy_maja_backoff_i_koncza_statusem_failed(self):
        with tempfile.TemporaryDirectory() as katalog:
            stan = StanProb(Path(katalog) / "state.json")
            chwila = datetime(2026, 9, 17, 10, tzinfo=timezone.utc)
            klient = AtrapaKlienta()
            z = zadanie(body_md="exit 1")

            obsluz_zadanie(klient, konfiguracja(), z, stan_prob=stan, teraz=chwila)
            self.assertFalse(stan.gotowe(z, teraz=chwila + timedelta(minutes=9)))
            self.assertTrue(stan.gotowe(z, teraz=chwila + timedelta(minutes=10)))

            obsluz_zadanie(klient, konfiguracja(), z, stan_prob=stan,
                           teraz=chwila + timedelta(minutes=10))
            self.assertFalse(stan.gotowe(z, teraz=chwila + timedelta(minutes=69)))
            self.assertTrue(stan.gotowe(z, teraz=chwila + timedelta(minutes=70)))

            obsluz_zadanie(klient, konfiguracja(), z, stan_prob=stan,
                           teraz=chwila + timedelta(minutes=70))
            self.assertEqual([s for _, s in klient.statusy].count("in_progress"), 3)
            self.assertEqual(klient.statusy[-1][1], "failed")
            self.assertIn("3 nieudane próby:", klient.wpisy[-1][1])

    def test_praca_bez_sprawozdania_NIE_zamyka_zadania(self):
        """Sedno zasady „sprawozdanie przed zamknięciem".

        Praca się udała, ale wpis nie przeszedł. Zamknięcie zadania zostawiłoby je oznaczone
        jako zrobione, bez śladu CO zrobiono — czyli dokładnie to, przed czym ten kanał broni.
        """
        klient = AtrapaKlienta(wpis_pada=True)
        wynik = obsluz_zadanie(klient, konfiguracja(), zadanie())

        self.assertIn("bez sprawozdania", wynik)
        self.assertEqual([s for _, s in klient.statusy], ["in_progress", "queued"])

    def test_zadanie_bez_sprawy_idzie_do_komentarza_i_JEST_zamykane(self):
        """POLITYKA ZMIENIONA W v0.4 — świadomie, decyzją Damiana z 15.09.

        Do v0.3 worker odmawiał: „nie ma sprawy = nie ma gdzie zdać sprawozdania = nie
        zamykamy". Problem w tym, że odmowa przychodziła PO wykonaniu pracy — więc praca
        przepadała, a zadanie wracało do kolejki, żeby wykonać ją jeszcze raz i znowu stracić.

        Damian: „twarda przy zakładaniu, miękka przy wykonaniu". Twardość ma być w API (422
        przy zakładaniu zadania bez sprawy — osobne zgłoszenie pod 796), a nie w workerze nad
        gotowym wynikiem. Wynik ląduje więc w komentarzu zadania, z jawnym zdaniem, że NIE MA
        GO NA ŻADNEJ OSI — bo cisza o tym byłaby gorsza niż brak wyniku.
        """
        klient = AtrapaKlienta()
        wynik = obsluz_zadanie(klient, konfiguracja(), zadanie(ticket_id=None))

        self.assertEqual(len(klient.komentarze), 1)
        self.assertIn("nie trafił na żadną oś", klient.komentarze[0][1])
        self.assertIn("completed", [s for _, s in klient.statusy])
        self.assertEqual(wynik, "zrobione")
        self.assertEqual(klient.wpisy, [], "wpis na sprawie, której nie ma")

    def test_gdy_nawet_komentarz_nie_przejdzie_zadanie_wraca_do_kolejki(self):
        """Ostatnia deska ratunku też może się złamać — wtedy NIE zamykamy.

        Zadanie zamknięte bez śladu gdziekolwiek wygląda jak zrobione i nikt nie wie, co
        z niego wyszło. Lepiej, żeby wróciło do kolejki.
        """
        klient = AtrapaKlienta(komentarz_pada=True)
        wynik = obsluz_zadanie(klient, konfiguracja(), zadanie(ticket_id=None))

        self.assertNotIn("completed", [s for _, s in klient.statusy])
        self.assertIn("bez sprawozdania", wynik)

    def test_brak_uprawnienia_zatrzymuje_workera_zamiast_kręcic_petla(self):
        """403 przy przyjęciu = worker staje i mówi, czego brakuje.

        Kręcenie się w pętli przy braku uprawnienia dałoby log pełen tego samego błędu
        i zadanie wykonywane w kółko bez szansy na zamknięcie.
        """
        klient = AtrapaKlienta(brak_uprawnienia=True)
        with self.assertRaises(SystemExit) as pulapka:
            obsluz_zadanie(klient, konfiguracja(), zadanie())
        self.assertIn("plans:write", str(pulapka.exception))

    def test_nieudane_zamkniecie_nie_udaje_sukcesu(self):
        klient = AtrapaKlienta(status_pada_na="completed")
        wynik = obsluz_zadanie(klient, konfiguracja(), zadanie())
        self.assertEqual(wynik, "wykonane, niezamknięte")
        self.assertEqual(len(klient.wpisy), 1, "sprawozdanie ma zostać, mimo że status nie wszedł")


class TestTresc(unittest.TestCase):

    def test_dlugie_wyjscie_jest_obcinane_z_adnotacja(self):
        klient = AtrapaKlienta()
        obsluz_zadanie(klient, konfiguracja(),
                       zadanie(body_md="python3 -c \"print('x'*9000)\""))
        tresc = klient.wpisy[0][1]
        self.assertIn("obcięte", tresc, "wpis ma być do czytania, nie zrzutem konsoli")
        self.assertLess(len(tresc), 6000)


if __name__ == "__main__":
    unittest.main()


class TestDrogaWynikuDoSprawy(unittest.TestCase):
    """CAŁA droga pliku wynikowego: model zapisuje do `outgoing/` → plik jest na sprawie.

    ADVERTPR-850. Każdy kawałek tej drogi miał test osobno (`wyniki.zbierz` zna `outgoing/`,
    `_zdaj_sprawozdanie` umie wysłać pliki), a droga jako całość — nie. I to właśnie w niej
    siedziała usterka: mechanizm działał, tylko model nie wiedział, gdzie odkładać pliki,
    więc `outgoing/` bywał pusty i nikt tego nie zauważał, bo każdy test z osobna świecił.

    Dowód z produkcji: wpis Kimi na ADVERTPR-846 — raport „zapisany jako audyt-fm-dev-r14.md",
    a wpis ma **zero załączników**.
    """

    def test_plik_z_outgoing_trafia_na_sprawe_jako_zalacznik(self):
        import tempfile

        with tempfile.TemporaryDirectory() as katalog:
            (Path(katalog) / "outgoing").mkdir()

            # Plik musi powstać W TRAKCIE zadania, nie przed nim — `wyniki.zbierz` bierze
            # wyłącznie pliki nowsze niż start. To nie jest kaprys testu: `outgoing/` bywa
            # pełen wyników poprzedniego zadania i bez tego warunku plik jednego klienta
            # trafiłby do sprawy drugiego. Wykonawca `shell` pozwala to odtworzyć wiernie.
            klient = AtrapaKlienta()
            wynik = obsluz_zadanie(
                klient, konfiguracja(katalog_roboczy=katalog),
                zadanie(body_md="printf '# Wynik\\n' > outgoing/raport.md; echo gotowe"))

            self.assertEqual(wynik, "zrobione", wynik)
            self.assertTrue(klient.wpisy_z_plikami,
                            "sprawozdanie poszło BEZ plików — plik z `outgoing/` przepadł")
            _, _, pliki = klient.wpisy_z_plikami[0]
            self.assertEqual([Path(p).name for p in pliki], ["raport.md"])

    def test_pusty_outgoing_nie_udaje_zalacznika(self):
        """Brak pliku to brak załącznika — a nie pusty załącznik albo awaria zadania."""
        import tempfile

        with tempfile.TemporaryDirectory() as katalog:
            (Path(katalog) / "outgoing").mkdir()
            klient = AtrapaKlienta()

            wynik = obsluz_zadanie(klient, konfiguracja(katalog_roboczy=katalog), zadanie())

            self.assertEqual(wynik, "zrobione")
            self.assertTrue(klient.wpisy or klient.wpisy_z_plikami,
                            "zadanie bez plików ma nadal zdać sprawozdanie")


class TestNieoddanegoWyniku(unittest.TestCase):
    """ADVERTPR-777: zadanie, które obiecało produkt i go nie oddało, NIE jest zrobione.

    Damian, 18.09: jedno zadanie zamknęło się jako zrobione z zerowym produktem. Bramka jest
    wąska celowo — patrzy na NIEDOTRZYMANE WSKAZANIE (`WYNIK: plik`), nie na „czy powstały
    jakieś pliki": zadanie „sprawdź i opisz" słusznie nie produkuje żadnych.
    """

    def test_obiecany_plik_ktorego_nie_ma_konczy_sie_statusem_failed(self):
        klient = AtrapaKlienta()
        obsluz_zadanie(klient, konfiguracja(),
                       zadanie(body_md="echo 'niby zrobione'\nexit 0\nWYNIK: raport-ktorego-nie-ma.pdf"))

        statusy = [s for _, s in klient.statusy]
        self.assertIn("failed", statusy, "zadanie bez obiecanego wyniku ma być nieudane")
        self.assertNotIn("completed", statusy, "to nie jest zadanie zrobione")

    def test_sprawozdanie_mowi_CZEGO_brakuje(self):
        """Werdykt bez nazwy brakującego pliku zmusza człowieka do zgadywania."""
        klient = AtrapaKlienta()
        obsluz_zadanie(klient, konfiguracja(),
                       zadanie(body_md="echo x\nexit 0\nWYNIK: raport-ktorego-nie-ma.pdf"))

        tresci = " ".join(t for _, t in klient.wpisy)
        self.assertIn("raport-ktorego-nie-ma.pdf", tresci)
        self.assertIn("nie oddało obiecanego wyniku", tresci)

    def test_zadanie_BEZ_obietnicy_dalej_zamyka_sie_normalnie(self):
        """Gdyby bramka patrzyła na `pliki`, każde zadanie opisowe byłoby nieudane."""
        klient = AtrapaKlienta()
        obsluz_zadanie(klient, konfiguracja(), zadanie(body_md="echo 'przegląd zrobiony'"))

        statusy = [s for _, s in klient.statusy]
        self.assertIn("completed", statusy)
        self.assertNotIn("failed", statusy)

    def test_gdy_SF_nie_zna_failed_zadanie_wraca_do_kolejki_a_NIE_zamyka_sie(self):
        """Instalacja sprzed 777 nie przyjmie `failed`. Wtedy kolejka — gorzej, ale bez kłamstwa."""
        klient = AtrapaKlienta(status_pada_na="failed")
        obsluz_zadanie(klient, konfiguracja(),
                       zadanie(body_md="echo x\nexit 0\nWYNIK: brak.pdf"))

        statusy = [s for _, s in klient.statusy]
        self.assertNotIn("completed", statusy)
        self.assertEqual(statusy[-1], "queued")
