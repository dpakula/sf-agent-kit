"""`sf-kit wpis-edytuj` / `wpis-wersje` i stronicowanie spraw (ADVERTPR-782).

v0.1 (24.09.2026) - APro Agents / borys-sf

CZEGO TU PILNUJEMY
1. **Ciało PATCH = pola `EntryPatch` z SF** (`content`, `reason`; `archived` nie wysyłamy).
   Pydantic po stronie SF po cichu gubi nieznane pola — literówka dałaby 200 i brak zmiany.
   Zbiór pól przepisany z `tickets/schemas.py` (master `5c377cfc`) i sprawdzony prawdziwym
   modelem (commit Kita opisuje jak).
2. **Historia mówi „zastąpiona … przez …"**, bo wiersz wersji to stan SPRZED zmiany, a jego
   autor to ten, kto go zastąpił. „v1 · Borys" czytałoby się jak „Borys napisał v1".
3. **Skrót wpisu prowadzi do JEDNEGO wpisu albo do odmowy** — poprawienie nie tego wpisu
   zostawia w cudzej historii ślad, którego nikt nie skasuje.
4. **`sprawy()` stronicuje przez `page`/`per_page`**, a numer zawęża `search`-em. Do 0.11 Kit
   wysyłał `limit`, który `/tickets` ignoruje — i sprawa starsza niż 25 ostatnich „nie istniała".

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import asystent, cli, wpisy  # noqa: E402
from sf_kit import config as konfiguracja  # noqa: E402
from sf_kit.api import BladAPI, BrakUprawnienia, Klient  # noqa: E402

#: `EntryPatch` w SF (backend/app/modules/tickets/schemas.py @ 5c377cfc).
POLA_ENTRY_PATCH = {"archived", "content", "reason"}

A = "aaaaaaaa-0000-4000-8000-000000000001"
B = "aaaaaaab-0000-4000-8000-000000000002"
C = "cccccccc-0000-4000-8000-000000000003"


class _Dziennik:
    """Atrapa `wpisy_sprawy` ze stronicowaniem po `offset`, jak `GET /tickets/{id}/entries`."""

    def __init__(self, ids, na_stronie=2):
        self.ids, self.na_stronie, self.wolania = list(ids), na_stronie, []

    def wpisy_sprawy(self, ticket_id, *, limit=100, offset=0):
        self.wolania.append(offset)
        # Sufit strony atrapy mniejszy niż prośba — jak serwer, który oddaje mniej niż limit.
        return {"pozycje": [{"id": i} for i in self.ids[offset:offset + limit]]}


class TestRozwinWpis(unittest.TestCase):

    def test_pelny_identyfikator_bez_pytania_SF(self):
        d = _Dziennik([])
        self.assertEqual(wpisy.rozwin_wpis(d, "s", A.upper()), A)
        self.assertEqual(d.wolania, [])

    def test_skrot_jednoznaczny(self):
        self.assertEqual(wpisy.rozwin_wpis(_Dziennik([A, C]), "s", "cccccc"), C)

    def test_skrot_niejednoznaczny_to_odmowa_z_kandydatami(self):
        with self.assertRaises(wpisy.ZlyWpis) as blad:
            wpisy.rozwin_wpis(_Dziennik([A, B]), "s", "aaaaaa")
        self.assertIn("2 wpisów", str(blad.exception))

    def test_za_krotki_skrot(self):
        with self.assertRaises(wpisy.ZlyWpis):
            wpisy.rozwin_wpis(_Dziennik([A]), "s", "aaaa")

    def test_brak_trafienia_mowi_tez_o_widocznosci(self):
        with self.assertRaises(wpisy.ZlyWpis) as blad:
            wpisy.rozwin_wpis(_Dziennik([A]), "s", "dddddd")
        self.assertIn("dostępu", str(blad.exception))

    def test_wpis_na_dalszej_stronie_jest_znaleziony(self):
        """Dziennik ma strony po 200; wpis spoza pierwszej nie może „nie istnieć"."""
        ids = [f"{i:08x}-0000-4000-8000-{i:012x}" for i in range(450)]
        d = _Dziennik(ids)
        self.assertEqual(wpisy.rozwin_wpis(d, "s", ids[430][:8]), ids[430])
        self.assertEqual(d.wolania, [0, 200, 400])


class TestCialoEdycji(unittest.TestCase):

    def test_tylko_pola_kontraktu(self):
        self.assertLessEqual(set(wpisy.cialo_edycji("x", "bo tak")), POLA_ENTRY_PATCH)
        self.assertEqual(wpisy.cialo_edycji("x", "bo tak"), {"content": "x", "reason": "bo tak"})

    def test_bez_powodu_nie_wysylamy_reason(self):
        self.assertEqual(wpisy.cialo_edycji("x", None), {"content": "x"})
        self.assertEqual(wpisy.cialo_edycji("x", "   "), {"content": "x"})

    def test_archiwum_nie_jest_ruszane(self):
        """`archived` pominięte = SF nie rusza archiwum (konwencja `EntryPatch`)."""
        self.assertNotIn("archived", wpisy.cialo_edycji("x", "y"))

    def test_pusta_tresc_odmowa_przed_wysylka(self):
        with self.assertRaises(wpisy.ZlyWpis):
            wpisy.cialo_edycji("  \n ", None)

    def test_limity_jak_w_SF(self):
        with self.assertRaises(wpisy.ZlyWpis):
            wpisy.cialo_edycji("x" * 20001, None)
        with self.assertRaises(wpisy.ZlyWpis):
            wpisy.cialo_edycji("x", "p" * 501)


class TestHistoria(unittest.TestCase):

    WPIS = {"id": A, "author_name": "api:kodeks", "created_at": "2026-09-20T10:00:00Z",
            "content": "trzecia", "edited_count": 2, "last_edited_at": "2026-09-24T09:00:00Z"}
    WERSJE = [
        {"version_no": 1, "content": "pierwsza", "author_name": "Agata",
         "created_at": "2026-09-22T08:00:00Z", "reason": None},
        {"version_no": 2, "content": "druga", "author_name": "Damian",
         "created_at": "2026-09-24T09:00:00Z", "reason": "literówka"},
    ]

    def test_autor_wersji_to_ten_kto_ja_ZASTAPIL(self):
        tekst = wpisy.historia_do_pokazania(self.WPIS, self.WERSJE)
        self.assertIn("v1 (pierwotna) — zastąpiona 2026-09-22 08:00 przez Agata", tekst)
        self.assertIn("v2 — zastąpiona 2026-09-24 09:00 przez Damian · powód: literówka", tekst)

    def test_od_najnowszej_i_z_biezaca_na_gorze(self):
        tekst = wpisy.historia_do_pokazania(self.WPIS, self.WERSJE)
        self.assertLess(tekst.index("TERAZ"), tekst.index("v2"))
        self.assertLess(tekst.index("v2"), tekst.index("v1"))
        self.assertIn("edytowano 2×", tekst)

    def test_nieedytowany(self):
        tekst = wpisy.historia_do_pokazania({**self.WPIS, "edited_count": 0}, [])
        self.assertIn("nie był edytowany", tekst)
        self.assertNotIn("POPRZEDNIE", tekst)


class _KlientAtrapa:
    def __init__(self, *, przed=None, po=None, blad=None, wersje=()):
        self.przed = przed or {"id": A, "content": "stara", "edited_count": 0}
        self.po, self.blad, self._wersje, self.wyslane = po, blad, list(wersje), None

    def sprawy(self, *, limit=50, szukaj=None):
        return [{"id": "sprawa-1", "ticket_number": 782, "ticket_prefix": "ADVERTPR"}]

    def wpisy_sprawy(self, ticket_id, *, limit=100, offset=0):
        return {"pozycje": [{"id": A}] if offset == 0 else []}

    def wpis_sprawy(self, ticket_id, entry_id):
        return self.przed

    def edytuj_wpis(self, ticket_id, entry_id, cialo):
        self.wyslane = cialo
        if self.blad:
            raise self.blad
        return self.po

    def wersje_wpisu(self, ticket_id, entry_id):
        return self._wersje


class TestPolecenia(unittest.TestCase):

    def setUp(self):
        self._stare = (konfiguracja.wczytaj, cli._klient)
        konfiguracja.wczytaj = lambda: konfiguracja.Konfiguracja(adres="https://x")

    def tearDown(self):
        konfiguracja.wczytaj, cli._klient = self._stare

    def _uruchom(self, argv, klient):
        cli._klient = lambda *_a, **_k: klient
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            kod = cli.main(argv)
        return kod, out.getvalue(), err.getvalue()

    def test_edycja_wysyla_tresc_i_powod_i_mowi_gdzie_historia(self):
        k = _KlientAtrapa(po={"id": A, "content": "nowa", "edited_count": 1})
        kod, out, _ = self._uruchom(["wpis-edytuj", "ADVERTPR-782", "aaaaaaaa",
                                     "--tresc", "nowa", "--powod", "literówka"], k)
        self.assertEqual(kod, 0)
        self.assertEqual(k.wyslane, {"content": "nowa", "reason": "literówka"})
        self.assertIn("edytowano 1×", out)
        self.assertIn("wpis-wersje ADVERTPR-782 aaaaaaaa", out)

    def test_ta_sama_tresc_nie_udaje_zmiany(self):
        k = _KlientAtrapa(po={"id": A, "content": "stara", "edited_count": 0})
        kod, out, _ = self._uruchom(["wpis-edytuj", "ADVERTPR-782", "aaaaaaaa",
                                     "--tresc", "stara"], k)
        self.assertEqual(kod, 0)
        self.assertIn("bez zmian", out)

    def test_403_pokazuje_powod_serwera_i_co_zrobic(self):
        blad = BrakUprawnienia("nie wolno ci (403)", kod=403,
                               szczegoly='{"detail":"Wpis może zmienić administrator '
                                         'Organizacji albo jego autor"}')
        kod, _, err = self._uruchom(["wpis-edytuj", "ADVERTPR-782", "aaaaaaaa",
                                     "--tresc", "x"], _KlientAtrapa(blad=blad))
        self.assertEqual(kod, 1)
        self.assertIn("może zmienić administrator", err)
        self.assertIn("Dopisz nowy", err)

    def test_pusta_tresc_kod_2_bez_siegania_do_SF(self):
        def _nie_wolno(*_a, **_k):
            raise AssertionError("sięgnięto do SF przy pustej treści")
        cli._klient = _nie_wolno
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            kod = cli.main(["wpis-edytuj", "ADVERTPR-782", "aaaaaaaa", "--tresc", "  "])
        self.assertEqual(kod, 2)

    def test_tresc_i_plik_naraz_to_blad_parsera(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["wpis-edytuj", "S-1", "aaaaaaaa", "--tresc", "x", "--plik", "y"])

    def test_wersje_wypisuja_historie(self):
        k = _KlientAtrapa(przed={"id": A, "content": "teraz", "edited_count": 1,
                                 "author_name": "api:x", "created_at": "2026-09-24T07:00:00Z"},
                          wersje=[{"version_no": 1, "content": "przedtem", "author_name": "Agata",
                                   "created_at": "2026-09-24T08:00:00Z"}])
        kod, out, _ = self._uruchom(["wpis-wersje", "ADVERTPR-782", "aaaaaaaa"], k)
        self.assertEqual(kod, 0)
        self.assertIn("zastąpiona 2026-09-24 08:00 przez Agata", out)


class TestStronicowanieSpraw(unittest.TestCase):
    """Prawdziwy `Klient.sprawy` z podmienionym `_wywolaj` — sprawdzamy ADRES, który wychodzi."""

    def _klient(self, strony):
        k = Klient(baza="https://x", klucz="k", organizacja="o")
        k.adresy = []

        def _wywolaj(metoda, sciezka, **_):
            k.adresy.append(sciezka)
            nr = int(parse_qs(urlparse(sciezka).query)["page"][0])
            return {"items": strony[nr - 1], "pages": len(strony)}
        k._wywolaj = _wywolaj
        return k

    def test_nie_wysyla_limit_tylko_page_i_per_page(self):
        k = self._klient([[{"id": 1}]])
        k.sprawy(limit=50)
        zapytanie = parse_qs(urlparse(k.adresy[0]).query)
        self.assertNotIn("limit", zapytanie, "`/tickets` ignoruje `limit` — to był cały błąd")
        self.assertEqual(zapytanie["per_page"], ["50"])

    def test_zbiera_kolejne_strony_do_limitu(self):
        k = self._klient([[{"id": i} for i in range(100)], [{"id": 100 + i} for i in range(100)],
                          [{"id": 200}]])
        self.assertEqual(len(k.sprawy(limit=150)), 150)
        self.assertEqual(len(k.adresy), 2)

    def test_szukaj_idzie_jako_search(self):
        k = self._klient([[]])
        k.sprawy(limit=10, szukaj="782")
        self.assertEqual(parse_qs(urlparse(k.adresy[0]).query)["search"], ["782"])

    def test_znajdz_sprawe_zaweza_po_numerze(self):
        class K:
            def sprawy(self, *, limit=50, szukaj=None):
                self.szukaj = szukaj
                return [{"id": "x", "ticket_number": 7820, "ticket_prefix": "ADVERTPR"},
                        {"id": "y", "ticket_number": 782, "ticket_prefix": "ADVERTPR"}]
        k = K()
        self.assertEqual(asystent.znajdz_sprawe(k, "ADVERTPR-782")["id"], "y")
        self.assertEqual(k.szukaj, "782", "numer ma iść do SF, a nie być szukany w 25 ostatnich")


if __name__ == "__main__":
    unittest.main()
