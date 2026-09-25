"""Flow odpowiedzi i treści w wersjach (SF-51, ADVERTPR-948).

v0.1 (25.09.2026) - APro Agents / kimi-autor-dpakula

PO CO TEN MODUŁ
Kontrakt: wpis borysa 7d7767ce na SF-51 (gałąź backendu `borys/sf51-publikacja-zgoda`).
Powód powstania jest incydent, nie wygodnik: 25.09 Wójt, prowadząc sprawę FMXA-1, założył
NOWĄ sprawę w złej Organizacji zamiast odpowiedzieć w istniejącej. Stąd trzy twarde reguły:

1. ZAPIS WYMAGA JAWNEJ ORGANIZACJI. Żadnej domyślnej z pliku, żadnej „jedyna z nadaniami".
   Dwie jedyne drogi: flaga `--org <slug>` albo Organizacja wyciągnięta z linku do sprawy
   (`?org=`). Wybór Organizacji przy zapisie zapada po stronie człowieka, nie Kitu.
2. LINK DO SPRAWY TO ADRES, POD KTÓRYM COŚ JUŻ ISTNIEJE. Kto prowadzi rozmowę w sprawie,
   odpowiada w niej (`sf-kit odpowiedz <link>`), a nie zakłada obok drugą.
3. TREŚĆ IDZIE W WERSJACH. Długi opis na sprawie nie jest aktualizowany w miejscu —
   kolejne wersje idą jako załączniki `nazwa-vN.md` z wpisem „co się zmieniło", a strażnik
   pilnuje, żeby nikt nie nadpisał opisu dłuższego niż 1500 znaków, gdy sprawa już opis ma.

CO TU SIEDZI
Wyłącznie reguły czyste (parsowanie linków, numeracja wersji, diff, strażnik, szkic).
Wołania API są w `api.Klient`, wypisywanie na ekran w `cli`.
"""
from __future__ import annotations

import difflib
import re
from urllib.parse import parse_qs, urlparse

#: Zdanie, którym Kit ostrzega przy KAŻDYM zapisie na sprawie-brykie (pkt 6 kontraktu SF-51).
#: W brzmieniu z kontraktu — dosłownie, bo tak ma je zasłyszeć człowiek.
OSTRZEZENIE_SZKICU = ("UWAGA: to jest SZKIC — szkic nie wychodzi do obiegu; członkowie "
                      "Organizacji widzą go tylko po linku.")

#: Statusy, po których poznajemy sprawę w wersji roboczej. `GET /tickets/{id}` nie niesie
#: osobnego znacznika szkicu — jest tylko `status`, więc zestaw rozpoznawczy trzymamy tutaj
#: i rozszerzamy, gdy backend powie, jaką wartością zapisuje szkic na PROD.
STATUSY_SZKICU = frozenset({"draft", "szkic", "robocza", "roboczy"})

_UUID = ("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
         "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
#: Link do sprawy w SF: host dowolny (makieta lokalna też), ścieżka `/tickets/<uuid>`,
#: query opcjonalne. Nie kotwiczymy na sf.dpakula.pl — testy i staging mają swoje hosty.
WZORZEC_LINKU = re.compile(rf"https?://[^\s/?#]+/tickets/(?P<id>{_UUID})(?P<query>[?][^\s#]*)?")

#: `nazwa.md` → (`nazwa`, `.md`). Koncówka z kropką, bo tak sklejamy nazwę wersji z powrotem.
WZORZEC_WERSJI = re.compile(r"^(?P<bazowa>.+)-v(?P<n>\d+)(?P<koncowka>(?:\.[A-Za-z0-9]+)*)$")

#: Strażnik opisu: dłuższy od tego PATCH na sprawie, która już opis ma, to nie aktualizacja —
#: to zasłonięcie historii treści (pkt 4 kontraktu SF-51).
MAX_OPISU_STRAZNIK = 1500


def link_z_tekstu(tekst: str) -> str | None:
    """Pierwszy link do sprawy SF w dowolnym tekście (kontekst zadania, wklejona rozmowa)."""
    trafienie = WZORZEC_LINKU.search(tekst or "")
    return trafienie.group(0) if trafienie else None


def sprawa_z_linku(tekst: str) -> str | None:
    """Identyfikator sprawy z linku — albo `None`, gdy tekst linkiem do sprawy nie jest."""
    trafienie = WZORZEC_LINKU.search(tekst or "")
    return trafienie.group("id") if trafienie else None


def organizacja_z_linku(tekst: str) -> str | None:
    """`?org=<slug>` z linku do sprawy. Link bez parametru daje `None` — to nie błąd,
    tylko informacja „jawności trzeba szukać gdzie indziej" (flaga --org)."""
    trafienie = WZORZEC_LINKU.search(tekst or "")
    if not trafienie:
        return None
    query = parse_qs(urlparse("https://x" + (trafienie.group("query") or "")).query)
    wartosci = query.get("org") or []
    return wartosci[0].strip() or None if wartosci else None


def czy_szkic(sprawa: dict) -> bool:
    """Czy karta sprawy mówi, że to wersja robocza. Pola `szkic`/`is_draft` sprawdzamy
    PRZED statusem: gdy backend dołoży znacznik, nie będziemy czekać na nowe wydanie Kitu."""
    if sprawa.get("szkic") is True or sprawa.get("is_draft") is True:
        return True
    return str(sprawa.get("status") or "").strip().lower() in STATUSY_SZKICU


def podziel_nazwe(plik: str) -> tuple[str, str]:
    """`raport.md` → (`raport`, `.md`). Bez rozszerzenia → koncówka pusta, nie `.md` zgadywane."""
    nazwa = str(plik).rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." not in nazwa.lstrip("."):
        return nazwa, ""
    bazowa, _, koncowka = nazwa.rpartition(".")
    return bazowa, "." + koncowka


def nazwa_wersji(bazowa: str, koncowka: str, n: int) -> str:
    return f"{bazowa}-v{n}{koncowka}"


def nastepna_wersje(nazwy_zalacznikow: list[str], bazowa: str, koncowka: str) -> int:
    """Numer NASTĘPNEJ wersji: jeden powyżej najwyższej istniejącej `bazowa-vN.koncowka`.
    Pusta historia daje 1 — nie zgadujemy numeru po dacie, bo kolejność wersji jest liczbowa."""
    najwyzsza = 0
    for nazwa in nazwy_zalacznikow:
        trafienie = WZORZEC_WERSJI.match(str(nazwa or ""))
        if not trafienie:
            continue
        if trafienie.group("bazowa") == bazowa and trafienie.group("koncowka") == koncowka:
            najwyzsza = max(najwyzsza, int(trafienie.group("n")))
    return najwyzsza + 1


def podsumowanie_zmian(stara: str, nowa: str) -> str:
    """Jedno zdanie „co się zmieniło" liczone z różnicy względem poprzedniej wersji.

    `tresc-wersja` bez `--zmiany` ma i tak powiedzieć czytelnikowi coś prawdziwego — liczba
    dodanyych i usuniętych wierszy jest gorsza od ludzkiego opisu, ale lepsza od milczenia.
    """
    if stara == nowa:
        return "treść identyczna z poprzednią wersją"
    dodane = usuniete = 0
    for wiersz in difflib.unified_diff(stara.splitlines(), nowa.splitlines(), lineterm=""):
        if wiersz.startswith("+") and not wiersz.startswith("+++"):
            dodane += 1
        elif wiersz.startswith("-") and not wiersz.startswith("---"):
            usuniete += 1
    return f"+{dodane}/−{usuniete} wierszy względem poprzedniej wersji"


def straznik_opisu(obecny: str, nowy: str) -> str | None:
    """Ostrzeżenie, gdy PATCH opisu zasłoniłby istniejącą treść — albo `None`, gdy przechodzi.

    Reguła jest celowo jednostronna: pusta sprawa może dostać długi opis (inicjalizacja
    treścią), ale sprawa, która opis MA, dostaje go już tylko w wersjach — nadpisanie
    długim tekstem ucina historię tego, co było, i nie daje się cofnąć.
    """
    if not (obecny or "").strip() or len(nowy or "") <= MAX_OPISU_STRAZNIK:
        return None
    return (f"Opis ma {len(nowy)} znaków (powyżej {MAX_OPISU_STRAZNIK}) i ta sprawa już opis "
            f"ma — nadpisanie go w całości ucina dotychczasową treść.\n"
            f"Oddawaj treść w wersjach: `sf-kit tresc-wersja <sprawa> <plik.md>` — plik pójdzie "
            f"jako załącznik `nazwa-vN.md` z wpisem «co się zmieniło», a opis zostaje "
            f"wskazówką do całości.\n"
            f"Gdy mimo wszystko opis ma zostać podmieniony, powtórz polecenie z `--mimo-to`.")
