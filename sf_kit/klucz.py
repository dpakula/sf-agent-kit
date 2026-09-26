"""Przechowywanie klucza API — jedyne miejsce, które go dotyka.

v0.1 (14.09.2026) - APro Agents / borys-sf

TRZY MIEJSCA, W KTÓRYCH KLUCZ WYCIEKA, I CO Z NIMI ROBIMY
═════════════════════════════════════════════════════════
1. **Argument procesu.** `ps aux` widzi każdy użytkownik maszyny, a historia powłoki zapisuje
   polecenie na dysk. Dlatego `init` PYTA o klucz (bez echa) i nie przyjmuje go parametrem.
   Nie ma flagi `--key`; brak takiej flagi jest funkcją, nie brakiem.
2. **Log.** Klucz nigdy nie trafia do `print`, do wyjątku ani do komunikatu błędu. Gdy trzeba
   powiedzieć, którego klucza użyto, mówimy `sk_live_…1a2b` (pierwsze 8 i ostatnie 4 znaki).
3. **Prompt modelu.** Model nie dostaje klucza — z SF rozmawia worker. To jest granica, przez
   którą nic nie przechodzi, i dlatego ten moduł nie ma żadnej funkcji „podaj klucz jako tekst
   do wstawienia gdziekolwiek".

macOS → pęk kluczy (`security`). Linux → plik `600`. Różnica jest w tym, co system oferuje,
nie w tym, jak bardzo się staramy: pęk kluczy jest szyfrowany i pyta o zgodę, plik `600` broni
tylko przed innym użytkownikiem tej maszyny — i tak jest napisane w README.
"""
from __future__ import annotations

import getpass
import os
import sys
import platform
import subprocess
from pathlib import Path

#: Nazwa usługi w pęku kluczy macOS. Stała, bo `security` szuka dokładnie po niej.
USLUGA = "sf-agent-kit"

#: Konto w pęku kluczy i nazwa pliku konfiguracji SPRZED podziału na agentów (v0.2 i starsze).
#: Zostaje na zawsze jako ścieżka odczytu: ludzie, którzy już mają Kit skonfigurowany, nie mają
#: obowiązku niczego przenosić, żeby aktualizacja nie zepsuła im pracy.
KONTO_JEDNEGO_AGENTA = "api-key"

#: Zmienna wskazująca katalog konfiguracji WPROST. Dla tych, którzy trzymają agentów poza
#: katalogiem domowym (kontener, wspólna maszyna) — i dla testów.
ZMIENNA_DOMU = "SF_KIT_HOME"

#: Prefiks kluczy SalesForge. Po nim rozpoznajemy pomyłkę („wkleiłeś nie to") i po nim
#: szuka hak gita.
PREFIKS_KLUCZA = "sk_live_"

#: Agent wybrany na czas tego uruchomienia (flagą `--agent`). Ustawia go CLI, zanim cokolwiek
#: sięgnie po konfigurację.
_wybrany: str | None = None

#: Ostrzeżenie „stary układ + nowy agent" raz na uruchomienie, nie przy każdym odczycie ścieżki.
_ostrzezono_o_starym = False


class WieluAgentow(RuntimeError):
    """Na tej maszynie jest kilku agentów i nie wiadomo, o którego chodzi."""


def ustaw_agenta(slug: str | None) -> None:
    """Wskaż agenta na czas tego uruchomienia. `None` = wróć do wykrywania."""
    global _wybrany
    _wybrany = (slug or "").strip() or None


def wybrany_agent() -> str | None:
    return _wybrany


def katalog_bazowy() -> Path:
    """Korzeń konfiguracji Kitu — nad katalogami poszczególnych agentów."""
    baza = os.environ.get("XDG_CONFIG_HOME")
    return Path(baza) / "sf-kit" if baza else Path.home() / ".config" / "sf-kit"


def agenci() -> list[str]:
    """Slugi agentów skonfigurowanych na tej maszynie, alfabetycznie.

    Agent = podkatalog z plikiem `config.json`. Katalog bez konfiguracji nie jest agentem,
    tylko śmieciem po nieudanym `init` — i nie ma prawa uczestniczyć w wyborze.
    """
    korzen = katalog_bazowy()
    if not korzen.is_dir():
        return []
    return sorted(k.name for k in korzen.iterdir()
                  if k.is_dir() and (k / "config.json").is_file())


def czy_uklad_jednego_agenta() -> bool:
    """Czy na tej maszynie leży konfiguracja sprzed podziału na agentów (v0.2)."""
    return (katalog_bazowy() / "config.json").is_file()


def sciezka_konfiguracji() -> Path:
    """Katalog konfiguracji TEGO agenta.

    KOLEJNOŚĆ ROZSTRZYGANIA — od najbardziej jawnego do najbardziej domyślnego:
      1. `SF_KIT_HOME` — powiedziane wprost, więc nie zgadujemy niczego dalej;
      2. `--agent <slug>` — wybór na to uruchomienie;
      3. układ sprzed podziału (`~/.config/sf-kit/config.json`) — czyli ktoś, kto skonfigurował
         Kit przed podziałem i nie ma powodu niczego przenosić; ma PIERWSZEŃSTWO przed jedynym
         nowym agentem (ADVERTPR-936), a obok niego ostrzeżenie, jak wskazać nowego;
      4. dokładnie JEDEN skonfigurowany agent (bez starego układu) — bierzemy jego, bez flagi;
      5. brak czegokolwiek — katalog bazowy, żeby `init` miał gdzie zacząć.

    Punkt 3 jest tu po to, żeby **nie karać pojedynczego użytkownika za to, że ktoś inny ma
    kilku agentów**: dopóki agent jest jeden, wszystko działa bez ani jednej flagi. Dopiero
    drugi agent każe powiedzieć, o którego chodzi — i wtedy mówimy to głośno (`WieluAgentow`),
    zamiast wybierać pierwszego z brzegu. Wybranie „któregoś" znaczyłoby pisanie do cudzej
    Organizacji cudzym kluczem, a to jest błąd, którego nie widać ani w wyniku, ani w logu.
    """
    wprost = os.environ.get(ZMIENNA_DOMU)
    if wprost:
        return Path(wprost).expanduser()

    korzen = katalog_bazowy()
    if _wybrany:
        return korzen / _wybrany

    znalezieni = agenci()
    if len(znalezieni) == 1:
        if czy_uklad_jednego_agenta():
            # ADVERTPR-936 (26.09): stary układ + JEDEN nowy agent. Bez flagi wygrywa STARY —
            # inaczej dodanie pierwszego agenta w podkatalogu przejmowało wszystko, co chodzi
            # bez `--agent` (np. ręcznie uruchomiony worker), razem z cudzym kluczem
            # i Organizacją. Odmowa zatrzymałaby starego agenta bez sposobu wskazania go flagą,
            # więc: stary działa dalej, nowy wymaga `--agent`, a my mówimy to głośno.
            global _ostrzezono_o_starym
            if not _ostrzezono_o_starym:
                _ostrzezono_o_starym = True
                print(f"Używam konfiguracji sprzed podziału ({korzen / 'config.json'}). Na tej "
                      f"maszynie jest też agent „{znalezieni[0]}” — do niego: "
                      f"`--agent {znalezieni[0]}`. Przeniesienie starej konfiguracji: `sf-kit init`.",
                      file=sys.stderr)
            return korzen
        return korzen / znalezieni[0]
    if len(znalezieni) > 1:
        if czy_uklad_jednego_agenta():
            # Stara konfiguracja obok nowych: ktoś jest w połowie przenosin. Nie zgadujemy.
            raise WieluAgentow(
                "Na tej maszynie jest kilku agentów ORAZ konfiguracja sprzed podziału.\n"
                f"Agenci: {', '.join(znalezieni)}\n"
                "Powiedz, o którego chodzi: `--agent <slug>`.")
        raise WieluAgentow(
            "Na tej maszynie jest kilku agentów — powiedz, o którego chodzi:\n"
            + "\n".join(f"  --agent {s}" for s in znalezieni))

    return korzen


def nazwa_lokalna(zapasowa: str) -> str:
    """Nazwa agenta NA TEJ MASZYNIE: katalog ustawień, konto w pęku, usługa, plik tętna.

    To NIE jest slug w SF (SF-32). Do 0.8.0 oba siedziały w jednym polu `slug` i `init` na
    macu zapisał nazwę z konwencji VPS (`kimi-mac-dpakula`) tam, gdzie worker odsiewa zadania
    po slugu z SF (`kimi-mac`) — „0 zadań" przy działającym koncie. Od 0.9.0 pole `slug` to
    slug z SF, a nazwa lokalna wynika z katalogu. Rozdzielenie chroni też ręczną poprawkę:
    `slug: kimi-mac` w katalogu `kimi-mac-dpakula` nie przestawia usługi launchd na agenta,
    którego katalogu nie ma.

    `zapasowa` — gdy katalog nie jest katalogiem agenta (`SF_KIT_HOME`, układ sprzed podziału).
    """
    korzen = katalog_bazowy()
    katalog = sciezka_konfiguracji()
    if katalog != korzen and katalog.parent == korzen:
        return katalog.name
    return zapasowa


def konto_w_peku() -> str:
    """Konto w pęku kluczy macOS: slug agenta albo konto sprzed podziału.

    Jeden wpis „api-key" na maszynę znaczył JEDEN agent na maszynę — a Damian planuje kilku
    w jednym Codeksie. Konto per slug rozdziela klucze tak, jak katalogi rozdzielają resztę.
    """
    return nazwa_lokalna(KONTO_JEDNEGO_AGENTA)


def _plik_klucza() -> Path:
    return sciezka_konfiguracji() / "credentials"


def czy_macos() -> bool:
    return platform.system() == "Darwin"


def skrot(klucz: str) -> str:
    """Klucz w postaci nadającej się do pokazania człowiekowi. NIGDY całość.

    Osiem znaków z przodu (czyli `sk_live_` plus nic) i cztery z tyłu wystarczą, żeby odróżnić
    dwa klucze od siebie, a nie wystarczą, żeby któregokolwiek użyć.
    """
    if not klucz:
        return "(brak)"
    if len(klucz) <= 14:
        return klucz[:4] + "…"
    return f"{klucz[:8]}…{klucz[-4:]}"


# ── zapis ────────────────────────────────────────────────────────────────────

def zapisz(klucz: str) -> str:
    """Zapisz klucz. Zwraca opis miejsca zapisu (do pokazania człowiekowi)."""
    if czy_macos():
        return _zapisz_keychain(klucz)
    return _zapisz_plik(klucz)


def _zapisz_keychain(klucz: str) -> str:
    """Pęk kluczy macOS. Klucz idzie przez STDIN narzędzia `security`, nie przez argument.

    `security add-generic-password -w <klucz>` byłoby dokładnie tym błędem, przed którym broni
    cały ten moduł — wartość wylądowałaby w `ps`. Wariant `-w` bez wartości każe narzędziu
    zapytać, a my odpowiadamy na jego stdin.
    """
    # `security` przy `-w` bez wartości pyta o hasło DWA razy („password data for new item"
    # i „retype password"). Podajemy je dwa razy na wejściu, żeby oba pytania dostały odpowiedź
    # i nie zostały na ekranie jako monity, których człowiek nie rozumie (Damian zobaczył je
    # przy pierwszym uruchomieniu i nie wiedział, czy ma coś wpisać).
    #
    # Ostrzeżenie uczciwe: sprawdzone jest to, że dodatkowa linia niczego nie psuje. NIE jest
    # sprawdzone na macOS, czy `security` czyta te pytania ze standardowego wejścia, czy prosto
    # z terminala — w tym drugim przypadku monity zostaną mimo wszystko i dlatego `init`
    # uprzedza o nich jednym zdaniem PRZED wywołaniem.
    wynik = subprocess.run(
        ["security", "add-generic-password", "-U", "-a", konto_w_peku(), "-s", USLUGA, "-w"],
        input=f"{klucz}\n{klucz}\n", text=True, capture_output=True,
    )
    if wynik.returncode != 0:
        # Komunikat `security` nie zawiera klucza — możemy go pokazać w całości.
        raise RuntimeError(f"nie udało się zapisać w pęku kluczy: {wynik.stderr.strip()}")
    return f'pęk kluczy macOS (usługa „{USLUGA}”, konto „{konto_w_peku()}”)'


def _zapisz_plik(klucz: str) -> str:
    """Plik `600` w katalogu `700`.

    Prawa nadajemy PRZED zapisem treści (`os.open` z `mode`), a nie po. Zapis jawnym plikiem
    i poprawienie praw w drugim kroku zostawia okno, w którym klucz leży z prawami domyślnymi
    — krótkie, ale wystarczające dla procesu, który akurat czyta katalog.
    """
    katalog = sciezka_konfiguracji()
    katalog.mkdir(parents=True, exist_ok=True)
    os.chmod(katalog, 0o700)

    plik = _plik_klucza()
    deskryptor = os.open(plik, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(deskryptor, "w") as f:
        f.write(klucz + "\n")
    os.chmod(plik, 0o600)

    if not czy_prawa_chronia():
        # Na Windows `chmod` jest niemal pustym gestem: ustawia tylko atrybut „tylko do
        # odczytu", a nie to, kto plik przeczyta. Zdanie „prawa 600" byłoby tam nieprawdą
        # o zabezpieczeniu — a nieprawda o zabezpieczeniu zdejmuje czujność skuteczniej,
        # niż brak zabezpieczenia ją podnosi.
        return (f"{plik} — UWAGA: na tym systemie prawa pliku NIE ograniczają dostępu. "
                f"Klucz leży w pliku czytelnym dla innych programów tego konta. "
                f"Zalecany WSL albo macOS/Linux — patrz README, sekcja o systemie.")
    return f"{plik} (prawa 600)"


def czy_prawa_chronia() -> bool:
    """Czy prawa pliku na tym systemie naprawdę ograniczają dostęp.

    Rozdzielone od `czy_macos`, bo to inne pytanie: macOS ma pęk kluczy, Linux ma działające
    prawa, a Windows nie ma ani jednego, ani drugiego — i to trzecie trzeba powiedzieć wprost
    zamiast obiecywać „prawa 600".
    """
    return os.name == "posix"


# ── odczyt ───────────────────────────────────────────────────────────────────

def wczytaj() -> str | None:
    """Klucz albo `None`. Kolejność: zmienna środowiskowa → pęk kluczy → plik.

    `SF_KIT_KEY` jest pierwsza, bo tak uruchamia się to w CI i w kontenerze, gdzie nie ma ani
    pęku kluczy, ani katalogu domowego wartego zapisu. Uwaga dla wołającego: zmienna
    środowiskowa jest widoczna w `/proc/<pid>/environ` dla właściciela procesu — to wygoda
    z ceną, nie zalecany domyślny sposób.
    """
    ze_srodowiska = os.environ.get("SF_KIT_KEY")
    if ze_srodowiska:
        return ze_srodowiska.strip()

    if czy_macos():
        z_keychain, _ = _wczytaj_keychain()
        if z_keychain:
            return z_keychain

    plik = _plik_klucza()
    if plik.exists():
        tresc = plik.read_text(encoding="utf-8").strip()
        if tresc:
            return tresc
    return None


#: Kod, którym `security` mówi „nie ma takiego wpisu". Każdy inny niezerowy znaczy coś
#: innego — najczęściej „jest, ale nie mogę go otworzyć" (proces bez dostępu do pęku).
KOD_BRAK_WPISU = 44

#: Trzy odpowiedzi na pytanie „dlaczego nie mam klucza". Rozróżnienie NIE jest kosmetyczne:
#: „nie zapisałeś klucza" każe człowiekowi uruchomić `init`, a „nie mam dostępu do pęku"
#: znaczy, że klucz JEST i wszystko działa poprawnie — tylko pyta o niego proces, który
#: z założenia nie ma go dostać (model w piaskownicy).
BRAK_WPISU = "brak_wpisu"
BRAK_DOSTEPU = "brak_dostepu"
ZNALEZIONY = "znaleziony"


def _wczytaj_keychain() -> tuple[str | None, str]:
    """`(klucz, powód)`. Powód mówi, CZEGO zabrakło — patrz stałe wyżej."""
    wynik = subprocess.run(
        ["security", "find-generic-password", "-a", konto_w_peku(), "-s", USLUGA, "-w"],
        text=True, capture_output=True,
    )
    if wynik.returncode == 0:
        klucz = wynik.stdout.strip()
        return (klucz or None), (ZNALEZIONY if klucz else BRAK_WPISU)
    if wynik.returncode == KOD_BRAK_WPISU:
        return None, BRAK_WPISU
    return None, BRAK_DOSTEPU


def powod_braku_klucza() -> str:
    """Zdanie tłumaczące, dlaczego `wczytaj()` nic nie oddało. Do pokazania człowiekowi.

    Wołane WYŁĄCZNIE wtedy, gdy klucza nie ma — sprawdza pęk drugi raz, ale tylko na ścieżce
    błędu, gdzie jedno dodatkowe wywołanie nic nie kosztuje, a zła diagnoza kosztuje wieczór.

    Przypadek, dla którego to powstało: `sf-kit` uruchomiony PRZEZ MODEL w piaskownicy nie ma
    dostępu do pęku kluczy i dostawał komunikat „Nie mam klucza. Uruchom `sf-kit init`" —
    czyli instrukcję naprawy czegoś, co nie jest zepsute. Klucz jest zapisany, a brak dostępu
    to zamierzone zachowanie: klucz należy do workera i do człowieka przy terminalu, nie do
    modelu (README, sekcja o kluczu).
    """
    if czy_macos():
        _, powod = _wczytaj_keychain()
        if powod == BRAK_DOSTEPU:
            return (
                "Klucz JEST zapisany, ale ten proces nie ma dostępu do pęku kluczy.\n"
                "Jeśli uruchamiasz `sf-kit` z wnętrza modelu (piaskownica Codexa), to jest\n"
                "zachowanie zamierzone — klucz należy do człowieka przy terminalu i do workera,\n"
                "nie do modelu. Uruchom to polecenie sam, w zwykłym terminalu.\n"
                "Jeśli jesteś przy terminalu i mimo to widzisz ten komunikat, odblokuj pęk\n"
                "kluczy (`security unlock-keychain`) albo zezwól narzędziu `security` na dostęp."
            )
    return "Nie mam klucza. Uruchom `./sf-kit init` — zapyta o niego i zapisze bezpiecznie."


def zapytaj(czy_pusty_ok: bool = False) -> str:
    """Zapytaj człowieka o klucz (bez echa) i oddaj wartość — ZAPIS robi wołający.

    Dlaczego osobno od zapisu: `init` w trybie DODAWANIA pyta o klucz, zanim wie, do
    którego podkatalogu zapisać (nazwę ustala dopiero `GET /me`). Wołający w trybie
    EDYCJI przekazuje `czy_pusty_ok=True` — wtedy pusty Enter znaczy „zostaw obecny".

    Walidujemy WYŁĄCZNIE prefiks i to, czy cokolwiek podano. Sprawdzanie długości albo
    znaków byłoby zgadywaniem cudzego formatu — a klucz, którego nie rozpoznajemy, i tak
    odrzuci serwer, i zrobi to wiarygodniej niż my.
    """
    if czy_macos():
        print("Klucz trafi do pęku kluczy macOS. System może przy tym wyświetlić własne\n"
              "pytania o hasło — nic nie wpisuj, one dotyczą tego samego klucza.")
    klucz = getpass.getpass("Klucz API SalesForge (nie będzie widoczny): ").strip()
    if not klucz:
        if czy_pusty_ok:
            return ""
        raise ValueError("nie podałeś klucza")
    if not klucz.startswith(PREFIKS_KLUCZA):
        raise ValueError(
            f'to nie wygląda na klucz SalesForge — powinien zaczynać się od „{PREFIKS_KLUCZA}”. '
            f"Jeśli wkleiłeś coś innego (np. token GitHuba), zacznij od nowa.")
    return klucz


def zapytaj_i_zapisz() -> tuple[str, str]:
    """Zapytaj o klucz (bez echa) i od razu zapisz. Zwraca `(skrót, gdzie zapisano)`.

    Zostało dla zgodności ze starszymi wywołaniami — logika pytania mieszka w `zapytaj`,
    zapis w `zapisz`.
    """
    klucz = zapytaj()
    gdzie = zapisz(klucz)
    return skrot(klucz), gdzie


def usun_z_peku(konto: str) -> bool:
    """Skasuj wpis z pęku kluczy macOS (używane przy przenosinach agentów).

    `False` = nie ma czego kasować albo `security` odmówił — obie sytuacje są do
    przyjęcia przy sprzątaniu po migracji, więc nie wywracamy się przez nie.
    """
    if not czy_macos():
        return False
    wynik = subprocess.run(
        ["security", "delete-generic-password", "-a", konto, "-s", USLUGA],
        capture_output=True, text=True)
    return wynik.returncode == 0
