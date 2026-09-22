"""`sf-kit os` i `sf-kit blok <id>` — trzecia płaszczyzna SF-7 (E4a + rdzeń bloku).

v1.0.0 (22.09.2026) - APro Agents / borys-sf · kontrakt: `e4a-kontrakt-dla-kitu.md`

CO TU JEST BRONIONE — I DLACZEGO AKURAT TO
══════════════════════════════════════════
Polecenie `os` jest cienkie: pyta API i wypisuje. Cała jego wartość siedzi w czterech
rozstrzygnięciach, z których KAŻDE psuje się cicho — bez wyjątku, bez błędu, z ekranem,
który wygląda poprawnie:

  1. domyślka: bez flagi ma iść `pelna=true` (decyzja Damiana 22.09). Odwrócenie jej nie
     wywala niczego — po prostu Kit i panel pokazują tę samą sprawę inaczej;
  2. grupę poznaje się po `typ`, nie po obecności `ile`;
  3. licznik wierszy liczy się z sumy `ile`, nie z długości listy — inaczej „5 wierszy"
     stoi tam, gdzie naprawdę jest 47;
  4. serwer bez E4a ignoruje `--zwinieta` i oddaje 200 z pełną osią. Bez ostrzeżenia człowiek
     bierze komplet wierszy za wynik zwinięcia.

Testy nie ruszają sieci: `_klient` jest podmieniany, a atrapa zapamiętuje, O CO ją zapytano —
bo połowa tych rozstrzygnięć to treść ŻĄDANIA, nie wypisanego tekstu.
"""
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, os_czasu  # noqa: E402

SPRAWA = "11111111-2222-3333-4444-555555555555"
BLOK = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _wiersz(ident, *, kiedy="2026-09-01T12:00:00Z", rodzaj="note", tresc="coś się stało",
            autor="Anna", typ="blok"):
    pozycja = {"id": ident, "kind": rodzaj, "content": tresc, "author_label": autor,
               "occurred_at": kiedy}
    if typ is not None:
        pozycja["typ"] = typ
    return pozycja


def _grupa(ident, *, ile=8, od="2026-09-01T12:04:00Z", do="2026-09-01T12:11:00Z",
           rodzaje=None, autorzy=("Anna", "Bartek", "Celina")):
    return {"typ": "grupa", "id": ident, "ile": ile, "od": od, "do": do,
            "rodzaje": rodzaje if rodzaje is not None else {"field_change": 5,
                                                            "status_change": 3},
            "autorzy": list(autorzy), "wiersze": [f"w{i}" for i in range(ile)]}


class _Klient:
    """Atrapa SF. Zapamiętuje ostatnie wywołanie — połowa testów bada ŻĄDANIE, nie wydruk."""

    def __init__(self, pozycje=None, *, blok=None, blad=None, next_cursor=None):
        self.pozycje = pozycje if pozycje is not None else []
        self._blok = blok or {}
        self._blad = blad
        self._next = next_cursor
        self.wolanie = None

    def sprawy(self, limit=50):
        return [{"id": SPRAWA, "ticket_number": 7, "ticket_prefix": "SF"}]

    def os_obiektu(self, entity_type, entity_id, *, pelna=True, rozwin="", limit=50, kursor=""):
        self.wolanie = {"typ": entity_type, "id": entity_id, "pelna": pelna,
                        "rozwin": rozwin, "limit": limit}
        if self._blad:
            raise self._blad
        return {"entity_type": entity_type, "entity_id": entity_id,
                "entries": self.pozycje, "next_cursor": self._next}

    def blok(self, blok_id):
        self.wolanie = {"blok": blok_id}
        if self._blad:
            raise self._blad
        return self._blok


class _ArgsOs:
    def __init__(self, sprawa="SF-7", **nadpisz):
        self.sprawa = sprawa
        self.pelna = False
        self.zwinieta = False
        self.rozwin = None
        self.limit = 50
        self.json = False
        for k, w in nadpisz.items():
            setattr(self, k, w)


class _ArgsBlok:
    def __init__(self, co=BLOK, json=False):
        self.co = co
        self.json = json


def _uruchom(monkeypatch, funkcja, args, klient):
    monkeypatch.setattr(cli.konfiguracja, "wczytaj", lambda: type("K", (), {"slug": "borys-sf"})())
    monkeypatch.setattr(cli, "_klient", lambda konf, a: klient)
    wy, err = io.StringIO(), io.StringIO()
    with redirect_stdout(wy), redirect_stderr(err):
        kod = funkcja(args)
    return kod, wy.getvalue(), err.getvalue()


# ── 1. domyślka i flagi: co naprawdę leci do serwera ───────────────────────────────────

def test_bez_flag_pyta_o_OS_PELNA(monkeypatch):
    """Decyzja Damiana 22.09: domyślka serwera zostaje domyślką Kita.

    MUTACJA: `pelna = args.pelna` zamiast `not (args.zwinieta or args.rozwin)` — ten test
    czerwienieje jako jedyny, a ekran w obu wariantach wygląda sensownie.
    """
    klient = _Klient([_wiersz("w1")])
    kod, wy, _ = _uruchom(monkeypatch, cli.polecenie_os, _ArgsOs(), klient)

    assert kod == 0
    assert klient.wolanie["pelna"] is True
    assert "pełna" in wy


def test_zwinieta_prosi_o_zwiniecie(monkeypatch):
    klient = _Klient([_grupa("g1")])
    kod, wy, _ = _uruchom(monkeypatch, cli.polecenie_os, _ArgsOs(zwinieta=True), klient)

    assert kod == 0
    assert klient.wolanie["pelna"] is False
    assert "zwinięta" in wy


def test_rozwin_sam_wlacza_zwijanie(monkeypatch):
    """Prośba o rozwinięcie grupy na PEŁNEJ osi nie ma treści — `--rozwin` implikuje zwinięcie.

    Kontrakt z handoffu: `--rozwin <id>` → `?pelna=false&rozwin=<id>`.
    """
    klient = _Klient([_grupa("g1")])
    kod, _, _ = _uruchom(monkeypatch, cli.polecenie_os, _ArgsOs(rozwin="g1"), klient)

    assert kod == 0
    assert klient.wolanie["pelna"] is False
    assert klient.wolanie["rozwin"] == "g1"


def test_pelna_z_rozwin_to_odmowa_a_nie_ciche_wygranie_jednej(monkeypatch):
    """Sprzeczne flagi: ciche wygranie jednej uczy człowieka, że flagi bywają ignorowane."""
    klient = _Klient([_wiersz("w1")])
    kod, wy, err = _uruchom(monkeypatch, cli.polecenie_os,
                            _ArgsOs(pelna=True, rozwin="g1"), klient)

    assert kod == 2
    assert klient.wolanie is None, "przy sprzecznych flagach nie pytamy serwera w ogóle"
    assert "rozwij" in err.lower()


# ── 2. wypisanie: grupa, licznik, sprzeczność „pozycje vs wiersze" ─────────────────────

def test_grupa_wypisuje_zakres_rodzaje_autorow_i_identyfikator(monkeypatch):
    """Jedna linia ma nieść wszystko, czego trzeba do decyzji „rozwijać czy nie"."""
    klient = _Klient([_grupa("a1faccfd-0000-0000-0000-000000000000")])
    kod, wy, _ = _uruchom(monkeypatch, cli.polecenie_os, _ArgsOs(zwinieta=True), klient)

    assert kod == 0
    assert "12:04–12:11" in wy
    assert "8 zmian technicznych" in wy
    assert "5× pole" in wy and "3× status" in wy
    assert "3 autorzy" in wy
    assert "[a1faccfd]" in wy, "bez identyfikatora nie da się użyć `--rozwin`"


def test_licznik_liczy_WIERSZE_a_nie_pozycje_listy(monkeypatch):
    """Punkt 2 handoffu: po zwinięciu lista jest krótsza, a oś tej samej długości.

    MUTACJA: policz `len(pozycje)` zamiast sumy `ile` — „3 wiersze osi" zamiast 18.
    """
    klient = _Klient([_wiersz("w1"), _grupa("g1", ile=8), _grupa("g2", ile=8)])
    kod, wy, _ = _uruchom(monkeypatch, cli.polecenie_os, _ArgsOs(zwinieta=True), klient)

    assert kod == 0
    assert "3 pozycji = 17 wierszy osi" in wy
    assert "2 grup zwinięta" in wy or "2 grup" in wy


def test_pusta_os_mowi_o_dostepie_zamiast_milczec(monkeypatch):
    """Pusto na osi bywa brakiem dostępu, nie brakiem zdarzeń — cisza myli w tę drugą stronę."""
    kod, wy, _ = _uruchom(monkeypatch, cli.polecenie_os, _ArgsOs(), _Klient([]))

    assert kod == 0
    assert "możesz zobaczyć" in wy


def test_json_oddaje_surowa_odpowiedz(monkeypatch):
    """`--json` jest dla skryptu — ma oddać to, co przyszło, bez naszego formatowania."""
    import json as _json
    klient = _Klient([_grupa("g1")])
    kod, wy, _ = _uruchom(monkeypatch, cli.polecenie_os, _ArgsOs(json=True), klient)

    dane = _json.loads(wy)
    assert kod == 0
    assert dane["entries"][0]["typ"] == "grupa"
    assert "zmian technicznych" not in wy, "w trybie --json nic nie dokładamy od siebie"


# ── 3. stary serwer: 200, pełna oś, zero protestu ──────────────────────────────────────

def test_api_bez_zwijania_daje_jasne_ostrzezenie(monkeypatch):
    """SEDNO: FastAPI ignoruje nieznany parametr, więc stary serwer oddaje 200 i pełną oś.

    Bez tego ostrzeżenia człowiek widzi komplet wierszy i bierze go za wynik zwinięcia —
    a potem zgłasza, że „zwijanie nie działa", nie wiedząc, że rozmawia ze starym API.
    """
    stare = [_wiersz("w1", typ=None), _wiersz("w2", typ=None)]
    kod, wy, _ = _uruchom(monkeypatch, cli.polecenie_os, _ArgsOs(zwinieta=True),
                          _Klient(stare))

    assert kod == 0
    assert "serwer nie zwija" in wy
    assert "KOMPLET" in wy


def test_nowe_api_bez_grup_NIE_ostrzega(monkeypatch):
    """Zwinięta oś, na której nie było czego zwijać, to normalny wynik — nie usterka serwera.

    Bez tego testu „ostrzegaj zawsze, gdy nie ma grup" przeszłoby jako poprawne i Kit
    krzyczałby na każdej krótkiej sprawie.
    """
    kod, wy, _ = _uruchom(monkeypatch, cli.polecenie_os, _ArgsOs(zwinieta=True),
                          _Klient([_wiersz("w1"), _wiersz("w2")]))

    assert kod == 0
    assert "serwer nie zwija" not in wy


# ── 4. `sf-kit blok <id>` ──────────────────────────────────────────────────────────────

BLOK_PELNY = {
    "id": BLOK, "rodzaj": "box", "sedno": "pytanie o termin",
    "tresc": "Czy zdążymy do piątku?", "widocznosc": "internal", "wewnetrzny": True,
    "autor_etykieta": "Damian", "wystapil_o": "2026-09-22T10:15:00Z",
    "kotwica_typ": "ticket", "kotwica_id": SPRAWA, "stan_bloku": "odpowiedziany",
    "odpowiedzi": 2, "adresaci": [{"slug": "borys-sf", "status": "consumed"}],
    "natywny_id": "99999999-8888-7777-6666-555555555555", "z_rdzenia": True,
}


def test_blok_pokazuje_rodzaj_sedno_kotwice_stan_i_odpowiedzi(monkeypatch):
    kod, wy, _ = _uruchom(monkeypatch, cli.polecenie_blok, _ArgsBlok(), _Klient(blok=BLOK_PELNY))

    assert kod == 0
    assert "pytanie o termin" in wy
    assert "Czy zdążymy do piątku?" in wy
    assert f"ticket {SPRAWA}" in wy
    assert "odpowiedziany" in wy
    assert "odpowiedzi: 2" in wy
    assert "borys-sf" in wy


def test_blok_z_drogi_zapasowej_przyznaje_sie_do_pustych_pol(monkeypatch):
    """`z_rdzenia=false` = wpis bez lustra: puste `sedno` i `stan` są PRAWDĄ, nie usterką.

    Bez tej linii człowiek patrzy na pusty ekran i zgłasza „Kit nie doczytuje bloków".
    """
    zapasowy = dict(BLOK_PELNY, z_rdzenia=False, sedno=None, stan_bloku=None)
    kod, wy, _ = _uruchom(monkeypatch, cli.polecenie_blok, _ArgsBlok(), _Klient(blok=zapasowy))

    assert kod == 0
    assert "bez lustra" in wy and "E5" in wy


def test_smiec_zamiast_identyfikatora_nie_leci_do_api(monkeypatch):
    """404 z serwera brzmi „nie ma albo nie dla ciebie" — przy literówce to zła podpowiedź.

    MUTACJA: skasuj sprawdzenie wzorca — człowiek z literówką dostaje komunikat o dostępie
    i idzie prosić administratora o uprawnienie, którego ma dość.
    """
    klient = _Klient(blok=BLOK_PELNY)
    kod, wy, err = _uruchom(monkeypatch, cli.polecenie_blok, _ArgsBlok(co="SF-7"), klient)

    assert kod == 2
    assert klient.wolanie is None, "nie pytamy serwera o coś, co nie jest identyfikatorem"
    assert "UUID" in err


def test_404_mowi_o_OBU_mozliwosciach(monkeypatch):
    """Serwer odmawia tak samo przy braku i przy braku dostępu — Kit nie zgaduje jednej."""
    klient = _Klient(blad=cli.BladAPI("nie znaleziono", kod=404))
    kod, _, err = _uruchom(monkeypatch, cli.polecenie_blok, _ArgsBlok(), klient)

    assert kod == 1
    assert "poza Twoim dostępem" in err and "identyfikator" in err


def test_503_mowi_ze_to_serwer_a_nie_ty(monkeypatch):
    """Rdzeń niezamontowany to stan instalacji, nie błąd pytającego."""
    klient = _Klient(blad=cli.BladAPI("moduł osi nie jest zamontowany", kod=503))
    kod, _, err = _uruchom(monkeypatch, cli.polecenie_blok, _ArgsBlok(), klient)

    assert kod == 1
    assert "nie jest gotowy" in err


# ── 5. formatowanie osi bez sieci ──────────────────────────────────────────────────────

def test_nieznany_rodzaj_wraca_surowy_zamiast_zniknac(monkeypatch):
    """Nowy rodzaj bloku dochodzi wpisem w rejestrze SF i nikt nie zaktualizuje mapy w Kicie.

    Lepszy surowy `deal_moved` na ekranie niż cicho pominięta połowa grupy.
    """
    podpis = os_czasu.podpis_rodzajow({"deal_moved": 4, "field_change": 2})

    assert "4× deal_moved" in podpis
    assert "2× pole" in podpis


def test_grupa_poznawana_po_TYP_a_nie_po_ile():
    """Punkt 1 handoffu. Wiersz z polem `ile` (kiedyś dojdzie) nie ma być brany za grupę."""
    udawana_grupa = {"typ": "blok", "ile": 9, "content": "wpis z licznikiem czegoś"}

    assert os_czasu.jest_grupa(udawana_grupa) is False
    assert os_czasu.ile_wierszy([udawana_grupa]) == 1


def test_zakres_czasu_gdy_grupa_trwa_chwile():
    """Grupa z jednej minuty ma pokazać jedną godzinę, nie „12:04–12:04"."""
    linia = os_czasu.wiersz_grupy(_grupa("g1", od="2026-09-01T12:04:00Z",
                                         do="2026-09-01T12:04:00Z"))

    assert "12:04" in linia and "–" not in linia


def test_nagłowek_dnia_przy_zmianie_daty():
    """Oś obejmująca tydzień pokazywałaby same godziny — trzy „12:04" pod rząd myli."""
    linie = os_czasu.wypisz([
        _wiersz("w1", kiedy="2026-09-01T12:04:00Z"),
        _wiersz("w2", kiedy="2026-09-02T09:00:00Z"),
    ])
    naglowki = [l for l in linie if l.startswith("\n──")]

    assert len(naglowki) == 2
    assert "2026-09-01" in naglowki[0] and "2026-09-02" in naglowki[1]


def test_zly_znacznik_czasu_nie_wywraca_osi():
    """Jeden nieczytelny znacznik nie ma prawa przewrócić całego polecenia."""
    linia = os_czasu.wiersz_bloku(_wiersz("w1", kiedy="wczoraj po obiedzie"))

    assert "--:--" in linia
