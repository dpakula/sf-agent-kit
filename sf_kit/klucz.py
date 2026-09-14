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
import platform
import subprocess
from pathlib import Path

#: Nazwa usługi w pęku kluczy macOS. Stała, bo `security` szuka dokładnie po niej.
USLUGA = "sf-agent-kit"
KONTO = "api-key"

#: Prefiks kluczy SalesForge. Po nim rozpoznajemy pomyłkę („wkleiłeś nie to") i po nim
#: szuka hak gita.
PREFIKS_KLUCZA = "sk_live_"


def sciezka_konfiguracji() -> Path:
    """Katalog konfiguracji. `XDG_CONFIG_HOME` uszanowany, bo tak działa reszta narzędzi."""
    baza = os.environ.get("XDG_CONFIG_HOME")
    return Path(baza) / "sf-kit" if baza else Path.home() / ".config" / "sf-kit"


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
        ["security", "add-generic-password", "-U", "-a", KONTO, "-s", USLUGA, "-w"],
        input=f"{klucz}\n{klucz}\n", text=True, capture_output=True,
    )
    if wynik.returncode != 0:
        # Komunikat `security` nie zawiera klucza — możemy go pokazać w całości.
        raise RuntimeError(f"nie udało się zapisać w pęku kluczy: {wynik.stderr.strip()}")
    return f'pęk kluczy macOS (usługa „{USLUGA}”, konto „{KONTO}”)'


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
        ["security", "find-generic-password", "-a", KONTO, "-s", USLUGA, "-w"],
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


def zapytaj_i_zapisz() -> tuple[str, str]:
    """Zapytaj człowieka o klucz (bez echa) i zapisz. Zwraca `(skrót, gdzie zapisano)`.

    Walidujemy WYŁĄCZNIE prefiks i to, czy cokolwiek podano. Sprawdzanie długości albo
    znaków byłoby zgadywaniem cudzego formatu — a klucz, którego nie rozpoznajemy, i tak
    odrzuci serwer, i zrobi to wiarygodniej niż my.
    """
    if czy_macos():
        print("Klucz trafi do pęku kluczy macOS. System może przy tym wyświetlić własne\n"
              "pytania o hasło — nic nie wpisuj, one dotyczą tego samego klucza.")
    klucz = getpass.getpass("Klucz API SalesForge (nie będzie widoczny): ").strip()
    if not klucz:
        raise ValueError("nie podałeś klucza")
    if not klucz.startswith(PREFIKS_KLUCZA):
        raise ValueError(
            f'to nie wygląda na klucz SalesForge — powinien zaczynać się od „{PREFIKS_KLUCZA}”. '
            f"Jeśli wkleiłeś coś innego (np. token GitHuba), zacznij od nowa.")
    gdzie = zapisz(klucz)
    return skrot(klucz), gdzie
