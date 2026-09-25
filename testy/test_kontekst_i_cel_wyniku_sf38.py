"""SF-38 — kontekst sprawy przed startem, wynik na wskazaną sprawę, jawność wysyłki.

v1.0.0 (25.09.2026) - APro Agents / borys-sf

CZEGO PILNUJĘ
═════════════
1. Załączniki sprawy lądują w `inbox/<external_id>/` z numeracją w kolejności wpisów (zdjęcia
   orzeczenia w kolejności stron), linki nie są pobierane, druga próba nie pobiera drugi raz.
2. Wykonawca z ramką DOSTAJE blok „KONTEKST SPRAWY" (opis, wpisy, ścieżki plików) — sprawdzone
   na tym, co naprawdę trafiło do polecenia, nie na funkcji pomocniczej.
3. Brak kontekstu (odmowa, wyjątek) NIE wywraca zadania i jest nazwany z typu.
4. `SPRAWA_WYNIKU:` kieruje wynik na wskazaną sprawę (+ notka na sprawie zadania); odmowa
   wskazanej sprawy nie gubi wyniku. `ORGANIZACJA_WYNIKU:` zmienia Organizację klienta.
5. Mniej załączników potwierdzonych przez SF niż wysłanych → notka na sprawie.
"""
import tempfile
import unittest
from pathlib import Path

from sf_kit import kontekst, wykonawcy
from sf_kit.api import BladAPI
from sf_kit.worker import _sprawdz_potwierdzone, _sprawozdanie_na_cel, obsluz_zadanie

from test_worker import AtrapaKlienta, konfiguracja, zadanie

SPRAWA = {
    "id": "22222222-2222-2222-2222-222222222222", "ticket_prefix": "ADVERTPR",
    "ticket_number": 927, "title": "IPET", "status": "in_progress", "priority": "high",
    "description": "Przygotuj IPET na podstawie orzeczenia (zdjęcia) i wzoru.",
    "entries": [
        {"id": "e2", "created_at": "2026-09-24T19:22:00Z", "entry_type": "note",
         "author_name": "Agata", "visibility": "internal", "content": "Uwaga: dane wrażliwe.",
         "attachments": [{"id": "a3", "filename": "x3", "original_filename": "strona 2.JPG",
                          "file_size": 3}]},
        {"id": "e1", "created_at": "2026-09-24T19:21:00Z", "entry_type": "note",
         "author_name": "Agata", "visibility": "internal", "content": "Materiały źródłowe",
         "attachments": [
             {"id": "a1", "filename": "x1", "original_filename": "wzór IPET.pdf", "file_size": 3},
             {"id": "a2", "filename": None, "original_filename": "link", "url": "https://x",
              "file_size": 0},
         ]},
    ],
}


class KlientZeSprawa(AtrapaKlienta):
    def __init__(self, *, sprawa=SPRAWA, pobieranie_pada=(), sprawa_pada=None, **kw):
        super().__init__(**kw)
        self._sprawa, self._pada, self._sprawa_pada = sprawa, set(pobieranie_pada), sprawa_pada
        self.pobrane: list[str] = []
        self.organizacja = "org-zadania"
        self.klony: list = []

    def sprawa(self, ticket_id):
        if self._sprawa_pada:
            raise self._sprawa_pada
        return self._sprawa

    def pobierz_zalacznik(self, attachment_id, cel, *, limit_bajtow):
        if attachment_id in self._pada:
            raise BladAPI("403 wpis wewnętrzny")
        self.pobrane.append(attachment_id)
        Path(cel).write_bytes(b"abc")
        return 3

    def w_organizacji(self, organizacja):
        klon = KlientZeSprawa(sprawa=self._sprawa)
        klon.organizacja = organizacja
        self.klony.append(klon)
        return klon


class TestPakietKontekstu(unittest.TestCase):
    def test_pliki_w_kolejnosci_wpisow_bez_linkow_i_bez_ponownego_pobrania(self):
        with tempfile.TemporaryDirectory() as k:
            klient = KlientZeSprawa()
            p = kontekst.przygotuj(klient, {"ticket_id": SPRAWA["id"], "external_id": "ipet-v2"},
                                   katalog_roboczy=k)
            self.assertEqual([f.name for f in p.pliki], ["01-wzór_IPET.pdf", "02-strona_2.JPG"])
            self.assertEqual(p.katalog, Path(k) / "inbox" / "ipet-v2")
            self.assertIn("inbox/ipet-v2/01-wzór_IPET.pdf", p.tekst)
            self.assertIn("Przygotuj IPET", p.tekst)
            self.assertIn("Uwaga: dane wrażliwe.", p.tekst)
            kontekst.przygotuj(klient, {"ticket_id": SPRAWA["id"], "external_id": "ipet-v2"},
                               katalog_roboczy=k)
            self.assertEqual(klient.pobrane, ["a1", "a3"], "druga próba pobrała pliki drugi raz")

    def test_odmowa_pliku_jest_nazwana_w_bloku(self):
        with tempfile.TemporaryDirectory() as k:
            p = kontekst.przygotuj(KlientZeSprawa(pobieranie_pada={"a3"}),
                                   {"ticket_id": SPRAWA["id"], "external_id": "z"},
                                   katalog_roboczy=k)
            self.assertEqual(len(p.pliki), 1)
            self.assertIn("NIE pobrano", p.tekst)
            self.assertIn("strona_2.JPG (403 wpis wewnętrzny)", p.tekst)

    def test_wyjatek_przy_karcie_nie_wywraca_i_ma_nazwe_typu(self):
        with tempfile.TemporaryDirectory() as k:
            p = kontekst.przygotuj(KlientZeSprawa(sprawa_pada=AttributeError("brak metody")),
                                   {"ticket_id": SPRAWA["id"]}, katalog_roboczy=k)
            self.assertIn("AttributeError", p.pominiete[0])
            self.assertIn("Masz tylko treść zadania", p.tekst)

    def test_zadanie_bez_sprawy_nie_ma_kontekstu(self):
        self.assertEqual(kontekst.przygotuj(KlientZeSprawa(), {"ticket_id": None},
                                            katalog_roboczy="/tmp").tekst, "")


class TestKontekstDochodziDoWykonawcy(unittest.TestCase):
    def test_polecenie_wykonawcy_z_ramka_niesie_kontekst_i_sciezki(self):
        widziane = {}

        class Szpieg(wykonawcy.Wykonawca):
            nazwa, chce_ramke = "szpieg38", True

            def dostepny(self):
                return True, ""

            def wykonaj(self, polecenie, *, katalog, limit_s):
                widziane["polecenie"] = polecenie
                widziane["pliki"] = sorted(p.name for p in (Path(katalog) / "inbox").rglob("*"))
                return wykonawcy.Wynik(True, "**Sedno** — ok")

        stare = dict(wykonawcy._WYKONAWCY)
        wykonawcy._WYKONAWCY["szpieg38"] = Szpieg()
        try:
            with tempfile.TemporaryDirectory() as k:
                obsluz_zadanie(KlientZeSprawa(), konfiguracja(runtime="szpieg38", katalog_roboczy=k),
                               zadanie(external_id="ipet-927"))
        finally:
            wykonawcy._WYKONAWCY.clear()
            wykonawcy._WYKONAWCY.update(stare)
        self.assertIn("--- KONTEKST SPRAWY", widziane["polecenie"])
        self.assertIn("inbox/ipet-927/01-wzór_IPET.pdf", widziane["polecenie"])
        self.assertIn("01-wzór_IPET.pdf", widziane["pliki"],
                      "plik ma LEŻEĆ w katalogu w chwili wykonania, nie tylko być wymieniony")


class TestCelWyniku(unittest.TestCase):
    CEL = "33333333-3333-3333-3333-333333333333"

    def test_wynik_na_wskazana_sprawe_i_notka_na_sprawie_zadania(self):
        klient = KlientZeSprawa()
        z = zadanie(body_md=f"Zrób IPET\nSPRAWA_WYNIKU: {self.CEL}")
        self.assertTrue(_sprawozdanie_na_cel(klient, z, "wynik", ["/tmp/a.docx"]))
        self.assertEqual(klient.wpisy_z_plikami[0][0], self.CEL)
        self.assertEqual(klient.wpisy[-1][0], z["ticket_id"])
        self.assertIn(self.CEL, klient.wpisy[-1][1])

    def test_organizacja_wyniku_przelacza_klienta(self):
        klient = KlientZeSprawa()
        org = "44444444-4444-4444-4444-444444444444"
        z = zadanie(body_md=f"SPRAWA_WYNIKU: {self.CEL}\nORGANIZACJA_WYNIKU: {org}")
        _sprawozdanie_na_cel(klient, z, "wynik", [])
        self.assertEqual(klient.klony[0].organizacja, org)
        self.assertEqual(klient.klony[0].wpisy[0][0], self.CEL)

    def test_odmowa_wskazanej_sprawy_nie_gubi_wyniku(self):
        class Odmawia(KlientZeSprawa):
            def wpis_z_plikami(self, ticket_id, tresc, pliki, **kw):
                if ticket_id == TestCelWyniku.CEL:
                    raise BladAPI("404 Ticket not found")
                return super().wpis_z_plikami(ticket_id, tresc, pliki, **kw)

        klient = Odmawia()
        z = zadanie(body_md=f"SPRAWA_WYNIKU: {self.CEL}")
        self.assertTrue(_sprawozdanie_na_cel(klient, z, "wynik", ["/tmp/a.md"]))
        tid, tresc, pliki = klient.wpisy_z_plikami[0]
        self.assertEqual(tid, z["ticket_id"])
        self.assertIn("404 Ticket not found", tresc)

    def test_bez_wskazania_zachowanie_bez_zmian(self):
        self.assertIsNone(_sprawozdanie_na_cel(KlientZeSprawa(), zadanie(), "w", []))


class TestJawnoscWysylki(unittest.TestCase):
    def test_mniej_potwierdzonych_niz_wyslanych_daje_notke(self):
        klient = KlientZeSprawa()
        _sprawdz_potwierdzone(klient, "t1", {"attachments": [{"original_filename": "a.md"}]},
                              ["/x/a.md", "/x/b.docx"])
        self.assertIn("b.docx", klient.wpisy[0][1])
        self.assertIn("NIE dołączony (1 z 2)", klient.wpisy[0][1])

    def test_komplet_i_brak_pola_nie_daja_notki(self):
        klient = KlientZeSprawa()
        _sprawdz_potwierdzone(klient, "t1", {"attachments": [{}, {}]}, ["/a", "/b"])
        _sprawdz_potwierdzone(klient, "t1", {}, ["/a"])
        self.assertEqual(klient.wpisy, [])


if __name__ == "__main__":
    unittest.main()
