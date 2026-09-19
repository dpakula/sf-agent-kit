"""Samoodnowienie klucza — Kit wymienia sekret, zanim ten wygaśnie (ADVERTPR-779, zakres B).

v0.7.0 (19.09.2026) - APro Agents / borys-sf

PO CO
═════
Klucz agenta żyje 30 dni. Bez tego modułu każda flota ma comiesięczną awarię o godzinie,
której nikt nie wybierał: worker przestaje brać zadania, a człowiek dowiaduje się z ciszy.
Od v0.5.5 Kit przynajmniej OSTRZEGA siedem dni wcześniej. Tu robi krok dalej — wymienia
sekret sam, jeśli SF na to pozwala.

ZAPIS PRZED WSZYSTKIM INNYM
SF odnawia klucz „jednym żywym sekretem": w chwili odpowiedzi stary jest martwy. Cała ta
funkcja istnieje po to, żeby między odebraniem nowego sekretu a zapisaniem go w pęku nie
działo się NIC, co mogłoby się wywrócić — żadnego logowania, formatowania dat ani sprawdzania
kształtu odpowiedzi. Najpierw zapis, potem reszta. Gdyby proces zginął po odpowiedzi,
a przed zapisem, agent traci dostęp bezpowrotnie i musi prosić człowieka o nowy klucz.

DECYDUJE SERWER, NIE KIT
Kit nie sprawdza, czy wolno mu się odnowić — próbuje i czyta odpowiedź. Uprawnienie
(`keys:self-renew`) i okno T-7 liczy SF; gdyby Kit liczył je drugi raz, po pierwszej zmianie
reguły jedna z tych dwóch arytmetyk byłaby nieprawdziwa i nikt by nie wiedział która.
Odmowa SF jest odpowiedzią, nie awarią: wraca jako zdanie dla człowieka.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from . import api, klucz as magazyn_klucza, tozsamosc as mod_tozsamosc


@dataclass
class Wynik:
    """Co się stało z kluczem. `zdanie` jest dla człowieka — do dziennika albo na ekran."""
    odnowiony: bool
    zdanie: str
    #: Gdzie sekret został zapisany (opis z magazynu). Pusty, gdy nic się nie zmieniło.
    gdzie: str = ""


def _powod_z_odpowiedzi(blad: api.BladAPI) -> str:
    """Zdanie, które SF napisał po polsku — z ciała odpowiedzi, nie z mapy kodów Kitu.

    Mapa kodów w `api.py` tłumaczy 409 na „ktoś zmienił ten obiekt przed tobą", a 429 na
    „serwer nie dał rady" — przy odnowieniu oba są nieprawdą. Tutaj każdy z tych kodów ma
    konkretne znaczenie i SF opisuje je w polu `detail`; kod jest tylko kopertą.
    """
    try:
        dane = json.loads(blad.szczegoly or "{}")
    except (ValueError, TypeError):
        return str(blad)
    szczegol = dane.get("detail")
    if isinstance(szczegol, str) and szczegol.strip():
        return szczegol.strip()
    return str(blad)


def rotuj(klient, *, zapis=None) -> Wynik:
    """Poproś SF o nowy sekret dla klucza, którym właśnie mówimy, i zapisz go.

    Zwraca `Wynik`; wyjątki wypuszcza tylko wtedy, gdy nie da się powiedzieć nic sensownego
    (brak sieci) — o tym decyduje wołający, bo worker ma pracować dalej, a człowiek przy
    terminalu chce zobaczyć błąd.
    """
    zapis = zapis or magazyn_klucza.zapisz

    toz = mod_tozsamosc.z_odpowiedzi(klient.kim_jestem())
    identyfikator = getattr(toz, "klucz_id", None)
    if not identyfikator:
        return Wynik(False,
                     "Ta wersja SalesForge nie podaje identyfikatora klucza, więc nie mam jak "
                     "wskazać, który odnowić. Poproś o przedłużenie człowieka.")

    try:
        odpowiedz = klient.odnow_klucz(identyfikator)
    except api.BladAPI as blad:
        return Wynik(False, _powod_z_odpowiedzi(blad))

    nowy = (odpowiedz or {}).get("api_key")
    if not nowy:
        # Serwer odpowiedział 200 bez sekretu — stary jest już martwy, a nowego nie ma.
        # Mówimy to wprost, bo to jedyna sytuacja, w której agent traci dostęp mimo sukcesu.
        return Wynik(False,
                     "SalesForge przyjął odnowienie, ale nie przysłał nowego sekretu. "
                     "Stary klucz najprawdopodobniej już nie działa — poproś o nowy.")

    # ZAPIS. Przed logowaniem, przed datami, przed czymkolwiek (patrz nagłówek).
    gdzie = zapis(nowy)

    # Dopiero teraz wolno się wywrócić: sekret jest na dysku.
    podmien = getattr(klient, "podmien_klucz", None)
    if callable(podmien):
        podmien(nowy)                    # żeby BIEŻĄCY proces mówił już nowym sekretem

    termin = str((odpowiedz or {}).get("expires_at") or "")[:10]
    do_kiedy = f" Ważny do {termin}." if termin else ""
    return Wynik(True,
                 f"Klucz odnowiony sam: {magazyn_klucza.skrot(nowy)}.{do_kiedy} "
                 f"Zapisany w: {gdzie}.",
                 gdzie=gdzie)
