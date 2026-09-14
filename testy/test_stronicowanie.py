"""Szukanie własnych zadań przechodzi CAŁĄ kolejkę, nie pierwszą stronę.

v0.2 (14.09.2026) - APro Agents / borys-sf

USTERKA, KTÓREJ TO PILNUJE
Wersja 0.1 pytała SalesForge o pierwsze 50 zadań agentów i odsiewała je u siebie. Przy 518
zadaniach w kolejce znaczyło to, że agent, którego zadanie stoi na pozycji 51 albo dalszej,
nie zobaczy go NIGDY — a worker wygląda wtedy na bezczynnego, nie na zepsutego. Cisza, którą
łatwo wziąć za spokój, jest gorsza od błędu: błąd ktoś zgłasza.

Atrapa udaje serwer ze stronicowaniem (`limit`/`offset`/`total`), bo tylko ona pozwala
postawić własne zadanie na trzeciej stronie i sprawdzić, czy zostanie znalezione.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit.api import STRON_NAJWYZEJ, Klient  # noqa: E402

MOJ_SLUG = "codex-formarketing"


class KlientZAtrapaSieci(Klient):
    """Prawdziwy `Klient`, podmieniona tylko warstwa sieci.

    Podmieniamy `_wywolaj`, a nie `zadania`, bo testowana logika (składanie `offset`, warunek
    końca) siedzi PONAD tą metodą — atrapa założona wyżej sprawdzałaby atrapę.
    """

    def __init__(self, *, kolejka: list[dict]):
        super().__init__(baza="https://atrapa.test", klucz="x", organizacja="org")
        self.kolejka = kolejka
        self.pytania: list[tuple[int, int]] = []   # (limit, offset) każdego żądania

    def _wywolaj(self, metoda, sciezka, *, cialo=None):
        from urllib.parse import parse_qs, urlparse

        parametry = parse_qs(urlparse(sciezka).query)
        limit = int(parametry["limit"][0])
        offset = int(parametry.get("offset", ["0"])[0])
        self.pytania.append((limit, offset))
        return {
            "items": self.kolejka[offset:offset + limit],
            "total": len(self.kolejka),
            "limit": limit,
            "offset": offset,
        }


def _kolejka(ile: int, *, moje_na: list[int]) -> list[dict]:
    """Kolejka `ile` zadań; na pozycjach `moje_na` (licząc od zera) stoją MOJE."""
    zadania = []
    for i in range(ile):
        moje = i in moje_na
        zadania.append({
            "id": f"zadanie-{i}",
            "external_id": f"ADVERTPR-{1000 + i}",
            "assigned_agent_slug": MOJ_SLUG if moje else "ktos-inny",
        })
    return zadania


class TestStronicowanie(unittest.TestCase):

    def test_moje_zadanie_na_TRZECIEJ_stronie_jest_znalezione(self):
        """Sedno usterki 0.1: 518 zadań, moje na pozycji 460.

        Strona po stronie SF ma sufit 200, więc to jest trzecia strona — dokładnie ten
        przypadek, którego wersja z jednym pytaniem nie umiała obsłużyć.
        """
        klient = KlientZAtrapaSieci(kolejka=_kolejka(518, moje_na=[460]))

        wynik = klient.moje_zadania(slug=MOJ_SLUG)

        self.assertEqual(len(wynik), 1)
        self.assertEqual(wynik.zadania[0]["external_id"], "ADVERTPR-1460")
        self.assertEqual(wynik.przejrzano, 518)
        self.assertEqual(wynik.wszystkich, 518)
        self.assertFalse(wynik.urwane)

    def test_szuka_do_pierwszego_trafienia_gdy_wolajacy_chce_jednego(self):
        """Worker bierze jedno zadanie na przebieg — nie ma po co czytać reszty kolejki.

        Bez tego każdy przebieg workera przy dużej tablicy kosztowałby trzy żądania zamiast
        jednego, co przy odstępie liczonym w sekundach robi różnicę dla serwera.
        """
        klient = KlientZAtrapaSieci(kolejka=_kolejka(518, moje_na=[3, 460]))

        wynik = klient.moje_zadania(slug=MOJ_SLUG, ile_najwyzej=1)

        self.assertEqual(len(wynik), 1)
        self.assertEqual(wynik.zadania[0]["external_id"], "ADVERTPR-1003")
        self.assertEqual(len(klient.pytania), 1, "trafienie na pierwszej stronie kończy szukanie")

    def test_bez_moich_zadan_przechodzi_cala_kolejke(self):
        """„Brak zadań" ma znaczyć „sprawdziłem wszystko", a nie „sprawdziłem początek"."""
        klient = KlientZAtrapaSieci(kolejka=_kolejka(450, moje_na=[]))

        wynik = klient.moje_zadania(slug=MOJ_SLUG)

        self.assertFalse(wynik)
        self.assertEqual(wynik.przejrzano, 450)
        self.assertFalse(wynik.urwane)
        self.assertEqual([o for _, o in klient.pytania], [0, 200, 400])

    def test_bezpiecznik_stron_jest_WIDOCZNY_w_wyniku(self):
        """Kolejka większa niż bezpiecznik: wynik ma powiedzieć, że przeglądanie urwano.

        Inaczej pusta lista po obiciu się o bezpiecznik jest nie do odróżnienia od uczciwego
        „nie masz zadań" — i agent melduje spokój tam, gdzie czeka praca.
        """
        za_duza = STRON_NAJWYZEJ * 200 + 500
        klient = KlientZAtrapaSieci(kolejka=_kolejka(za_duza, moje_na=[za_duza - 1]))

        wynik = klient.moje_zadania(slug=MOJ_SLUG)

        self.assertFalse(wynik, "zadanie stoi za bezpiecznikiem — nie znajdziemy go")
        self.assertTrue(wynik.urwane)
        self.assertEqual(len(klient.pytania), STRON_NAJWYZEJ)
        self.assertLess(wynik.przejrzano, wynik.wszystkich)

    def test_pusta_strona_konczy_przegladanie_mimo_klamiacego_licznika(self):
        """`total` z serwera bywa policzony inaczej niż strona (filtry, uprawnienia).

        Bez warunku „pusta strona kończy" jedno przekłamanie licznika dawałoby dwadzieścia
        żądań pod rząd przy KAŻDYM przebiegu workera. Z nim kosztuje jedno dodatkowe, puste —
        bo po pierwszej stronie nie ma jeszcze skąd wiedzieć, że licznik kłamie.
        """
        klient = KlientZAtrapaSieci(kolejka=_kolejka(10, moje_na=[]))
        klient.kolejka = _kolejka(10, moje_na=[])

        # Serwer twierdzi, że ma tysiąc zadań, a oddaje dziesięć.
        def klamliwe(metoda, sciezka, *, cialo=None):
            odp = KlientZAtrapaSieci._wywolaj(klient, metoda, sciezka, cialo=cialo)
            odp["total"] = 1000
            return odp

        klient._wywolaj = klamliwe
        wynik = klient.moje_zadania(slug=MOJ_SLUG)

        self.assertEqual(len(klient.pytania), 2, "druga strona jest pusta i kończy pętlę")
        self.assertTrue(wynik.urwane, "…ale rozjazd licznika zostaje widoczny")

    def test_wynik_zachowuje_sie_jak_lista_dla_wolajacego(self):
        """`if wynik:`, `len(wynik)`, `for z in wynik` — wołający pyta o zadania najczęściej."""
        klient = KlientZAtrapaSieci(kolejka=_kolejka(5, moje_na=[1, 2]))

        wynik = klient.moje_zadania(slug=MOJ_SLUG)

        self.assertTrue(wynik)
        self.assertEqual(len(wynik), 2)
        self.assertEqual([z["external_id"] for z in wynik], ["ADVERTPR-1001", "ADVERTPR-1002"])


if __name__ == "__main__":
    unittest.main()
