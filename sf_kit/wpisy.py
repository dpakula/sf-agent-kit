"""Poprawianie wpisów na sprawie i ich historia wersji (ADVERTPR-782).

v0.1 (24.09.2026) - APro Agents / borys-sf
Kontrakt po stronie SF: `backend/docs/API-WPISY-WERSJE.md` (arek, 15.09) — trasy
`PATCH /tickets/{id}/entries/{eid}` (`content`, `reason`) i `GET …/entries/{eid}/versions`.
Nazwy tras i pól są TE SAME co w API (decyzja D1, Agata 24.09): druga nazwa tej samej rzeczy
w Kicie byłaby rozjazdem, którego zasada 14.09 zabrania.

JAK CZYTAĆ HISTORIĘ — I DLACZEGO KIT MÓWI TO WPROST
═══════════════════════════════════════════════════
Wiersz historii to stan **SPRZED** zmiany; bieżąca treść jest na samym wpisie (decyzja arka
z 15.09). Autor i data wiersza mówią więc, KTO I KIEDY TEN STAN ZASTĄPIŁ — nie kto go napisał.
Wypisanie „v1 · Borys · 10:00" czytałoby się jak „Borys napisał v1", a to nieprawda za każdym
razem, gdy poprawia się cudzy wpis. Stąd forma „zastąpiona … przez …".

SKRÓT IDENTYFIKATORA WPISU
Wpisy podajemy w rozmowie skrótem (`dba3ae21`), bo tak je pokazują Kit i wpisy. Skrót
rozwijamy po dzienniku sprawy — i ODMAWIAMY, gdy pasuje do dwóch wpisów: poprawienie nie
tego wpisu zostawia w historii cudzej wypowiedzi ślad, którego nikt nie skasuje.
"""
from __future__ import annotations

import re

#: Skrót musi być na tyle długi, żeby w realnej sprawie wskazywał jeden wpis. Sześć znaków
#: szesnastkowych to 16,7 mln możliwości — przy kilkuset wpisach sprawy kolizja jest rzadka,
#: a gdy się zdarzy, `rozwin_wpis` ją nazywa.
MIN_SKROT = 6

#: Limity pól z `EntryPatch` w SF (`content` max 20000, `reason` max 500) — sprawdzane PRZED
#: wysyłką, żeby odmowa mówiła po ludzku, a nie przez 422 z drukiem pola.
MAX_TRESC = 20000
MAX_POWOD = 500

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_SKROT = re.compile(r"^[0-9a-fA-F-]+$")

#: Ile stron dziennika przeglądamy przy rozwijaniu skrótu (po 200) — sufit, nie pętla bez końca.
MAX_STRON = 25
NA_STRONE = 200


class ZlyWpis(ValueError):
    """Wskazanie wpisu nie prowadzi do jednego wpisu. Komunikat jest gotowy do pokazania."""


def czy_pelny_uuid(wskazanie: str) -> bool:
    """Czy wskazanie jest pełnym identyfikatorem wpisu. Tego NIE rozwijamy lokalnie —
    pełny identyfikator (np. zgoda z innej sprawy tej Organizacji) przechodzi do serwera
    bez odpytywania dziennika; to serwer sprawdzi, czy wpis istnieje i czy się nadaje."""
    return bool(_UUID.match((wskazanie or "").strip().lower()))


def rozwin_wpis(klient, sprawa_id: str, wskazanie: str) -> str:
    """Pełny identyfikator wpisu z pełnego id albo ze skrótu (≥ `MIN_SKROT` znaków)."""
    w = (wskazanie or "").strip().lower()
    if _UUID.match(w):
        return w
    if not _SKROT.match(w) or len(w.replace("-", "")) < MIN_SKROT:
        raise ZlyWpis(f"„{wskazanie}” nie wygląda na identyfikator wpisu — podaj pełny "
                      f"identyfikator albo jego początek (co najmniej {MIN_SKROT} znaków).")
    trafienia: list[str] = []
    for strona in range(MAX_STRON):
        odp = klient.wpisy_sprawy(sprawa_id, limit=NA_STRONE, offset=strona * NA_STRONE)
        pozycje = (odp or {}).get("pozycje") or []
        trafienia += [str(p.get("id")) for p in pozycje
                      if str(p.get("id") or "").lower().startswith(w)]
        if len(pozycje) < NA_STRONE:
            break
    trafienia = list(dict.fromkeys(trafienia))
    if not trafienia:
        raise ZlyWpis(f"na tej sprawie nie ma wpisu zaczynającego się od „{wskazanie}” "
                      f"(albo nie masz do niego dostępu — poziom widoczności).")
    if len(trafienia) > 1:
        raise ZlyWpis(f"„{wskazanie}” pasuje do {len(trafienia)} wpisów "
                      f"({', '.join(t[:13] for t in trafienia)}) — podaj dłuższy skrót.")
    return trafienia[0]


def cialo_edycji(tresc: str, powod: str | None) -> dict:
    """Ciało `PATCH` — tylko pola kontraktu `EntryPatch`, `reason` wyłącznie gdy podany."""
    if not (tresc or "").strip():
        raise ZlyWpis("Pusta treść: wpis bez treści to nie edycja, tylko jego usunięcie "
                      "(tak samo odmawia SF).")
    if len(tresc) > MAX_TRESC:
        raise ZlyWpis(f"Treść ma {len(tresc)} znaków — SF przyjmuje najwyżej {MAX_TRESC}.")
    cialo: dict = {"content": tresc}
    if powod is not None and powod.strip():
        if len(powod) > MAX_POWOD:
            raise ZlyWpis(f"Powód ma {len(powod)} znaków — SF przyjmuje najwyżej {MAX_POWOD}.")
        cialo["reason"] = powod.strip()
    return cialo


def _kiedy(wartosc) -> str:
    return (str(wartosc or "?").replace("T", " "))[:16]


def historia_do_pokazania(wpis: dict, wersje: list[dict], *, skrot: int = 160) -> str:
    """Bieżąca treść + wersje od najnowszej. Treść skracana do `skrot` znaków (0 = całość)."""
    def _tnij(t) -> str:
        plaska = " ".join(str(t or "").split())
        return plaska if not skrot or len(plaska) <= skrot else plaska[: skrot - 1] + "…"

    ile = int(wpis.get("edited_count") or 0)
    linie = [f"Wpis {str(wpis.get('id'))[:8]} · autor: {wpis.get('author_name') or '?'} · "
             f"napisany {_kiedy(wpis.get('created_at'))}"]
    if ile:
        linie.append(f"edytowano {ile}× · ostatnio {_kiedy(wpis.get('last_edited_at'))}")
    else:
        linie.append("nie był edytowany")
    linie.append(f"\nTERAZ:\n  {_tnij(wpis.get('content'))}")
    if not wersje:
        return "\n".join(linie)
    linie.append("\nPOPRZEDNIE (od najnowszej; autor i data = KTO I KIEDY tę wersję zastąpił):")
    for v in sorted(wersje, key=lambda v: int(v.get("version_no") or 0), reverse=True):
        nr = int(v.get("version_no") or 0)
        opis = " (pierwotna)" if nr == 1 else ""
        powod = f" · powód: {v['reason']}" if v.get("reason") else ""
        linie.append(f"  v{nr}{opis} — zastąpiona {_kiedy(v.get('created_at'))} przez "
                     f"{v.get('author_name') or '?'}{powod}")
        linie.append(f"      {_tnij(v.get('content'))}")
    return "\n".join(linie)
