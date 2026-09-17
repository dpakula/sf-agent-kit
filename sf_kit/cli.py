"""`sf-kit` — jedno polecenie, kilka poleceń podrzędnych.

v0.1 (14.09.2026) - APro Agents / borys-sf

Zasada, która rządzi tym plikiem: **komunikat ma mówić, co zrobić dalej.** Nie „błąd 403",
tylko „brakuje uprawnienia X, poproś administratora". Kit uruchamia ktoś, kto nas nie zna
i nie ma kogo zapytać o drugiej w nocy.
"""
from __future__ import annotations

import argparse
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
PROFILE = ("worker", "autor", "koordynator")
PROFIL_DOMYSLNY = "worker"
from . import klucz as magazyn_klucza
from . import autor
from . import koordynator
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
    """Klient z USTALONĄ Organizacją. Nigdy „pierwsza z brzegu" — patrz `tozsamosc.wybierz`.

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
    return klient


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
    konf.organizacja = _wybierz_organizacje_w_init(konf, pytaj)

    plik = konfiguracja.zapisz(konf)
    print(f"\nUstawienia zapisane: {plik}")
    _wlacz_ochrone_repozytorium()
    # `./sf-kit`, nie `sf-kit`: dowiązania w PATH nikt jeszcze nie zakładał, więc krótsza
    # forma kończy się „command not found" w pierwszej minucie pracy z narzędziem.
    print(f"\nSprawdź, czy działa: {_jak_wolac()} whoami")
    return 0


def _wybierz_organizacje_w_init(konf: konfiguracja.Konfiguracja, pytaj) -> str:
    """Pokaż Organizacje z SF i ustal DOMYŚLNĄ. Zwraca uuid albo pusty napis.

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
        return konf.organizacja

    print(f"  konto: {toz.konto_nazwa or '(bez nazwy)'}"
          f"{' · agent' if toz.konto_kind == 'agent' else ''}")
    print(f"\nTwoje Organizacje:\n{tozsamosc.lista_do_pokazania(toz.organizacje)}\n")

    z_nadaniami = toz.z_nadaniami
    if not z_nadaniami:
        print("W żadnej nie masz jeszcze nadanych uprawnień — poproś administratora.\n"
              "Ustawienia zapiszę bez domyślnej Organizacji.")
        return ""

    if len(z_nadaniami) == 1:
        jedyna = z_nadaniami[0]
        print(f"Uprawnienia masz tylko w „{jedyna.slug}” — ustawiam ją jako domyślną.")
        return jedyna.uuid

    # Kilka do wyboru: podpowiadamy tę z pliku (migracja z 0.3), ale nie wybieramy za człowieka.
    teraz = toz.znajdz(konf.organizacja) if konf.organizacja else None
    podane = pytaj("Domyślna Organizacja (slug; Enter = brak, będę podawał --org)",
                   teraz.slug if teraz else "")
    if not podane:
        print("Dobrze — każde polecenie będzie wymagało --org <slug>.")
        return ""
    wybrana = toz.znajdz(podane)
    if wybrana is None:
        print(f"Nie znam Organizacji „{podane}” na Twojej liście — zapisuję bez domyślnej.",
              file=sys.stderr)
        return ""
    if not wybrana.ma_nadania:
        print(f"W „{wybrana.slug}” nie masz nadań — zapisuję bez domyślnej, "
              f"żeby polecenia nie kończyły się odmową w połowie.", file=sys.stderr)
        return ""
    return wybrana.uuid


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

    print(f"agent:        {konf.slug or '(nie ustawiony)'}"
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



def polecenie_heartbeat(args) -> int:
    """Czy worker tego agenta żyje. Kod wyjścia 0 = tak, 1 = nie — pod czujkę."""
    from . import usluga

    # Slug z konfiguracji: od v0.5.3 tętno jest per worker, nie per konto systemowe.
    konf = konfiguracja.wczytaj()
    zywy, co = usluga.czy_zywy(slug=konf.slug or None)
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

    # System wybieramy z `sys.platform`, nie z pytania do człowieka: plik dla obcego systemu
    # jest bezużyteczny, a wybrany ręcznie bywa wybrany źle. `--system` zostaje dla przypadku,
    # w którym ktoś generuje plik dla INNEJ maszyny niż ta, na której stoi.
    docelowy = getattr(args, "system", None) or ("macos" if sys.platform == "darwin" else "linux")
    polecenie = os.path.abspath(sys.argv[0])

    if docelowy == "macos":
        sciezka = usluga.sciezka_plist(konf.slug)
        tresc = usluga.tresc_plist(slug=konf.slug, polecenie=polecenie,
                                   katalog_domowy=str(Path.home()))
    else:
        sciezka = usluga.sciezka_unitu(konf.slug)
        tresc = usluga.tresc_unitu(
            slug=konf.slug,
            polecenie=polecenie,
            katalog_domowy=str(Path.home()),
            plik_srodowiska=str(Path.home() / ".config" / "sf-kit" / f"{konf.slug}.env"),
        )

    if args.pokaz:
        print(tresc)
        return 0

    sciezka.parent.mkdir(parents=True, exist_ok=True)
    sciezka.write_text(tresc, encoding="utf-8")

    if docelowy == "macos":
        etykieta = usluga.etykieta_launchd(konf.slug)
        (Path.home() / "Library" / "Logs" / "sf-kit").mkdir(parents=True, exist_ok=True)
        print(f"Zapisałem agenta launchd: {sciezka}\n")
        print("Włącz go (bez sudo, agent użytkownika) — JEDNO polecenie:")
        print(f"  launchctl bootstrap gui/$(id -u) {sciezka}\n")
        print("Sprawdzenie i podgląd logu:")
        print(f"  launchctl print gui/$(id -u)/{etykieta} | head -20")
        print(f"  tail -f ~/Library/Logs/sf-kit/worker-{konf.slug}.log\n")
        print("Wyłączenie:")
        print(f"  launchctl bootout gui/$(id -u)/{etykieta}\n")
        print("Jeśli `launchctl bootstrap` odpowie „Input/output error”, agent jest już "
              "wczytany — najpierw `bootout`, potem `bootstrap`.")
        return 0

    print(f"Zapisałem jednostkę: {sciezka}\n")
    print("Włącz ją (bez sudo, usługa użytkownika):")
    print("  systemctl --user daemon-reload")
    print(f"  systemctl --user enable --now {usluga.nazwa_unitu(konf.slug)}")
    print(f"  systemctl --user status {usluga.nazwa_unitu(konf.slug)}\n")
    print("Żeby worker chodził także wtedy, gdy nie jesteś zalogowany:")
    print(f"  sudo loginctl enable-linger {os.environ.get('USER', 'twoj-uzytkownik')}")
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


def polecenie_zlec(args) -> int:
    """Zadanie dla agenta — ZAWSZE na sprawie."""
    konf = konfiguracja.wczytaj()
    klient, org = _koordynator(konf, args)

    tresc = _opis_z_wejscia(args)
    try:
        agenci = koordynator.flota(klient)
        agent = koordynator.znajdz_agenta(agenci, args.agent_slug)
        sprawa = autor.znajdz_sprawe(klient, args.sprawa)
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
    print(f"  sprawa: {autor.numer_sprawy(sprawa)}")
    print(f"  {autor.adres_sprawy(str(sprawa['id']), baza=konf.adres)}")
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
    klient = _klient(konf, args)
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


def polecenie_zglos(args) -> int:
    """Nowa sprawa z gotową pracą — z załącznikami, obserwującymi i numerem na wyjściu."""
    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)

    opis = _opis_z_wejscia(args) or autor.opis_domyslny(args.tytul)
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
    if getattr(args, "szkic", False):
        # Szkic bez tego zdania wygląda jak zgłoszenie, które nie doszło: nie ma maila, nie ma
        # sprawy na liście, nie ma numeru w powiadomieniu. Mówimy wprost, co się stało i kto
        # domyka — bo tego ostatniego kroku agent NIE wykona (publikacja to akt człowieka).
        _pokaz_sprawe(konf, sprawa_id, numer,
                      co_dalej="To jest SZKIC — nie poszło żadne powiadomienie i sprawy nie ma "
                               "na listach.\nOpublikować może tylko człowiek, w SF: przycisk "
                               "„Opublikuj” na sprawie.\nDo tego czasu dopisujesz do niej "
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
    """
    konf = konfiguracja.wczytaj()
    klient = _klient(konf, args)

    if args.do and not args.sprawa:
        tresc = _opis_z_wejscia(args)
        if not tresc:
            print("Wiadomość bez treści nie niesie niczego. Podaj `--opis plik.md`.",
                  file=sys.stderr)
            return 2
        return _wyslij_wiadomosc(klient, args.do, tresc)

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

    if args.do:
        # Wpis JEST zapisany — wiadomość jest dodatkiem. Porażka wysyłki nie ma prawa
        # przedstawić zapisanego wpisu jako nieudanego.
        _wyslij_wiadomosc(klient, args.do, tresc or "(wpis z załącznikami)")

    _pokaz_sprawe(konf, sprawa_id, autor.numer_sprawy(sprawa),
                  co_dalej="Wpis dodany.")
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
    klient = _klient(konf, args)
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
        numer = autor.numer_sprawy(s) or str(s.get("id", ""))[:8]
        zmiana = autor.ostatnia_zmiana(s)
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
    pod.add_parser("heartbeat", help="czy worker tego agenta żyje").set_defaults(funkcja=polecenie_heartbeat)
    us = pod.add_parser("usluga",
                        help="[worker] usługa workera: systemd (Linux) albo launchd (macOS)")
    us.add_argument("--pokaz", action="store_true",
                    help="wypisz treść pliku zamiast go zapisywać")
    us.add_argument("--system", choices=["linux", "macos"], default=None,
                    help="dla JAKIEGO systemu generować (domyślnie: ten, na którym stoisz) "
                         "— przydatne, gdy przygotowujesz plik dla innej maszyny")
    us.set_defaults(funkcja=polecenie_usluga)

    # ── profil AUTOR ────────────────────────────────────────────────────────
    z = pod.add_parser("zglos", help="[autor] zgłoś gotową pracę jako nową sprawę")
    z.add_argument("--tytul", required=True, help="jednym zdaniem: co jest gotowe")
    z.add_argument("--opis", default=None, metavar="PLIK",
                   help="plik z opisem (albo `-` = ze standardowego wejścia)")
    z.add_argument("--tag", default=None, help="kategoria sprawy, np. makieta")
    z.add_argument("--zalacz", nargs="*", default=[], metavar="PLIK",
                   help="pliki do dołączenia (idą JEDNYM wpisem)")
    z.add_argument("--szkic", action="store_true",
                   help="wersja robocza: NIC nie wysyła, publikuje człowiek w SF (SF-4)")
    z.set_defaults(funkcja=polecenie_zglos)

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

    wp = pod.add_parser("wpis", help="[autor] dopisz postęp albo odpowiedź do sprawy")
    wp.add_argument("--do", dest="do", default=None, metavar="SLUG",
                    help="wyślij to TAKŻE jako wiadomość do sesji agenta (bez --sprawa: "
                         "samodzielna wiadomość)")
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

    # ── profil KOORDYNATOR ────────────────────────────────────────────────────
    pod.add_parser("flota", help="[koordynator] agenci tej Organizacji"
                   ).set_defaults(funkcja=polecenie_flota)

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
