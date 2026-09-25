"""`sf-kit` — jedno polecenie, kilka poleceń podrzędnych.

v0.1 (14.09.2026) - APro Agents / borys-sf

Zasada, która rządzi tym plikiem: **komunikat ma mówić, co zrobić dalej.** Nie „błąd 403",
tylko „brakuje uprawnienia X, poproś administratora". Kit uruchamia ktoś, kto nas nie zna
i nie ma kogo zapytać o drugiej w nocy.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import WERSJA
from . import skrzynka
from . import config as konfiguracja

#: Trzy profile w JEDNYM narzędziu (decyzja Damiana 15.09). Profil nie ogranicza uprawnień —
#: te są po stronie SalesForge — tylko POKAZUJE to, co do danej roli należy, i chowa resztę.
#: Od v0.4 uprawnienia widać naprawdę: `GET /me` oddaje je per Organizacja (ADVERTPR-796),
#: więc profil przestał być wyłącznie deklaracją człowieka.
PROFILE = ("worker", "asystent", "koordynator")
PROFIL_DOMYSLNY = "worker"
from . import klucz as magazyn_klucza
from . import asystent
from . import flow
from . import os_czasu
from . import koordynator
from . import kontrakt
from . import rotacja as mod_rotacja
from . import tozsamosc
from .api import BladAPI, Klient


def _klient_bez_organizacji(konf: konfiguracja.Konfiguracja) -> Klient:
    """Klient do `GET /me` — jedynej trasy, która działa, zanim wiadomo, w której Organizacji."""
    kl = magazyn_klucza.wczytaj()
    if not kl:
        raise SystemExit(magazyn_klucza.powod_braku_klucza())
    braki = konf.braki()
    if braki:
        raise SystemExit(
            "Konfiguracja jest niepełna — brakuje: " + ", ".join(braki) + ".\n"
            f"Popraw {konfiguracja.sciezka()} albo uruchom `sf-kit init` jeszcze raz.")
    return Klient(baza=konf.adres, klucz=kl)


def _tozsamosc(klient: Klient) -> tozsamosc.Tozsamosc:
    """`GET /me` albo zrozumiała odmowa. Jedno miejsce, w którym Kit pyta „kim jestem"."""
    try:
        return tozsamosc.z_odpowiedzi(klient.kim_jestem())
    except BladAPI as blad:
        raise SystemExit(
            f"Nie udało się odczytać, kim jesteś ({blad}).\n"
            f"Sprawdź adres ({klient.baza}) i klucz — `sf-kit init` zapisze go od nowa.") from None


def _klient(konf: konfiguracja.Konfiguracja, args=None) -> Klient:
    """Klient z USTALONĄ Organizacją. Nigdy „pierwsza z brzegu" — patrz `tozsamosc.wybierz`."""
    return _klient_i_organizacja(konf, args)[0]


def _klient_i_organizacja(konf: konfiguracja.Konfiguracja,
                          args=None) -> tuple[Klient, tozsamosc.Organizacja]:
    """Jak `_klient`, plus Organizacja z `GET /me` — z niej worker bierze slug do porównania.

    Kosztuje jedno dodatkowe żądanie (`GET /me`) na wywołanie polecenia i to jest świadoma
    cena: bez niego Kit nie wie, czy w Organizacji z pliku agent ma jeszcze jakiekolwiek
    nadania, a praca bez nadań kończy się odmową serwera W POŁOWIE — po założeniu sprawy,
    przed dołożeniem załącznika. `worker` płaci ją raz, przy starcie pętli, nie co takt.
    """
    klient = _klient_bez_organizacji(konf)
    toz = _tozsamosc(klient)
    try:
        org = tozsamosc.wybierz(
            toz,
            wskazana=(getattr(args, "org", None) or ""),
            z_pliku=konf.organizacja,
        )
    except tozsamosc.BrakWyboru as brak:
        raise SystemExit(str(brak)) from None
    klient.organizacja = org.uuid
    return klient, org


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

    # Nazwa PRZED wczytaniem konfiguracji — bo to ona wskazuje, którą konfigurację wczytać.
    # To jest nazwa NA TEJ MASZYNIE (katalog, usługa). Slug w SF bierzemy niżej z `GET /me`
    # (SF-32) — podpowiedzią jest nazwa katalogu, nie pole `slug`, bo po ręcznej poprawce
    # te dwie rzeczy się różnią i Enter przeniósłby ustawienia do katalogu, którego nie ma.
    wstepny = konfiguracja.wczytaj_jesli_jest()
    nazwa = pytaj("Nazwa agenta na tej maszynie — katalog ustawień i usługa "
                  "(zwykle slug z SF, np. codex-formarketing)",
                  getattr(args, "agent", None)
                  or (magazyn_klucza.nazwa_lokalna(wstepny.slug) if wstepny else ""))
    if not nazwa:
        print("Bez nazwy nie wiem, którym agentem jesteś ani gdzie zapisać ustawienia.",
              file=sys.stderr)
        return 2
    magazyn_klucza.ustaw_agenta(nazwa)

    konf = konfiguracja.wczytaj()
    # Do odpowiedzi SF slug = nazwa; `GET /me` niżej go poprawi, jeśli SF mówi inaczej.
    konf.slug = konf.slug or nazwa
    konf.profil = pytaj(f"Profil: {' / '.join(PROFILE)}", konf.profil or PROFIL_DOMYSLNY)
    # ADVERTPR-959: stara nazwa `autor` przyjęta i od razu zamieniona — człowiek wpisujący ją
    # z pamięci albo ze starej instrukcji nie ma dostać odmowy.
    konf.profil = konfiguracja.PROFIL_ALIASY.get(konf.profil, konf.profil)
    if konf.profil not in PROFILE:
        print(f"Nie znam profilu „{konf.profil}”. Dostępne: {', '.join(PROFILE)}",
              file=sys.stderr)
        return 2

    konf.adres = pytaj("Adres SalesForge", konf.adres)
    if konf.profil == "worker":
        konf.katalog_roboczy = pytaj("Katalog roboczy (pusty = bieżący)", konf.katalog_roboczy)
        konf.runtime = pytaj("Wykonawca: codex, kimi albo shell", konf.runtime)

    # KLUCZ PRZED ORGANIZACJĄ — i to jest cała zmiana v0.4. Do v0.3 `init` kazał wpisać
    # identyfikator Organizacji, którego agent skądś nie ma: dostaje klucz, nie UUID, więc
    # przepisywał go z cudzej wiadomości. Od 15.09 `GET /me` działa bez nagłówka Organizacji
    # (ADVERTPR-796), więc możemy zapytać SF, zamiast pytać człowieka o coś, czego nie wie.
    print()
    try:
        skrot, gdzie = magazyn_klucza.zapytaj_i_zapisz()
    except (ValueError, RuntimeError) as blad:
        print(f"Klucz NIE został zapisany: {blad}", file=sys.stderr)
        return 1

    print(f"Klucz {skrot} zapisany: {gdzie}")
    konf.organizacja, toz = _wybierz_organizacje_w_init(konf, pytaj)
    konf.slug = _slug_z_sf_w_init(toz, konf, nazwa)

    plik = konfiguracja.zapisz(konf)
    print(f"\nUstawienia zapisane: {plik}")
    _wlacz_ochrone_repozytorium()
    # `./sf-kit`, nie `sf-kit`: dowiązania w PATH nikt jeszcze nie zakładał, więc krótsza
    # forma kończy się „command not found" w pierwszej minucie pracy z narzędziem.
    print(f"\nSprawdź, czy działa: {_jak_wolac()} whoami")
    return 0


def _slug_z_sf_w_init(toz: "tozsamosc.Tozsamosc | None", konf: konfiguracja.Konfiguracja,
                      nazwa: str) -> str:
    """Slug do zapisania w ustawieniach: ten z SF, a gdy SF nie mówi jednoznacznie — dotychczasowy.

    SF-32: `init` na macu zapisał `kimi-mac-dpakula` (konwencja z VPS), a w SF konto miało
    `kimi-mac`. Worker odsiewa zadania po tym polu, więc widział „0 zadań". Pytanie człowieka
    o slug było pytaniem o coś, co SF wie lepiej — i co człowiek przepisuje z pamięci.
    """
    if toz is None:
        print(f"Slug zostaje „{konf.slug}” — nie sprawdziłem go w SF. "
              f"Worker sprawdzi go przy starcie.", file=sys.stderr)
        return konf.slug
    w_sf = tozsamosc.slug_w_sf(toz, konf.organizacja)
    if not w_sf:
        print(f"SF nie podaje jednego sluga dla tego konta — zostawiam „{konf.slug}”. "
              f"Worker porówna go ze slugiem w Organizacji, w której wystartuje.")
        return konf.slug
    if w_sf != nazwa:
        print(f"\nUWAGA: na tej maszynie agent nazywa się „{nazwa}”, a w SF jego slug to "
              f"„{w_sf}”.\n  Zapisuję „{w_sf}” — po nim worker odsiewa zadania. Katalog "
              f"ustawień i usługa zostają pod „{nazwa}”.", file=sys.stderr)
    elif w_sf != konf.slug:
        print(f"Slug poprawiony według SF: „{konf.slug}” → „{w_sf}”.")
    else:
        print(f"Slug w SF: „{w_sf}” — zgodny.")
    return w_sf


def _wybierz_organizacje_w_init(
        konf: konfiguracja.Konfiguracja,
        pytaj) -> tuple[str, "tozsamosc.Tozsamosc | None"]:
    """Pokaż Organizacje z SF i ustal DOMYŚLNĄ. Zwraca (uuid albo pusty napis, tożsamość).

    Tożsamość oddajemy dalej, bo z tej samej odpowiedzi `init` bierze slug (SF-32) — drugie
    `GET /me` byłoby drugim miejscem, w którym może się nie udać.

    Domyślna Organizacja jest WYGODĄ, nie wyborem podejmowanym za człowieka:
    · dokładnie jedna z nadaniami → ustawiamy ją i mówimy o tym wprost;
    · kilka → pytamy, a puste Enter znaczy „nie ustawiaj, będę podawał --org";
    · zero → nie ustawiamy nic i mówimy, czego brakuje.

    Nieudane `GET /me` NIE przerywa `init`: klucz jest już zapisany, a ustawienia bez domyślnej
    Organizacji są poprawnym stanem (`--org` działa zawsze). Przerwanie tutaj kazałoby zaczynać
    od początku z powodu, który może być chwilową awarią sieci.
    """
    print("\nPytam SalesForge, do jakich Organizacji należysz…")
    try:
        toz = tozsamosc.z_odpowiedzi(
            Klient(baza=konf.adres, klucz=magazyn_klucza.wczytaj()).kim_jestem())
    except (BladAPI, SystemExit) as blad:
        print(f"  nie udało się ({blad}). Ustawienia zapiszę bez domyślnej Organizacji —\n"
              f"  podawaj --org <slug> przy poleceniach albo uruchom `init` ponownie.",
              file=sys.stderr)
        return konf.organizacja, None

    print(f"  konto: {toz.konto_nazwa or '(bez nazwy)'}"
          f"{' · agent' if toz.konto_kind == 'agent' else ''}")
    print(f"\nTwoje Organizacje:\n{tozsamosc.lista_do_pokazania(toz.organizacje)}\n")

    z_nadaniami = toz.z_nadaniami
    if not z_nadaniami:
        print("W żadnej nie masz jeszcze nadanych uprawnień — poproś administratora.\n"
              "Ustawienia zapiszę bez domyślnej Organizacji.")
        return "", toz

    if len(z_nadaniami) == 1:
        jedyna = z_nadaniami[0]
        print(f"Uprawnienia masz tylko w „{jedyna.slug}” — ustawiam ją jako domyślną.")
        return jedyna.uuid, toz

    # Kilka do wyboru: podpowiadamy tę z pliku (migracja z 0.3), ale nie wybieramy za człowieka.
    teraz = toz.znajdz(konf.organizacja) if konf.organizacja else None
    podane = pytaj("Domyślna Organizacja (slug; Enter = brak, będę podawał --org)",
                   teraz.slug if teraz else "")
    if not podane:
        print("Dobrze — każde polecenie będzie wymagało --org <slug>.")
        return "", toz
    wybrana = toz.znajdz(podane)
    if wybrana is None:
        print(f"Nie znam Organizacji „{podane}” na Twojej liście — zapisuję bez domyślnej.",
              file=sys.stderr)
        return "", toz
    if not wybrana.ma_nadania:
        print(f"W „{wybrana.slug}” nie masz nadań — zapisuję bez domyślnej, "
              f"żeby polecenia nie kończyły się odmową w połowie.", file=sys.stderr)
        return "", toz
    return wybrana.uuid, toz


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


def polecenie_whoami(args) -> int:
    """Kim jestem — Z SALESFORGE, nie z pliku ustawień.

    Do v0.3 `whoami` wypisywał to, co stało w konfiguracji, i sondował klucz próbą odczytu
    zadań. Czytało się to jak odpowiedź serwera, a było odczytem WŁASNEGO pliku: Organizacja
    mogła być nieaktualna, odebrane członkostwo wyglądało tak samo jak działające.
    Od v0.4 pyta `GET /me` (ADVERTPR-796) — a plik służy już tylko do wskazania domyślnej.
    """
    konf = konfiguracja.wczytaj()
    kl = magazyn_klucza.wczytaj()
    if not kl:
        raise SystemExit(magazyn_klucza.powod_braku_klucza())

    lokalna = magazyn_klucza.nazwa_lokalna(konf.slug)
    print(f"agent:        {konf.slug or '(nie ustawiony)'}"
          f"{f'   (na tej maszynie: {lokalna})' if lokalna != konf.slug else ''}"
          f"   profil: {konf.profil}")
    print(f"ustawienia:   {konfiguracja.sciezka()}")
    print(f"klucz:        {magazyn_klucza.skrot(kl)}")
    print(f"adres:        {konf.adres}")

    toz = _tozsamosc(Klient(baza=konf.adres, klucz=kl))
    print(f"konto:        {toz.konto_nazwa or '(bez nazwy)'}"
          f"{' · agent' if toz.konto_kind == 'agent' else ''}")
    if toz.klucz_prefiks:
        zaw = " · ZAWĘŻONY" if toz.klucz_zawezony else ""
        print(f"klucz w SF:   {toz.klucz_prefiks} · scope {toz.klucz_scope}{zaw}")
    print(f"\nOrganizacje:\n{tozsamosc.lista_do_pokazania(toz.organizacje)}")

    try:
        org = tozsamosc.wybierz(toz, wskazana=(getattr(args, "org", None) or ""),
                                z_pliku=konf.organizacja)
    except tozsamosc.BrakWyboru as brak:
        # To NIE jest awaria: `whoami` ma pokazać stan także wtedy (zwłaszcza wtedy), gdy
        # praca nie ruszy. Kod wyjścia mówi „nie da się pracować", treść mówi dlaczego.
        print(f"\n{brak}")
        return 1

    print(f"\npracuję w:    {org.slug} ({org.nazwa})"
          f"{'  ← z --org' if getattr(args, 'org', None) else ''}")
    print(f"uprawnienia:  {', '.join(org.uprawnienia) or '(brak)'}")
    print(f"slug w SF:    {org.agent_slug or '(członkostwo bez sluga)'}")
    rozjazd = tozsamosc.rozjazd_sluga(konf.slug, org)
    if rozjazd:
        # SF-32: tu `whoami` pokazywał działające konto, a worker obok widział „0 zadań".
        print(f"\nUWAGA: {rozjazd}\n  Worker odmówi startu. Popraw: `{_jak_wolac()} init` albo "
              f'"slug": "{org.agent_slug}" w {konfiguracja.sciezka()}')

    klient = Klient(baza=konf.adres, klucz=kl, organizacja=org.uuid)
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

    # Data ważności klucza — od v0.4 czytana z `GET /me`. Do v0.3 była tu „luka SF"; okazała
    # się nią przez cztery dni, bo trasa, która ją oddaje, powstała 15.09.
    print(f"ważny do:     {_waznosc_klucza(toz)}")
    print("\nZmian statusu nie sonduję — README, sekcja „Kiedy coś nie działa”.")
    return 0 if "NIE DZIAŁA" not in str(wynik.get("odczyt_zadan")) else 1


def _waznosc_klucza(toz: tozsamosc.Tozsamosc) -> str:
    """Data ważności albo „bezterminowy". Pusta wartość z SF znaczy brak terminu, nie brak wiedzy.

    Przy dacie stoi ILE TO JEST DNI (ADVERTPR-779): sama data każe człowiekowi liczyć w głowie,
    a liczenie w głowie jest tym, czego się nie robi — i stąd klucze wygasające „nagle".
    """
    wygasa = getattr(toz, "klucz_wygasa", None)
    if not wygasa:
        return "bezterminowy (SF nie ma ustawionego terminu)"
    dni = tozsamosc.dni_do_wygasniecia(toz)
    if dni is None:
        return str(wygasa)
    if dni < 0:
        return f"{wygasa} — WYGASŁ {abs(dni)} dni temu"
    if dni == 0:
        return f"{wygasa} — wygasa DZIŚ"
    return f"{wygasa} (za {dni} {'dzień' if dni == 1 else 'dni'})"


def _licznik(wynik) -> str:
    """Jedno zdanie o liczbach, używane przez `whoami` i `tasks`.

    Dwie liczby, obie nazwane: ile zadań jest MOICH i ile pozycji kolejki Organizacji przy tym
    przejrzano. Jedna liczba bez nazwy („zadania: 524") znaczyła całą kolejkę i regularnie
    była brana za własną — Codex musiał to człowiekowi tłumaczyć na głos.
    """
    return (f"Twoje w kolejce: {len(wynik)} · "
            f"przejrzano zadań Organizacji: {wynik.przejrzano}"
            + (f" z {wynik.wszystkich}" if wynik.urwane else ""))



def polecenie_rotate(args) -> int:
    """Wymień sekret klucza, zanim wygaśnie — kluczem, który jeszcze żyje (ADVERTPR-779 B).

    Klucz musi mieć nadanie `keys:self-renew` na koncie w tej Organizacji i być w oknie
    siedmiu dni przed terminem. Decyduje SalesForge; Kit próbuje i pokazuje odpowiedź.

    Po udanej rotacji STARY SEKRET JEST MARTWY — nowy jest już zapisany w tym samym miejscu,
    z którego Kit czyta klucz, więc nie trzeba nic przepisywać. Gdyby zapis się nie udał,
    zobaczysz błąd i dostęp będzie do odzyskania tylko przez człowieka; dlatego zapis idzie
    przed jakimkolwiek wypisywaniem na ekran.
    """
    konf = konfiguracja.wczytaj()
    kl = magazyn_klucza.wczytaj()
    if not kl:
        raise SystemExit(magazyn_klucza.powod_braku_klucza())

    # Organizacja jest OBOWIĄZKOWA, choć odnowienie wygląda na czynność ponad nimi: uprawnienie
    # `keys:self-renew` jest nadaniem na CZŁONKOSTWIE, więc bez wskazania Organizacji SF nie ma
    # czego policzyć i oddaje 403. Pierwsza wersja tego polecenia budowała klienta bez
    # Organizacji i dostawała odmowę przy najzupełniej poprawnym kluczu.
    klient_bez_org = Klient(baza=konf.adres, klucz=kl)
    toz = _tozsamosc(klient_bez_org)
    try:
        org = tozsamosc.wybierz(toz, wskazana=(getattr(args, "org", None) or ""),
                                z_pliku=konf.organizacja)
    except tozsamosc.BrakWyboru as brak:
        print(str(brak))
        return 1

    klient = Klient(baza=konf.adres, klucz=kl, organizacja=org.uuid)
    wynik = mod_rotacja.rotuj(klient)
    print(wynik.zdanie)
    if not wynik.odnowiony:
        # Kod wyjścia 1, bo to jest odpowiedź „nie odnowiłem" — a skrypt, który tego nie
        # sprawdzi, poszedłby dalej z kluczem, któremu zostało kilka dni.
        return 1
    print("Stary sekret przestał działać w chwili odpowiedzi — to zamierzone "
          "(„jeden żywy sekret naraz”).")
    return 0


def polecenie_heartbeat(args) -> int:
    """Czy worker tego agenta żyje. Kod wyjścia 0 = tak, 1 = nie — pod czujkę."""
    from . import usluga

    # Slug z konfiguracji: od v0.5.3 tętno jest per worker, nie per konto systemowe.
    konf = konfiguracja.wczytaj()
    zywy, co = usluga.czy_zywy(slug=magazyn_klucza.nazwa_lokalna(konf.slug) or None)
    print(co)
    return 0 if zywy else 1


def polecenie_usluga(args) -> int:
    """Wygeneruj jednostkę systemd dla workera tego agenta.

    Piszemy PLIK i mówimy, co dalej — zamiast wołać `systemctl` samemu. Polecenie, które
    z własnej woli włącza usługę na cudzej maszynie, jest trudne do cofnięcia przez kogoś,
    kto nie wiedział, że je uruchamia; wygenerowany plik można przeczytać przed decyzją.
    """
    from . import usluga

    konf = konfiguracja.wczytaj()
    if not konf.slug:
        print("Najpierw `sf-kit init` — bez sluga agenta nie ma czego uruchamiać.", file=sys.stderr)
        return 2
    # Usługa, jej plik i log nazywają się jak agent NA TEJ MASZYNIE — `--agent` w wierszu
    # polecenia musi trafić w katalog ustawień. Slug z SF (SF-32) bywa inny.
    nazwa = magazyn_klucza.nazwa_lokalna(konf.slug)

    # System wybieramy z `sys.platform`, nie z pytania do człowieka: plik dla obcego systemu
    # jest bezużyteczny, a wybrany ręcznie bywa wybrany źle. `--system` zostaje dla przypadku,
    # w którym ktoś generuje plik dla INNEJ maszyny niż ta, na której stoi.
    docelowy = getattr(args, "system", None) or ("macos" if sys.platform == "darwin" else "linux")
    polecenie = os.path.abspath(sys.argv[0])

    if docelowy == "macos":
        sciezka = usluga.sciezka_plist(nazwa)
        tresc = usluga.tresc_plist(slug=nazwa, polecenie=polecenie,
                                   katalog_domowy=str(Path.home()))
    else:
        sciezka = usluga.sciezka_unitu(nazwa)
        tresc = usluga.tresc_unitu(
            slug=nazwa,
            polecenie=polecenie,
            katalog_domowy=str(Path.home()),
            plik_srodowiska=str(Path.home() / ".config" / "sf-kit" / f"{nazwa}.env"),
        )

    if args.pokaz:
        print(tresc)
        return 0

    sciezka.parent.mkdir(parents=True, exist_ok=True)
    sciezka.write_text(tresc, encoding="utf-8")

    if docelowy == "macos":
        etykieta = usluga.etykieta_launchd(nazwa)
        (Path.home() / "Library" / "Logs" / "sf-kit").mkdir(parents=True, exist_ok=True)
        print(f"Zapisałem agenta launchd: {sciezka}\n")
        print("Włącz go (bez sudo, agent użytkownika) — JEDNO polecenie:")
        print(f"  launchctl bootstrap gui/$(id -u) {sciezka}\n")
        print("Sprawdzenie i podgląd logu:")
        print(f"  launchctl print gui/$(id -u)/{etykieta} | head -20")
        print(f"  tail -f ~/Library/Logs/sf-kit/worker-{nazwa}.log\n")
        print("Wyłączenie:")
        print(f"  launchctl bootout gui/$(id -u)/{etykieta}\n")
        print("Jeśli `launchctl bootstrap` odpowie „Input/output error”, agent jest już "
              "wczytany — najpierw `bootout`, potem `bootstrap`.")
        return 0

    print(f"Zapisałem jednostkę: {sciezka}\n")
    print("Włącz ją (bez sudo, usługa użytkownika):")
    print("  systemctl --user daemon-reload")
    print(f"  systemctl --user enable --now {usluga.nazwa_unitu(nazwa)}")
    print(f"  systemctl --user status {usluga.nazwa_unitu(nazwa)}\n")
    print("Żeby worker chodził także wtedy, gdy nie jesteś zalogowany:")
    print(f"  sudo loginctl enable-linger {os.environ.get('USER', 'twoj-uzytkownik')}")
    return 0

def polecenie_blok(args) -> int:
    """`sf-kit blok typy` — katalog rodzajów; `sf-kit blok <id>` — jeden blok przez rdzeń.

    `odpowiedz` (SF-23) nadal NIE ISTNIEJE i nadal mówi o tym wprost: zapis odpowiedzi
    wchodzi etapem E3. Polecenie, które istnieje i zawsze pada, jest gorsze od polecenia,
    którego nie ma — uczy człowieka, że Kit bywa zepsuty.
    """
    podpolecenie = (getattr(args, "co", None) or "typy").strip()

    if podpolecenie != "typy":
        return _blok_jeden(args, podpolecenie)

    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)
    try:
        typy = klient.typy_blokow()
    except BladAPI as blad:
        print(f"Nie udało się pobrać katalogu typów: {blad}", file=sys.stderr)
        return 1

    if not typy:
        print("SF nie zna żadnego rodzaju bloku. To nie jest normalny stan — "
              "zgłoś na SF-7.", file=sys.stderr)
        return 1

    print(f"Rodzaje bloku ({len(typy)}):\n")
    for t in typy:
        stany = ", ".join(t.get("stany") or []) or "—"
        print(f"  {t.get('rodzaj')}")
        print(f"    {t.get('etykieta')}")
        print(f"    stany: {stany}")
        for a in t.get("akcje") or []:
            # Uprawnienie pokazujemy ZAWSZE, gdy jest: człowiek pytający Kita o typy zwykle
            # chce wiedzieć, czego mu braknie, zanim spróbuje.
            perm = a.get("uprawnienie")
            dopisek = f"  (wymaga: {perm})" if perm else ""
            print(f"    · {a.get('nazwa')} — {a.get('etykieta')}{dopisek}")
        print()
    return 0


def _blok_jeden(args, wskazanie: str) -> int:
    """`sf-kit blok <id>` — odczyt bloku przez rdzeń (`GET /blocks/{id}`, SF-7).

    DWA IDENTYFIKATORY, JEDNO POLECENIE
    ═══════════════════════════════════
    Wpis żyje dziś na dwóch powierzchniach (rdzeń i dziennik sprawy) i ma na nich RÓŻNE
    identyfikatory. Kit nie pyta, który to który — rdzeń rozwiązuje oba, więc człowiek wkleja
    ten, który widzi na ekranie, z którego przyszedł.

    404 MA TU JEDNO ZNACZENIE I NIE UDAJEMY, ŻE MA DWA
    ══════════════════════════════════════════════════
    Serwer odmawia tak samo, gdy bloku nie ma, jak i gdy jest ponad poziomem pytającego —
    świadomie, bo rozróżnienie zdradzałoby jego istnienie. Komunikat mówi obie możliwości
    zamiast zgadywać jedną; podpowiadanie „pewnie nie masz uprawnień" przy literówce
    w identyfikatorze wysyła człowieka do administratora zamiast do schowka.
    """
    if wskazanie == "odpowiedz":
        print("`sf-kit blok odpowiedz` jeszcze nie działa — zapis odpowiedzi-dziecka wchodzi\n"
              "etapem E3 (sprawa SF-7). Odczyt bloku działa: `sf-kit blok <id>`.",
              file=sys.stderr)
        return 2
    if wskazanie == "pokaz":
        print("`pokaz` zniknęło jako osobne słowo — blok pokazuje sam identyfikator:\n"
              "  sf-kit blok <id>        (identyfikator z nawiasu przy wierszu `sf-kit os`)",
              file=sys.stderr)
        return 2
    if not asystent.WZORZEC_UUID.match(wskazanie):
        # Sprawdzamy TU, a nie przez strzał w API: „404 — nie ma albo nie dla ciebie" przy
        # literówce wysyła człowieka do administratora po dostęp, którego wcale nie potrzebuje.
        print(f"„{wskazanie}” nie wygląda na identyfikator bloku (oczekuję UUID).\n"
              "Identyfikator bierze się z nawiasu przy wierszu `sf-kit os <sprawa>`\n"
              "albo z adresu wpisu w panelu.", file=sys.stderr)
        return 2

    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)
    try:
        blok = klient.blok(wskazanie)
    except BladAPI as blad:
        if blad.kod == 404:
            print(f"Nie ma bloku „{wskazanie}” — albo jest poza Twoim dostępem.\n"
                  "SalesForge odmawia tak samo w obu przypadkach, żeby nie zdradzać, że blok\n"
                  "istnieje. Sprawdź identyfikator; jeśli jest dobry — poproś o dostęp do sprawy.",
                  file=sys.stderr)
            return 1
        if blad.kod == 503:
            # 503 na tej trasie niesie POWÓD (np. „brakuje tabel rewizji E1"), a nasz własny
            # tekst dla 503 brzmi „odczekaj i spróbuj później" — co przy braku migracji jest
            # radą fałszywą: czekanie nie pomoże, pomoże migracja.
            print(_detal_serwera(blad)
                  or f"Rdzeń Bloku nie jest gotowy na tym serwerze: {blad}", file=sys.stderr)
            return 1
        print(f"Nie udało się pobrać bloku: {blad}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(blok, ensure_ascii=False, indent=2))
        return 0

    rodzaj = os_czasu.NAZWY_RODZAJOW.get(blok.get("rodzaj") or "", blok.get("rodzaj") or "?")
    print(f"\n{rodzaj} · {blok.get('autor_etykieta') or '—'} · "
          f"{(blok.get('wystapil_o') or '')[:16].replace('T', ' ')}")
    print(f"  id:         {blok.get('id')}")
    if blok.get("natywny_id"):
        print(f"  w dzienniku: {blok['natywny_id']}")
    if blok.get("sedno"):
        print(f"  sedno:      {blok['sedno']}")
    if blok.get("kotwica_typ"):
        print(f"  kotwica:    {blok['kotwica_typ']} {blok.get('kotwica_id')}")
    print(f"  widoczność: {blok.get('widocznosc')}")
    for etykieta, klucz in (("stan:", "stan_bloku"), ("status:", "status"),
                            ("stan typu:", "stan_typu")):
        if blok.get(klucz):
            print(f"  {etykieta:<11} {blok[klucz]}")
    if blok.get("w_odpowiedzi_na"):
        print(f"  odpowiedź na: {blok['w_odpowiedzi_na']}")
    print(f"  odpowiedzi: {blok.get('odpowiedzi', 0)}")
    for a in blok.get("adresaci") or []:
        print(f"    → {a.get('slug') or a.get('user_id')} · {a.get('status')}")
    # `z_rdzenia=false` znaczy „ten wiersz przyszedł drogą zapasową, od właściciela bytu" —
    # wtedy pola rewizji E1 (sedno, stan) są puste Z NATURY, nie z usterki odczytu. Człowiek
    # patrzący na pusty ekran ma wiedzieć, czy patrzy na brak danych, czy na brak lustra.
    if blok.get("z_rdzenia") is False:
        print("\n  (wpis bez lustra w rdzeniu — pola `sedno` i `stan` będą puste do etapu E5)")
    tresc = (blok.get("tresc") or "").strip()
    print(f"\n{tresc}\n" if tresc else "\n  (bez treści)\n")
    return 0


def _detal_serwera(blad) -> str:
    """Pole `detail` z odpowiedzi serwera, jeśli da się je odczytać. Pusty napis, gdy nie.

    ⚠️ Używać TYLKO tam, gdzie treść jest komunikatem dla człowieka (503 o stanie instalacji).
    Przy 422 serwer potrafi wydrukować wartość odrzuconego pola, a to bywa czyjaś dana —
    dlatego nie robimy z tego domyślnego zachowania dla wszystkich kodów.
    """
    try:
        dane = json.loads(getattr(blad, "szczegoly", "") or "")
    except (ValueError, TypeError):
        return ""
    detal = dane.get("detail") if isinstance(dane, dict) else None
    return detal if isinstance(detal, str) else ""


def _pelny_id_grupy(klient, sprawa, skrot: str, *, limit: int) -> str | None:
    """Skrót z nawiasu (`[296dad5c]`) → pełny identyfikator grupy. `None` = już powiedziałem czemu nie.

    DLACZEGO W OGÓLE: wiersz-grupa pokazuje OSIEM znaków, bo pełny UUID zabiera ćwierć
    szerokości terminala i wypycha treść. Gdyby `--rozwin` wymagał pełnego, jedyne, co widać
    na ekranie, byłoby bezużyteczne — a serwer na nieznany identyfikator nie protestuje:
    oddaje oś dalej zwiniętą, bez słowa. Człowiek widzi „nic się nie stało" i nie wie czemu.
    Złapane przy pierwszym uruchomieniu na żywej osi SF-7.

    Cena: jedno dodatkowe pytanie o stronę — tylko wtedy, gdy podano skrót.
    """
    try:
        strona = klient.os_obiektu("ticket", str(sprawa["id"]), pelna=False, limit=limit)
    except BladAPI as blad:
        print(f"Nie udało się pobrać osi: {blad}", file=sys.stderr)
        return None

    kandydaci = [str(p.get("id")) for p in (strona.get("entries") or [])
                 if os_czasu.jest_grupa(p) and str(p.get("id")).startswith(skrot)]
    if not kandydaci:
        print(f"Nie ma grupy zaczynającej się od „{skrot}” na tej stronie osi.\n"
              "Grupy istnieją tylko w widoku zwiniętym i tylko na TEJ stronie — przy dużym\n"
              f"`--limit` bywają inne. Sprawdź `sf-kit os <sprawa> --zwinieta --limit {limit}`.",
              file=sys.stderr)
        return None
    if len(kandydaci) > 1:
        # Rozwinięcie NIE TEJ grupy wygląda dokładnie jak rozwinięcie tej właściwej — człowiek
        # nie ma jak zauważyć pomyłki. Dlatego odmowa z kandydatami, a nie „pierwszy z brzegu".
        print(f"„{skrot}” pasuje do {len(kandydaci)} grup:", file=sys.stderr)
        for k in kandydaci:
            print(f"  {k}", file=sys.stderr)
        print("Podaj więcej znaków.", file=sys.stderr)
        return None
    return kandydaci[0]


def polecenie_os(args) -> int:
    """`sf-kit os <sprawa>` — oś sprawy, wierszami albo ze zwiniętymi ciągami (SF-7 E4a).

    DOMYŚLNIE PEŁNA — I TO NIE JEST MOJA DECYZJA
    ════════════════════════════════════════════
    `pelna=true` jest domyślką serwera (decyzja Damiana 22.09: przełączenie na zwiniętą
    dopiero po UI kapsuły). Klient wiersza poleceń nie rozstrzyga tego prywatnie: gdyby Kit
    zwijał domyślnie, ta sama sprawa wyglądałaby inaczej w panelu i w Kicie, a rozmowa
    „widzę osiem, a ty pięć" nie miałaby rozstrzygnięcia.

    STARY SERWER NIE PROTESTUJE — WIĘC MÓWIMY MY
    ════════════════════════════════════════════
    API bez E4a ignoruje nieznane parametry zapytania i oddaje pełną oś ze statusem 200.
    Bez ostrzeżenia człowiek zobaczyłby 200 wierszy i wziął je za wynik zwinięcia.
    """
    if args.rozwin and args.pelna:
        print("`--rozwin` rozwija JEDNĄ grupę na zwiniętej osi — przy `--pelna` nie ma czego\n"
              "rozwijać, bo wszystkie wiersze i tak są widoczne. Wybierz jedno.",
              file=sys.stderr)
        return 2

    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)

    try:
        sprawa = asystent.znajdz_sprawe(klient, args.sprawa)
    except (ValueError, BladAPI) as blad:
        print(str(blad), file=sys.stderr)
        return 1

    # `--rozwin` sam włącza zwijanie: prośba o rozwinięcie grupy na PEŁNEJ osi nie ma treści,
    # a odmawianie jej byłoby uczeniem człowieka składni zamiast zrozumienia go.
    pelna = not (args.zwinieta or args.rozwin)
    rozwin = (args.rozwin or "").strip()
    try:
        if rozwin and not asystent.WZORZEC_UUID.match(rozwin):
            rozwin = _pelny_id_grupy(klient, sprawa, rozwin, limit=args.limit)
            if rozwin is None:
                return 2
        strona = klient.os_obiektu("ticket", str(sprawa["id"]), pelna=pelna,
                                   rozwin=rozwin, limit=args.limit)
    except BladAPI as blad:
        print(f"Nie udało się pobrać osi: {blad}", file=sys.stderr)
        return 1

    pozycje = strona.get("entries") or []
    if args.json:
        print(json.dumps(strona, ensure_ascii=False, indent=2))
        return 0

    numer = asystent.numer_sprawy(sprawa) or str(sprawa["id"])[:8]
    print(f"\nOś sprawy {numer} — {'pełna' if pelna else 'zwinięta'}"
          f"{f', rozwinięta grupa {args.rozwin[:8]}' if args.rozwin and not pelna else ''}")

    if not pozycje:
        print("\n  (na tej osi nie ma nic, co możesz zobaczyć)\n")
        return 0

    for linia in os_czasu.wypisz(pozycje):
        print(linia)

    wierszy = os_czasu.ile_wierszy(pozycje)
    grup = sum(1 for p in pozycje if os_czasu.jest_grupa(p))
    print()
    if grup:
        print(f"{len(pozycje)} pozycji = {wierszy} wierszy osi "
              f"({os_czasu.odmiana_grup(grup)}; rozwiń przez `--rozwin <id>`)")
    else:
        print(f"{wierszy} wierszy osi")

    # Serwer na nieznany `rozwin` nie protestuje — oddaje oś dalej zwiniętą. Bez tego zdania
    # człowiek widzi „nic się nie stało" i nie wie, czy to on się pomylił, czy Kit.
    if rozwin and any(str(p.get("id")) == rozwin for p in pozycje if os_czasu.jest_grupa(p)):
        print(f"\nUWAGA: grupa {rozwin[:8]} wróciła nadal zwinięta — serwer jej nie rozwinął.\n"
              "Zwykle znaczy to, że ciąg zmienił się od czasu, gdy widziałeś ten identyfikator.")

    # Świadomie NIE piszę „X z Y wpisów sprawy": oś obiektu nie oddaje licznika całości
    # (`razem` jest w dzienniku sprawy, nie tutaj), a liczba policzona z długości listy
    # mówiłaby o stronie, nie o osi — i po zwinięciu kłamałaby podwójnie.
    if strona.get("next_cursor"):
        print(f"To nie koniec osi — jest następna strona (limit {args.limit}).")

    if not pelna and not os_czasu.serwer_zwija(pozycje):
        print("\nUWAGA: pełna oś, serwer nie zwija — to API jest starsze niż E4a i zignorowało\n"
              "`--zwinieta`. Widzisz KOMPLET wierszy, nie wynik zwinięcia.")
    return 0


def polecenie_tasks(args) -> int:
    """Moje zadania w kolejce."""
    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)
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
        sprawa = z.get("ticket_ref") or z.get("ticket_id")
        print(f"  {z.get('external_id')}")
        print(f"    {z.get('title')}")
        if sprawa:
            print(f"    sprawa: {sprawa}   id: {z.get('id')}")
        else:
            # Zadanie bez sprawy WYKONAMY (polityka v0.4: twarda przy zakładaniu, miękka przy
            # wykonaniu), ale człowiek ma wiedzieć O TYM WCZEŚNIEJ, a nie dowiadywać się po
            # fakcie, że wyniku nie ma na żadnej osi. Neutralne „— bez sprawy" z v0.3 tego
            # nie mówiło: wyglądało jak brakujące pole, a nie jak konsekwencja.
            print(f"    ⚠ bez sprawy — wynik trafi tylko do komentarza zadania")
            print(f"    id: {z.get('id')}")
    return 0


# ══ profil KOORDYNATOR (v0.4) ════════════════════════════════════════════════
#
# Pięć poleceń, którymi człowiek rozdaje pracę flocie i ją odbiera. Wszystkie przechodzą przez
# `_koordynator()` — jedno miejsce, w którym sprawdzamy, czy klucz ma do tego prawo W TEJ
# Organizacji. Sprawdzenie idzie po `GET /me`, nie po polu `profil` w pliku ustawień: profil
# jest deklaracją człowieka, a uprawnienia mieszkają po stronie SF.

def _koordynator(konf: konfiguracja.Konfiguracja, args):
    """`(klient, organizacja)` albo odmowa mówiąca, czego brakuje. Nigdy 403 w twarz."""
    klient = _klient_bez_organizacji(konf)
    toz = _tozsamosc(klient)
    try:
        org = tozsamosc.wybierz(toz, wskazana=(getattr(args, "org", None) or ""),
                                z_pliku=konf.organizacja)
    except tozsamosc.BrakWyboru as brak:
        raise SystemExit(str(brak)) from None

    if not koordynator.czy_wolno_zlecac(org.uprawnienia):
        gdzie = [o.slug for o in toz.organizacje
                 if koordynator.czy_wolno_zlecac(o.uprawnienia)]
        podpowiedz = (f"Możesz zlecać w: {', '.join(gdzie)} — dodaj --org <slug>."
                      if gdzie else
                      f"W żadnej ze swoich Organizacji nie masz uprawnienia "
                      f"`{koordynator.UPRAWNIENIE_ZLECANIA}`. Poproś administratora.")
        raise SystemExit(
            f"Polecenia koordynatora wymagają uprawnienia "
            f"`{koordynator.UPRAWNIENIE_ZLECANIA}`, a w „{org.slug}” go nie masz.\n{podpowiedz}"
        )
    klient.organizacja = org.uuid
    return klient, org


def polecenie_flota(args) -> int:
    """Agenci Organizacji — kto w ogóle może dostać zadanie."""
    konf = konfiguracja.wczytaj()
    klient, org = _koordynator(konf, args)
    try:
        agenci = koordynator.flota(klient)
    except BladAPI as blad:
        print(f"Nie udało się pobrać listy agentów: {blad}", file=sys.stderr)
        return 1

    if not agenci:
        print(f"W „{org.slug}” nie ma zarejestrowanych agentów.")
        return 0
    print(f"Flota w „{org.slug}” ({len(agenci)}):\n")
    for a in agenci:
        print(f"  {a.opis()}")
    bez_sluga = [a for a in agenci if not a.wolalny]
    if bez_sluga:
        print(f"\n{len(bez_sluga)} członkostw agenta bez sluga — takiego agenta widać, ale nie "
              f"da się do niego zlecić. To błąd konfiguracji po stronie administratora.")
    return 0


def polecenie_flota_rejestr(args) -> int:
    """Migawka `agents.json` → SF, z rozjazdami w odpowiedzi (SF-18).

    Kody wyjścia dla tic / worker-tick: 0 = przyjęte (także z rozjazdami — rozjazd jest
    wiadomością dla człowieka, nie awarią wysyłki), 1 = nie wysłano, 2 = zły plik.
    """
    import socket

    from . import rejestr_floty

    try:
        dane = rejestr_floty.wczytaj(args.plik)
    except rejestr_floty.ZlyRejestr as blad:
        print(f"Nie wysyłam: {blad}", file=sys.stderr)
        return 2
    migawka = rejestr_floty.zbuduj(dane, nadawca=socket.gethostname().split(".")[0])

    print(f"Rejestr: {args.plik} — {len(migawka.cialo['agenci'])} wpisów "
          f"(aktywnych {sum(1 for a in migawka.cialo['agenci'] if a['aktywny'])}).")
    for ident, slug, skad in migawka.pochodzenie:
        if skad != "id" or ident != slug:
            print(f"  {ident:<24} → slug {slug}  (z `{skad}`)")
    for zdanie in migawka.ostrzezenia:
        print(f"  UWAGA: {zdanie}", file=sys.stderr)

    if args.pokaz:
        print(json.dumps(migawka.cialo, ensure_ascii=False, indent=2))
        print("\n--pokaz: nic nie wysłałem.")
        return 0

    konf = konfiguracja.wczytaj()
    # Ta sama bramka co reszta profilu koordynatora (README: „wszystkie wymagają plans:write").
    # To jest wygoda, nie zabezpieczenie — rozstrzyga serwer.
    klient, org = _koordynator(konf, args)
    try:
        odp = klient.zapisz_migawke_rejestru(migawka.cialo)
    except BladAPI as blad:
        # 503 z tej trasy to INSTALACJA (brak tabel rewizji), nie przeciążenie — ogólny
        # komunikat „odczekaj" wysłałby człowieka na fałszywy trop. Treść serwera mówi prawdę.
        szczegol = f"\n  serwer: {blad.szczegoly}" if getattr(blad, "kod", None) == 503 else ""
        print(f"Migawka NIE poszła do „{org.slug}”: {blad}{szczegol}", file=sys.stderr)
        return 1

    rozjazdy = odp.get("rozjazdy") or []
    print(f"\nSF („{org.slug}”) przyjął {odp.get('przyjeto')} wpisów. "
          f"Rozjazdy wobec rejestru SF: {len(rozjazdy)}.")
    # Pogrupowane po rodzaju, z licznikiem na początku: rozjazdów nazwy bywa kilkanaście
    # i bez grupowania przykrywają te dwa, które naprawdę coś znaczą (konto bez wpisu).
    from collections import Counter
    liczniki = Counter(r.get("rodzaj") for r in rozjazdy)
    if liczniki:
        print("  " + ", ".join(f"{rodzaj}: {ile}" for rodzaj, ile in sorted(liczniki.items())))
    for r in sorted(rozjazdy, key=lambda r: (r.get("rodzaj") or "", r.get("slug") or "")):
        strony = " / ".join(x for x in (
            f"SF: {r.get('w_sf')}" if r.get("w_sf") else "",
            f"lokalnie: {r.get('lokalnie')}" if r.get("lokalnie") else "") if x)
        print(f"  {r.get('rodzaj'):<18} {r.get('slug') or '(bez sluga)':<22} "
              f"{r.get('szczegol') or ''}{f'  [{strony}]' if strony else ''}")
    return 0


def polecenie_zlec(args) -> int:
    """Zadanie dla agenta — ZAWSZE na sprawie."""
    konf = konfiguracja.wczytaj()
    klient, org = _koordynator(konf, args)

    tresc = _opis_z_wejscia(args)
    try:
        agenci = koordynator.flota(klient)
        agent = koordynator.znajdz_agenta(agenci, args.agent_slug)
        sprawa = asystent.znajdz_sprawe(klient, args.sprawa)
        koordynator.sprawdz_sprawe_dla_wykonawcy(
            klient, ticket_id=str(sprawa["id"]), agent=agent)
    except koordynator.Odmowa as odmowa:
        print(str(odmowa), file=sys.stderr)
        return 2
    except (ValueError, BladAPI) as blad:
        print(f"Nie udało się zlecić: {blad}", file=sys.stderr)
        return 1

    try:
        zadanie = klient.zaloz_zadanie(
            tytul=args.tytul, agent_id=agent.user_id, ticket_id=str(sprawa["id"]),
            tresc=tresc, priorytet=args.priorytet, termin=args.termin,
            projekt=args.projekt, kategoria=args.kategoria,
        )
    except BladAPI as blad:
        print(f"Nie udało się zlecić: {blad}", file=sys.stderr)
        return 1

    print(f"Zlecone: {zadanie.get('external_id')} → {agent.slug}")
    print(f"  sprawa: {asystent.numer_sprawy(sprawa)}")
    print(f"  {asystent.adres_sprawy(str(sprawa['id']), baza=konf.adres)}")
    print(f"\nWynik pojawi się na tej sprawie. Sprawdź: "
          f"{_jak_wolac()} odbierz {zadanie.get('external_id')}")
    return 0


def polecenie_kolejka(args) -> int:
    """Co flota ma na głowie — zadania w toku, per agent."""
    konf = konfiguracja.wczytaj()
    klient, org = _koordynator(konf, args)
    statusy = [args.status] if args.status else list(koordynator.W_TOKU)
    try:
        zadania = []
        urwane: list[str] = []
        for status in statusy:
            strona = klient.zadania(status=status, limit=100)
            pozycje = strona.get("items") or strona.get("pozycje") or []
            zadania.extend(pozycje)
            # Jedna strona na status. Gdy kolejka jest dłuższa, MÓWIMY o tym — licznik, który
            # pokazuje „12 zadań", gdy jest ich 130, kłamie w jedyną stronę, która ma znaczenie
            # dla kogoś planującego pracę floty.
            razem = int(strona.get("total") or 0)
            if razem > len(pozycje):
                urwane.append(f"{status}: widzę {len(pozycje)} z {razem}")
    except BladAPI as blad:
        print(f"Nie udało się pobrać kolejki: {blad}", file=sys.stderr)
        return 1

    if args.agent_slug:
        zadania = [z for z in zadania
                   if (z.get("assigned_agent_slug") or "") == args.agent_slug]
    if not zadania:
        print(f"Nic w toku w „{org.slug}”"
              f"{f' dla {args.agent_slug}' if args.agent_slug else ''}.")
        return 0

    print(f"Kolejka floty w „{org.slug}” ({len(zadania)}):\n")
    for z in sorted(zadania, key=lambda z: (z.get("assigned_agent_slug") or "~", z.get("status"))):
        sprawa = z.get("ticket_ref") or z.get("ticket_id")
        print(f"  [{z.get('status'):<12}] {z.get('external_id')} → "
              f"{z.get('assigned_agent_slug') or '(nikt)'}")
        print(f"      {z.get('title')}")
        if not sprawa:
            print("      ⚠ bez sprawy — wynik trafi tylko do komentarza zadania")
    if urwane:
        print(f"\nUWAGA: to nie jest cała kolejka — {'; '.join(urwane)}. "
              f"Zawęź przez --agent-slug albo --status.")
    return 0


def polecenie_odbierz(args) -> int:
    """Zamknij zadanie — ale dopiero po sprawdzeniu, że wynik naprawdę jest na sprawie."""
    konf = konfiguracja.wczytaj()
    klient, _org = _koordynator(konf, args)

    try:
        znalezione = koordynator.znajdz_zadanie(klient, args.zadanie)
    except (koordynator.Odmowa, BladAPI) as blad:
        print(str(blad), file=sys.stderr)
        return 2
    if znalezione.zadanie is None:
        print(znalezione.powod_braku(args.zadanie), file=sys.stderr)
        return 2
    zadanie = znalezione.zadanie

    ticket_id = zadanie.get("ticket_id")
    external_id = zadanie.get("external_id") or ""
    if not ticket_id:
        print(f"Zadanie {external_id} nie ma sprawy, więc wyniku nie ma gdzie sprawdzić.\n"
              f"Jego wynik (jeśli powstał) jest w komentarzu zadania — obejrzyj go w panelu "
              f"i zamknij zadanie ręcznie, świadomie.", file=sys.stderr)
        return 2

    jest, co = koordynator.wynik_jest_na_sprawie(
        klient, ticket_id=str(ticket_id), external_id=external_id)
    if not jest:
        # ODMOWA, nie ostrzeżenie. Zamknięcie „na słowo" znaczy, że `completed` przestaje
        # cokolwiek znaczyć — zadania schodzą z tablicy niezależnie od tego, co po nich zostało.
        print(f"Nie zamykam {external_id}: {co}.\n"
              f"Sprawdź sprawę w panelu. Jeśli wynik naprawdę jest, a ja go nie widzę — "
              f"zamknij zadanie w panelu, świadomie.", file=sys.stderr)
        return 2

    try:
        klient.ustaw_status(str(zadanie.get("id")), "completed")
    except BladAPI as blad:
        print(f"Wynik jest na sprawie, ale nie mogę zamknąć zadania: {blad}", file=sys.stderr)
        return 1
    print(f"Odebrane: {external_id} — {co}.")
    return 0


def polecenie_status(args) -> int:
    """`whoami` koordynatora: kim jestem, gdzie pracuję i co flota ma na głowie."""
    kod = polecenie_whoami(args)
    print()
    try:
        polecenie_kolejka(args)
    except SystemExit as stop:
        # Brak uprawnień koordynatora nie ma unieważniać tego, co `whoami` już pokazał.
        print(str(stop), file=sys.stderr)
    return kod


def polecenie_worker(args) -> int:
    from .worker import uruchom
    konf = konfiguracja.wczytaj()
    klient, org = _klient_i_organizacja(konf, args)
    rozjazd = tozsamosc.rozjazd_sluga(konf.slug, org)
    if rozjazd:
        # SF-32 (ADVERTPR-918): worker z cudzym slugiem kręci się pusty i wygląda na zdrowy —
        # tętno bije, zadań „nie ma". Odmowa na starcie jest jedynym miejscem, w którym
        # ktoś to zobaczy. Slugu NIE poprawiamy sami: zmiana ustawień przez proces w tle,
        # bez człowieka przy terminalu, to decyzja, której nikt by nie zauważył.
        raise SystemExit(
            f"{rozjazd}\n\nWorker nie startuje. Popraw slug: `{_jak_wolac()} init` albo\n"
            f'  "slug": "{org.agent_slug}"\nw {konfiguracja.sciezka()}')
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


# ══ profil ASYSTENT (v0.3) ══════════════════════════════════════════════════════
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
    print(f"Adres:  {asystent.adres_sprawy(sprawa_id, baza=konf.adres)}")
    print(f"\n{co_dalej}")


# ══ SKRZYNKA WIADOMOŚCI (ADVERTPR-812) ═══════════════════════════════════════
#
# Odbiór przez PULL: agent pobiera swoje wiadomości tak, jak bierze zadania. Most tic zostaje
# budzikiem dla sesji, które akurat nic nie robią — nie jedynym sposobem dowiedzenia się
# czegokolwiek. Kontrakt: `backend/docs/API-SKRZYNKA-WIADOMOSCI-812.md`.


def polecenie_inbox(args) -> int:
    """Moje wiadomości. Domyślnie POKAZUJE i POTWIERDZA odbiór; `--podejrzyj` tylko pokazuje.

    Potwierdzenie jest domyślne, bo skrzynka bez potwierdzania to czwarty półkanał: wygląda
    jak dostarczone i nikt nie wie, czy ktokolwiek to przeczytał. `--podejrzyj` istnieje dla
    człowieka, który chce zerknąć cudzym... to znaczy WŁASNYM kluczem, nie zabierając sobie
    wiadomości z kolejki przed właściwym taktem pętli.
    """
    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)

    odebrane = skrzynka.pobierz(klient, limit=args.limit, dni=args.dni)
    if odebrane.powod_braku:
        # 503 przed rewizją, 422 przy kluczu bez właściciela albo koncie bez sluga agenckiego.
        # Oba są stanem konfiguracji, nie awarią Kitu — i mają brzmieć jak stan.
        print(f"Skrzynka niedostępna: {odebrane.powod_braku}", file=sys.stderr)
        return 3
    if not odebrane.cos_jest:
        print("Skrzynka pusta.")
        return 0

    print(skrzynka.opis(odebrane))
    if odebrane.zalegle:
        print(f"\nZALEGŁE (dłużej niż próg): {odebrane.zalegle}")

    if args.podejrzyj:
        print("\n(--podejrzyj: odbioru NIE potwierdzono — wiadomości zostają w kolejce)")
        return 0

    skrzynka.potwierdz(klient, odebrane)
    if odebrane.niepotwierdzone:
        print(f"\nUWAGA: {len(odebrane.niepotwierdzone)} wiadomości pokazano, ale NIE udało się "
              f"potwierdzić ich odbioru — wrócą w następnym takcie.", file=sys.stderr)
        return 1
    print(f"\nOdbiór potwierdzony ({len(odebrane.wiadomosci)}).")
    return 0


def polecenie_outbox(args) -> int:
    """Czy to, co wysłałem, doszło. Odpowiedź na to jedno pytanie, nie druga skrzynka."""
    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)
    try:
        dane = klient.nadane(dni=args.dni, tylko_zalegle=args.zalegle)
    except BladAPI as blad:
        print(f"Nie udało się pobrać wysłanych: {blad}", file=sys.stderr)
        return 3

    pozycje = dane.get("wiadomosci") or []
    if not pozycje:
        print("Nic nie wysłałeś w tym oknie." if not args.zalegle
              else "Nic nie zalega — wszystko odebrane.")
        return 0
    print(f"{len(pozycje)} z {dane.get('razem', 0)} · zalega: {dane.get('zalegle', 0)}\n")
    for w in pozycje:
        znacznik = (w.get("utworzono") or "")[:16].replace("T", " ")
        stan = f"{w.get('odebrali', 0)}/{w.get('adresatow', 0)} odebrało"
        if w.get("odpowiedzieli"):
            stan += f", {w['odpowiedzieli']} odpowiedziało"
        if w.get("nieudanych"):
            stan += f", {w['nieudanych']} nieudanych"
        flaga = " ⚠ ZALEGA" if w.get("zalega") else ""
        print(f"  [{znacznik}] → {', '.join(w.get('adresaci') or ['?'])}{flaga}")
        print(f"    {stan}   ({w.get('status')})")
        print(f"    {(w.get('body') or '')[:100]}")
    return 0


#: Zmienna środowiskowa, która niesie kontekst zadania do `sf-kit nowa-sprawa` — ta sama
#: treść, co argument `--kontekst`, dla wykonawców wołanych z poza Kitowego parsera.
ZMIENNA_KONTEKSTU = "SF_KIT_KONTEKST"


def _klient_dla_zapisu(konf: konfiguracja.Konfiguracja, args,
                       org_z_linku: str = "") -> tuple[Klient, tozsamosc.Organizacja]:
    """Klient do ZAPISU: Organizacja wyłącznie jawna — `--org` albo `?org=` z linku (SF-51).

    Odmowa jest łagodna i pouczająca: komunikat mówi, CO podać, nie tylko że brakuje.
    """
    klient = _klient_bez_organizacji(konf)
    toz = _tozsamosc(klient)
    try:
        org = tozsamosc.wybierz_dla_zapisu(
            toz, wskazana=(getattr(args, "org", None) or ""), z_linku=org_z_linku or "")
    except tozsamosc.BrakWyboru as brak:
        raise SystemExit(str(brak)) from None
    klient.organizacja = org.uuid
    return klient, org


def _sprawa_dla_zapisu(klient: Klient, wskazanie: str) -> tuple[dict, str]:
    """`(sprawa, org_z_linku)`. Link daje identyfikator od razu (bez przeszukiwania listy)
    i niesie własną Organizację; numer/uuid rozwiązujemy po liście, jak dotychczas."""
    link = flow.sprawa_z_linku(wskazanie)
    if link:
        return {"id": link}, flow.organizacja_z_linku(wskazanie) or ""
    return asystent.znajdz_sprawe(klient, wskazanie), ""


def _ostrzez_o_szkicu(klient: Klient, sprawa_id: str) -> None:
    """Jedno zdanie przy zapisie na szkicu — człowiek ma wiedzieć, że nikt tego nie zobaczy,
    dopóki sprawa nie wejdzie do obiegu: koordynator publikuje na zgodę (`publikuj --zgoda`)
    albo człowiek w panelu (pkt 6 kontraktu SF-51)."""
    try:
        if flow.czy_szkic(klient.sprawa(sprawa_id)):
            print(f"\n{flow.OSTRZEZENIE_SZKICU}", file=sys.stderr)
    except BladAPI:
        pass                              # ostrzeżenie jest dodatkiem, nie bramką


def polecenie_nowa_sprawa(args) -> int:
    """Nowa sprawa z gotową pracą — z załącznikami, obserwującymi i numerem na wyjściu.

    SF-51: zapis wymaga jawnej Organizacji (`--org` — link tu nie wchodzi, bo nowej sprawy
    jeszcze nie ma). A gdy w kontekście zadania stoi link do ISTNIEJĄCEJ sprawy, odmawiamy
    z podpowiedzią — to jest dokładnie sytuacja z 25.09 (Wójt założył nową sprawę w złej
    Organizacji zamiast odpowiedzieć w FMXA-1).
    """
    kontekst = getattr(args, "kontekst", None)
    if kontekst is None:
        kontekst = os.environ.get(ZMIENNA_KONTEKSTU, "")
    if kontekst:
        link = flow.link_z_tekstu(kontekst)
        if link:
            print("W kontekście tego zadania jest już sprawa:\n"
                  f"  {link}\n"
                  "Nie zakładaj obok niej nowej — ODPOWIEDZ w tej:\n"
                  f"  sf-kit odpowiedz \"{link}\" --opis odpowiedz.md\n"
                  "Jeśli naprawdę ma powstać osobna sprawa, uruchom ponownie bez --kontekst "
                  f"i bez zmiennej {ZMIENNA_KONTEKSTU}.", file=sys.stderr)
            return 2

    konf = konfiguracja.wczytaj()
    klient = _klient_dla_zapisu(konf, args)[0]

    opis = _opis_z_wejscia(args) or asystent.opis_domyslny(args.tytul)
    try:
        odp = klient.zaloz_sprawe(
            tytul=args.tytul, opis=opis, kategoria=args.tag or None,
            obserwatorzy=konf.obserwatorzy_domyslni or None,
            szkic=bool(getattr(args, "szkic", False)),
        )
    except BladAPI as blad:
        print(f"Nie udało się założyć sprawy: {blad}", file=sys.stderr)
        return 1

    sprawa_id = str(odp.get("ticket_id") or odp.get("id") or "")
    numer = asystent.numer_sprawy(odp) or ""

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

    if asystent.czy_opis_wymaga_uzupelnienia(opis):
        print("\nUWAGA: opis został ze szkieletu (nawiasy do wypełnienia). "
              "Uzupełnij go wpisem, zanim ktoś to odbierze.")
    if getattr(args, "szkic", False):
        # Szkic bez tego zdania wygląda jak zgłoszenie, które nie doszło: nie ma maila, nie ma
        # sprawy na liście, nie ma numeru w powiadomieniu. Mówimy wprost, co się stało i jak
        # się domyka — publikacja to akt człowieka: koordynator na zgodę albo panel SF.
        _pokaz_sprawe(konf, sprawa_id, numer,
                      co_dalej="To jest SZKIC — nie poszło żadne powiadomienie i sprawy nie ma "
                               "na listach.\nDo obiegu sprawę wprowadza człowiek: koordynator "
                               "poleceniem `sf-kit publikuj --zgoda <wpis>` (zgoda ownera/"
                               "admina z tej Organizacji) albo w panelu SF przyciskiem "
                               "„Opublikuj”.\nDo tego czasu dopisujesz do niej "
                               "wpisami jak zwykle (też po cichu):\n"
                               f"  sf-kit wpis {numer or sprawa_id} --opis notatka.md")
        return 0
    _pokaz_sprawe(konf, sprawa_id, numer,
                  co_dalej="Od tej chwili pytania i postęp idą WPISAMI na tej sprawie:\n"
                           f"  sf-kit wpis {numer or sprawa_id} --opis notatka.md")
    return 0


def polecenie_wpis(args) -> int:
    """Wpis na istniejącej sprawie — postęp, kolejna wersja, odpowiedź.

    `--do <slug>` (ADVERTPR-812) wysyła to samo jako WIADOMOŚĆ do sesji agenta. Bez `--sprawa`
    jest to samodzielna wiadomość; razem ze sprawą — wpis na sprawie ORAZ wiadomość, żeby
    adresat nie musiał jej zauważyć sam.

    SF-51: wpis to ZAPIS — Organizacja musi być jawna (`--org` albo link do sprawy z `?org=`),
    a na sprawie-szkicu Kit ostrzega przed zapisem, nie po nim.
    """
    if not args.sprawa and not args.do:
        # Sprawa jest opcjonalna WYŁĄCZNIE przy `--do` (samodzielna wiadomość). Bez obu
        # nie wiadomo, gdzie ten tekst miałby wylądować — a domyślenie się tego za człowieka
        # znaczyłoby wpis w sprawie wybranej przez Kita.
        print("Nie wiem, gdzie to dopisać. Podaj sprawę (`sf-kit wpis SF-7 --opis …`)\n"
              "albo adresata wiadomości (`sf-kit wpis --do <slug> --opis …`).", file=sys.stderr)
        return 2

    konf = konfiguracja.wczytaj()

    if args.do and not args.sprawa:
        klient = _klient(konf, args)
        tresc = _opis_z_wejscia(args)
        if not tresc:
            print("Wiadomość bez treści nie niesie niczego. Podaj `--opis plik.md`.",
                  file=sys.stderr)
            return 2
        return _wyslij_wiadomosc(klient, args.do, tresc)

    org_z_linku = ""
    if flow.sprawa_z_linku(args.sprawa):
        org_z_linku = flow.organizacja_z_linku(args.sprawa) or ""
    klient = _klient_dla_zapisu(konf, args, org_z_linku)[0]

    try:
        sprawa, _ = _sprawa_dla_zapisu(klient, args.sprawa)
    except (ValueError, BladAPI) as blad:
        print(str(blad), file=sys.stderr)
        return 1

    tresc = _opis_z_wejscia(args)
    if not tresc and not args.zalacz:
        print("Wpis bez treści i bez plików nie niesie niczego. "
              "Podaj `--opis plik.md` albo `--zalacz …`.", file=sys.stderr)
        return 2

    sprawa_id = str(sprawa["id"])
    _ostrzez_o_szkicu(klient, sprawa_id)
    try:
        if args.zalacz:
            klient.wpis_z_plikami(sprawa_id, tresc, args.zalacz,
                                  widocznosc=args.widocznosc)
        else:
            klient.wpis(sprawa_id, tresc, widocznosc=args.widocznosc)
    except (BladAPI, FileNotFoundError) as blad:
        print(f"Nie udało się dopisać: {blad}", file=sys.stderr)
        return 1

    if args.do:
        # Wpis JEST zapisany — wiadomość jest dodatkiem. Porażka wysyłki nie ma prawa
        # przedstawić zapisanego wpisu jako nieudanego.
        _wyslij_wiadomosc(klient, args.do, tresc or "(wpis z załącznikami)")

    _pokaz_sprawe(konf, sprawa_id, asystent.numer_sprawy(sprawa),
                  co_dalej="Wpis dodany.")
    return 0


def _powod_serwera(blad: BladAPI) -> str:
    """`detail` z odpowiedzi SF, gdy jest napisem — tam SF mówi, DLACZEGO odmówił."""
    try:
        detail = json.loads(getattr(blad, "szczegoly", "") or "{}").get("detail")
    except (ValueError, AttributeError):
        return ""
    return detail if isinstance(detail, str) else ""


def _sprawa_i_wpis(klient, args) -> tuple[dict, str] | None:
    """Sprawa i PEŁNY identyfikator wpisu albo `None` (komunikat już wypisany)."""
    from . import wpisy

    try:
        sprawa = asystent.znajdz_sprawe(klient, args.sprawa)
        return sprawa, wpisy.rozwin_wpis(klient, str(sprawa["id"]), args.wpis)
    except (ValueError, BladAPI) as blad:
        print(str(blad), file=sys.stderr)
        return None


def polecenie_wpis_edytuj(args) -> int:
    """Popraw treść wpisu na sprawie — SF zachowuje poprzednią wersję (ADVERTPR-782).

    Kody wyjścia: 0 poprawione (albo treść bez zmian), 1 odmowa/błąd SF, 2 złe wejście.
    """
    from . import wpisy

    from types import SimpleNamespace

    # `_opis_z_wejscia` zna plik i `-` (stdin) — ta sama droga co przy `wpis --opis`.
    tresc = args.tresc if args.tresc is not None else _opis_z_wejscia(
        SimpleNamespace(opis=args.plik))
    try:
        cialo = wpisy.cialo_edycji(tresc or "", args.powod)
    except wpisy.ZlyWpis as blad:
        print(f"Nie wysyłam: {blad}", file=sys.stderr)
        return 2

    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)
    wynik = _sprawa_i_wpis(klient, args)
    if wynik is None:
        return 1
    sprawa, wpis_id = wynik
    sprawa_id = str(sprawa["id"])
    try:
        przed = klient.wpis_sprawy(sprawa_id, wpis_id)
        po = klient.edytuj_wpis(sprawa_id, wpis_id, cialo)
    except BladAPI as blad:
        powod = _powod_serwera(blad)
        print(f"Wpis {wpis_id[:8]} NIE został poprawiony: {powod or blad}", file=sys.stderr)
        if getattr(blad, "kod", None) == 403:
            # Własność wpisu pisanego kluczem rozpoznaje SF dopiero od wdrożenia 782 D5
            # (znacznik `autor_klucza`); starsze wpisy nie są niczyje. Mówimy, co zrobić.
            print("  Bez roli administratora Organizacji poprawisz tylko własny wpis: napisany\n"
                  "  tym kluczem albo kluczem tego samego właściciela, i to dopiero po wdrożeniu\n"
                  "  782 na serwerze (starsze wpisy poprawia administrator). Dopisz nowy wpis\n"
                  "  z korektą albo poproś administratora "
                  "(README: „Poprawianie własnych wpisów”).", file=sys.stderr)
        return 1

    ile_przed, ile_po = int(przed.get("edited_count") or 0), int(po.get("edited_count") or 0)
    if ile_po == ile_przed and (po.get("content") or "") == (przed.get("content") or ""):
        # SF nie tworzy wersji dla identycznej treści — mówimy to, zamiast udawać zmianę.
        print(f"Wpis {wpis_id[:8]}: treść bez zmian — nie powstała nowa wersja.")
        return 0
    print(f"Wpis {wpis_id[:8]} poprawiony (edytowano {ile_po}×). Poprzednia treść została "
          f"w historii: `{_jak_wolac()} wpis-wersje {args.sprawa} {wpis_id[:8]}`.")
    return 0


def polecenie_wpis_wersje(args) -> int:
    """Bieżąca treść wpisu i jego poprzednie wersje (ADVERTPR-782)."""
    from . import wpisy

    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)
    wynik = _sprawa_i_wpis(klient, args)
    if wynik is None:
        return 1
    sprawa, wpis_id = wynik
    try:
        wpis = klient.wpis_sprawy(str(sprawa["id"]), wpis_id)
        wersje = klient.wersje_wpisu(str(sprawa["id"]), wpis_id)
    except BladAPI as blad:
        print(f"Nie udało się pobrać historii: {_powod_serwera(blad) or blad}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"wpis": wpis, "wersje": wersje}, ensure_ascii=False, indent=2,
                         default=str))
        return 0
    print(wpisy.historia_do_pokazania(wpis, wersje, skrot=0 if args.pelne else 160))
    return 0


def _wyslij_wiadomosc(klient, slug: str, tresc: str) -> int:
    """Wiadomość do sesji agenta. Odmowę uprawnienia tłumaczymy WPROST.

    POMIAR Z 16.09, ŻEBY NIKT NIE SZUKAŁ USTERKI W KICIE: uprawnienie `console:write` ma
    w całej instalacji **jeden aktywny klucz na 31** — poller mostu (`iris-console-bridge`).
    Żaden klucz agencki go nie ma, więc ta droga odbije się o 403 do czasu, aż ktoś nada
    to uprawnienie. To decyzja o dostępie, nie usterka: komunikat mówi, o co poprosić.
    """
    try:
        klient.wiadomosc_do(slug, tresc)
    except BladAPI as blad:
        if getattr(blad, "kod", None) == 403:
            print(f"Twój klucz nie ma uprawnienia `console:write`, więc nie może wysłać "
                  f"wiadomości do „{slug}”. Wpis (jeśli był) ZOSTAŁ zapisany.\n"
                  f"Pomiar z 16.09: to uprawnienie ma 1 aktywny klucz na 31 (poller mostu). "
                  f"Poproś Agatę o `console:write` dla swojego klucza.", file=sys.stderr)
            return 4
        print(f"Nie udało się wysłać wiadomości do „{slug}”: {blad}", file=sys.stderr)
        return 1
    print(f"Wiadomość wysłana do „{slug}”.")
    return 0


def polecenie_zalacz(args) -> int:
    """Same pliki do istniejącej sprawy — jednym wpisem, więc jednym powiadomieniem."""
    konf = konfiguracja.wczytaj()
    org_z_linku = ""
    if flow.sprawa_z_linku(args.sprawa):
        org_z_linku = flow.organizacja_z_linku(args.sprawa) or ""
    klient = _klient_dla_zapisu(konf, args, org_z_linku)[0]
    try:
        sprawa, _ = _sprawa_dla_zapisu(klient, args.sprawa)
        _ostrzez_o_szkicu(klient, str(sprawa["id"]))
        klient.wpis_z_plikami(str(sprawa["id"]), args.notka or "Załączniki.", args.pliki)
    except (ValueError, BladAPI, FileNotFoundError) as blad:
        print(str(blad), file=sys.stderr)
        return 1
    print(f"Wysłane pliki: {len(args.pliki)}")
    _pokaz_sprawe(konf, str(sprawa["id"]), asystent.numer_sprawy(sprawa), co_dalej="Gotowe.")
    return 0


# ── flow odpowiedzi i treści w wersjach (SF-51, ADVERTPR-948) ─────────────────


def polecenie_odpowiedz(args) -> int:
    """Odpowiedź w ISTNIEJĄCEJ sprawie — domyślnie wiadomość widoczna na zewnątrz,
    z `--wewn` notatka wewnętrzna. Organizacja bierze się z linku do sprawy (`?org=`).

    To polecenie istnieje, żeby odpowiedź była łatwiejsza niż założenie nowej sprawy:
    wystarczy wkleić link ze sprawy, którą się prowadzi.
    """
    if not args.sprawa:
        print("Podaj link do sprawy (z ?org=…) albo numer z --org: "
              "sf-kit odpowiedz <link|numer> --opis odpowiedz.md [--wewn]", file=sys.stderr)
        return 2
    konf = konfiguracja.wczytaj()
    org_z_linku = flow.organizacja_z_linku(args.sprawa) or ""
    klient = _klient_dla_zapisu(konf, args, org_z_linku)[0]
    try:
        sprawa, _ = _sprawa_dla_zapisu(klient, args.sprawa)
    except (ValueError, BladAPI) as blad:
        print(str(blad), file=sys.stderr)
        return 1

    tresc = _opis_z_wejscia(args)
    if not tresc:
        print("Odpowiedź bez treści nie niesie niczego. Podaj `--opis plik.md` "
              "(albo `-` ze standardowego wejścia).", file=sys.stderr)
        return 2

    sprawa_id = str(sprawa["id"])
    _ostrzez_o_szkicu(klient, sprawa_id)
    widocznosc = "internal" if args.wewn else "external"
    try:
        klient.wpis(sprawa_id, tresc, widocznosc=widocznosc)
    except BladAPI as blad:
        print(f"Nie udało się odpowiedzieć: {blad}", file=sys.stderr)
        return 1
    co = "Notatka wewnętrzna dodana." if args.wewn else "Odpowiedź wysłana (widoczna na zewnątrz)."
    _pokaz_sprawe(konf, sprawa_id, asystent.numer_sprawy(sprawa), co_dalej=co)
    return 0


def polecenie_tresc_wersja(args) -> int:
    """Kolejna wersja treści: załącznik `nazwa-vN.md` + wpis „co się zmieniło" (SF-51).

    Numer bierze się z historii załączników na sprawie (najwyższy istniejący `nazwa-vN` + 1) —
    nie z dat, bo wersja to liczba porządkowa. Opis „co się zmieniło" najlepiej podać
    `--zmiany`; bez niego Kit liczy go z różnicy względem poprzedniej wersji.
    """
    from types import SimpleNamespace

    konf = konfiguracja.wczytaj()
    org_z_linku = ""
    if flow.sprawa_z_linku(args.sprawa):
        org_z_linku = flow.organizacja_z_linku(args.sprawa) or ""
    klient = _klient_dla_zapisu(konf, args, org_z_linku)[0]
    try:
        sprawa, _ = _sprawa_dla_zapisu(klient, args.sprawa)
    except (ValueError, BladAPI) as blad:
        print(str(blad), file=sys.stderr)
        return 1
    sprawa_id = str(sprawa["id"])

    try:
        karta = klient.sprawa(sprawa_id)
    except BladAPI as blad:
        print(f"Nie udało się odczytać sprawy: {blad}", file=sys.stderr)
        return 1
    _ostrzez_o_szkicu(klient, sprawa_id)

    bazowa, koncowka = flow.podziel_nazwe(args.plik)
    zalaczniki = [(z.get("original_filename") or z.get("filename") or "", str(z.get("id") or ""))
                  for e in karta.get("entries") or []
                  for z in e.get("attachments") or []]
    n = flow.nastepna_wersje([nazwa for nazwa, _ in zalaczniki], bazowa, koncowka)
    nazwa = flow.nazwa_wersji(bazowa, koncowka, n)

    try:
        tresc_pliku = Path(args.plik).expanduser().read_text(encoding="utf-8")
    except OSError as blad:
        print(f"Nie udało się przeczytać pliku {args.plik}: {blad}", file=sys.stderr)
        return 2

    zmiany = _opis_z_wejscia(SimpleNamespace(opis=args.zmiany))
    if not zmiany:
        poprzednia = (dict(zalaczniki).get(flow.nazwa_wersji(bazowa, koncowka, n - 1))
                      if n > 1 else "")
        if poprzednia:
            try:
                import tempfile
                with tempfile.TemporaryDirectory() as katalog:
                    cel = Path(katalog) / "poprzednia"
                    klient.pobierz_zalacznik(poprzednia, cel, limit_bajtow=10 << 20)
                    zmiany = flow.podsumowanie_zmian(
                        cel.read_text(encoding="utf-8", errors="replace"), tresc_pliku)
            except (BladAPI, OSError):
                zmiany = ""
        if not zmiany:
            zmiany = ("pierwsza wersja tej treści na sprawie" if n == 1 else
                      f"wersja v{n}; nie udało się porównać z v{n - 1} — opisz zmiany "
                      f"`--zmiany`, jeśli mają być widoczne")

    wpis = (f"**Wersja v{n}** — `{bazowa}{koncowka}`.\n\n"
            f"**Co się zmieniło** — {zmiany}.\n\n"
            f"Załącznik: `{nazwa}`.")

    import tempfile
    with tempfile.TemporaryDirectory() as katalog:
        kopia = Path(katalog) / nazwa
        kopia.write_text(tresc_pliku, encoding="utf-8")
        try:
            klient.wpis_z_plikami(sprawa_id, wpis, [str(kopia)])
        except (BladAPI, FileNotFoundError) as blad:
            print(f"Nie udało się wysłać wersji v{n}: {blad}", file=sys.stderr)
            return 1

    print(f"Wersja v{n} wysłana jako {nazwa} (wpis z opisem zmian).")
    _pokaz_sprawe(konf, sprawa_id, asystent.numer_sprawy(sprawa),
                  co_dalej="Kolejna wersja: sf-kit tresc-wersja "
                           f"{asystent.numer_sprawy(sprawa) or sprawa_id} {args.plik}")
    return 0


def polecenie_opis_sprawy(args) -> int:
    """`PATCH /tickets/{id}` z nowym opisem — pod strażnikiem długości (SF-51).

    Strażnik: opis dłuższy niż próg ze `config.json` (`straznik_opisu_max`, domyślnie 1500
    znaków) na sprawie, która już opis ma, zatrzymuje polecenie z propozycją `tresc-wersja`.
    `--mimo-to` znaczy: czytam ostrzeżenie i świadomie nadpisuję.
    """
    konf = konfiguracja.wczytaj()
    org_z_linku = ""
    if flow.sprawa_z_linku(args.sprawa):
        org_z_linku = flow.organizacja_z_linku(args.sprawa) or ""
    klient = _klient_dla_zapisu(konf, args, org_z_linku)[0]
    try:
        sprawa, _ = _sprawa_dla_zapisu(klient, args.sprawa)
        karta = klient.sprawa(str(sprawa["id"]))
    except (ValueError, BladAPI) as blad:
        print(str(blad), file=sys.stderr)
        return 1

    from types import SimpleNamespace
    opis = _opis_z_wejscia(SimpleNamespace(opis=args.plik))
    if opis is None:
        print("Podaj opis plikiem: --plik opis.md (albo `-` ze standardowego wejścia).",
              file=sys.stderr)
        return 2

    ostrzezenie = flow.straznik_opisu(karta.get("description") or "", opis,
                                      limit=konf.straznik_opisu_max)
    if ostrzezenie and not args.mimo_to:
        print(ostrzezenie, file=sys.stderr)
        return 2

    try:
        klient.zmien_opis_sprawy(str(sprawa["id"]), opis)
    except BladAPI as blad:
        print(f"Nie udało się zmienić opisu: {blad}", file=sys.stderr)
        return 1
    print("Opis sprawy zmieniony.")
    return 0


def polecenie_publikuj(args) -> int:
    """Publikacja szkicu do obiegu ze zgodą — `--zgoda` to wpis z zgodą człowieka z rolą
    owner/admin na publikację (SF-51). Pełny identyfikator wpisu przechodzi bez rozwijania:
    zgoda może leżeć na DOWOLNEJ sprawie tej Organizacji (w tym na oknie rozmowy z
    koordynatorem), a Organizację, autora i wiek zgody (≤ 7 dni) sprawdza serwer. Skrót
    (początek ≥ 6 znaków) rozwijamy na publikowanej sprawie. Bez zgody trasa odmawia —
    Kit pokazuje `detail` serwera bez zmian."""
    from . import wpisy

    konf = konfiguracja.wczytaj()
    org_z_linku = ""
    if flow.sprawa_z_linku(args.sprawa):
        org_z_linku = flow.organizacja_z_linku(args.sprawa) or ""
    klient = _klient_dla_zapisu(konf, args, org_z_linku)[0]
    try:
        sprawa, _ = _sprawa_dla_zapisu(klient, args.sprawa)
    except (ValueError, BladAPI) as blad:
        print(str(blad), file=sys.stderr)
        return 1
    sprawa_id = str(sprawa["id"])

    if wpisy.czy_pelny_uuid(args.zgoda):
        wpis_id = args.zgoda.strip().lower()
    else:
        try:
            wpis_id = wpisy.rozwin_wpis(klient, sprawa_id, args.zgoda)
        except wpisy.ZlyWpis as blad:
            print(f"Nie wysyłam: {blad}", file=sys.stderr)
            return 2

    try:
        klient.publikuj(sprawa_id, zgoda=wpis_id)
    except BladAPI as blad:
        print(f"Nie udało się opublikować: {_powod_serwera(blad) or blad}", file=sys.stderr)
        return 1
    print("Sprawa opublikowana.")
    return 0


def polecenie_sprawy(args) -> int:
    """Sprawy w Organizacji tego klucza — żeby wiedzieć, do czego dopisywać."""
    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)
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
        numer = asystent.numer_sprawy(s) or str(s.get("id", ""))[:8]
        zmiana = asystent.ostatnia_zmiana(s)
        print(f"  {numer:14} {(s.get('title') or '')[:58]}")
        print(f"  {'':14} {s.get('status', '?'):12} {zmiana}")
    return 0


def polecenie_sprawa(args) -> int:
    """SF-38: karta sprawy dla WYKONAWCY — odczyt kluczem Kita, klucz nie trafia do promptu.

    Ten sam tekst, który worker dokleja do ramki (`kontekst._tekst`) — jeden format, więc
    wykonawca doczytujący w trakcie widzi to samo, co dostał na starcie, tylko bez obcięcia
    liczby wpisów. Co wolno przeczytać, rozstrzyga serwer (clearance klucza).
    """
    from . import kontekst

    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)
    try:
        wskazana = asystent.znajdz_sprawe(klient, args.sprawa)
        karta = klient.sprawa(str(wskazana.get("id")))
    except BladAPI as blad:
        print(f"Nie udało się pobrać sprawy: {blad}", file=sys.stderr)
        return 1
    poprzedni = kontekst.ILE_WPISOW
    try:
        kontekst.ILE_WPISOW = 10_000 if args.wszystkie else poprzedni
        print(kontekst._tekst(karta, kontekst.Pakiet(), Path.cwd()))
    finally:
        kontekst.ILE_WPISOW = poprzedni
    zal = [(z.get("id"), z.get("original_filename")) for e in karta.get("entries") or []
           for z in e.get("attachments") or [] if z.get("filename")]
    if zal:
        print("\nZałączniki (id → nazwa), pobranie: `sf-kit zalacznik <id> --do <plik>`:")
        for zid, nazwa in zal:
            print(f"  {zid}  {nazwa}")
    return 0


def polecenie_zalacznik(args) -> int:
    """SF-38: pobierz jeden załącznik do pliku — dla wykonawcy, bez klucza w prompcie."""
    from . import kontekst

    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)
    cel = Path(args.do or f"zalacznik-{args.id}")
    try:
        ile = klient.pobierz_zalacznik(args.id, cel, limit_bajtow=kontekst.LIMIT_PLIKU)
    except BladAPI as blad:
        print(f"Nie udało się pobrać załącznika: {blad}", file=sys.stderr)
        return 1
    print(f"Zapisano {cel} ({ile} B)")
    return 0


# ── profil KOORDYNATOR: warstwa administracyjna (ADVERTPR-879) ───────────────
#
# Trzy polecenia niżej to trzy wpadki z jednej doby (18.09), w której koordynatorka trzy razy
# ogłosiła „tego się nie da", a funkcja istniała. Czwarte (`kontrakt`) istnieje po to, żeby
# czwartej wpadki nie było — bo trzy polecenia rozwiązują trzy wczorajsze pomyłki i ani jednej
# jutrzejszej.
#
# BRAMKI UPRAWNIEŃ TU NIE MA I TO JEST DECYZJA. `_koordynator()` sprawdza `plans:write`, bo
# zlecanie zadań tego wymaga — ale nadania wymagają roli owner, a konto agenta superadmina,
# i żadne z nich nie ma nic wspólnego z `plans:write`. Odsianie po cudzym uprawnieniu
# odebrałoby polecenie komuś, kto ma prawo je wykonać. Rozstrzyga serwer; Kit dba tylko o to,
# żeby jego odmowa dało się przeczytać.


def _pola_surowe(args) -> dict:
    """`--pole nazwa=wartość` → słownik. Furtka na pola, których Kit jeszcze nie modeluje.

    PO CO TA FURTKA ISTNIEJE, SKORO KIT I TAK JE ODRZUCI
    Bez niej bramka z `_sprawdz_pola` byłaby teatrem: argparse przepuszcza wyłącznie flagi,
    które sam zna, więc ciało żądania nigdy nie zawierałoby nieznanego pola i sprawdzenie
    nie miałoby czego łapać. Człowiek, który wie (albo myśli, że wie), że trasa przyjmuje
    jeszcze jedno pole, sięgnie po nie i tak — dziś przez curl, gdzie nikt go nie ostrzeże.

    Furtka przenosi ten moment do Kita: pole, które trasa zna, pojedzie; pole, którego nie
    zna, zatrzyma się z adresem tej, która je obsługuje. To jest cała różnica między
    „przyjęte i zignorowane" a „odmowa, która mówi, dokąd iść".

    Wartości `true`/`false`/`null` i liczby rozpoznajemy, resztę zostawiamy tekstem —
    zgadywanie typów dalej niż to kończy się polem `"1"` tam, gdzie miało być `1`.
    """
    wynik: dict = {}
    for wpis in (getattr(args, "pola", None) or []):
        if "=" not in wpis:
            raise SystemExit(f"`--pole {wpis}` — brakuje znaku `=`. Poprawnie: --pole nazwa=wartość")
        nazwa, _, wartosc = wpis.partition("=")
        nazwa = nazwa.strip()
        wartosc = wartosc.strip()
        if wartosc.lower() in {"true", "false"}:
            wynik[nazwa] = (wartosc.lower() == "true")
        elif wartosc.lower() in {"null", "none"}:
            wynik[nazwa] = None
        elif wartosc.lstrip("-").isdigit():
            wynik[nazwa] = int(wartosc)
        else:
            wynik[nazwa] = wartosc
    return wynik


def _sprawdz_pola(op, cialo: dict) -> None:
    """Wymaganie 3 ze sprawy: pole, którego trasa nie obsługuje, ZATRZYMUJEMY przed wysyłką.

    Po wysłaniu jest za późno na rozpoznanie pomyłki — serwer albo je cicho pominie (to jest
    potwierdzona usterka `PATCH …/agents/{uuid}` z polem `permissions`: HTTP 200 i zero skutku),
    albo odpowie 422 nie mówiąc, gdzie to pole naprawdę mieszka.
    """
    nieznane = kontrakt.nieznane_pola(op, cialo)
    if not nieznane:
        return
    linie = [f"Te pola nie należą do operacji `{op.nazwa}` ({op.metoda} {op.trasa}):"]
    linie += [f"  {pole} — {powod}" for pole, powod in nieznane]
    linie.append(f"\nPełny opis operacji: {_jak_wolac()} kontrakt {op.nazwa}")
    raise SystemExit("\n".join(linie))


def polecenie_kontrakt(args) -> int:
    """Co dana operacja potrafi i jakich pól wymaga. Bez sieci, bez klucza, bez logowania."""
    if getattr(args, "sprawdz", False):
        return _kontrakt_sprawdz(args)

    nazwa = (getattr(args, "operacja", None) or "").strip()
    if not nazwa:
        print(kontrakt.spis())
        return 0

    op = kontrakt.znajdz(nazwa)
    if op:
        print(op.opis())
        return 0

    # „Nie ma" z POWODEM, nie samo „nie znam". Bo „nie da się" bez powodu wraca następnego
    # dnia jako to samo pytanie — a wpisane do sprawy jest fałszywą diagnozą do prostowania.
    powod = kontrakt.podpowiedz_nie_ma(nazwa)
    if powod:
        print(f"`{nazwa}` — Kit tego nie obsługuje.\n\n{powod}")
        return 0

    print(f"Nie znam operacji `{nazwa}`.\n", file=sys.stderr)
    print(kontrakt.spis(), file=sys.stderr)
    return 2


def _kontrakt_sprawdz(args) -> int:
    """Porównaj katalog Kitu z żywym `openapi.json`. Rozjazd ma boleć tu, nie u człowieka.

    Katalog w `kontrakt.py` jest kopią kształtu, który żyje po drugiej stronie — czyli
    kandydatem do cichego rozjazdu. To polecenie jest jedyną rzeczą, która robi z niego
    kandydata GŁOŚNEGO.
    """
    import json as _json
    import urllib.error
    import urllib.request

    konf = konfiguracja.wczytaj()
    adres = f"{konf.adres.rstrip('/')}/openapi.json"
    try:
        with urllib.request.urlopen(adres, timeout=30) as odp:
            surowe = odp.read().decode("utf-8", errors="replace")
        opis = _json.loads(surowe)
    except (urllib.error.URLError, ValueError) as blad:
        # Osobny, jawny komunikat dla przypadku „200, ale to nie jest kontrakt". Sprawdzone
        # 18.09: `sf.dpakula.pl/openapi.json` oddaje HTTP 200 i stronę frontu, bo nginx nie
        # przepuszcza tej ścieżki do backendu. Sam kod odpowiedzi powiedziałby „jest".
        print(f"Nie mam skąd wziąć kontraktu z serwera ({adres}).\n"
              f"Powód: {blad}\n\n"
              f"Jeśli adres oddaje HTTP 200 ze stroną, to znaczy, że `/openapi.json` łapie "
              f"front, a nie API — poproś o przepuszczenie tej ścieżki do backendu "
              f"(ADVERTPR-879).\n"
              f"Katalog Kitu działa dalej bez tego; sprawdzono go z kodem "
              f"{kontrakt.SPRAWDZONO}.", file=sys.stderr)
        return 1

    sciezki = opis.get("paths", {})
    schematy = (opis.get("components") or {}).get("schemas") or {}

    def pola_zadania(wzorzec: str, metoda: str) -> tuple[set, set]:
        """Nazwy pól ciała i pola wymagane — z żywego opisu, nie z naszej pamięci."""
        trasa = (sciezki.get(wzorzec) or {}).get(metoda) or {}
        ciało = trasa.get("requestBody") or {}
        odn = (((ciało.get("content") or {}).get("application/json") or {})
               .get("schema") or {}).get("$ref", "")
        schemat = schematy.get(odn.rsplit("/", 1)[-1], {}) if odn else {}
        return set(schemat.get("properties") or {}), set(schemat.get("required") or [])

    rozjazdy = 0
    for op in kontrakt.KATALOG:
        wzorzec = op.trasa.replace("{numer}", "{tenant_id}").replace("{uuid}", "{user_id}")
        if wzorzec not in sciezki:
            print(f"✗ {op.nazwa}: serwer nie zna trasy {wzorzec}")
            rozjazdy += 1
            continue
        metoda = op.metoda.rsplit("/", 1)[-1].strip().lower()
        serwer, serwer_wymaga = pola_zadania(wzorzec, metoda)
        nasze = set(op.wymagane) | set(op.opcjonalne)
        # Porównujemy OBIE strony różnicy. „Serwer zna, my nie" znaczy, że Kit odrzuci pole,
        # które przeszłoby — i to jest gorsze niż odwrotność, bo blokuje pracę.
        nowe_u_nich = sorted(serwer - nasze)
        martwe_u_nas = sorted(nasze - serwer)
        inne_wymagane = sorted(serwer_wymaga.symmetric_difference(set(op.wymagane)))
        if nowe_u_nich or martwe_u_nas or inne_wymagane:
            rozjazdy += 1
            print(f"✗ {op.nazwa} ({metoda.upper()} {wzorzec})")
            if nowe_u_nich:
                print(f"    serwer przyjmuje, Kit ODRZUCI: {', '.join(nowe_u_nich)}")
            if martwe_u_nas:
                print(f"    Kit wymienia, serwer nie zna: {', '.join(martwe_u_nas)}")
            if inne_wymagane:
                print(f"    rozjazd pól wymaganych: {', '.join(inne_wymagane)}")
        else:
            print(f"✓ {op.nazwa}: {metoda.upper()} {wzorzec}")

    print(f"\nSprawdzono {len(kontrakt.KATALOG)} operacji, rozjazdów: {rozjazdy}.")
    if rozjazdy:
        print(f"Katalog Kitu (`sf_kit/kontrakt.py`, sprawdzony {kontrakt.SPRAWDZONO}) "
              f"rozjechał się z serwerem — popraw katalog, zanim ktoś oprze na nim pracę.")
    return 1 if rozjazdy else 0


def polecenie_agent_dodaj(args) -> int:
    """Konto agenta: użytkownik + członkostwo + nadania + klucz, jednym aktem.

    Wpadka, którą to zamyka (18.09): „nie da się założyć konta agenta przez API, bo
    `POST /agents` odpowiada odmową metody". Właściwa trasa jest pod Organizacją.
    """
    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)
    op = kontrakt.znajdz("agent-dodaj")

    uprawnienia = list(args.uprawnienia) if args.uprawnienia else None
    cialo = {"email": args.email, "full_name": args.nazwa, "agent_slug": args.slug}
    if uprawnienia is not None:
        cialo["permissions"] = uprawnienia
    cialo.update(_pola_surowe(args))
    _sprawdz_pola(op, cialo)

    try:
        numer = klient.numer_organizacji(getattr(args, "org", None) or "")
    except BladAPI as blad:
        print(f"Nie umiem wskazać Organizacji: {blad}", file=sys.stderr)
        return 1

    try:
        wynik = klient.zaloz_agenta(numer, email=args.email, nazwa=args.nazwa,
                                    slug=args.slug, uprawnienia=uprawnienia,
                                    dodatkowe=_pola_surowe(args))
    except BladAPI as blad:
        print(f"Nie udało się założyć konta: {blad}", file=sys.stderr)
        if getattr(blad, "kod", None) == 403:
            print("Tę operację wykonuje wyłącznie superadmin SF — rola owner Organizacji "
                  "tu nie wystarczy.", file=sys.stderr)
        return 1

    konto = wynik.get("user") or {}
    klucz_out = wynik.get("api_key") or {}
    nadane = list(wynik.get("nadania") or [])
    print(f"Konto założone: {konto.get('email')} (slug `{args.slug}`, Organizacja nr {numer})")
    print(f"  nadania na członkostwie: {', '.join(nadane) or 'brak'}")

    # Serwer ODSIEWA uprawnienia spoza swojego katalogu po cichu — odpowiedź pokazuje stan
    # faktyczny, ale nikt jej nie czyta linijka po linijce. Różnicę mówimy wprost, bo
    # „poprosiłam o `plans:write`, dostałam ciszę" to następna noc szukania, czemu agent
    # dostaje 403 mimo „nadanego" uprawnienia.
    if uprawnienia:
        odpadlo = sorted(set(uprawnienia) - set(nadane))
        if odpadlo:
            print(f"  ⚠ serwer ODSIAŁ: {', '.join(odpadlo)} — te uprawnienia nie są "
                  f"w jego katalogu nadawalnych. Konto ich NIE ma.")

    sekret = klucz_out.get("api_key") or ""
    if sekret:
        print(f"\n  klucz (widoczny RAZ, przekaż go teraz): {sekret}")
        print(f"  prefiks: {klucz_out.get('key_prefix')}   zakres: {klucz_out.get('scope')}")

    # WERYFIKACJA, nie kod odpowiedzi. 201 na konfigurację, która nie działa, to jest dokładnie
    # to, co kosztowało pół nocy przy kluczu z polem `scope`.
    if sekret and not args.bez_proby:
        print("\nPróbne wywołanie nowym kluczem (`GET /me`):")
        try:
            kim = klient.probne_wywolanie(sekret)
        except BladAPI as blad:
            print(f"  ✗ klucz NIE DZIAŁA: {blad}", file=sys.stderr)
            print("  Konto powstało, ale sekretem nie da się pracować — zgłoś to, "
                  "zanim go przekażesz.", file=sys.stderr)
            return 1
        orgs = [o.get("slug") for o in (kim.get("organizacje") or [])]
        print(f"  ✓ działa — konto {(kim.get('konto') or {}).get('email')}, "
              f"Organizacje: {', '.join(str(o) for o in orgs) or 'brak'}")
    return 0


def polecenie_nadaj(args) -> int:
    """Nadania na CZŁONKOSTWIE konta w tej Organizacji — odczyt i zapis.

    Wpadka, którą to zamyka (18.09): „nie ma tras odczytu ani zapisu nadań" — bo pytanie szło
    pod adresem agenta. Trasy są pod adresem użytkownika w Organizacji.
    """
    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)
    op = kontrakt.znajdz("nadaj")

    # BRAMKA PRZED SIECIĄ, nie po niej. Pierwsza wersja sprawdzała pola dopiero przed zapisem,
    # czyli PO odczycie stanu — a gdy odczyt kończył się odmową (403 to tu normalna sytuacja
    # dla kogoś, kto nie jest ownerem), człowiek dostawał komunikat o uprawnieniach i nigdy
    # nie dowiadywał się, że w dodatku wysyłał pole, którego ta trasa nie zna. Błąd składni
    # żądania ma być widoczny zawsze, niezależnie od tego, czy wolno je w ogóle wykonać.
    zamiar = {"ustaw_domyslne": True} if args.domyslne else {
        "permissions": list(args.uprawnienia)}
    zamiar.update(_pola_surowe(args))
    if not args.pokaz:
        _sprawdz_pola(op, zamiar)

    if args.uprawnienia and args.domyslne:
        # Serwer rozstrzyga to na korzyść `ustaw_domyslne` i robi to po cichu. Suma tych dwóch
        # rzeczy nie istnieje, więc pytanie o nią jest pomyłką, a nie wyborem do zgadnięcia.
        print("`--domyslne` i `--uprawnienie` wykluczają się: serwer w takim żądaniu bierze "
              "sam zestaw domyślny i lista przepada bez słowa. Wybierz jedno.", file=sys.stderr)
        return 2

    try:
        numer = klient.numer_organizacji(getattr(args, "org", None) or "")
    except BladAPI as blad:
        print(f"Nie umiem wskazać Organizacji: {blad}", file=sys.stderr)
        return 1

    try:
        przed = klient.nadania(numer, args.konto)
    except BladAPI as blad:
        print(f"Nie udało się odczytać nadań: {blad}", file=sys.stderr)
        if getattr(blad, "kod", None) == 404:
            print("404 tutaj znaczy jedno z dwojga: nie ma takiego konta ALBO nie ma ono "
                  "AKTYWNEGO członkostwa w tej Organizacji. Zawieszone członkostwo nie "
                  "daje nic, więc nadanie na nim też by nie dało.", file=sys.stderr)
        return 1

    stan = list(przed.get("permissions") or [])
    if args.pokaz or (not args.uprawnienia and not args.domyslne):
        print(f"{przed.get('email')} w Organizacji nr {numer}:")
        print(f"  {', '.join(stan) or 'brak nadań'}")
        if not args.pokaz:
            print(f"\nŻeby zmienić: {_jak_wolac()} nadaj {args.konto} "
                  f"--uprawnienie tickets:read --uprawnienie tickets:comment")
            print(f"           albo: {_jak_wolac()} nadaj {args.konto} --domyslne")
        return 0

    try:
        po = klient.ustaw_nadania(numer, args.konto,
                                  uprawnienia=list(args.uprawnienia), domyslne=args.domyslne,
                                  dodatkowe=_pola_surowe(args))
    except BladAPI as blad:
        print(f"Nie udało się zapisać nadań: {blad}", file=sys.stderr)
        if getattr(blad, "kod", None) == 403:
            print("Nadania zmienia owner Organizacji albo superadmin — rola admin "
                  "tu nie wystarczy.", file=sys.stderr)
        return 1

    teraz = list(po.get("permissions") or [])
    nadane = sorted(set(teraz) - set(stan))
    odebrane = sorted(set(stan) - set(teraz))
    print(f"{po.get('email')} w Organizacji nr {numer}:")
    print(f"  {', '.join(teraz) or 'brak nadań'}")
    if nadane:
        print(f"  + {', '.join(nadane)}")
    if odebrane:
        print(f"  − {', '.join(odebrane)}")
    if not nadane and not odebrane:
        print("  (bez zmian — dokładnie to już tam było)")
    return 0


def polecenie_agent_napraw(args) -> int:
    """Członkostwo ISTNIEJĄCEGO konta: slug, rodzaj, katalog boardu.

    To jest trasa, na której siedziała usterka z ADVERTPR-879: `permissions` przyjmowane
    i ignorowane, 200 i zero skutku. Po stronie API poprawione tego samego dnia; tutaj
    bramka stoi przed wysyłką, żeby pomyłkę rozpoznać, zanim zamieni się w żądanie.
    """
    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)
    op = kontrakt.znajdz("agent-napraw")

    cialo: dict = {}
    if args.slug:
        cialo["agent_slug"] = args.slug
    if args.rodzaj:
        cialo["kind"] = args.rodzaj
    if args.katalog:
        cialo["board_root"] = args.katalog
    cialo.update(_pola_surowe(args))
    _sprawdz_pola(op, cialo)

    if not cialo:
        print("Nie podałaś, co poprawić. Co najmniej jedno z: --slug, --rodzaj, --katalog.",
              file=sys.stderr)
        return 2
    if cialo.get("kind") == "agent" and not cialo.get("agent_slug"):
        # Serwer odrzuci to 422, ale powód warto podać ZANIM ktoś zobaczy kod błędu: plakietka
        # agenta bez katalogu boardu to stan, który wygląda na zrobiony i nie działa (SF-37).
        print("`--rodzaj agent` wymaga `--slug`: slug wskazuje katalog boardu, a bez niego "
              "delegacja odbija się 422 dopiero w momencie użycia.", file=sys.stderr)
        return 2

    try:
        numer = klient.numer_organizacji(getattr(args, "org", None) or "")
        wynik = klient.napraw_agenta(numer, args.konto, slug=args.slug or "",
                                     rodzaj=args.rodzaj or "", katalog=args.katalog or "",
                                     dodatkowe=_pola_surowe(args))
    except BladAPI as blad:
        print(f"Nie udało się poprawić członkostwa: {blad}", file=sys.stderr)
        if getattr(blad, "kod", None) == 403:
            print("Tę operację wykonuje wyłącznie superadmin SF.", file=sys.stderr)
        return 1

    print(f"Członkostwo poprawione: {wynik.get('email')} w „{wynik.get('tenant_slug')}”")
    print(f"  rodzaj: {wynik.get('kind')}   slug: {wynik.get('agent_slug') or 'brak'}")
    print(f"  katalog boardu: {wynik.get('board_root') or 'kanon ze sluga'}")
    print(f"\nUprawnień to NIE zmienia — te nadaje `{_jak_wolac()} nadaj {args.konto}`.")
    return 0


def polecenie_klucz_wystaw(args) -> int:
    """Klucz API w tej Organizacji — i próbne wywołanie, zanim ktokolwiek go dostanie.

    Wpadka, którą to zamyka (18.09): pole `scope` przyjęte i zignorowane. Serwer odpowiedział
    201 na konfigurację, która nie działa, a wyszło to po pół nocy pracy.
    """
    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)
    op = kontrakt.znajdz("klucz-wystaw")

    # `None` (brak zawężenia) i `[]` (klucz bez żadnych praw) to po tamtej stronie dwie różne
    # rzeczy — kontrakt 545 §4.3. Kit nie ma prawa zamienić jednego w drugie, bo tak powstaje
    # martwy sekret: 201 przy wystawieniu i 403 na każdym żądaniu.
    uprawnienia = list(args.uprawnienia) if args.uprawnienia else None

    cialo = {"source_name": args.nazwa, "scope": args.zakres, "permissions": uprawnienia}
    if args.opis:
        cialo["description"] = args.opis
    if args.wlasciciel:
        cialo["user_email"] = args.wlasciciel
    cialo.update(_pola_surowe(args))
    _sprawdz_pola(op, cialo)

    if args.zakres == "user" and not args.wlasciciel:
        print("Klucz osobisty (`--zakres user`) pożycza prawa właściciela, więc bez "
              "`--wlasciciel <mail>` nie ma czyich praw pożyczyć.", file=sys.stderr)
        return 2

    try:
        wynik = klient.wystaw_klucz(nazwa=args.nazwa, opis=args.opis or "",
                                    zakres=args.zakres, wlasciciel=args.wlasciciel or "",
                                    uprawnienia=uprawnienia, dodatkowe=_pola_surowe(args))
    except BladAPI as blad:
        print(f"Nie udało się wystawić klucza: {blad}", file=sys.stderr)
        return 1

    sekret = wynik.get("api_key") or ""
    print(f"Klucz wystawiony: {wynik.get('key_prefix')}…  zakres: {wynik.get('scope')}")
    print(f"  właściciel: {wynik.get('user_email') or 'brak (klucz integracyjny)'}")
    zaw = wynik.get("permissions")
    print(f"  zawężenie: {', '.join(zaw) if zaw else 'brak — pełne prawa właściciela'}")
    print(f"\n  sekret (widoczny RAZ): {sekret}")

    if args.bez_proby:
        return 0
    print("\nPróbne wywołanie tym kluczem (`GET /me`):")
    try:
        kim = klient.probne_wywolanie(sekret)
    except BladAPI as blad:
        print(f"  ✗ klucz NIE DZIAŁA: {blad}", file=sys.stderr)
        print("  Nie przekazuj go — 201 przy wystawieniu nie jest dowodem, że działa.",
              file=sys.stderr)
        return 1
    orgs = [o.get("slug") for o in (kim.get("organizacje") or [])]
    klucz_info = kim.get("klucz") or {}
    print(f"  ✓ działa — zakres {klucz_info.get('scope')}, "
          f"zawężony: {'tak' if klucz_info.get('zawezony') else 'nie'}")
    print(f"  Organizacje, w których zadziała: {', '.join(str(o) for o in orgs) or 'brak'}")
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
    # `--org` jest GLOBALNE, a nie flagą wybranych poleceń: agent bywa członkiem kilku
    # Organizacji i musi móc wskazać właściwą przy KAŻDYM poleceniu. Flaga na części poleceń
    # znaczyłaby, że reszta cicho używa domyślnej — czyli dokładnie to, przed czym broni
    # zasada „nigdy pierwsza z brzegu".
    parser.add_argument("--org", default=None, metavar="SLUG|UUID",
                        help="w której Organizacji wykonać to polecenie "
                             "(domyślna jest wygodą, nie regułą)")
    pod = parser.add_subparsers(dest="polecenie", required=True)

    pod.add_parser("init", help="zapisz klucz i ustawienia").set_defaults(funkcja=polecenie_init)
    pod.add_parser("whoami", help="sprawdź, czy klucz działa").set_defaults(funkcja=polecenie_whoami)
    pod.add_parser("tasks", help="pokaż moje zadania").set_defaults(funkcja=polecenie_tasks)
    bl = pod.add_parser("blok", help="[agent] jeden blok osi albo katalog rodzajów (SF-7)")
    bl.add_argument("co", nargs="?", default="typy",
                    help="identyfikator bloku (rdzeniowy albo dziennikowy) "
                         "albo `typy` — katalog rodzajów")
    bl.add_argument("--json", action="store_true", help="surowa odpowiedź serwera")
    bl.set_defaults(funkcja=polecenie_blok)

    # `os` stoi przy `blok`, bo to ta sama warstwa: oś pokazuje ciąg bloków, `blok` — jeden
    # z nich w całości. Identyfikator z nawiasu przy wierszu osi wkleja się wprost w `sf-kit blok`.
    osc = pod.add_parser("os", help="[agent] oś sprawy — wiersze, ze zwijaniem ciągów (SF-7)")
    osc.add_argument("sprawa", help="numer (SF-7) albo identyfikator sprawy")
    grupa_widoku = osc.add_mutually_exclusive_group()
    # Wzajemnie wykluczające się, bo `--pelna --zwinieta` naraz nie ma znaczenia, a ciche
    # wygranie jednej z nich uczy człowieka, że flagi bywają ignorowane.
    grupa_widoku.add_argument("--pelna", action="store_true",
                              help="wiersz po wierszu (domyślnie — tak samo jak w panelu)")
    grupa_widoku.add_argument("--zwinieta", action="store_true",
                              help="zwiń ciągi zmian technicznych w wiersze-grupy")
    osc.add_argument("--rozwin", default=None, metavar="ID",
                     help="rozwiń TĘ grupę (identyfikator z nawiasu); działa ze `--zwinieta`")
    osc.add_argument("--limit", type=int, default=50, help="ile wpisów na stronę (domyślnie 50)")
    osc.add_argument("--json", action="store_true", help="surowa odpowiedź serwera")
    osc.set_defaults(funkcja=polecenie_os)
    pod.add_parser("heartbeat", help="czy worker tego agenta żyje").set_defaults(funkcja=polecenie_heartbeat)
    pod.add_parser("rotate", help="wymień sekret klucza przed wygaśnięciem (okno 7 dni)"
                   ).set_defaults(funkcja=polecenie_rotate)
    us = pod.add_parser("usluga",
                        help="[worker] usługa workera: systemd (Linux) albo launchd (macOS)")
    us.add_argument("--pokaz", action="store_true",
                    help="wypisz treść pliku zamiast go zapisywać")
    us.add_argument("--system", choices=["linux", "macos"], default=None,
                    help="dla JAKIEGO systemu generować (domyślnie: ten, na którym stoisz) "
                         "— przydatne, gdy przygotowujesz plik dla innej maszyny")
    us.set_defaults(funkcja=polecenie_usluga)

    # ── profil ASYSTENT ────────────────────────────────────────────────────────
    # `zglos` i `nowa-sprawa` to jedno polecenie pod dwiema nazwami — SF-51 wprowadza
    # nazwę mówiącą, co powstaje, i strażnik kontekstu; dotychczasowa nazwa zostaje,
    # bo ludzie i skrypty jej używają.
    def _parser_nowej_sprawy(nazwa: str, help_txt: str):
        p = pod.add_parser(nazwa, help=help_txt)
        p.add_argument("--tytul", required=True, help="jednym zdaniem: co jest gotowe")
        p.add_argument("--opis", default=None, metavar="PLIK",
                       help="plik z opisem (albo `-` = ze standardowego wejścia)")
        p.add_argument("--tag", default=None, help="kategoria sprawy, np. makieta")
        p.add_argument("--zalacz", nargs="*", default=[], metavar="PLIK",
                       help="pliki do dołączenia (idą JEDNYM wpisem)")
        p.add_argument("--szkic", action="store_true",
                       help="wersja robocza: NIC nie wysyła, publikuje człowiek w SF (SF-4)")
        p.add_argument("--kontekst", default=None, metavar="TEKST",
                       help="kontekst zadania (link do sprawy) — gdy w nim jest istniejąca "
                            "sprawa, Kit odmawia i podpowiada `odpowiedz` (SF-51); "
                            f"alternatywnie zmienna {ZMIENNA_KONTEKSTU}")
        p.set_defaults(funkcja=polecenie_nowa_sprawa)
        return p

    _parser_nowej_sprawy("zglos", "[asystent] zgłoś gotową pracę jako nową sprawę")
    _parser_nowej_sprawy("nowa-sprawa", "[asystent] nowa sprawa z gotową pracą (SF-51)")

    ib = pod.add_parser("inbox", help="[agent] moje wiadomości — pokaż i potwierdź odbiór")
    ib.add_argument("--limit", type=int, default=skrzynka.LIMIT_TAKTU,
                    help=f"ile wziąć w tym takcie (domyślnie {skrzynka.LIMIT_TAKTU})")
    ib.add_argument("--dni", type=int, default=None, help="okno skrzynki w dniach")
    ib.add_argument("--podejrzyj", action="store_true",
                    help="pokaż BEZ potwierdzania odbioru (wiadomości zostają w kolejce)")
    ib.set_defaults(funkcja=polecenie_inbox)

    ob = pod.add_parser("outbox", help="[agent] czy to, co wysłałem, doszło")
    ob.add_argument("--dni", type=int, default=None, help="okno w dniach")
    ob.add_argument("--zalegle", action="store_true", help="tylko nieodebrane po progu")
    ob.set_defaults(funkcja=polecenie_outbox)

    wp = pod.add_parser("wpis", help="[asystent] dopisz postęp albo odpowiedź do sprawy")
    wp.add_argument("--do", dest="do", default=None, metavar="SLUG",
                    help="wyślij to TAKŻE jako wiadomość do sesji agenta (bez --sprawa: "
                         "samodzielna wiadomość)")
    # `nargs="?"`, bo `--do <slug>` BEZ sprawy jest udokumentowaną drogą („samodzielna
    # wiadomość") i `polecenie_wpis` obsługuje ją od v0.5.1 — tylko parser jej nie przepuszczał.
    # Pomoc obiecywała coś, co kończyło się `error: the following arguments are required`.
    wp.add_argument("sprawa", nargs="?", default=None,
                    help="numer (FM-12), identyfikator albo link do sprawy z ?org=… "
                         "(można pominąć przy `--do`: wtedy sama wiadomość)")
    wp.add_argument("--opis", default=None, metavar="PLIK",
                    help="plik z treścią (albo `-` = ze standardowego wejścia)")
    wp.add_argument("--zalacz", nargs="*", default=[], metavar="PLIK")
    wp.add_argument("--widocznosc", choices=["internal", "external"], default="internal",
                    help="internal = widzi zespół (domyślnie), external = widzi też klient")
    wp.set_defaults(funkcja=polecenie_wpis)

    # ADVERTPR-782: poprawianie wpisów. Nazwy po polsku jak reszta Kitu, trasy i pola —
    # dokładnie te z API (`PATCH …/entries/{id}`, `…/versions`; decyzja D1, 24.09).
    we = pod.add_parser("wpis-edytuj", help="[agent] popraw treść wpisu — SF zachowa "
                                            "poprzednią wersję (ADVERTPR-782)")
    we.add_argument("sprawa", help="numer (FM-12) albo identyfikator sprawy")
    we.add_argument("wpis", help="identyfikator wpisu albo jego początek (min. 6 znaków)")
    zrodlo = we.add_mutually_exclusive_group(required=True)
    zrodlo.add_argument("--plik", default=None, metavar="PLIK",
                        help="nowa treść z pliku (`-` = ze standardowego wejścia) — ZALECANE")
    zrodlo.add_argument("--tresc", default=None, metavar="TEKST",
                        help="nowa treść wprost (krótkie poprawki; argument widać w `ps`)")
    we.add_argument("--powod", default=None, metavar="TEKST",
                    help="po co ta zmiana — trafia do historii wersji (do 500 znaków)")
    we.set_defaults(funkcja=polecenie_wpis_edytuj)

    ww = pod.add_parser("wpis-wersje", help="[agent] bieżąca treść wpisu i jego poprzednie "
                                            "wersje (ADVERTPR-782)")
    ww.add_argument("sprawa", help="numer (FM-12) albo identyfikator sprawy")
    ww.add_argument("wpis", help="identyfikator wpisu albo jego początek (min. 6 znaków)")
    ww.add_argument("--pelne", action="store_true", help="pełne treści zamiast skrótów")
    ww.add_argument("--json", action="store_true", help="surowa odpowiedź SF")
    ww.set_defaults(funkcja=polecenie_wpis_wersje)

    za = pod.add_parser("zalacz", help="[asystent] dołóż pliki do istniejącej sprawy")
    za.add_argument("sprawa", help="numer (FM-12), identyfikator albo link do sprawy z ?org=…")
    za.add_argument("pliki", nargs="+", metavar="PLIK")
    za.add_argument("--notka", default=None, help="jedno zdanie, co to za pliki")
    za.set_defaults(funkcja=polecenie_zalacz)

    # ── flow odpowiedzi i treści w wersjach (SF-51, ADVERTPR-948) ─────────────
    od = pod.add_parser("odpowiedz", help="[asystent] odpowiedz w ISTNIEJĄCEJ sprawie — "
                                           "wiadomość na zewnątrz / notatka --wewn (SF-51)")
    od.add_argument("sprawa", help="link do sprawy (z ?org=…) albo numer — przy numerze "
                                   "Organizację podaj przez --org")
    od.add_argument("--opis", default=None, metavar="PLIK",
                    help="treść odpowiedzi (albo `-` = ze standardowego wejścia)")
    od.add_argument("--wewn", action="store_true",
                    help="notatka wewnętrzna (domyślnie: wiadomość widoczna na zewnątrz)")
    od.set_defaults(funkcja=polecenie_odpowiedz)

    tv = pod.add_parser("tresc-wersja", help="[asystent] kolejna wersja treści: załącznik "
                                             "nazwa-vN.md + wpis „co się zmieniło” (SF-51)")
    tv.add_argument("sprawa", help="numer, identyfikator albo link do sprawy z ?org=…")
    tv.add_argument("plik", metavar="PLIK", help="plik z treścią (np. raport.md)")
    tv.add_argument("--zmiany", default=None, metavar="PLIK",
                    help="co się zmieniło — plik albo `-`; bez tego Kit liczy z różnicy "
                         "względem poprzedniej wersji")
    tv.set_defaults(funkcja=polecenie_tresc_wersja)

    os_ = pod.add_parser("opis-sprawy", help="[asystent] zmień opis sprawy — długi opis "
                                             "zatrzymuje strażnik, treść idź w wersjach (SF-51)")
    os_.add_argument("sprawa", help="numer, identyfikator albo link do sprawy z ?org=…")
    os_.add_argument("--plik", required=True, metavar="PLIK",
                     help="nowy opis (albo `-` = ze standardowego wejścia)")
    os_.add_argument("--mimo-to", dest="mimo_to", action="store_true",
                     help="nadpisz mimo ostrzeżenia strażnika (świadoma decyzja)")
    os_.set_defaults(funkcja=polecenie_opis_sprawy)

    pu = pod.add_parser("publikuj", help="[asystent] opublikuj szkic ze zgodą — --zgoda to wpis "
                                         "z zgodą ownera/admina na publikację (SF-51)")
    pu.add_argument("sprawa", help="numer, identyfikator albo link do sprawy z ?org=…")
    pu.add_argument("--zgoda", required=True, metavar="WPIS",
                    help="pełny identyfikator wpisu z zgodą ownera/admina (może być z innej "
                         "sprawy tej Organizacji, ≤ 7 dni) albo jego początek ≥ 6 znaków "
                         "z publikowanej sprawy")
    pu.set_defaults(funkcja=polecenie_publikuj)

    sp = pod.add_parser("sprawy", help="[asystent] sprawy w tej Organizacji")
    sp.add_argument("--limit", type=int, default=50)
    sp.set_defaults(funkcja=polecenie_sprawy)
    sa = pod.add_parser("sprawa", help="[wykonawca] karta sprawy: opis, wpisy, załączniki (SF-38)")
    sa.add_argument("sprawa", help="numer (ADVERTPR-927) albo identyfikator sprawy")
    sa.add_argument("--wszystkie", action="store_true", help="wszystkie wpisy, nie ostatnie 15")
    sa.set_defaults(funkcja=polecenie_sprawa)
    za = pod.add_parser("zalacznik", help="[wykonawca] pobierz jeden załącznik do pliku (SF-38)")
    za.add_argument("id", help="identyfikator załącznika (z `sf-kit sprawa`)")
    za.add_argument("--do", help="ścieżka pliku docelowego (domyślnie zalacznik-<id>)")
    za.set_defaults(funkcja=polecenie_zalacznik)

    # ── profil KOORDYNATOR ────────────────────────────────────────────────────
    fl = pod.add_parser("flota", help="[koordynator] agenci tej Organizacji; "
                                      "`flota rejestr PLIK` — migawka rejestru do SF")
    fl.set_defaults(funkcja=polecenie_flota)
    # Podpolecenie OPCJONALNE: gołe `sf-kit flota` ma działać jak dotąd.
    fl_pod = fl.add_subparsers(dest="flota_co", required=False)
    fr = fl_pod.add_parser("rejestr", help="wyślij migawkę agents.json do SF (SF-18)")
    fr.add_argument("plik", help="ścieżka do agents.json (rejestr Agaty, na macu)")
    fr.add_argument("--pokaz", action="store_true",
                    help="pokaż, co poszłoby do SF, i NIC nie wysyłaj")
    fr.set_defaults(funkcja=polecenie_flota_rejestr)

    zl = pod.add_parser("zlec", help="[koordynator] zleć zadanie agentowi (zawsze na sprawie)")
    zl.add_argument("--tytul", required=True, help="jednym zdaniem: co ma powstać")
    zl.add_argument("--agent-slug", required=True, dest="agent_slug",
                    help="komu zlecasz (slug z `flota`)")
    zl.add_argument("--sprawa", required=True,
                    help="numer (AUT-12) albo identyfikator sprawy — WYMAGANE")
    zl.add_argument("--opis", default=None, metavar="PLIK",
                    help="treść zadania z pliku albo `-` dla standardowego wejścia")
    zl.add_argument("--priorytet", default="medium",
                    choices=["low", "medium", "high", "urgent"])
    zl.add_argument("--termin", default=None, metavar="DATA", help="np. 2026-09-20T18:00:00Z")
    zl.add_argument("--projekt", default=None, help="kod projektu")
    zl.add_argument("--kategoria", default=None)
    zl.set_defaults(funkcja=polecenie_zlec)

    ko = pod.add_parser("kolejka", help="[koordynator] co flota ma w toku")
    ko.add_argument("--agent-slug", default=None, dest="agent_slug", help="zawęź do agenta")
    ko.add_argument("--status", default=None,
                    choices=["queued", "in_progress", "on_hold", "completed"])
    ko.set_defaults(funkcja=polecenie_kolejka)

    od = pod.add_parser("odbierz", help="[koordynator] zamknij zadanie po sprawdzeniu wyniku")
    od.add_argument("zadanie", help="identyfikator zadania (`external_id` albo uuid)")
    od.set_defaults(funkcja=polecenie_odbierz)

    # ── profil KOORDYNATOR: warstwa administracyjna (ADVERTPR-879) ────────────
    #
    # NIGDZIE nie ma flagi z numerem Organizacji i to jest cała odpowiedź na pułapkę
    # z wymagania 2 sprawy. Numer w ścieżce to `tenants.id`, a nagłówek niesie `uuid` —
    # dwa identyfikatory tej samej Organizacji w jednym żądaniu. Zamiast ostrzegać przed
    # pomyłką, odbieramy okazję do jej popełnienia: Kit tłumaczy `--org <slug>` na numer sam.

    kt = pod.add_parser("kontrakt",
                        help="[koordynator] co dana operacja potrafi i jakich pól wymaga")
    kt.add_argument("operacja", nargs="?", default=None,
                    help="nazwa operacji; bez niej — spis wszystkich")
    kt.add_argument("--sprawdz", action="store_true",
                    help="porównaj katalog Kitu z żywym openapi.json serwera")
    kt.set_defaults(funkcja=polecenie_kontrakt)

    ad = pod.add_parser("agent-dodaj",
                        help="[koordynator] załóż konto agenta (konto + nadania + klucz)")
    ad.add_argument("slug", help="slug agenta = nazwa katalogu boardu (male-litery-z-myslnikami)")
    ad.add_argument("--email", required=True)
    ad.add_argument("--nazwa", required=True, help="nazwa wyświetlana konta")
    ad.add_argument("--uprawnienie", dest="uprawnienia", action="append", default=[],
                    metavar="NAZWA",
                    help="powtarzalne; bez tego serwer nadaje swój zestaw domyślny")
    ad.add_argument("--bez-proby", dest="bez_proby", action="store_true",
                    help="nie wołaj GET /me nowym kluczem (domyślnie Kit to robi)")
    ad.add_argument("--pole", dest="pola", action="append", default=[], metavar="NAZWA=WARTOSC",
                    help="pole ciała żądania, którego Kit nie modeluje; nieznane trasie "
                         "zostanie ODRZUCONE z adresem właściwej trasy")
    ad.set_defaults(funkcja=polecenie_agent_dodaj)

    nd = pod.add_parser("nadaj",
                        help="[koordynator] uprawnienia konta w tej Organizacji")
    nd.add_argument("konto", help="uuid konta (nie slug agenta)")
    nd.add_argument("--uprawnienie", dest="uprawnienia", action="append", default=[],
                    metavar="NAZWA", help="powtarzalne; ZASTĘPUJE dotychczasowy zestaw")
    nd.add_argument("--domyslne", action="store_true",
                    help="ustaw zestaw domyślny agenta (wyklucza się z --uprawnienie)")
    nd.add_argument("--pokaz", action="store_true", help="tylko odczyt, bez zapisu")
    nd.add_argument("--pole", dest="pola", action="append", default=[], metavar="NAZWA=WARTOSC",
                    help="pole ciała żądania, którego Kit nie modeluje; nieznane trasie "
                         "zostanie ODRZUCONE z adresem właściwej trasy")
    nd.set_defaults(funkcja=polecenie_nadaj)

    an = pod.add_parser("agent-napraw",
                        help="[koordynator] popraw członkostwo istniejącego konta")
    an.add_argument("konto", help="uuid albo adres konta")
    an.add_argument("--slug", default=None, help="slug agenta = nazwa katalogu boardu")
    an.add_argument("--rodzaj", default=None, choices=["agent", "human"])
    an.add_argument("--katalog", default=None, metavar="SCIEZKA",
                    help="nadpisanie katalogu boardu (bez tego: kanon ze sluga)")
    an.add_argument("--pole", dest="pola", action="append", default=[], metavar="NAZWA=WARTOSC",
                    help="pole ciała żądania, którego Kit nie modeluje; nieznane trasie "
                         "zostanie ODRZUCONE z adresem właściwej trasy")
    an.set_defaults(funkcja=polecenie_agent_napraw)

    kw = pod.add_parser("klucz-wystaw",
                        help="[koordynator] wystaw klucz API i sprawdź, że działa")
    kw.add_argument("nazwa", help="źródło klucza — po czym go poznasz na liście")
    kw.add_argument("--opis", default=None)
    kw.add_argument("--zakres", default="tenant", choices=["tenant", "user", "super_admin"],
                    help="jak daleko klucz sięga w Organizacjach (to NIE są uprawnienia)")
    kw.add_argument("--wlasciciel", default=None, metavar="MAIL",
                    help="wymagane przy --zakres user: czyje prawa klucz pożycza")
    kw.add_argument("--uprawnienie", dest="uprawnienia", action="append", default=[],
                    metavar="NAZWA",
                    help="ZAWĘŻENIE klucza; bez tego klucz ma pełne prawa właściciela")
    kw.add_argument("--bez-proby", dest="bez_proby", action="store_true",
                    help="nie wołaj GET /me nowym kluczem (domyślnie Kit to robi)")
    kw.add_argument("--pole", dest="pola", action="append", default=[], metavar="NAZWA=WARTOSC",
                    help="pole ciała żądania, którego Kit nie modeluje; nieznane trasie "
                         "zostanie ODRZUCONE z adresem właściwej trasy")
    kw.set_defaults(funkcja=polecenie_klucz_wystaw)

    st = pod.add_parser("status", help="[koordynator] kim jestem + kolejka floty")
    st.add_argument("--agent-slug", default=None, dest="agent_slug")
    st.add_argument("--status", default=None,
                    choices=["queued", "in_progress", "on_hold", "completed"])
    st.set_defaults(funkcja=polecenie_status)

    w = pod.add_parser("worker", help="[worker] pętla: bierz zadania, wykonuj, raportuj")
    # `kimi` DOŁOŻONY w v0.5.3 (ADVERTPR-850). Adapter `WykonawcaKimi` był w Kicie od 807 C3
    # i działał — tylko parser go nie przyjmował, więc jedyną drogą do niego było obejście CLI
    # (stąd „osobny skrypt na OVH"). Mechanizm bez drogi do siebie jest mechanizmem, którego nie ma.
    w.add_argument("--runtime", choices=["codex", "kimi", "shell"], default=None,
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
