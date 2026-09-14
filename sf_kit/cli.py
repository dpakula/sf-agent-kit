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

#: Trzy profile w JEDNYM narzędziu (decyzja Damiana 15.09). Profil nie ogranicza uprawnień —
#: te są po stronie SalesForge — tylko POKAZUJE to, co do danej roli należy, i chowa resztę.
#: Docelowo rozstrzygnie to `GET /me`; dopóki go nie ma, profil jest deklaracją człowieka,
#: a README mówi wprost, czego każdy z nich potrzebuje.
PROFILE = ("worker", "autor", "koordynator")
PROFIL_DOMYSLNY = "worker"
from . import klucz as magazyn_klucza
from . import autor
from .api import BladAPI, Klient


def _klient(konf: konfiguracja.Konfiguracja) -> Klient:
    """Klient API albo zrozumiały komunikat i wyjście. Nigdy `KeyError` w twarz."""
    kl = magazyn_klucza.wczytaj()
    if not kl:
        raise SystemExit(magazyn_klucza.powod_braku_klucza())
    braki = konf.braki()
    if braki:
        raise SystemExit(
            "Konfiguracja jest niepełna — brakuje: " + ", ".join(braki) + ".\n"
            f"Popraw {konfiguracja.sciezka()} albo uruchom `sf-kit init` jeszcze raz.")
    return Klient(baza=konf.adres, klucz=kl, organizacja=konf.organizacja)


def polecenie_init(args) -> int:
    """Zapytaj o slug, profil i resztę ustawień. Klucz — bez echa, na końcu.

    SLUG JEST PIERWSZY I TO NIE JEST KOLEJNOŚĆ Z GRZECZNOŚCI: od niego zależy, GDZIE wyląduje
    konfiguracja (`~/.config/sf-kit/<slug>/`) i pod jakim kontem klucz w pęku. Pytanie o niego
    później znaczyłoby zapisywanie do katalogu, o którym jeszcze nie wiemy.
    """
    print("Konfiguracja SF Agent Kit. Enter zostawia wartość w nawiasie.\n")

    def pytaj(etykieta: str, teraz: str) -> str:
        podane = input(f"{etykieta} [{teraz or 'brak'}]: ").strip()
        return podane or teraz

    # Slug PRZED wczytaniem konfiguracji — bo to on wskazuje, którą konfigurację wczytać.
    wstepny = konfiguracja.wczytaj_jesli_jest()
    slug = pytaj("Twój slug agenta w SF (np. codex-formarketing)",
                 getattr(args, "agent", None) or (wstepny.slug if wstepny else ""))
    if not slug:
        print("Bez sluga nie wiem, którym agentem jesteś ani gdzie zapisać ustawienia.",
              file=sys.stderr)
        return 2
    magazyn_klucza.ustaw_agenta(slug)

    konf = konfiguracja.wczytaj()
    konf.slug = slug
    konf.profil = pytaj(f"Profil: {' / '.join(PROFILE)}", konf.profil or PROFIL_DOMYSLNY)
    if konf.profil not in PROFILE:
        print(f"Nie znam profilu „{konf.profil}”. Dostępne: {', '.join(PROFILE)}",
              file=sys.stderr)
        return 2

    konf.adres = pytaj("Adres SalesForge", konf.adres)
    konf.organizacja = pytaj("Identyfikator Organizacji (X-Tenant-Id)", konf.organizacja)
    if konf.profil == "worker":
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
    _wlacz_ochrone_repozytorium()
    # `./sf-kit`, nie `sf-kit`: dowiązania w PATH nikt jeszcze nie zakładał, więc krótsza
    # forma kończy się „command not found" w pierwszej minucie pracy z narzędziem.
    print(f"\nSprawdź, czy działa: {_jak_wolac()} whoami")
    return 0


def _jak_wolac() -> str:
    """`sf-kit` albo `./sf-kit` — zależnie od tego, czy polecenie jest widoczne w PATH.

    Podpowiedź, która nie działa po wklejeniu, jest gorsza od braku podpowiedzi: człowiek
    dostaje „command not found" i nie wie, czy zepsuł instalację, czy tak ma być.
    """
    import shutil

    return "sf-kit" if shutil.which("sf-kit") else "./sf-kit"


def _wlacz_ochrone_repozytorium() -> None:
    """Włącz sprawdzanie commitów pod kątem klucza — w katalogu Kitu.

    README obiecywał to od wersji 0.1, a `init` tego NIE robił: ochrona przed zapisaniem
    klucza w repozytorium istniała jako skrypt, który trzeba było uruchomić samemu, i nikt
    o tym nie wiedział. Nieprawdziwe zdanie o zabezpieczeniu jest gorsze od braku
    zabezpieczenia, bo zdejmuje czujność.

    Cicho pomijamy przypadki, w których nie ma czego włączać (Kit pobrany bez gita) — to nie
    jest błąd konfiguracji użytkownika. Nieudaną instalację MÓWIMY, bo wtedy człowiek myśli,
    że jest chroniony.
    """
    import subprocess
    from pathlib import Path

    instalator = Path(__file__).resolve().parent.parent / "hooks" / "install.sh"
    if not instalator.exists():
        return
    try:
        wynik = subprocess.run(["bash", str(instalator)], cwd=str(instalator.parent.parent),
                               capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as blad:
        print(f"\nUWAGA: nie udało się włączyć ochrony przed zapisaniem klucza w repozytorium "
              f"({blad}). Włącz ją ręcznie: ./hooks/install.sh", file=sys.stderr)
        return

    if wynik.returncode == 0:
        print("Ochrona przed zapisaniem klucza w repozytorium: włączona.")
    elif "not a git repository" in (wynik.stderr or "").lower():
        pass          # Kit pobrany bez gita — nie ma commitów, nie ma czego pilnować
    else:
        print(f"\nUWAGA: ochrona przed zapisaniem klucza w repozytorium NIE została włączona "
              f"({(wynik.stderr or wynik.stdout).strip()[:200]}). "
              f"Włącz ją ręcznie: ./hooks/install.sh", file=sys.stderr)


def polecenie_whoami(_args) -> int:
    """Sonda klucza. SalesForge nie ma endpointu „kim jestem" — więc próbujemy odczytu."""
    konf = konfiguracja.wczytaj()
    kl = magazyn_klucza.wczytaj()
    if not kl:
        raise SystemExit(magazyn_klucza.powod_braku_klucza())

    print(f"agent:        {konf.slug or '(nie ustawiony)'}"
          f"   profil: {konf.profil}")
    print(f"ustawienia:   {konfiguracja.sciezka()}")
    print(f"klucz:        {magazyn_klucza.skrot(kl)}")
    print(f"adres:        {konf.adres}")
    print(f"Organizacja:  {konf.organizacja or '(nie ustawiona)'}")

    braki = konf.braki()
    if braki:
        print("\nKonfiguracja niepełna — brakuje: " + ", ".join(braki))
        return 1

    klient = Klient(baza=konf.adres, klucz=kl, organizacja=konf.organizacja)
    wynik = klient.sprawdz_klucz()
    print(f"\nodczyt zadań: {wynik.get('odczyt_zadan')}")
    # „zadania: 524" znaczyło CAŁĄ kolejkę Organizacji i myliło: Codex musiał tłumaczyć
    # człowiekowi, że to nie są jego zadania. Obie liczby naraz, z nazwami — i ta sama
    # formuła co w `tasks`, żeby dwa polecenia nie mówiły o tym samym różnymi słowami.
    if "NIE DZIAŁA" not in str(wynik.get("odczyt_zadan")):
        try:
            moje = klient.moje_zadania(slug=konf.slug)
            print(f"zadania:      {_licznik(moje)}")
        except BladAPI as blad:
            print(f"zadania:      nie udało się policzyć — {blad}")

    # Data ważności klucza. SalesForge nie oddaje jej dziś posiadaczowi klucza — i to jest
    # zgłoszona luka, nie nasza niewiedza. Jedna linia: `whoami` ma być odczytem stanu,
    # a nie miejscem na wykład (pełne wyjaśnienie → README, „Ograniczenia wersji 0.2").
    print("ważny do:     brak danych z API — patrz README, „Ograniczenia wersji 0.2”.")
    print("\nZmian statusu nie sonduję — README, sekcja „Kiedy coś nie działa”.")
    return 0 if "NIE DZIAŁA" not in str(wynik.get("odczyt_zadan")) else 1


def _licznik(wynik) -> str:
    """Jedno zdanie o liczbach, używane przez `whoami` i `tasks`.

    Dwie liczby, obie nazwane: ile zadań jest MOICH i ile pozycji kolejki Organizacji przy tym
    przejrzano. Jedna liczba bez nazwy („zadania: 524") znaczyła całą kolejkę i regularnie
    była brana za własną — Codex musiał to człowiekowi tłumaczyć na głos.
    """
    return (f"Twoje w kolejce: {len(wynik)} · "
            f"przejrzano zadań Organizacji: {wynik.przejrzano}"
            + (f" z {wynik.wszystkich}" if wynik.urwane else ""))


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
        print(f'Brak zadań dla agenta „{konf.slug}”. {_licznik(wynik)}')
        if wynik.urwane:
            print("UWAGA: przeglądanie urwał bezpiecznik stron — to NIE jest pewne „brak zadań”.")
        return 0
    print(f"{_licznik(wynik)}\n")
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


# ══ profil AUTOR (v0.3) ══════════════════════════════════════════════════════
#
# Cztery polecenia, którymi agent PCHA do SF gotową pracę człowieka. Wszystkie wypisują
# na końcu NUMER I ADRES sprawy — bo to jest jedyne, co człowiek ma potem powiedzieć
# albo wkleić komuś innemu.

def _opis_z_wejscia(args) -> str | None:
    """Opis z pliku albo ze standardowego wejścia (`--opis -`). `None` = nie podano.

    Treść idzie PLIKIEM, nie argumentem: opisy są długie i wielolinijkowe, a argument
    procesu widzi każdy na maszynie przez `ps` — ta sama zasada, co przy kluczu, tyle że
    tu chodzi o cudzą treść, nie o sekret.
    """
    zrodlo = getattr(args, "opis", None)
    if not zrodlo:
        return None
    if zrodlo == "-":
        return sys.stdin.read()
    from pathlib import Path

    plik = Path(zrodlo).expanduser()
    if not plik.is_file():
        raise SystemExit(f"nie ma pliku z opisem: {plik}")
    return plik.read_text(encoding="utf-8")


def _pokaz_sprawe(konf, sprawa_id: str, numer: str, *, co_dalej: str) -> None:
    print(f"\nSprawa: {numer or sprawa_id}")
    print(f"Adres:  {autor.adres_sprawy(sprawa_id, baza=konf.adres)}")
    print(f"\n{co_dalej}")


def polecenie_zglos(args) -> int:
    """Nowa sprawa z gotową pracą — z załącznikami, obserwującymi i numerem na wyjściu."""
    konf = konfiguracja.wczytaj()
    klient = _klient(konf)

    opis = _opis_z_wejscia(args) or autor.opis_domyslny(args.tytul)
    try:
        odp = klient.zaloz_sprawe(
            tytul=args.tytul, opis=opis, kategoria=args.tag or None,
            obserwatorzy=konf.obserwatorzy_domyslni or None,
        )
    except BladAPI as blad:
        print(f"Nie udało się założyć sprawy: {blad}", file=sys.stderr)
        return 1

    sprawa_id = str(odp.get("ticket_id") or odp.get("id") or "")
    numer = autor.numer_sprawy(odp) or ""

    if args.zalacz:
        try:
            klient.wpis_z_plikami(sprawa_id, "Pliki do tego zgłoszenia.", args.zalacz)
            print(f"Załączniki wysłane: {len(args.zalacz)}")
        except (BladAPI, FileNotFoundError) as blad:
            # Sprawa JUŻ jest — mówimy, czego brakuje, zamiast udawać, że nic nie powstało.
            print(f"Sprawa powstała, ale załączniki NIE poszły: {blad}", file=sys.stderr)
            _pokaz_sprawe(konf, sprawa_id, numer,
                          co_dalej="Dołóż pliki: sf-kit zalacz <sprawa> <plik…>")
            return 1

    if autor.czy_opis_wymaga_uzupelnienia(opis):
        print("\nUWAGA: opis został ze szkieletu (nawiasy do wypełnienia). "
              "Uzupełnij go wpisem, zanim ktoś to odbierze.")
    _pokaz_sprawe(konf, sprawa_id, numer,
                  co_dalej="Od tej chwili pytania i postęp idą WPISAMI na tej sprawie:\n"
                           f"  sf-kit wpis {numer or sprawa_id} --opis notatka.md")
    return 0


def polecenie_wpis(args) -> int:
    """Wpis na istniejącej sprawie — postęp, kolejna wersja, odpowiedź."""
    konf = konfiguracja.wczytaj()
    klient = _klient(konf)
    try:
        sprawa = autor.znajdz_sprawe(klient, args.sprawa)
    except (ValueError, BladAPI) as blad:
        print(str(blad), file=sys.stderr)
        return 1

    tresc = _opis_z_wejscia(args)
    if not tresc and not args.zalacz:
        print("Wpis bez treści i bez plików nie niesie niczego. "
              "Podaj `--opis plik.md` albo `--zalacz …`.", file=sys.stderr)
        return 2

    sprawa_id = str(sprawa["id"])
    try:
        if args.zalacz:
            klient.wpis_z_plikami(sprawa_id, tresc, args.zalacz,
                                  widocznosc=args.widocznosc)
        else:
            klient.wpis(sprawa_id, tresc, widocznosc=args.widocznosc)
    except (BladAPI, FileNotFoundError) as blad:
        print(f"Nie udało się dopisać: {blad}", file=sys.stderr)
        return 1

    _pokaz_sprawe(konf, sprawa_id, autor.numer_sprawy(sprawa),
                  co_dalej="Wpis dodany.")
    return 0


def polecenie_zalacz(args) -> int:
    """Same pliki do istniejącej sprawy — jednym wpisem, więc jednym powiadomieniem."""
    konf = konfiguracja.wczytaj()
    klient = _klient(konf)
    try:
        sprawa = autor.znajdz_sprawe(klient, args.sprawa)
        klient.wpis_z_plikami(str(sprawa["id"]), args.notka or "Załączniki.", args.pliki)
    except (ValueError, BladAPI, FileNotFoundError) as blad:
        print(str(blad), file=sys.stderr)
        return 1
    print(f"Wysłane pliki: {len(args.pliki)}")
    _pokaz_sprawe(konf, str(sprawa["id"]), autor.numer_sprawy(sprawa), co_dalej="Gotowe.")
    return 0


def polecenie_sprawy(args) -> int:
    """Sprawy w Organizacji tego klucza — żeby wiedzieć, do czego dopisywać."""
    konf = konfiguracja.wczytaj()
    klient = _klient(konf)
    try:
        lista = klient.sprawy(limit=args.limit)
    except BladAPI as blad:
        print(f"Nie udało się pobrać spraw: {blad}", file=sys.stderr)
        return 1

    if not lista:
        print("Brak spraw w tej Organizacji.")
        return 0
    print(f"Sprawy w Organizacji ({len(lista)}):\n")
    for s in lista:
        numer = autor.numer_sprawy(s) or str(s.get("id", ""))[:8]
        zmiana = (s.get("ostatnia_edycja") or s.get("updated_at") or "")[:16].replace("T", " ")
        print(f"  {numer:14} {(s.get('title') or '')[:58]}")
        print(f"  {'':14} {s.get('status', '?'):12} {zmiana}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sf-kit",
        description="SF Agent Kit — odbieraj zadania z SalesForge, wykonuj je, raportuj.")
    # `--version` przed podkomendami: pierwsze pytanie przy każdym zgłoszeniu brzmi „która
    # wersja u ciebie stoi", a odpowiedź „nie wiem" kosztuje rundę korespondencji.
    parser.add_argument("--version", action="version", version=f"sf-kit {WERSJA}")
    # `--agent` jest globalny, bo dotyczy KAŻDEGO polecenia: wskazuje, czyją konfigurację
    # i czyj klucz wziąć. Przy jednym agencie na maszynie nie trzeba go podawać nigdy.
    parser.add_argument("--agent", default=None, metavar="SLUG",
                        help="którym agentem jesteś (gdy na tej maszynie jest ich kilku)")
    pod = parser.add_subparsers(dest="polecenie", required=True)

    pod.add_parser("init", help="zapisz klucz i ustawienia").set_defaults(funkcja=polecenie_init)
    pod.add_parser("whoami", help="sprawdź, czy klucz działa").set_defaults(funkcja=polecenie_whoami)
    pod.add_parser("tasks", help="pokaż moje zadania").set_defaults(funkcja=polecenie_tasks)

    # ── profil AUTOR ────────────────────────────────────────────────────────
    z = pod.add_parser("zglos", help="[autor] zgłoś gotową pracę jako nową sprawę")
    z.add_argument("--tytul", required=True, help="jednym zdaniem: co jest gotowe")
    z.add_argument("--opis", default=None, metavar="PLIK",
                   help="plik z opisem (albo `-` = ze standardowego wejścia)")
    z.add_argument("--tag", default=None, help="kategoria sprawy, np. makieta")
    z.add_argument("--zalacz", nargs="*", default=[], metavar="PLIK",
                   help="pliki do dołączenia (idą JEDNYM wpisem)")
    z.set_defaults(funkcja=polecenie_zglos)

    wp = pod.add_parser("wpis", help="[autor] dopisz postęp albo odpowiedź do sprawy")
    wp.add_argument("sprawa", help="numer (FM-12) albo identyfikator sprawy")
    wp.add_argument("--opis", default=None, metavar="PLIK",
                    help="plik z treścią (albo `-` = ze standardowego wejścia)")
    wp.add_argument("--zalacz", nargs="*", default=[], metavar="PLIK")
    wp.add_argument("--widocznosc", choices=["internal", "external"], default="internal",
                    help="internal = widzi zespół (domyślnie), external = widzi też klient")
    wp.set_defaults(funkcja=polecenie_wpis)

    za = pod.add_parser("zalacz", help="[autor] dołóż pliki do istniejącej sprawy")
    za.add_argument("sprawa", help="numer (FM-12) albo identyfikator sprawy")
    za.add_argument("pliki", nargs="+", metavar="PLIK")
    za.add_argument("--notka", default=None, help="jedno zdanie, co to za pliki")
    za.set_defaults(funkcja=polecenie_zalacz)

    sp = pod.add_parser("sprawy", help="[autor] sprawy w tej Organizacji")
    sp.add_argument("--limit", type=int, default=50)
    sp.set_defaults(funkcja=polecenie_sprawy)

    w = pod.add_parser("worker", help="[worker] pętla: bierz zadania, wykonuj, raportuj")
    w.add_argument("--runtime", choices=["codex", "shell"], default=None,
                   help="czym wykonywać zadania (domyślnie z konfiguracji)")
    w.add_argument("--interval", type=int, default=None, help="co ile sekund odpytywać")
    w.add_argument("--once", action="store_true", help="jeden przebieg zamiast pętli")
    w.set_defaults(funkcja=polecenie_worker)

    args = parser.parse_args(argv)
    magazyn_klucza.ustaw_agenta(getattr(args, "agent", None))
    try:
        return args.funkcja(args)
    except magazyn_klucza.WieluAgentow as blad:
        # Nie wybieramy „któregoś": pisanie do cudzej Organizacji cudzym kluczem jest błędem,
        # którego nie widać ani w wyniku, ani w logu.
        print(str(blad), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nPrzerwane.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
