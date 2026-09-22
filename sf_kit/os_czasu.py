"""Oś sprawy w terminalu — wiersze i grupy (SF-7 E4a).

v1.0.0 (22.09.2026) - APro Agents / borys-sf · kontrakt: `e4a-kontrakt-dla-kitu.md`

DLACZEGO OSOBNY MODUŁ, A NIE KOLEJNE 150 LINII W `cli.py`
═════════════════════════════════════════════════════════
Bo tu mieszka JEDYNA nietrywialna logika polecenia `os` — rozpoznanie, co przyszło z serwera,
i policzenie, ile naprawdę stoi za skróconą listą. To da się sprawdzić testem bez sieci,
bez klucza i bez SalesForge; gdyby siedziało w `polecenie_os`, każdy test musiałby postawić
atrapę HTTP tylko po to, żeby sprawdzić, czy „8 zmian" liczy się z `ile`, a nie z długości listy.

TRZY RZECZY, KTÓRE ŁATWO ZROBIĆ ŹLE (i dlatego mają tu własne funkcje)
══════════════════════════════════════════════════════════════════════
1. **Grupę poznaje się po `typ`, nigdy po obecności `ile`.** Zwykły wiersz też ma dziś `typ`
   (`"blok"`) — pole doszło addytywnie. Rozpoznawanie po `ile` zadziała dziś i złamie się
   w dniu, w którym wiersz dostanie własny licznik czegokolwiek.
2. **`razem` i `ukryte` z odpowiedzi liczą WPISY, nie pozycje listy.** Po zwinięciu lista jest
   krótsza, a te liczniki się nie zmieniają. Licznik „ile widzę" trzeba złożyć z sumy `ile`.
3. **Serwer bez E4a nie protestuje** — nieznany parametr zapytania jest w FastAPI po prostu
   ignorowany. Odpowiedź wraca pełna i wygląda jak poprawna, więc człowiek widzi 200 wierszy
   i myśli, że tyle zostało po zwinięciu. Rozpoznajemy to po BRAKU pola `typ` w pozycjach
   i mówimy wprost, zamiast udawać, że zwinięcie się udało.
"""
from __future__ import annotations

from datetime import datetime

#: Techniczne nazwy rodzajów → to, co człowiek rozumie. Backend oddaje klucze (`field_change`)
#: świadomie: tłumaczenie to decyzja o języku interfejsu, a Kit mówi po polsku.
#:
#: ⚠️ NIEZNANY KLUCZ WRACA W POSTACI SUROWEJ, nie znika i nie jest błędem. Nowy rodzaj bloku
#: dochodzi w SF wpisem w rejestrze i nikt nie ma obowiązku pamiętać o tej mapie — lepszy
#: surowy `deal_moved` na ekranie niż cicho pominięta połowa grupy.
NAZWY_RODZAJOW = {
    "field_change": "pole",
    "status_change": "status",
    "system": "system",
    "message": "wiadomość",
    "note": "notatka",
    "created": "utworzenie",
    "wpis": "wpis",
    "box": "box",
    "wiadomosc": "wiadomość",
    "zdarzenie": "zdarzenie",
    "plik": "plik",
}


def czas(wartosc: str | None) -> datetime | None:
    """Znacznik czasu z API. `None`, gdy pusty albo w postaci, której nie rozumiemy.

    Nie rzucamy: jeden nieczytelny znacznik nie ma prawa przewrócić całej osi. Wiersz bez
    czasu pokaże się z „--:--" i to jest uczciwsze niż wywalone polecenie.
    """
    if not wartosc:
        return None
    try:
        return datetime.fromisoformat(str(wartosc).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _godzina(wartosc: str | None) -> str:
    chwila = czas(wartosc)
    return chwila.strftime("%H:%M") if chwila else "--:--"


def _dzien(wartosc: str | None) -> str:
    chwila = czas(wartosc)
    return chwila.strftime("%Y-%m-%d") if chwila else "(bez daty)"


def jest_grupa(pozycja: dict) -> bool:
    """Czy to wiersz-grupa. PO POLU `typ` — patrz nagłówek modułu, punkt 1."""
    return (pozycja or {}).get("typ") == "grupa"


def serwer_zwija(pozycje: list[dict]) -> bool:
    """Czy odpowiedź w ogóle pochodzi z API, które zna zwijanie (E4a).

    Pusta oś nie jest dowodem w żadną stronę — przy zerze pozycji mówimy „zna", bo ostrzeżenie
    „serwer nie zwija" przy sprawie bez wpisów byłoby myleniem człowieka na pustym miejscu.
    """
    return all("typ" in (p or {}) for p in pozycje) if pozycje else True


def ile_wierszy(pozycje: list[dict]) -> int:
    """Ile wierszy osi stoi za tą listą — grupa liczy się swoim `ile`, nie jako jeden.

    To jest ta liczba, z której wolno liczyć postęp. `razem` z odpowiedzi mówi o WPISACH
    całej osi i po zwinięciu się nie zmienia (punkt 2 w nagłówku).
    """
    suma = 0
    for p in pozycje:
        suma += int(p.get("ile") or 0) if jest_grupa(p) else 1
    return suma


def podpis_rodzajow(rodzaje: dict) -> str:
    """`5× pole, 3× status` — z czego zrobiona jest grupa, bez rozwijania jej."""
    czesci = [f"{ile}× {NAZWY_RODZAJOW.get(rodzaj, rodzaj)}"
              for rodzaj, ile in sorted((rodzaje or {}).items(), key=lambda p: -int(p[1]))]
    return ", ".join(czesci)


def _odmiana_autorow(ilu: int) -> str:
    """„1 autor", „3 autorów" — bo „3 autor" czyta się jak usterka, a nie jak skrót."""
    if ilu == 1:
        return "1 autor"
    if 2 <= ilu <= 4:
        return f"{ilu} autorzy"
    return f"{ilu} autorów"


def wiersz_grupy(grupa: dict) -> str:
    """Jedna linia zwiniętego ciągu, z identyfikatorem do `--rozwin`.

    Identyfikator jest w nawiasie i jest STABILNY — zadziała, gdy ktoś wklei go do rozmowy
    i użyje godzinę później, choćby oś zdążyła urosnąć od końca.
    """
    od, do = _godzina(grupa.get("od")), _godzina(grupa.get("do"))
    zakres = od if od == do else f"{od}–{do}"
    ile = int(grupa.get("ile") or 0)
    rodzaje = podpis_rodzajow(grupa.get("rodzaje") or {})
    autorzy = _odmiana_autorow(len(grupa.get("autorzy") or []))
    opis = f"{ile} zmian technicznych" + (f" ({rodzaje})" if rodzaje else "")
    return f"  {zakres:>11}  ⋯  {opis} · {autorzy}      [{str(grupa.get('id') or '')[:8]}]"


def wiersz_bloku(blok: dict, *, szerokosc: int = 96) -> str:
    """Jeden wpis osi: czas, rodzaj, autor, pierwsza linia treści."""
    tresc = (blok.get("content") or blok.get("tresc") or "").strip()
    pierwsza = tresc.splitlines()[0].strip() if tresc else ""
    rodzaj = NAZWY_RODZAJOW.get(blok.get("kind") or blok.get("rodzaj") or "",
                                blok.get("kind") or blok.get("rodzaj") or "?")
    autor = (blok.get("author_label") or blok.get("autor_etykieta") or "").strip() or "—"
    linia = f"  {_godzina(blok.get('occurred_at') or blok.get('wystapil_o')):>11}  " \
            f"{rodzaj:<12} {autor:<20} {pierwsza}"
    return linia if len(linia) <= szerokosc else linia[:szerokosc - 1].rstrip() + "…"


def wypisz(pozycje: list[dict]) -> list[str]:
    """Cała oś w liniach — z nagłówkiem dnia przy każdej zmianie daty.

    Nagłówek dnia nie jest ozdobą: bez niego oś obejmująca tydzień pokazuje same godziny
    i „12:04" trzy razy pod rząd wygląda jak trzy zdarzenia z tej samej chwili.
    """
    linie: list[str] = []
    ostatni_dzien = None
    for p in pozycje:
        dzien = _dzien(p.get("od") if jest_grupa(p)
                       else (p.get("occurred_at") or p.get("wystapil_o")))
        if dzien != ostatni_dzien:
            linie.append(f"\n── {dzien} " + "─" * 40)
            ostatni_dzien = dzien
        linie.append(wiersz_grupy(p) if jest_grupa(p) else wiersz_bloku(p))
    return linie
