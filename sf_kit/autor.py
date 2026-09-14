"""Profil AUTOR — agent PCHA do SalesForge gotową pracę człowieka (v0.3).

v0.3 (15.09.2026) - APro Agents / borys-sf

RÓŻNICA WOBEC WORKERA, W JEDNYM ZDANIU
Worker CIĄGNIE zadania z kolejki i je wykonuje. Autor pracuje obok człowieka i **zgłasza
wynik**: postęp wpisami, a gotową rzecz — nową sprawą z plikami.

CO TU SIEDZI
Reguły, które nie zależą od tego, czy woła je polecenie, czy coś innego: jak nazywa się
sprawa („FM-12"), jak rozpoznać ją po tym, co podał człowiek, i co wpisać w opis, gdy
podał sam tytuł. Wywołania API są w `api.Klient`, wypisywanie na ekran w `cli`.

DLACZEGO OSOBNY MODUŁ, A NIE FUNKCJE W CLI
Bo narzędzie `sf` dla człowieka (ADVERTPR-787) ma być CIENKĄ nakładką na to samo. Reguła
zapisana w funkcji obsługującej polecenie byłaby nie do użycia bez udawania wiersza poleceń.
"""
from __future__ import annotations

import re

#: Tak wygląda numer sprawy podany przez człowieka: `FM-12`, `advertpr-777`, `777`.
#: Prefiks bywa pisany małymi literami — to jest to samo zgłoszenie.
WZORZEC_NUMERU = re.compile(r"^\s*(?:([A-Za-z][A-Za-z0-9]*)-)?(\d+)\s*$")

#: Identyfikator techniczny. Rozpoznajemy go, żeby nie szukać sprawy po liście, gdy człowiek
#: (albo skrypt) poda wprost UUID.
WZORZEC_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def numer_sprawy(sprawa: dict) -> str:
    """`FM-12` — nazwa sprawy do pokazania człowiekowi. Pusty napis, gdy sprawa jej nie ma."""
    prefiks = (sprawa.get("ticket_prefix") or "").strip()
    numer = sprawa.get("ticket_number")
    if not numer:
        return ""
    return f"{prefiks}-{numer}" if prefiks else str(numer)


def adres_sprawy(sprawa_id: str, *, baza: str) -> str:
    """Adres sprawy w przeglądarce. Liczony, nigdy nie zapisywany — jak `url` boxa w SF."""
    return f"{baza.rstrip('/')}/tickets/{sprawa_id}"


def znajdz_sprawe(klient, wskazanie: str) -> dict:
    """Sprawa wskazana numerem (`FM-12`, `12`) albo identyfikatorem. Rzuca, gdy nie ma jednej.

    NUMER ROZWIĄZUJEMY PRZEZ LISTĘ, bo SalesForge nie ma dziś odczytu po numerze — to jest
    obejście i tak ma być opisane, nie ukryte. Cena: jedno pytanie o listę spraw.

    Sam numer bez prefiksu (`12`) jest dopuszczony, bo tak ludzie mówią w rozmowie. Jeśli
    pasuje wtedy więcej niż jedna sprawa, ODMAWIAMY i wypisujemy kandydatów — dopisanie
    postępu do niewłaściwej sprawy jest nie do odróżnienia od poprawnej pracy.
    """
    wskazanie = (wskazanie or "").strip()
    if WZORZEC_UUID.match(wskazanie):
        return {"id": wskazanie}

    trafienie = WZORZEC_NUMERU.match(wskazanie)
    if not trafienie:
        raise ValueError(
            f"nie rozumiem „{wskazanie}” — podaj numer sprawy (np. FM-12) "
            f"albo jej identyfikator.")

    prefiks, numer = trafienie.group(1), int(trafienie.group(2))
    kandydaci = [
        s for s in klient.sprawy(limit=200)
        if s.get("ticket_number") == numer
        and (prefiks is None
             or (s.get("ticket_prefix") or "").lower() == prefiks.lower())
    ]
    if not kandydaci:
        raise ValueError(
            f"nie znalazłem sprawy „{wskazanie}” w tej Organizacji. "
            f"Sprawdź `sf-kit sprawy`; być może należy do innej.")
    if len(kandydaci) > 1:
        nazwy = ", ".join(numer_sprawy(s) for s in kandydaci)
        raise ValueError(
            f"„{wskazanie}” pasuje do kilku spraw ({nazwy}) — podaj numer z prefiksem.")
    return kandydaci[0]


#: Układ opisu zgłoszenia. Trzy pytania, na które odbiorca i tak musi odpowiedzieć sobie sam,
#: gdy ich nie ma: co to jest, co dokładnie dostaję i jak to u siebie otworzyć.
SZABLON_OPISU = """**Sedno** — {tytul}.

**Co jest** — (co powstało: ile stron/widoków, w czym zrobione, czego NIE obejmuje)

**Jak odebrać** — (od którego pliku zacząć, czego potrzeba do otwarcia, na co zwrócić uwagę)
"""


def opis_domyslny(tytul: str) -> str:
    """Szkielet opisu, gdy człowiek podał sam tytuł.

    Pusty opis jest gorszy niż szkielet z nawiasami: przy szkielecie widać, czego brakuje,
    i widać to ZANIM zgłoszenie pójdzie dalej. Agent, który dostaje sam tytuł, ma te trzy
    rzeczy dopisać — README mówi mu to wprost.
    """
    return SZABLON_OPISU.format(tytul=tytul.rstrip("."))


def czy_opis_wymaga_uzupelnienia(opis: str) -> bool:
    """Czy w opisie zostały nawiasy ze szkieletu — czyli czy ktoś go nie wypełnił.

    Kit tego nie blokuje: bywa, że tytuł wystarcza, a zgłoszenie z pustymi nawiasami jest
    i tak lepsze niż praca, o której nikt nie wie. Ale mówi o tym na ekranie, żeby człowiek
    zdecydował świadomie.
    """
    return "(co powstało" in opis or "(od którego pliku" in opis


def ostatnia_zmiana(sprawa: dict) -> str:
    """Kiedy sprawa ostatnio drgnęła — `RRRR-MM-DD GG:MM` albo pusty napis.

    `ostatnia_edycja` jest SŁOWNIKIEM (kto, kiedy, awatar), nie napisem — pierwsza wersja
    tego kodu próbowała je pociąć jak tekst i wywracała `sf-kit sprawy` wyjątkiem
    `KeyError: slice(...)`. Żaden test jednostkowy tego nie widział, bo wszystkie karmiły
    funkcje uproszczonym kształtem sprawy; złapał to dopiero test odbiorczy na prawdziwych
    danych. Stąd ta funkcja: jedno miejsce, które zna prawdziwy kształt.
    """
    edycja = sprawa.get("ostatnia_edycja")
    kiedy = edycja.get("kiedy") if isinstance(edycja, dict) else edycja
    kiedy = kiedy or sprawa.get("updated_at") or ""
    return str(kiedy)[:16].replace("T", " ")
