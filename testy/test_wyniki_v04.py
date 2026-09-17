"""Wynik zadania jako ZAŁĄCZNIK — v0.4 (ADVERTPR-777 część B, 799).

v0.4 (15.09.2026) - APro Agents / borys-sf

CO TU JEST MIERZONE
═══════════════════
Damian (15.09): *„czy agent nie powinien dodać treści jako załączniki?"*. Do v0.3 worker pisał
w sprawozdaniu ścieżkę pliku na SWOJEJ maszynie — informację bezużyteczną dla każdego, kto tej
maszyny nie ma.

Trzy rzeczy, które mogą pójść źle i każda z nich zostawia ślad u KLIENTA:

1. **Doklejenie cudzych plików.** `outgoing/` bywa pełne rzeczy z poprzednich zadań; wzięcie
   ich „bo leżą" znaczy pliki jednego klienta w sprawie drugiego. Stąd filtr po czasie startu.
2. **Wyjście poza katalog roboczy.** Treść zadania pisze ktoś inny niż właściciel maszyny,
   a `WYNIK: ../../.ssh/id_rsa` wygląda dokładnie jak literówka.
3. **Cicha strata wyniku.** Plik odrzucony przez SF (zły typ) ma zostać SPAKOWANY, a nie
   pominięty — praca jest zrobiona, więc przepaść nie może.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import wyniki  # noqa: E402


class _Katalog(unittest.TestCase):
    """Świeży katalog roboczy na każdy test — testy o plikach nie mogą dzielić dysku."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.baza = Path(self._tmp.name)
        (self.baza / wyniki.KATALOG_WYNIKOW).mkdir()
        self.addCleanup(self._tmp.cleanup)

    def plik(self, wzgledna: str, tresc: str = "coś", *, wiek_s: float = 0) -> Path:
        p = self.baza / wzgledna
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(tresc, encoding="utf-8")
        if wiek_s:
            stary = time.time() - wiek_s
            import os
            os.utime(p, (stary, stary))
        return p


class TestOdczytuWskazan(_Katalog):

    def test_czyta_linie_WYNIK(self):
        tresc = "Zrób raport.\nWYNIK: outgoing/raport.pdf\nI to tyle."
        self.assertEqual(wyniki.sciezki_z_tresci(tresc), ["outgoing/raport.pdf"])

    def test_wiele_linii_w_kolejnosci(self):
        tresc = "WYNIK: a.pdf\ncoś\nWYNIK: b.png"
        self.assertEqual(wyniki.sciezki_z_tresci(tresc), ["a.pdf", "b.png"])

    def test_znosi_markdownowa_liste_i_wielkosc_liter(self):
        """Zadania pisze człowiek w Markdownie, nie w formacie."""
        self.assertEqual(wyniki.sciezki_z_tresci("- wynik:  a.pdf  "), ["a.pdf"])
        self.assertEqual(wyniki.sciezki_z_tresci("* WYNIK: b.pdf"), ["b.pdf"])

    def test_slowo_wynik_w_zdaniu_nie_jest_wskazaniem(self):
        """Bez dwukropka to zwykłe zdanie — inaczej połowa zadań miałaby przypadkowe załączniki."""
        self.assertEqual(wyniki.sciezki_z_tresci("Wynik ma być czytelny."), [])


class TestZbierania(_Katalog):

    def test_wskazanie_i_wszystkie_swieze_pliki_sa_zalaczane(self):
        """Jawny wynik nie może ukryć innych plików utworzonych podczas zadania."""
        self.plik("outgoing/raport.pdf")
        self.plik("outgoing/smieci.pdf")
        z = wyniki.zbierz("WYNIK: outgoing/raport.pdf", katalog=self.baza, od_czasu=0)
        self.assertEqual([p.name for p in z.pliki], ["raport.pdf", "smieci.pdf"])

    def test_wskazany_plik_jest_szukany_w_work_zadania(self):
        self.plik("work/zadania/raport.md")
        z = wyniki.zbierz("WYNIK: raport.md", katalog=self.baza, od_czasu=time.time() + 60)
        self.assertEqual([p.name for p in z.pliki], ["raport.md"])

    def test_bez_wskazania_bierze_NOWE_z_outgoing(self):
        self.plik("outgoing/nowy.pdf")
        z = wyniki.zbierz("zrób coś", katalog=self.baza, od_czasu=time.time() - 60)
        self.assertEqual([p.name for p in z.pliki], ["nowy.pdf"])

    def test_stare_pliki_z_outgoing_NIE_ida_na_cudza_sprawe(self):
        """SEDNO: `outgoing/` bywa pełne rzeczy z poprzednich zadań — i z poprzednich klientów."""
        self.plik("outgoing/poprzednie-zadanie.pdf", wiek_s=3600)
        self.plik("outgoing/to-zadanie.pdf")
        z = wyniki.zbierz("", katalog=self.baza, od_czasu=time.time() - 60)
        self.assertEqual([p.name for p in z.pliki], ["to-zadanie.pdf"])

    def test_brak_katalogu_outgoing_to_pusty_wynik_a_nie_awaria(self):
        import shutil
        shutil.rmtree(self.baza / wyniki.KATALOG_WYNIKOW)
        self.assertFalse(wyniki.zbierz("", katalog=self.baza, od_czasu=0))


class TestOdmow(_Katalog):

    def test_sciezka_poza_katalogiem_roboczym_jest_odrzucana(self):
        """`WYNIK: ../../.ssh/id_rsa` wygląda jak literówka i ma się skończyć odmową."""
        z = wyniki.zbierz("WYNIK: ../../etc/passwd", katalog=self.baza, od_czasu=0)
        self.assertEqual(z.pliki, [])
        self.assertIn("poza katalogiem roboczym", z.pominiete[0])

    def test_sciezka_bezwzgledna_poza_katalogiem_tez(self):
        z = wyniki.zbierz("WYNIK: /etc/hostname", katalog=self.baza, od_czasu=0)
        self.assertEqual(z.pliki, [])

    def test_nieistniejacy_plik_jest_wymieniony_a_nie_przemilczany(self):
        z = wyniki.zbierz("WYNIK: outgoing/nie-ma.pdf", katalog=self.baza, od_czasu=0)
        self.assertEqual(z.pliki, [])
        self.assertIn("nie ma takiego pliku", z.pominiete[0])

    def test_pusty_plik_nie_jest_wynikiem(self):
        self.plik("outgoing/pusty.pdf", tresc="")
        z = wyniki.zbierz("WYNIK: outgoing/pusty.pdf", katalog=self.baza, od_czasu=0)
        self.assertEqual(z.pliki, [])
        self.assertIn("pusty", z.pominiete[0])

    def test_katalog_wskazany_jako_wynik(self):
        z = wyniki.zbierz(f"WYNIK: {wyniki.KATALOG_WYNIKOW}", katalog=self.baza, od_czasu=0)
        self.assertIn("to katalog", z.pominiete[0])

    def test_sufit_liczby_zalacznikow(self):
        for n in range(21):
            self.plik(f"outgoing/p{n:02d}.pdf")
        z = wyniki.zbierz("", katalog=self.baza, od_czasu=time.time() - 60)
        self.assertEqual(len(z.pliki), wyniki.MAKS_PLIKOW)
        self.assertTrue(any("powyżej" in p for p in z.pominiete))

    def test_brak_wskazanego_pliku_jest_opisany(self):
        z = wyniki.zbierz("WYNIK: brak.md", katalog=self.baza, od_czasu=0)
        self.assertFalse(z.pliki)
        self.assertIn("nie ma takiego pliku", z.pominiete[0])


class TestPakowania(_Katalog):

    def test_json_jest_wysylany_jako_txt_a_nie_odrzucany(self):
        self.plik("outgoing/raport.json", tresc='{"a": 1}')
        z = wyniki.zbierz("", katalog=self.baza, od_czasu=time.time() - 60)

        self.assertEqual([p.name for p in z.pliki], ["raport.json.txt"])
        self.assertTrue(z.pliki[0].exists())
        self.assertEqual(z.pliki[0].read_text(encoding="utf-8"), '{"a": 1}')
        self.assertEqual(z.pominiete, [])
        self.assertIn("wysłano jako", z.uwagi[0])

    def test_html_tez(self):
        self.plik("outgoing/makieta.html", tresc="<p>x</p>")
        z = wyniki.zbierz("", katalog=self.baza, od_czasu=time.time() - 60)
        self.assertEqual([p.name for p in z.pliki], ["makieta.html.zip"])

    def test_kazdy_plik_osobno_a_nie_wszystko_w_jedno_archiwum(self):
        """Człowiek otwierający sprawę ma widzieć, ILE rzeczy dostał i jak się nazywają."""
        self.plik("outgoing/a.json", tresc="{}")
        self.plik("outgoing/b.json", tresc="{}")
        z = wyniki.zbierz("", katalog=self.baza, od_czasu=time.time() - 60)
        self.assertEqual(sorted(p.name for p in z.pliki), ["a.json.txt", "b.json.txt"])

    def test_pdf_i_png_ida_bez_pakowania(self):
        self.plik("outgoing/raport.pdf")
        self.plik("outgoing/zrzut.png")
        z = wyniki.zbierz("", katalog=self.baza, od_czasu=time.time() - 60)
        self.assertEqual(sorted(p.name for p in z.pliki), ["raport.pdf", "zrzut.png"])
        self.assertEqual(z.tymczasowe, [])

    def test_archiwa_sa_zgloszone_do_posprzatania(self):
        """Oryginał to praca człowieka i zostaje; archiwum zrobiliśmy my i my je kasujemy."""
        self.plik("outgoing/raport.json", tresc="{}")
        z = wyniki.zbierz("", katalog=self.baza, od_czasu=time.time() - 60)
        self.assertEqual([p.name for p in z.tymczasowe], ["raport.json.txt"])

    def test_archiwum_NIE_powstaje_w_katalogu_roboczym(self):
        """ZNALEZIONE NA ŻYWEJ SPRAWIE (15.09) — i jest to wyciek, nie bałagan.

        Pierwsza wersja pakowała archiwum OBOK oryginału, czyli w `outgoing/`. Przy następnym
        zadaniu ten sam plik jest tam „nowy" i idzie jako WYNIK NASTĘPNEGO ZADANIA — czyli na
        sprawę innego klienta. Zauważone, bo próba na sprawie 777 pokazała ten sam załącznik
        dwa razy: raz świeżo spakowany, raz zostawiony przez poprzednie uruchomienie.

        Sprzątanie po sobie tego nie załatwia: wystarczy, że raz się nie uda, i śmieć zostaje.
        """
        self.plik("outgoing/raport.json", tresc="{}")
        z = wyniki.zbierz("", katalog=self.baza, od_czasu=time.time() - 60)

        archiwum = z.pliki[0]
        self.assertFalse(
            str(archiwum).startswith(str(self.baza)),
            f"archiwum {archiwum} leży w katalogu roboczym — wejdzie jako wynik następnego zadania",
        )
        w_outgoing = {p.name for p in (self.baza / wyniki.KATALOG_WYNIKOW).iterdir()}
        self.assertEqual(w_outgoing, {"raport.json"})

    def test_ten_sam_plik_wskazany_dwa_razy_idzie_raz(self):
        """Dwa identyczne załączniki w jednym wpisie wyglądają jak usterka SF, a są naszą."""
        self.plik("outgoing/raport.pdf")
        z = wyniki.zbierz("WYNIK: outgoing/raport.pdf\nWYNIK: outgoing/raport.pdf",
                          katalog=self.baza, od_czasu=0)
        self.assertEqual([p.name for p in z.pliki], ["raport.pdf"])

    def test_posprzatanie_usuwa_archiwa_i_zostawia_oryginaly(self):
        self.plik("outgoing/raport.json", tresc="{}")
        z = wyniki.zbierz("", katalog=self.baza, od_czasu=time.time() - 60)
        archiwum = z.pliki[0]
        self.assertTrue(archiwum.exists())

        wyniki.posprzataj(z)

        self.assertFalse(archiwum.exists())
        self.assertTrue((self.baza / "outgoing" / "raport.json").exists())
        self.assertEqual(z.tymczasowe, [])


class TestOpisu(_Katalog):

    def test_opis_wymienia_zalaczone_i_pominiete(self):
        self.plik("outgoing/raport.pdf")
        z = wyniki.zbierz("WYNIK: outgoing/raport.pdf\nWYNIK: outgoing/nie-ma.pdf",
                          katalog=self.baza, od_czasu=0)
        opis = wyniki.opis_dla_wpisu(z)
        self.assertIn("raport.pdf", opis)
        self.assertIn("Nie załączono", opis)
        self.assertIn("nie-ma.pdf", opis)

    def test_bez_plikow_opis_jest_pusty(self):
        """Zadanie, które nie produkuje plików, nie ma dostawać zdania o załącznikach."""
        self.assertEqual(wyniki.opis_dla_wpisu(wyniki.Zebrane()), "")


if __name__ == "__main__":
    unittest.main()
