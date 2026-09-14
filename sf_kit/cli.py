"""`sf-kit` — jedno polecenie, kilka poleceń podrzędnych.

v0.1 (14.09.2026) - APro Agents / borys-sf

Zasada, która rządzi tym plikiem: **komunikat ma mówić, co zrobić dalej.** Nie „błąd 403",
tylko „brakuje uprawnienia X, poproś administratora". Kit uruchamia ktoś, kto nas nie zna
i nie ma kogo zapytać o drugiej w nocy.
"""
from __future__ import annotations

import argparse
import sys

from . import WERSJA
from . import config as konfiguracja
from . import klucz as magazyn_klucza
from .api import BladAPI, Klient


def _klient(konf: konfiguracja.Konfiguracja) -> Klient:
    """Klient API albo zrozumiały komunikat i wyjście. Nigdy `KeyError` w twarz."""
    kl = magazyn_klucza.wczytaj()
    if not kl:
        raise SystemExit(
            "Nie mam klucza. Uruchom `sf-kit init` — zapyta o niego i zapisze bezpiecznie.")
    braki = konf.braki()
    if braki:
        raise SystemExit(
            "Konfiguracja jest niepełna — brakuje: " + ", ".join(braki) + ".\n"
            f"Popraw {konfiguracja.sciezka()} albo uruchom `sf-kit init` jeszcze raz.")
    return Klient(baza=konf.adres, klucz=kl, organizacja=konf.organizacja)


def polecenie_init(_args) -> int:
    """Zapytaj o klucz i o resztę ustawień. Klucz — bez echa, resztę zwyczajnie."""
    print("Konfiguracja SF Agent Kit. Enter zostawia wartość w nawiasie.\n")
    konf = konfiguracja.wczytaj()

    def pytaj(etykieta: str, teraz: str) -> str:
        podane = input(f"{etykieta} [{teraz or 'brak'}]: ").strip()
        return podane or teraz

    konf.adres = pytaj("Adres SalesForge", konf.adres)
    konf.organizacja = pytaj("Identyfikator Organizacji (X-Tenant-Id)", konf.organizacja)
    konf.slug = pytaj("Twój slug agenta w SF (np. codex-2-dpakula)", konf.slug)
    konf.katalog_roboczy = pytaj("Katalog roboczy (pusty = bieżący)", konf.katalog_roboczy)
    konf.runtime = pytaj("Wykonawca: codex albo shell", konf.runtime)

    plik = konfiguracja.zapisz(konf)
    print(f"\nUstawienia zapisane: {plik}")

    print()
    try:
        skrot, gdzie = magazyn_klucza.zapytaj_i_zapisz()
    except ValueError as blad:
        print(f"Klucz NIE został zapisany: {blad}", file=sys.stderr)
        return 1
    except RuntimeError as blad:
        print(f"Klucz NIE został zapisany: {blad}", file=sys.stderr)
        return 1

    print(f"Klucz {skrot} zapisany: {gdzie}")
    print("\nSprawdź, czy działa: sf-kit whoami")
    return 0


def polecenie_whoami(_args) -> int:
    """Sonda klucza. SalesForge nie ma endpointu „kim jestem" — więc próbujemy odczytu."""
    konf = konfiguracja.wczytaj()
    kl = magazyn_klucza.wczytaj()
    if not kl:
        raise SystemExit("Nie mam klucza. Uruchom `sf-kit init`.")

    print(f"klucz:        {magazyn_klucza.skrot(kl)}")
    print(f"adres:        {konf.adres}")
    print(f"Organizacja:  {konf.organizacja or '(nie ustawiona)'}")
    print(f"mój slug:     {konf.slug or '(nie ustawiony)'}")

    braki = konf.braki()
    if braki:
        print("\nKonfiguracja niepełna — brakuje: " + ", ".join(braki))
        return 1

    wynik = Klient(baza=konf.adres, klucz=kl, organizacja=konf.organizacja).sprawdz_klucz()
    print(f"\nodczyt zadań: {wynik.get('odczyt_zadan')}")
    if wynik.get("zadan_widocznych"):
        print(f"zadania:      {wynik['zadan_widocznych']}")

    # Data ważności klucza. SalesForge nie oddaje jej dziś posiadaczowi klucza — i to jest
    # zgłoszona luka, nie nasza niewiedza. Jedna linia: `whoami` ma być odczytem stanu,
    # a nie miejscem na wykład (pełne wyjaśnienie → README, „Ograniczenia wersji 0.2").
    print("ważny do:     brak danych z API — patrz README, „Ograniczenia wersji 0.2”.")
    print("\nZmian statusu nie sonduję — README, sekcja „Kiedy coś nie działa”.")
    return 0 if "NIE DZIAŁA" not in str(wynik.get("odczyt_zadan")) else 1


def polecenie_tasks(_args) -> int:
    """Moje zadania w kolejce."""
    konf = konfiguracja.wczytaj()
    klient = _klient(konf)
    try:
        wynik = klient.moje_zadania(slug=konf.slug)
    except BladAPI as blad:
        print(f"Nie udało się pobrać zadań: {blad}", file=sys.stderr)
        return 1

    if not wynik:
        print(f'Brak zadań w kolejce dla agenta „{konf.slug}”'
              f' (przejrzano {wynik.przejrzano} z {wynik.wszystkich} pozycji kolejki).')
        if wynik.urwane:
            print("UWAGA: przeglądanie urwał bezpiecznik stron — to NIE jest pewne „brak zadań”.")
        return 0
    print(f'Zadania w kolejce dla „{konf.slug}” ({len(wynik)} '
          f'z {wynik.wszystkich} pozycji kolejki):\n')
    for z in wynik:
        sprawa = z.get("ticket_ref") or z.get("ticket_id") or "— bez sprawy"
        print(f"  {z.get('external_id')}")
        print(f"    {z.get('title')}")
        print(f"    sprawa: {sprawa}   id: {z.get('id')}")
    return 0


def polecenie_worker(args) -> int:
    from .worker import uruchom
    konf = konfiguracja.wczytaj()
    klient = _klient(konf)
    if args.runtime:
        konf.runtime = args.runtime
    if args.interval:
        konf.odstep_s = args.interval

    if konf.runtime == "shell" and not konf.zezwol_shell:
        raise SystemExit(
            "Wykonawca `shell` jest wyłączony.\n\n"
            "`shell` wykonuje treść zadania JAK POLECENIE POWŁOKI na tej maszynie. Służy\n"
            "wyłącznie do sprawdzenia, czy cała pętla działa bez modelu — nie do pracy.\n\n"
            "Jeśli naprawdę tego chcesz, dopisz do pliku ustawień\n"
            f"  {konfiguracja.sciezka()}\n"
            '  "zezwol_shell": true\n\n'
            "Do zwykłej pracy użyj `--runtime codex`.")
    return uruchom(klient, konf, raz=args.once)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sf-kit",
        description="SF Agent Kit — odbieraj zadania z SalesForge, wykonuj je, raportuj.")
    # `--version` przed podkomendami: pierwsze pytanie przy każdym zgłoszeniu brzmi „która
    # wersja u ciebie stoi", a odpowiedź „nie wiem" kosztuje rundę korespondencji.
    parser.add_argument("--version", action="version", version=f"sf-kit {WERSJA}")
    pod = parser.add_subparsers(dest="polecenie", required=True)

    pod.add_parser("init", help="zapisz klucz i ustawienia").set_defaults(funkcja=polecenie_init)
    pod.add_parser("whoami", help="sprawdź, czy klucz działa").set_defaults(funkcja=polecenie_whoami)
    pod.add_parser("tasks", help="pokaż moje zadania").set_defaults(funkcja=polecenie_tasks)

    w = pod.add_parser("worker", help="pętla: bierz zadania, wykonuj, raportuj")
    w.add_argument("--runtime", choices=["codex", "shell"], default=None,
                   help="czym wykonywać zadania (domyślnie z konfiguracji)")
    w.add_argument("--interval", type=int, default=None, help="co ile sekund odpytywać")
    w.add_argument("--once", action="store_true", help="jeden przebieg zamiast pętli")
    w.set_defaults(funkcja=polecenie_worker)

    args = parser.parse_args(argv)
    try:
        return args.funkcja(args)
    except KeyboardInterrupt:
        print("\nPrzerwane.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
