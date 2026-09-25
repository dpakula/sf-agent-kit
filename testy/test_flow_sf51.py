"""`odpowiedz`, `nowa-sprawa` (kontekst), `tresc-wersja`, `opis-sprawy`, `publikuj` (SF-51).

v0.1 (25.09.2026) - APro Agents / kimi-autor-dpakula

CZEGO TU PILNUJEMY
1. **Zapis wymaga jawnej Organizacji** — `--org` albo `?org=` z linku. Bez tego odmowa,
   która mówi, CO podać (pkt 1 kontraktu SF-51).
2. **`odpowiedz` odpowiada w istniejącej sprawie** — domyślnie na zewnątrz, `--wewn` wewnątrz;
   Organizację bierze z linku (pkt 2).
3. **`nowa-sprawa` przy linku do istniejącej sprawy w kontekście odmawia** z podpowiedzią
   „odpowiedz w sprawie X" — to jest zapora na wypadek z 25.09 (pkt 3).
4. **`tresc-wersja` numeruje wersje po załącznikach** (`nazwa-vN.md`, najwyższy N + 1),
   a strażnik zatrzymuje `PATCH` opisu dłuższego niż 1500 znaków na sprawie z opisem (pkt 4).
5. **`publikuj` wysyła zgodę** jako identyfikator wpisu — pełny albo początek ≥ 6 znaków (pkt 5).
6. **Zapis na szkicu ostrzega** w brzmieniu z kontraktu (pkt 6).

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import autor, cli, flow, tozsamosc, wpisy  # noqa: E402
from sf_kit import config as konfiguracja  # noqa: E402
from sf_kit.api import BladAPI, BrakUprawnienia, Klient  # noqa: E402

A = "aaaaaaaa-0000-4000-8000-000000000001"
B = "aaaaaaab-0000-4000-8000-000000000002"
TICKET = "f372127f-8d12-4fbb-81ba-7297a9dba875"
LINK = f"https://sf.dpakula.pl/tickets/{TICKET}?org=advertpro-co"
ORG = tozsamosc.Organizacja(uuid="289cef06-b8b9-4a0c-967f-2533b08e82c4",
                            slug="advertpro-co", nazwa="ADVERTpro.co",
                            uprawnienia=["tickets:comment", "tickets:read"])


class _KlientZapisu:
    """Atrapa klienta dla poleceń zapisu SF-51 — zapisuje, co poszłoby do SF."""

    def __init__(self, *, karta=None, blad=None):
        self.karta = karta or {"id": TICKET, "status": "new", "description": "opis",
                               "entries": []}
        self.blad = blad
        self.wpisy = []           # (ticket_id, tresc, widocznosc)
        self.paczki = []          # (ticket_id, tresc, pliki)
        self.publikacje = []      # (ticket_id, zgoda)
        self.opisy = []           # (ticket_id, opis)
        self.zalozone = []        # ciała zaloz_sprawe
        self.pobrania = {}        # attachment_id → zawartość (bytes)
        self.odpytania_dziennika = 0   # ile razy pytano o wpisy sprawy (rozwijanie skrótu)

    def wpis(self, ticket_id, tresc, *, widocznosc="internal"):
        if self.blad:
            raise self.blad
        self.wpisy.append((ticket_id, tresc, widocznosc))

    def wpis_z_plikami(self, ticket_id, tresc, pliki, *, widocznosc="internal"):
        if self.blad:
            raise self.blad
        self.paczki.append((ticket_id, tresc, [str(p) for p in pliki]))

    def sprawa(self, ticket_id):
        return self.karta

    def sprawy(self, *, limit=50, szukaj=None):
        return [{"id": TICKET, "ticket_number": 948, "ticket_prefix": "ADVERTPR"}]

    def wpisy_sprawy(self, ticket_id, *, limit=100, offset=0):
        self.odpytania_dziennika += 1
        return {"pozycje": [{"id": A}, {"id": B}]} if offset == 0 else []

    def publikuj(self, ticket_id, *, zgoda):
        if self.blad:
            raise self.blad
        self.publikacje.append((ticket_id, zgoda))

    def zmien_opis_sprawy(self, ticket_id, opis):
        if self.blad:
            raise self.blad
        self.opisy.append((ticket_id, opis))

    def zaloz_sprawe(self, **kwargs):
        if self.blad:
            raise self.blad
        self.zalozone.append(kwargs)
        return {"ticket_id": TICKET, "ticket_prefix": "ADVERTPR", "ticket_number": 948}

    def pobierz_zalacznik(self, attachment_id, cel, *, limit_bajtow):
        if attachment_id not in self.pobrania:
            raise BladAPI(f"brak załącznika {attachment_id} w atrapy")
        cel = Path(cel)
        cel.write_bytes(self.pobrania[attachment_id])
        return len(self.pobrania[attachment_id])


class TestLinki(unittest.TestCase):

    def test_sprawa_i_organizacja_z_linku(self):
        self.assertEqual(flow.sprawa_z_linku(LINK), TICKET)
        self.assertEqual(flow.organizacja_z_linku(LINK), "advertpro-co")

    def test_link_bez_org_i_nielink(self):
        self.assertIsNone(flow.organizacja_z_linku(
            f"https://sf.dpakula.pl/tickets/{TICKET}"))
        self.assertIsNone(flow.sprawa_z_linku("ADVERTPR-948"))

    def test_link_w_dluzszym_kontekscie(self):
        tekst = (f"Sprawa klienta: proszę o odpowiedź. Zgłoszenie: {LINK} — "
                 "pilne, termin jutro.")
        self.assertEqual(flow.link_z_tekstu(tekst), LINK)
        self.assertEqual(flow.sprawa_z_linku(tekst), TICKET)


class TestWybierzDlaZapisu(unittest.TestCase):

    def _tozsamosc(self):
        return tozsamosc.Tozsamosc(
            konto_nazwa="k", konto_kind="agent", klucz_prefiks="sk", klucz_scope="user",
            klucz_zawezony=False,
            organizacje=[ORG,
                         tozsamosc.Organizacja(uuid="u2", slug="sf", nazwa="SF",
                                               uprawnienia=[])])

    def test_org_jawnie_wskazana(self):
        self.assertIs(tozsamosc.wybierz_dla_zapisu(self._tozsamosc(),
                                                   wskazana="advertpro-co"), ORG)

    def test_org_z_linku(self):
        self.assertIs(tozsamosc.wybierz_dla_zapisu(self._tozsamosc(),
                                                   z_linku="advertpro-co"), ORG)

    def test_brak_wskazania_to_odmowa_z_instrukcja(self):
        with self.assertRaises(tozsamosc.BrakWyboru) as blad:
            tozsamosc.wybierz_dla_zapisu(self._tozsamosc())
        komunikat = str(blad.exception)
        self.assertIn("--org", komunikat)
        self.assertIn("?org=", komunikat)

    def test_org_z_linku_spoza_listy_to_odmowa(self):
        with self.assertRaises(tozsamosc.BrakWyboru) as blad:
            tozsamosc.wybierz_dla_zapisu(self._tozsamosc(), z_linku="inna-org")
        self.assertIn("inna-org", str(blad.exception))

    def test_org_bez_nadan_to_odmowa_nawet_jawnie(self):
        with self.assertRaises(tozsamosc.BrakWyboru):
            tozsamosc.wybierz_dla_zapisu(self._tozsamosc(), wskazana="sf")


class TestPoleceniaZapisu(unittest.TestCase):
    """Polecenia SF-51 z podstawionym klientem zapisu — żadnej sieci."""

    def setUp(self):
        self._stare = (konfiguracja.wczytaj, cli._klient_dla_zapisu)
        konfiguracja.wczytaj = lambda: konfiguracja.Konfiguracja(adres="https://x")
        self.chwytacz = {}

    def tearDown(self):
        konfiguracja.wczytaj, cli._klient_dla_zapisu = self._stare
        os.environ.pop("SF_KIT_KONTEKST", None)

    def _uruchom(self, argv, klient):
        def _klient_dla_zapisu(konf, args, org_z_linku=""):
            self.chwytacz["org_z_linku"] = org_z_linku
            return klient, ORG

        cli._klient_dla_zapisu = _klient_dla_zapisu
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            kod = cli.main(argv)
        return kod, out.getvalue(), err.getvalue()

    def _plik(self, tresc):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
        tmp.write(tresc)
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        return tmp.name

    def test_odpowiedz_domyslnie_na_zewnatrz(self):
        k = _KlientZapisu()
        plik = self._plik("Dzień dobry, sprawdziliśmy zgłoszenie.")
        kod, out, _ = self._uruchom(["odpowiedz", LINK, "--opis", plik], k)
        self.assertEqual(kod, 0)
        self.assertEqual(k.wpisy, [(TICKET, "Dzień dobry, sprawdziliśmy zgłoszenie.",
                                    "external")])
        self.assertEqual(self.chwytacz["org_z_linku"], "advertpro-co")

    def test_odpowiedz_wewn_to_notatka_wewnetrzna(self):
        k = _KlientZapisu()
        plik = self._plik("tylko dla zespołu")
        kod, _, _ = self._uruchom(["odpowiedz", LINK, "--opis", plik, "--wewn"], k)
        self.assertEqual(kod, 0)
        self.assertEqual(k.wpisy[0][2], "internal")

    def test_odpowiedz_przy_numerze_wymaga_org_z_linku_lub_flagi(self):
        k = _KlientZapisu()
        plik = self._plik("x")
        kod, _, _ = self._uruchom(["odpowiedz", "ADVERTPR-948", "--opis", plik], k)
        self.assertEqual(kod, 0)
        self.assertEqual(self.chwytacz["org_z_linku"], "")
        self.assertEqual(k.wpisy[0][0], TICKET)

    def test_zapis_na_szkicu_ostrzega_przed_zapisem(self):
        k = _KlientZapisu(karta={"id": TICKET, "status": "draft", "entries": []})
        plik = self._plik("kolejny krok")
        kod, _, err = self._uruchom(["odpowiedz", LINK, "--opis", plik], k)
        self.assertEqual(kod, 0)
        self.assertIn("szkic nie wychodzi do obiegu", err)
        self.assertIn("tylko po linku", err)

    def test_zapis_na_nie_szkicu_bez_ostrzezenia(self):
        k = _KlientZapisu(karta={"id": TICKET, "status": "new", "entries": []})
        plik = self._plik("kolejny krok")
        _, _, err = self._uruchom(["odpowiedz", LINK, "--opis", plik], k)
        self.assertNotIn("SZKIC", err)

    def test_wpis_przyjmuje_link(self):
        k = _KlientZapisu()
        plik = self._plik("postęp")
        kod, _, _ = self._uruchom(["wpis", LINK, "--opis", plik], k)
        self.assertEqual(kod, 0)
        self.assertEqual(self.chwytacz["org_z_linku"], "advertpro-co")
        self.assertEqual(k.wpisy[0][2], "internal", "`wpis` zostaje wewnętrzny jak dotąd")

    def test_nowa_sprawa_z_kontekstem_z_linkiem_odmawia(self):
        k = _KlientZapisu()
        kontekst = f"prowadź tę rozmowę: {LINK}"
        kod, _, err = self._uruchom(
            ["nowa-sprawa", "--tytul", "X", "--kontekst", kontekst], k)
        self.assertEqual(kod, 2)
        self.assertIn("ODPOWIEDZ", err)
        self.assertIn(LINK, err)
        self.assertEqual(k.zalozone, [], "żadnego zapisu przy odmowie")

    def test_nowa_sprawa_z_kontekstem_bez_linku_zaklada(self):
        k = _KlientZapisu()
        kod, _, _ = self._uruchom(
            ["nowa-sprawa", "--tytul", "X", "--kontekst", "same ustalenia, bez linku"], k)
        self.assertEqual(kod, 0)
        self.assertEqual(len(k.zalozone), 1)

    def test_nowa_sprawa_czyta_kontekst_ze_zmiennej(self):
        k = _KlientZapisu()
        os.environ["SF_KIT_KONTEKST"] = f"treść zadania ze sprawą {LINK}"
        kod, _, err = self._uruchom(["nowa-sprawa", "--tytul", "X"], k)
        self.assertEqual(kod, 2)
        self.assertIn("ODPOWIEDZ", err)
        self.assertEqual(k.zalozone, [])

    def test_zglos_zostaje_i_przechodzi_przez_straznika(self):
        k = _KlientZapisu()
        kod, _, err = self._uruchom(
            ["zglos", "--tytul", "X", "--kontekst", f"prowadź: {LINK}"], k)
        self.assertEqual(kod, 2)
        self.assertIn("ODPOWIEDZ", err)


class TestTrescWersja(unittest.TestCase):

    def setUp(self):
        self._stare = (konfiguracja.wczytaj, cli._klient_dla_zapisu)
        konfiguracja.wczytaj = lambda: konfiguracja.Konfiguracja(adres="https://x")
        self.k = None

        def _klient_dla_zapisu(konf, args, org_z_linku=""):
            return self.k, ORG

        cli._klient_dla_zapisu = _klient_dla_zapisu
        self.addCleanup(self._przywroc)

    def _przywroc(self):
        konfiguracja.wczytaj, cli._klient_dla_zapisu = self._stare

    def _uruchom(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            kod = cli.main(argv)
        return kod, out.getvalue(), err.getvalue()

    def _karta_z(self, nazwy):
        return {"id": TICKET, "status": "new", "description": "",
                "entries": [{"attachments": [
                    {"id": f"z{i}", "original_filename": n, "filename": n}
                    for i, n in enumerate(nazwy)]}]}

    def test_numeracja_od_najwyzszej_istniejacej(self):
        self.k = _KlientZapisu(karta=self._karta_z(["raport-v1.md", "raport-v2.md"]))
        with tempfile.TemporaryDirectory() as kat:
            plik = Path(kat) / "raport.md"
            plik.write_text("nowa treść", encoding="utf-8")
            kod, out, _ = self._uruchom(["tresc-wersja", LINK, str(plik)])
        self.assertEqual(kod, 0)
        _, wpis, pliki = self.k.paczki[0]
        self.assertTrue(pliki[0].endswith("raport-v3.md"), pliki)
        self.assertIn("Wersja v3", wpis)
        self.assertIn("Co się zmieniło", wpis)

    def test_pierwsza_wersja_bez_historii(self):
        self.k = _KlientZapisu(karta=self._karta_z([]))
        tmp = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
        tmp.write("pierwsza")
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        kod, _, _ = self._uruchom(["tresc-wersja", LINK, tmp.name])
        self.assertEqual(kod, 0)
        _, wpis, pliki = self.k.paczki[0]
        self.assertTrue(pliki[0].endswith("-v1.md"))
        self.assertIn("pierwsza wersja", wpis)

    def test_zmiany_z_pliku_trafiaja_do_wpisu(self):
        self.k = _KlientZapisu(karta=self._karta_z([]))
        with tempfile.TemporaryDirectory() as kat:
            plik = Path(kat) / "raport.md"
            plik.write_text("treść", encoding="utf-8")
            zmiany = Path(kat) / "zmiany.md"
            zmiany.write_text("poprawiono tabelę cen", encoding="utf-8")
            kod, _, _ = self._uruchom(["tresc-wersja", LINK, str(plik),
                                       "--zmiany", str(zmiany)])
        self.assertEqual(kod, 0)
        self.assertIn("poprawiono tabelę cen", self.k.paczki[0][1])

    def test_auto_diff_gdy_brak_zmian(self):
        self.k = _KlientZapisu(karta=self._karta_z(["raport-v1.md"]))
        self.k.pobrania["z0"] = "stara\nlinia\n".encode()
        with tempfile.TemporaryDirectory() as kat:
            plik = Path(kat) / "raport.md"
            plik.write_text("nowa\nlinia\ndodatkowa\n", encoding="utf-8")
            kod, _, _ = self._uruchom(["tresc-wersja", LINK, str(plik)])
        self.assertEqual(kod, 0)
        self.assertIn("+2/−1 wierszy", self.k.paczki[0][1])


class TestStraznikOpisu(unittest.TestCase):

    def test_reguly_straznika(self):
        dlugi = "x" * 1501
        self.assertIsNone(flow.straznik_opisu("", dlugi, limit=1500),
                          "pusta sprawa może dostać długi opis")
        self.assertIsNone(flow.straznik_opisu("stary opis", "x" * 1500, limit=1500))
        komunikat = flow.straznik_opisu("stary opis", dlugi, limit=1500)
        self.assertIsNotNone(komunikat)
        self.assertIn("1500", komunikat)
        self.assertIn("tresc-wersja", komunikat)

    def test_limit_z_configu(self):
        """Próg ustawia użytkownik w config.json — strażnik dostaje go z zewnątrz,
        a nie z twardej stałej w kodzie."""
        dlugi = "x" * 501
        self.assertIsNone(flow.straznik_opisu("stary opis", dlugi, limit=1500))
        komunikat = flow.straznik_opisu("stary opis", dlugi, limit=500)
        self.assertIsNotNone(komunikat)
        self.assertIn("500", komunikat)


class TestOpisSprawy(unittest.TestCase):

    def setUp(self):
        self._stare = (konfiguracja.wczytaj, cli._klient_dla_zapisu)
        konfiguracja.wczytaj = lambda: konfiguracja.Konfiguracja(adres="https://x")
        self.k = _KlientZapisu(karta={"id": TICKET, "status": "new",
                                      "description": "już jest opis", "entries": []})
        cli._klient_dla_zapisu = lambda konf, args, org_z_linku="": (self.k, ORG)
        self.addCleanup(self._przywroc)

    def _przywroc(self):
        konfiguracja.wczytaj, cli._klient_dla_zapisu = self._stare

    def _uruchom(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            kod = cli.main(argv)
        return kod, out.getvalue(), err.getvalue()

    def test_dlugi_opis_na_sprawe_z_opisem_zatrzymuje(self):
        with tempfile.TemporaryDirectory() as kat:
            plik = Path(kat) / "opis.md"
            plik.write_text("x" * 1501, encoding="utf-8")
            kod, _, err = self._uruchom(["opis-sprawy", LINK, "--plik", str(plik)])
        self.assertEqual(kod, 2)
        self.assertIn("tresc-wersja", err)
        self.assertEqual(self.k.opisy, [], "strażnik blokuje przed PATCH-em")

    def test_mimo_to_nadpisuje(self):
        with tempfile.TemporaryDirectory() as kat:
            plik = Path(kat) / "opis.md"
            plik.write_text("x" * 1501, encoding="utf-8")
            kod, _, _ = self._uruchom(["opis-sprawy", LINK, "--plik", str(plik),
                                       "--mimo-to"])
        self.assertEqual(kod, 0)
        self.assertEqual(self.k.opisy, [(TICKET, "x" * 1501)])

    def test_krotki_opis_przechodzi(self):
        with tempfile.TemporaryDirectory() as kat:
            plik = Path(kat) / "opis.md"
            plik.write_text("krótko", encoding="utf-8")
            kod, _, _ = self._uruchom(["opis-sprawy", LINK, "--plik", str(plik)])
        self.assertEqual(kod, 0)
        self.assertEqual(len(self.k.opisy), 1)


class TestPublikuj(unittest.TestCase):

    def setUp(self):
        self._stare = (konfiguracja.wczytaj, cli._klient_dla_zapisu)
        konfiguracja.wczytaj = lambda: konfiguracja.Konfiguracja(adres="https://x")
        self.k = _KlientZapisu()
        cli._klient_dla_zapisu = lambda konf, args, org_z_linku="": (self.k, ORG)
        self.addCleanup(self._przywroc)

    def _przywroc(self):
        konfiguracja.wczytaj, cli._klient_dla_zapisu = self._stare

    def _uruchom(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            kod = cli.main(argv)
        return kod, out.getvalue(), err.getvalue()

    def test_publikuj_wysyla_zgode_jako_wpis(self):
        kod, out, _ = self._uruchom(["publikuj", LINK, "--zgoda", "aaaaaaaa"])
        self.assertEqual(kod, 0)
        self.assertEqual(self.k.publikacje, [(TICKET, A)], "skrót rozwinięty do pełnego id")
        self.assertGreater(self.k.odpytania_dziennika, 0, "skrót rozwijamy po dzienniku")

    def test_publikuj_pelny_uuid_bez_rozwijania(self):
        """Zgoda z innej sprawy: pełny identyfikator przechodzi bez odpytania dziennika —
        Organizację, autora i wiek zgody sprawdza serwer, nie Kit."""
        kod, _, _ = self._uruchom(["publikuj", LINK, "--zgoda", B])
        self.assertEqual(kod, 0)
        self.assertEqual(self.k.publikacje, [(TICKET, B)], "pełny UUID przechodzi bez zmian")
        self.assertEqual(self.k.odpytania_dziennika, 0,
                         "pełnego UUID nie rozwijamy po publikowanej sprawie")

    def test_publikuj_pokazuje_powod_serwera(self):
        blad = BrakUprawnienia("nie wolno (403)", kod=403,
                               szczegoly='{"detail":"Publikacja wymaga zgody na sprawie"}')
        self.k = _KlientZapisu(blad=blad)
        kod, _, err = self._uruchom(["publikuj", LINK, "--zgoda", A])
        self.assertEqual(kod, 1)
        self.assertIn("Publikacja wymaga zgody", err)


class TestCzySzkic(unittest.TestCase):

    def test_rozpoznawanie_szkicu(self):
        self.assertTrue(flow.czy_szkic({"status": "draft"}))
        self.assertTrue(flow.czy_szkic({"status": " DRAFT "}))
        self.assertFalse(flow.czy_szkic({"status": "SZKIC"}), "tylko `draft` po stronie serwera")
        self.assertFalse(flow.czy_szkic({"status": "robocza"}))
        self.assertFalse(flow.czy_szkic({"status": "new", "szkic": True}),
                         "osobnej flagi nie ma i nie będzie (SF-4: szkic to status)")
        self.assertFalse(flow.czy_szkic({"status": "new", "is_draft": True}))
        self.assertFalse(flow.czy_szkic({"status": "new"}))
        self.assertFalse(flow.czy_szkic({}))


class TestApiPublikujAdres(unittest.TestCase):
    """Prawdziwy `Klient` z podmienionym `_wywolaj` — sprawdzamy ADRES i ciało żądania."""

    def test_post_publikuj_z_zgoda(self):
        k = Klient(baza="https://x", klucz="k", organizacja="o")
        k.zapisy = []

        def _wywolaj(metoda, sciezka, *, cialo=None, **_):
            k.zapisy.append((metoda, sciezka, cialo))
            return {}

        k._wywolaj = _wywolaj
        k.publikuj(TICKET, zgoda=A)
        # DOSŁOWNY kształt z kontraktu (wpis 8ee30c11 na ADVERTPR-948) — atrapa nie zna
        # modelu serwera, więc porównujemy z kontraktem, nie z tym, co Kit akurat wysyła.
        # Schemat serwera ma extra=forbid: zgoda jako sam napis dostałaby 422.
        self.assertEqual(k.zapisy, [("POST", f"tickets/{TICKET}/publikuj",
                                     {"zgoda": {"wpis_id": A}})])

    def test_patch_opisu_tylko_description(self):
        k = Klient(baza="https://x", klucz="k", organizacja="o")
        k.zapisy = []

        def _wywolaj(metoda, sciezka, *, cialo=None, **_):
            k.zapisy.append((metoda, sciezka, cialo))
            return {}

        k._wywolaj = _wywolaj
        k.zmien_opis_sprawy(TICKET, "nowy")
        self.assertEqual(k.zapisy, [("PATCH", f"tickets/{TICKET}",
                                     {"description": "nowy"})])


if __name__ == "__main__":
    unittest.main()
