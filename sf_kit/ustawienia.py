"""`sf-kit ustawienia` — ustawienia lokalne Kita i ustawienia konta w SF w jednym poleceniu (SF-173).

v1.1.0 (02.10.2026) - APro Agents / borys-sf · SF-170: `pracuje_dla` = e-mail sprawdzany w SF
v1.0.0 (02.10.2026) - APro Agents / borys-sf · projekt: wpis 7fde1fad na SF-173

PO CO
═════
Damian (01.10): Kit ma mieć ustawienia, które agent może zmieniać, a w szczególności poziom
powiadomień swój i swojego człowieka. Ustawienia żyją w DWÓCH miejscach i polecenie mówi wprost,
które jest które:

- **lokalne** (ten komputer, plik Kita): `organizacja`, `auto_update`, `pracuje_dla` (SF-170);
- **w SF** (konto): `powiadomienia.poziom` = `cisza | wazne | wszystko`. Co znaczy „ważne",
  decyduje SF (`katalog_spraw`), nie Kit — inaczej każda wersja Kita miałaby własne „ważne".

ŹRÓDŁO WARTOŚCI (SF-202)
════════════════════════
Przy każdym zdarzeniu Kit pokazuje, SKĄD wzięła się wartość (`preferencja`, `domyślne`,
`obowiązkowe`, `wyciszenie`). Bez tego nikt nie zrozumie, czemu dostał maila.

CUDZE USTAWIENIA
════════════════
`--czlowiek` (człowiek z `pracuje_dla`) albo `--osoba <id konta>`. SF wpuszcza tylko za ZGODĄ tej
osoby (przełącznik w jej profilu) albo admina Organizacji; odmowę tłumaczymy po polsku, a osoba
dostaje od SF zawiadomienie o każdej zmianie, której nie zrobiła sama.
"""
from __future__ import annotations

from dataclasses import fields

from .api import BladAPI, BrakUprawnienia

POZIOMY = ("cisza", "wazne", "wszystko")
KANALY = ("email", "in_app", "push")
KLUCZ_POZIOMU = "powiadomienia.poziom"

#: Ustawienia lokalne, które polecenie pozwala zmienić (reszta pliku = `sf-kit init`).
LOKALNE = {
    "organizacja": "domyślna Organizacja (slug)",
    "auto_update": "off | patch — samoczynne poprawki u workera",
    "pracuje_dla": "e-mail człowieka, dla którego pracuje asystent (SF-170; sprawdzany w SF)",
}
AUTO_UPDATE = ("off", "patch")

ZRODLA = {
    "preferencja": "ustawione",
    "preferencja_wszystkich": "ustawione dla wszystkich",
    "domyslne_katalogu": "domyślne",
    "domyslne_poziomu": "domyślne",
    "obowiazkowe": "obowiązkowe",
    "wyciszenie": "wyciszone",
}

ZGODA_PODPOWIEDZ = (
    "SF odmówił: zmiana cudzych powiadomień wymaga zgody tej osoby albo roli admina.\n"
    "Osoba włącza zgodę sama: Ustawienia → Powiadomienia → „Pozwól asystentowi zarządzać "
    "moimi powiadomieniami” (w SF: nadanie `notifications:manage:by-agent` na członkostwie).")


def _kanaly(lista) -> str:
    return ", ".join(lista) if lista else "—"


def pokaz_lokalne(konf, plik) -> list[str]:
    wiersze = [f"Ustawienia lokalne (ten komputer, {plik}):"]
    znane = {f.name for f in fields(konf)}
    for klucz, opis in LOKALNE.items():
        wartosc = getattr(konf, klucz, None) if klucz in znane else None
        wiersze.append(f"  {klucz:<14} {wartosc if wartosc not in (None, '') else '(nie ustawione)'}"
                       f"   — {opis}")
    return wiersze


def pokaz_sf(stan: dict, *, kogo: str) -> list[str]:
    poziom = stan.get("poziom")
    opis_poziomu = {"domyslny": "domyślny (nic nie ustawiono)", None: "własny układ"}.get(poziom, poziom)
    wiersze = [f"Ustawienia w SF — {kogo}:",
               f"  {KLUCZ_POZIOMU:<22} {opis_poziomu}"
               f"{'   (WYCISZONE w całości)' if stan.get('wyciszona') else ''}",
               f"  podsumowanie            {(stan.get('podsumowanie') or {}).get('rytm', '?')}",
               "", f"  {'zdarzenie':<28} {'kanały':<22} skąd"]
    for p in stan.get("pozycje") or []:
        if p.get("grupa") != "sprawy" and not p.get("wazne"):
            continue
        wiersze.append(f"  {str(p.get('etykieta'))[:28]:<28} {_kanaly(p.get('kanaly')):<22} "
                       f"{ZRODLA.get(p.get('zrodlo'), p.get('zrodlo'))}")
    if stan.get("nadpisania_regul"):
        wiersze.append(f"\n  Uwaga: {stan['nadpisania_regul']} ustawień pojedynczych reguł — na konkretnej "
                       "sprawie wynik może być inny (tryb i macierz obserwującego też).")
    if "zgoda_na_automat" in stan:
        wiersze.append(f"  zgoda na zarządzanie przez asystenta: {'tak' if stan['zgoda_na_automat'] else 'nie'}")
    return wiersze


def zmien_lokalne(konf, klucz: str, wartosc: str) -> str:
    """Zmień ustawienie lokalne na obiekcie konfiguracji; oddaje opis zmiany. `ValueError` przy złej."""
    if klucz not in LOKALNE:
        raise ValueError(f"nieznane ustawienie lokalne: {klucz} (znane: {', '.join(LOKALNE)})")
    if klucz == "auto_update" and wartosc not in AUTO_UPDATE:
        raise ValueError(f"auto_update: {' albo '.join(AUTO_UPDATE)}")
    stara = getattr(konf, klucz, None)
    setattr(konf, klucz, wartosc or None)
    return f"{klucz}: {stara or '(nie ustawione)'} → {wartosc or '(nie ustawione)'}"


def kanaly_z_argumentu(tekst: str | None) -> list[str] | None:
    if not tekst:
        return None
    lista = [k.strip() for k in tekst.split(",") if k.strip()]
    obce = [k for k in lista if k not in KANALY]
    if obce:
        raise ValueError(f"--kanaly: dozwolone {', '.join(KANALY)} (nieznane: {', '.join(obce)})")
    return lista


def pokaz_historie(wpisy: list[dict]) -> list[str]:
    if not wpisy:
        return ["Historia: brak zmian (albo zmiany sprzed SF-173, bez szczegółów)."]
    wiersze = ["Historia zmian (najnowsze pierwsze):"]
    for w in wpisy:
        przed = (w.get("przed") or {}).get("poziom")
        po = (w.get("po") or {}).get("poziom")
        zmiana = f"poziom {przed or 'własny'} → {po or 'własny'}" if (w.get("przed") or w.get("po")) \
            else "(bez szczegółów)"
        wiersze.append(f"  {str(w.get('kiedy'))[:16]}  {w.get('kto') or '?'}  {zmiana}"
                       f"{'  · ' + w['opis'] if w.get('opis') else ''}")
    return wiersze


def odmowa_po_polsku(blad: BladAPI) -> str:
    """403 na cudzych ustawieniach = brak zgody osoby; mówimy, jak ją włączyć, a nie samo „403"."""
    if isinstance(blad, BrakUprawnienia) or getattr(blad, "kod", None) == 403:
        return ZGODA_PODPOWIEDZ
    return str(blad)
