"""Kontekst sprawy dla wykonawcy — pliki do `inbox/<external_id>/` i blok w prompcie (SF-38).

v1.0.0 (25.09.2026) - APro Agents / borys-sf

PO CO — INCYDENT 24.09 (ADVERTPR-927)
═════════════════════════════════════
Zadanie z 13 załącznikami na sprawie (wzór IPET, przykład, 11 zdjęć orzeczenia). Worker przekazał
Codexowi SAMĄ treść zadania. Codex nie miał plików i nie ma klucza SF — skończył „blokadą".
Agata skopiowała pliki ręcznie i wystawiła zadanie drugi raz.

CO ROBI
═══════
Przed startem zadania przy sprawie:
1. czyta kartę sprawy kluczem Kita — co wolno temu kluczowi, rozstrzyga SERWER (clearance),
2. pobiera załączniki wpisów do `inbox/<external_id>/` z nazwami `NN-<nazwa>` w kolejności
   wpisów (zdjęcia orzeczenia zostają w kolejności stron), pomija już pobrane,
3. składa blok „KONTEKST SPRAWY" (opis + ostatnie wpisy + lista plików) doklejany do ramki.

CZEGO NIE ROBI
══════════════
* nie wkłada klucza do promptu — wykonawca doczytuje przez `sf-kit sprawa` / `sf-kit zalacznik`,
* nie przerywa zadania, gdy kontekstu nie da się pobrać: zadanie idzie jak przed SF-38, a braki
  są wymienione w bloku z nazwy („nie pobrano: …"), żeby wykonawca nie wziął luki za całość.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .api import BladAPI

#: Ile ostatnich wpisów idzie do promptu. Starsze są w sprawie (`sf-kit sprawa`).
ILE_WPISOW = 15
#: Ile znaków z jednego wpisu. Opis sprawy dostaje więcej — to on zwykle niesie polecenie.
LIMIT_WPISU = 1500
LIMIT_OPISU = 6000
#: Sufity pobierania — pojedynczy plik i całość. Nad nimi pomijamy Z NAZWĄ, nie po cichu.
LIMIT_PLIKU = 50 << 20
LIMIT_RAZEM = 300 << 20

KATALOG = "inbox"


@dataclass
class Pakiet:
    katalog: Path | None = None
    pliki: list[Path] = field(default_factory=list)
    pominiete: list[str] = field(default_factory=list)
    tekst: str = ""


def _bezpieczna_nazwa(nazwa: str) -> str:
    """Nazwa pliku bez ścieżek i znaków, które psują powłokę — ale czytelna dla człowieka."""
    nazwa = Path(nazwa or "plik").name
    nazwa = re.sub(r"[^\w.\-]+", "_", nazwa, flags=re.UNICODE).strip("._") or "plik"
    return nazwa[:120]


def _zalaczniki(sprawa: dict) -> list[dict]:
    """Załączniki wszystkich widocznych wpisów, w kolejności wpisów (od najstarszego)."""
    wpisy = sorted(sprawa.get("entries") or [], key=lambda e: e.get("created_at") or "")
    wynik = []
    for wpis in wpisy:
        for zal in wpis.get("attachments") or []:
            if zal.get("url") and not zal.get("storage_path") and not zal.get("filename"):
                continue                      # link, nie plik — zostaje w bloku tekstowym
            wynik.append(zal)
    return wynik


def _pobierz(klient, sprawa: dict, cel: Path, pakiet: Pakiet) -> None:
    razem = 0
    for numer, zal in enumerate(_zalaczniki(sprawa), start=1):
        nazwa = _bezpieczna_nazwa(zal.get("original_filename") or zal.get("filename") or "")
        sciezka = cel / f"{numer:02d}-{nazwa}"
        rozmiar = int(zal.get("file_size") or 0)
        if sciezka.exists() and (not rozmiar or sciezka.stat().st_size == rozmiar):
            pakiet.pliki.append(sciezka)            # druga próba tego samego zadania
            razem += sciezka.stat().st_size
            continue
        if razem + rozmiar > LIMIT_RAZEM:
            pakiet.pominiete.append(f"{nazwa} (przekroczony sufit {LIMIT_RAZEM >> 20} MB na zadanie)")
            continue
        try:
            razem += klient.pobierz_zalacznik(str(zal["id"]), sciezka, limit_bajtow=LIMIT_PLIKU)
            pakiet.pliki.append(sciezka)
        except BladAPI as blad:
            pakiet.pominiete.append(f"{nazwa} ({blad})")
        except Exception as blad:                  # noqa: BLE001 — patrz `przygotuj`
            pakiet.pominiete.append(f"{nazwa} ({type(blad).__name__}: {blad})")


def _wpis_tekstem(wpis: dict) -> str:
    autor = wpis.get("author_name") or wpis.get("author_email") or "?"
    kiedy = (wpis.get("created_at") or "")[:16].replace("T", " ")
    poziom = wpis.get("visibility") or ("internal" if wpis.get("is_internal") else "public")
    tresc = (wpis.get("content") or "").strip()
    if len(tresc) > LIMIT_WPISU:
        tresc = tresc[:LIMIT_WPISU] + f" […obcięte — {len(wpis['content'])} znaków, `sf-kit sprawa`]"
    zal = [z.get("original_filename") for z in (wpis.get("attachments") or [])]
    ogon = f"\n  (załączniki: {', '.join(n for n in zal if n)})" if zal else ""
    return f"- {kiedy} UTC · {autor} · {wpis.get('entry_type')} · {poziom}\n  {tresc or '(bez treści)'}{ogon}"


def _tekst(sprawa: dict, pakiet: Pakiet, katalog_roboczy: Path) -> str:
    numer = (f"{sprawa.get('ticket_prefix')}-{sprawa.get('ticket_number')}"
             if sprawa.get("ticket_number") else sprawa.get("id"))
    opis = (sprawa.get("description") or "").strip()
    if len(opis) > LIMIT_OPISU:
        opis = opis[:LIMIT_OPISU] + " […obcięte — całość: `sf-kit sprawa`]"
    wpisy = [e for e in sorted(sprawa.get("entries") or [], key=lambda e: e.get("created_at") or "")
             if e.get("entry_type") in ("message", "note", "attachment", "created")]
    starsze = max(0, len(wpisy) - ILE_WPISOW)
    linie = [
        "--- KONTEKST SPRAWY (pobrany przez Kit przed startem; masz go, nie zgaduj) ---",
        f"Sprawa {numer}: {sprawa.get('title') or ''}".rstrip(),
        f"Status: {sprawa.get('status')} · priorytet: {sprawa.get('priority')}",
        "", "Opis sprawy:", opis or "(brak opisu)", "",
        f"Ostatnie wpisy ({len(wpisy) - starsze} z {len(wpisy)}"
        + (f"; starsze: `sf-kit sprawa {sprawa.get('id')}`" if starsze else "") + "):",
        *[_wpis_tekstem(e) for e in wpisy[starsze:]],
    ]
    if pakiet.pliki:
        linie += ["", f"Pliki ze sprawy (pobrane do katalogu roboczego, {len(pakiet.pliki)}):",
                  *[f"- {p.relative_to(katalog_roboczy)}" for p in pakiet.pliki]]
    if pakiet.pominiete:
        linie += ["", "NIE pobrano (brak = nie masz tego pliku, nie zakładaj jego treści):",
                  *[f"- {p}" for p in pakiet.pominiete]]
    linie += ["", "Doczytanie w trakcie pracy (odczyt w zakresie tego zadania, bez klucza w prompcie):",
              f"- `sf-kit sprawa {sprawa.get('id')}` — pełna karta sprawy",
              "- `sf-kit zalacznik <id> --do <plik>` — pojedynczy załącznik",
              "--- KONIEC KONTEKSTU SPRAWY ---"]
    return "\n".join(linie)


def przygotuj(klient, zadanie: dict, *, katalog_roboczy: str | Path) -> Pakiet:
    """Pakiet kontekstu dla zadania przy sprawie. Zadanie bez sprawy → pusty pakiet."""
    ticket_id = zadanie.get("ticket_id")
    if not ticket_id:
        return Pakiet()
    katalog_roboczy = Path(katalog_roboczy)
    nazwa = _bezpieczna_nazwa(str(zadanie.get("external_id") or zadanie.get("id") or "zadanie"))
    cel = katalog_roboczy / KATALOG / nazwa
    pakiet = Pakiet(katalog=cel)
    try:
        sprawa = klient.sprawa(str(ticket_id))
    except Exception as blad:                      # noqa: BLE001
        # Każdy wyjątek, nie tylko `BladAPI`: kontekst jest DODATKIEM i jego brak nie ma prawa
        # wywrócić zadania, które przed SF-38 wykonałoby się bez niego. Typ wyjątku idzie
        # z nazwy do logu i do promptu — literówka (`AttributeError`) nie znika jako „brak sieci".
        blad = f"{type(blad).__name__}: {blad}" if not isinstance(blad, BladAPI) else str(blad)
        pakiet.pominiete.append(f"karta sprawy ({blad})")
        pakiet.tekst = ("--- KONTEKST SPRAWY ---\nNie udało się pobrać sprawy "
                        f"({blad}). Masz tylko treść zadania.\n--- KONIEC KONTEKSTU SPRAWY ---")
        return pakiet
    cel.mkdir(parents=True, exist_ok=True)
    _pobierz(klient, sprawa, cel, pakiet)
    pakiet.tekst = _tekst(sprawa, pakiet, katalog_roboczy)
    return pakiet
