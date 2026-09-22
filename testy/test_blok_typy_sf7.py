"""`sf-kit blok typy` — katalog rodzajów bloku (SF-7).

v1.0.0 (21.09.2026) - APro Agents / borys-sf

Testy pilnują dwóch rzeczy, bo obie da się zepsuć po cichu:
  1. że `typy` naprawdę pokazuje to, co odda SF (łącznie z uprawnieniami — po to się pyta),
  2. że `pokaz`/`odpowiedz` **odmawiają z powodem**, a nie padają na 404 z serwera.

Druga jest ważniejsza, niż wygląda: polecenie, które istnieje i zawsze pada, uczy człowieka,
że Kit bywa zepsuty. Odmowa z numerem sprawy mówi, na co czekać.
"""
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli  # noqa: E402


class _Args:
    def __init__(self, co="typy"):
        self.co = co


class _Klient:
    def __init__(self, typy=None, blad=None):
        self._typy = typy if typy is not None else []
        self._blad = blad

    def typy_blokow(self):
        if self._blad:
            raise self._blad
        return self._typy


TYPY = [
    {"rodzaj": "box", "etykieta": "Box konsoli",
     "stany": ["open", "answered"],
     "akcje": [{"nazwa": "odpowiedz", "etykieta": "Odpowiedz",
                "uprawnienie": "console:write", "zmienia_stan": True}]},
    {"rodzaj": "plik", "etykieta": "Plik", "stany": [],
     "akcje": [{"nazwa": "pobierz", "etykieta": "Pobierz",
                "uprawnienie": None, "zmienia_stan": False}]},
]


def _uruchom(monkeypatch, klient, co="typy"):
    monkeypatch.setattr(cli.konfiguracja, "wczytaj", lambda: type("K", (), {"slug": "borys-sf"})())
    monkeypatch.setattr(cli, "_klient", lambda konf, args: klient)
    wy, err = io.StringIO(), io.StringIO()
    with redirect_stdout(wy), redirect_stderr(err):
        kod = cli.polecenie_blok(_Args(co))
    return kod, wy.getvalue(), err.getvalue()


def test_typy_pokazuje_rodzaje_stany_i_akcje(monkeypatch):
    kod, wy, _ = _uruchom(monkeypatch, _Klient(TYPY))

    assert kod == 0
    assert "box" in wy and "Box konsoli" in wy
    assert "open, answered" in wy
    assert "odpowiedz" in wy


def test_typy_pokazuje_WYMAGANE_UPRAWNIENIE(monkeypatch):
    """Po to człowiek pyta Kita o typy: żeby wiedzieć, czego mu zabraknie, ZANIM spróbuje."""
    kod, wy, _ = _uruchom(monkeypatch, _Klient(TYPY))

    assert "wymaga: console:write" in wy


def test_akcja_bez_uprawnienia_nie_udaje_ze_go_wymaga(monkeypatch):
    """`uprawnienie: null` ma dać czysty wiersz, nie „wymaga: None"."""
    kod, wy, _ = _uruchom(monkeypatch, _Klient(TYPY))

    assert "pobierz — Pobierz" in wy
    assert "None" not in wy, "null uprawnienia wyciekł do tekstu dla człowieka"


def test_rodzaj_bez_stanow_pokazuje_kreske_a_nie_pustke(monkeypatch):
    """Pusta lista stanów znaczy „brak cyklu życia" — pusty wiersz wygląda na usterkę."""
    kod, wy, _ = _uruchom(monkeypatch, _Klient(TYPY))

    assert "stany: —" in wy


def test_pokaz_odsyla_do_nowej_skladni_zamiast_padac(monkeypatch):
    """`pokaz` było słowem-obietnicą przed E1; od 22.09 blok pokazuje sam identyfikator.

    Stare słowo nie ma prawa po cichu zniknąć: ktoś ma je w skrypcie albo w notatce, a „nie ma
    bloku «pokaz»" wyglądałoby na usterkę Kita. Odmowa mówi, CO wpisać zamiast.
    """
    kod, wy, err = _uruchom(monkeypatch, _Klient(TYPY), co="pokaz")

    assert kod == 2, "odmowa ma mieć własny kod wyjścia, inny niż błąd sieci (1)"
    assert "sf-kit blok <id>" in err, "odmowa ma podać nową składnię"
    assert wy == "", "przy odmowie nic nie wypisujemy na wyjście"


def test_odpowiedz_nadal_odmawia_z_powodem(monkeypatch):
    """Zapis odpowiedzi wchodzi etapem E3 — polecenie, które zawsze pada, uczy, że Kit bywa zepsuty."""
    kod, wy, err = _uruchom(monkeypatch, _Klient(TYPY), co="odpowiedz")

    assert kod == 2
    assert "E3" in err and "SF-7" in err, "odmowa ma mówić, NA CO czekać"
    assert wy == ""


def test_pusty_katalog_to_blad_a_nie_cisza(monkeypatch):
    """SF bez ani jednego rodzaju bloku to stan niemożliwy — cisza ukryłaby usterkę."""
    kod, _, err = _uruchom(monkeypatch, _Klient([]))

    assert kod == 1 and "SF-7" in err


def test_blad_api_nie_wywraca_kita(monkeypatch):
    kod, _, err = _uruchom(monkeypatch, _Klient(blad=cli.BladAPI("503 od bramy")))

    assert kod == 1 and "503" in err
