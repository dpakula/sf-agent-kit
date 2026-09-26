"""`sf-kit init` — lista agentów, tryb dodawania (klucz → `GET /me`) i tryb edycji.

v0.1 (26.09.2026) - APro Agents / kimi-autor · decyzje Damiana 26.09 (ADVERTPR-960, runda 2)

CO SIĘ ZMIENIŁO WOBEC STAREGO `init`
═════════════════════════════════════
Stary `init` pytał o nazwę agenta, a potem o resztę — człowiek przepisywał z pamięci
rzeczy, które SF zna lepiej. Nowy układ (decyzje Damiana 26.09):

1. **Ekran startowy to LISTA agentów** tej maszyny (nazwa, Organizacja, profil, czy żyje
   worker, gdzie leżą ustawienia) i pytanie `[numer] edytuj agenta · [n] dodaj nowego ·
   [q] wyjdź`. Pusta maszyna od razu wchodzi w tryb dodawania.
2. **Tryb dodawania zaczyna od KLUCZA**: `GET /me` mówi Kitowi, kto nim jest — nazwę
   (slug; klucz osobisty bez sluga → część adresu przed `@`), domyślną Organizację
   (jedyna z nadaniami wygrywa, przy kilku pytamy) i profil Z UPRAWNIEŃ
   (`plans:write` → koordynator, `tickets:write` → asystent, inaczej worker). Kit pokazuje
   to zwykłym językiem, pyta o potwierdzenie i dopiero wtedy zapisuje w nowym podkatalogu.
   O nazwę NIE PYTA. Klucz agenta, który już jest na liście, prowadzi do edycji.
3. **Tryb edycji** pokazuje pola z obecnymi wartościami (Enter zostawia): klucz
   (np. po rotacji — NOWY klucz musi należeć do TEGO SAMEGO agenta, `/me` zwraca ten sam
   slug, inaczej odmowa: „dodaj go jako nowego”), Organizacja domyślna, profil, adres SF.
4. **Stary układ** (jeden `config.json` bez podkatalogu, sprzed v0.3) widnieje na liście
   z adnotacją i — na życzenie — przenosi się do podkatalogu: config + klucz (plik albo
   konto w pęku). Jednostkę usługi trzeba potem przegenerować przez `sf-kit usluga`.

Logiki `klucz.sciezka_konfiguracji()` TEN MODUŁ NIE RUSZA — rozstrzyganie „który agent"
bez flagi zostaje tam, gdzie było poprawione w 0.13.4 (ADVERTPR-936, wariant B).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from . import config as konfiguracja
from . import klucz as magazyn_klucza
from . import tozsamosc
from . import usluga
from .api import BladAPI, Klient

#: Trzy profile w JEDNYM narzędziu (decyzja Damiana 15.09). Profil nie ogranicza uprawnień —
#: te są po stronie SalesForge — tylko POKAZUJE to, co do danej roli należy.
PROFILE = ("worker", "asystent", "koordynator")
PROFIL_DOMYSLNY = "worker"


class _KoniecWejscia(Exception):
    """stdin się skończył (init wywołany z potoku) — kończymy bez tracebacka."""


# ── małe pytania ──────────────────────────────────────────────────────────────


def _pytaj(etykieta: str, teraz: str) -> str:
    try:
        podane = input(f"{etykieta} [{teraz or 'brak'}]: ").strip()
    except EOFError as brak:
        raise _KoniecWejscia from brak
    return podane or teraz


def _potwierdz(etykieta: str) -> bool:
    try:
        return input(f"{etykieta}: ").strip().lower() in ("t", "tak", "y", "yes")
    except EOFError:
        return False


# ── lista agentów ─────────────────────────────────────────────────────────────


@dataclass
class WierszAgenta:
    """Jeden wiersz ekranu startowego — agent w podkatalogu albo stary układ."""

    nazwa: str                                  # nazwa lokalna: katalog (stary: slug z ustawień)
    katalog: Path                               # gdzie leży config.json
    konf: "konfiguracja.Konfiguracja | None"    # None = config nieczytelny
    stary_uklad: bool


def _czytaj_konfig(plik: Path) -> "konfiguracja.Konfiguracja | None":
    """Konfiguracja z konkretnego pliku — bez globalnego rozstrzygania agenta.

    Lista pokazuje KAŻDEGO agenta naraz, więc `konfiguracja.wczytaj()` (jeden agent
    na raz) nie nadaje się do czytania wierszy. Zepsuty plik nie wywraca listy:
    wiersz pokaże adnotację, nie tracebacka.
    """
    try:
        dane = json.loads(plik.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(dane, dict):
        return None
    znane = {p for p in konfiguracja.Konfiguracja.__dataclass_fields__}
    konf = konfiguracja.Konfiguracja(**{k: v for k, v in dane.items() if k in znane})
    konf.profil = konfiguracja.PROFIL_ALIASY.get(konf.profil, konf.profil)
    return konf


def _wiersze_agentow() -> list[WierszAgenta]:
    korzen = magazyn_klucza.katalog_bazowy()
    wiersze = [
        WierszAgenta(nazwa=nazwa, katalog=korzen / nazwa,
                     konf=_czytaj_konfig(korzen / nazwa / konfiguracja.PLIK),
                     stary_uklad=False)
        for nazwa in magazyn_klucza.agenci()
    ]
    if magazyn_klucza.czy_uklad_jednego_agenta():
        konf = _czytaj_konfig(korzen / konfiguracja.PLIK)
        wiersze.append(WierszAgenta(
            nazwa=(konf.slug if konf and konf.slug else "stary-uklad"),
            katalog=korzen, konf=konf, stary_uklad=True))
    return wiersze


def _status_workera(wiersz: WierszAgenta) -> str:
    """Czy worker tego wiersza żyje — z tętna (`usluga.czy_zywy`)."""
    konf = wiersz.konf
    if konf is None:
        return "nie wiem (config nieczytelny)"
    if konf.profil != "worker":
        return f"nie dotyczy (profil: {konf.profil})"
    # Tętno worker zapisuje pod nazwą lokalną — dla wiersza z podkatalogu to nazwa
    # katalogu, dla starego układu slug z ustawień (tam `nazwa_lokalna` oddaje zapasową).
    zyje, _ = usluga.czy_zywy(slug=wiersz.nazwa)
    return "działa" if zyje else "nie odpowiada"


def _pokaz_liste(wiersze: list[WierszAgenta]) -> None:
    print("Agenci na tej maszynie:\n")
    for numer, wiersz in enumerate(wiersze, start=1):
        if wiersz.stary_uklad:
            print(f"  [{numer}] {wiersz.nazwa}  ← STARY UKŁAD")
        else:
            print(f"  [{numer}] {wiersz.nazwa}")
        if wiersz.konf is None:
            print(f"      UWAGA: {wiersz.katalog / konfiguracja.PLIK} jest nieczytelny — "
                  f"popraw go ręcznie.\n")
            continue
        konf = wiersz.konf
        print(f"      Organizacja: {konf.organizacja or '(brak domyślnej)'} · "
              f"profil: {konf.profil}")
        print(f"      worker: {_status_workera(wiersz)}")
        gdzie = str(wiersz.katalog / konfiguracja.PLIK)
        if wiersz.stary_uklad:
            gdzie += " (stary układ — przenieść do podkatalogu?)"
        print(f"      ustawienia: {gdzie}\n")


# ── rozmowy z SF ──────────────────────────────────────────────────────────────


def _me_dla(adres: str, klucz_wartosc: str) -> tozsamosc.Tozsamosc:
    """`GET /me` dla KLUCZA, zanim istnieje dla niego konfiguracja."""
    return tozsamosc.z_odpowiedzi(Klient(baza=adres, klucz=klucz_wartosc).kim_jestem())


def _nazwa_z_me(toz: tozsamosc.Tozsamosc) -> str | None:
    """Nazwa agenta na tej maszynie, WEDŁUG SF — nie pytamy człowieka.

    Slug bierzemy z członkostw (wspólny dla wszystkich Organizacji; przy dwóch
    różnych nie zgadujemy). Klucz osobisty bez `agent_slug` → część adresu przed `@`.
    """
    slugi = {o.agent_slug for o in toz.organizacje if o.agent_slug}
    if len(slugi) == 1:
        return slugi.pop()
    if len(slugi) > 1:
        return None
    email = (toz.konto_email or "")
    if "@" in email:
        return email.split("@", 1)[0]
    return None


def _suma_uprawnien(organizacje: list[tozsamosc.Organizacja]) -> list[str]:
    prawa: set[str] = set()
    for org in organizacje:
        prawa.update(org.uprawnienia)
    return sorted(prawa)


def _profil_z_uprawnien(uprawnienia: list[str]) -> str:
    """Profil z nadanych uprawnień (decyzja Damiana 26.09). `plans:write` sprawdzamy
    pierwsze — koordynator bywa też uprawniony do zapisu spraw, a rola szersza wygrywa."""
    prawa = set(uprawnienia or [])
    if "plans:write" in prawa:
        return "koordynator"
    if "tickets:write" in prawa:
        return "asystent"
    return PROFIL_DOMYSLNY


def _uzasadnienie_profilu(profil: str, uprawnienia: list[str]) -> str:
    if profil == "koordynator":
        return "masz plans:write"
    if profil == "asystent":
        return "masz tickets:write"
    return "bez tickets:write i plans:write"


def _wybierz_organizacje(toz: tozsamosc.Tozsamosc) -> tuple[str, str, list[str]]:
    """Domyślna Organizacja dla NOWEGO agenta. Zwraca `(uuid, slug, uprawnienia)` —
    uprawnienia służą do ustalenia profilu.

    Jedyna z nadanymi → ona (mówimy wprost). Kilka → pytamy. Zero → zapis bez domyślnej.
    """
    z_nadaniami = toz.z_nadaniami
    if not z_nadaniami:
        print("W żadnej Organizacji nie masz jeszcze nadanych uprawnień — poproś "
              "administratora. Zapiszę ustawienia bez domyślnej Organizacji "
              "(przy zapisach podawaj --org).")
        return "", "", []
    if len(z_nadaniami) == 1:
        jedyna = z_nadaniami[0]
        print(f"Uprawnienia masz tylko w „{jedyna.slug}” — ustawiam ją jako domyślną.")
        return jedyna.uuid, jedyna.slug, list(jedyna.uprawnienia)
    print(f"\nMasz nadania w kilku Organizacjach:\n"
          f"{tozsamosc.lista_do_pokazania(z_nadaniami)}\n")
    podane = _pytaj("Domyślna Organizacja (slug; Enter = brak, będę podawał --org)", "")
    if not podane:
        return "", "", _suma_uprawnien(z_nadaniami)
    wybrana = toz.znajdz(podane)
    if wybrana is None:
        print(f"Nie znam Organizacji „{podane}” na Twojej liście — zapisuję bez domyślnej.",
              file=sys.stderr)
        return "", "", _suma_uprawnien(z_nadaniami)
    if not wybrana.ma_nadania:
        print(f"W „{wybrana.slug}” nie masz nadań — zapisuję bez domyślnej, żeby zapis "
              f"nie kończył się odmową w połowie.", file=sys.stderr)
        return "", "", _suma_uprawnien(z_nadaniami)
    return wybrana.uuid, wybrana.slug, list(wybrana.uprawnienia)


# ── tryb dodawania ────────────────────────────────────────────────────────────


def _tryb_dodawania(*, ochrona, jak_wolac) -> int:
    print("Dodawanie agenta. Klucz wystawia administrator SalesForge i przekazuje go "
          "menedżerem haseł — wpisz go tutaj, nigdy w rozmowie z agentem.\n")
    adres = _pytaj("Adres SalesForge", konfiguracja.Konfiguracja().adres)
    try:
        wartosc = magazyn_klucza.zapytaj()
    except ValueError as blad:
        print(f"Klucz NIE został zapisany: {blad}", file=sys.stderr)
        return 1
    except EOFError as brak:
        raise _KoniecWejscia from brak
    try:
        toz = _me_dla(adres, wartosc)
    except BladAPI as blad:
        print(f"Nie udało się odczytać konta tego klucza ({blad}).\n"
              f"Klucz NIE został zapisany — sprawdź klucz i adres.", file=sys.stderr)
        return 1

    nazwa = _nazwa_z_me(toz)
    if nazwa is None:
        rozne = {o.agent_slug for o in toz.organizacje if o.agent_slug}
        if len(rozne) > 1:
            print("SF podaje DWIE różne nazwy tego agenta ("
                  + ", ".join(sorted(rozne))
                  + ") — nie zgaduję, która jest właściwa. Uporządkuj slugi w panelu "
                    "SalesForge i spróbuj ponownie.", file=sys.stderr)
        else:
            print("SF nie podaje nazwy tego konta (brak sluga agenta i adresu e-mail) — "
                  "nadaj agentowi slug w panelu SalesForge i spróbuj ponownie.",
                  file=sys.stderr)
        return 2

    if nazwa in magazyn_klucza.agenci():
        print(f"Ten agent już jest na tej maszynie — przejść do edycji?")
        if _potwierdz("[t/N]"):
            return _tryb_edycji(nazwa, ochrona=ochrona, jak_wolac=jak_wolac)
        return 0
    cel = magazyn_klucza.katalog_bazowy() / nazwa
    if cel.exists():
        print(f"Katalog {cel} już istnieje, a nie jest agentem (brak w nim config.json). "
              f"Zajrzyj do niego ręcznie.", file=sys.stderr)
        return 2

    org_uuid, org_slug, org_prawa = _wybierz_organizacje(toz)
    profil = _profil_z_uprawnien(org_prawa)

    print("\nKit rozpoznał klucz:")
    print(f"  agent:    {nazwa}")
    if toz.konto_nazwa and toz.konto_nazwa != nazwa:
        print(f"  konto:    {toz.konto_nazwa}"
              f"{' (agent)' if toz.konto_kind == 'agent' else ''}")
    print(f"  domyślna Organizacja: {org_slug or '(brak — przy zapisach podawaj --org)'}")
    print(f"  profil:   {profil} ({_uzasadnienie_profilu(profil, org_prawa)})")
    print(f"  adres:    {adres}")
    print(f"\nZapiszę w nowym podkatalogu: {cel}")
    if not _potwierdz("\nZapisać? [t/N]"):
        print("Nic nie zapisałem.")
        return 0

    magazyn_klucza.ustaw_agenta(nazwa)
    gdzie = magazyn_klucza.zapisz(wartosc)
    konf = konfiguracja.Konfiguracja(adres=adres, organizacja=org_uuid,
                                     slug=nazwa, profil=profil)
    plik = konfiguracja.zapisz(konf)
    print(f"\nKlucz {magazyn_klucza.skrot(wartosc)} zapisany: {gdzie}")
    print(f"Ustawienia zapisane: {plik}")
    ochrona()
    print(f"\nSprawdź, czy działa: {jak_wolac()} whoami")
    return 0


# ── tryb edycji ───────────────────────────────────────────────────────────────


def _klucz_tego_samego_agenta(nazwa: str, konf, wartosc: str) -> bool:
    """Nowy klucz w trybie edycji MUSI należeć do TEGO SAMEGO agenta (decyzja Damiana
    26.09): `/me` z nim ma oddać TEN SAM slug. Inaczej odmawiamy — podmiana klucza
    na obcy pod istniejącą nazwą zamieniłaby tego agenta w kogoś innego bez słowa."""
    try:
        toz = _me_dla(konf.adres, wartosc)
    except BladAPI as blad:
        print(f"Nie udało się sprawdzić klucza w SF ({blad}).\n"
              f"Klucz NIE został zapisany.", file=sys.stderr)
        return False
    w_sf = _nazwa_z_me(toz)
    if w_sf is None:
        print(f"Tym kluczem SF nie podaje nazwy agenta — nie potwierdzę, że należy do "
              f"„{nazwa}”. Klucz NIE został zapisany; jeśli to NOWY agent, dodaj go "
              f"przez „dodaj nowego”.", file=sys.stderr)
        return False
    if konf.slug and w_sf != konf.slug:
        print(f"Ten klucz należy do innego agenta — w SF to „{w_sf}”, a ten agent to "
              f"„{konf.slug}”. Dodaj go jako nowego.", file=sys.stderr)
        return False
    if not konf.slug:
        konf.slug = w_sf
    return True


def _edytuj_organizacje(konf, toz: tozsamosc.Tozsamosc) -> None:
    """Pytanie o domyślną Organizację w trybie edycji: Enter zostawia, `-` usuwa."""
    obecna = toz.znajdz(konf.organizacja) if konf.organizacja else None
    podane = _pytaj("Organizacja domyślna (slug; Enter = zostaw; '-' = usuń)",
                    obecna.slug if obecna else (konf.organizacja or ""))
    if obecna and podane == obecna.slug:
        return
    if podane == (konf.organizacja or ""):
        return
    if podane == "-":
        konf.organizacja = ""
        print("Domyślna Organizacja usunięta — przy zapisach podawaj --org.")
        return
    wybrana = toz.znajdz(podane)
    if wybrana is None:
        print(f"Nie znam Organizacji „{podane}” na Twojej liście — zostawiam dotychczasową.",
              file=sys.stderr)
        return
    if not wybrana.ma_nadania:
        print(f"W „{wybrana.slug}” nie masz nadań — zostawiam dotychczasową, żeby zapis "
              f"nie kończył się odmową w połowie.", file=sys.stderr)
        return
    konf.organizacja = wybrana.uuid


def _tryb_edycji(nazwa: str, *, ochrona, jak_wolac) -> int:
    magazyn_klucza.ustaw_agenta(nazwa)
    try:
        konf = konfiguracja.wczytaj()
    except RuntimeError as blad:
        print(str(blad), file=sys.stderr)
        return 2
    print(f"Edycja agenta „{nazwa}”. Enter zostawia wartość w nawiasie.\n")

    try:
        nowy = magazyn_klucza.zapytaj(czy_pusty_ok=True)
    except ValueError as blad:
        print(f"Klucz NIE został zapisany: {blad}", file=sys.stderr)
        return 1
    except EOFError as brak:
        raise _KoniecWejscia from brak
    if nowy:
        if not _klucz_tego_samego_agenta(nazwa, konf, nowy):
            return 2
        magazyn_klucza.zapisz(nowy)
        print(f"Klucz {magazyn_klucza.skrot(nowy)} zapisany: "
              f"{magazyn_klucza.sciezka_konfiguracji()}")

    # Świeża rozmowa z SF (nowym kluczem, gdy podmieniony) — do listy Organizacji.
    toz = None
    obecny = magazyn_klucza.wczytaj()
    if obecny:
        try:
            toz = _me_dla(konf.adres, obecny)
        except BladAPI as blad:
            print(f"  (nie odpytam SF o Organizacje: {blad} — zostawiam, co jest)",
                  file=sys.stderr)
    if toz is not None:
        print(f"\nTwoje Organizacje:\n{tozsamosc.lista_do_pokazania(toz.organizacje)}\n")
        _edytuj_organizacje(konf, toz)

    konf.profil = _pytaj(f"Profil: {' / '.join(PROFILE)}",
                         konf.profil or PROFIL_DOMYSLNY)
    # ADVERTPR-959: stara nazwa `autor` przyjęta i od razu zamieniona.
    konf.profil = konfiguracja.PROFIL_ALIASY.get(konf.profil, konf.profil)
    if konf.profil not in PROFILE:
        print(f"Nie znam profilu „{konf.profil}”. Dostępne: {', '.join(PROFILE)}",
              file=sys.stderr)
        return 2

    konf.adres = _pytaj("Adres SalesForge", konf.adres)

    plik = konfiguracja.zapisz(konf)
    print(f"\nUstawienia zapisane: {plik}")
    ochrona()
    print(f"\nSprawdź, czy działa: {jak_wolac()} whoami")
    return 0


# ── przenosiny starego układu ─────────────────────────────────────────────────


def _przenies_stary_uklad(wiersz: WierszAgenta, *, jak_wolac) -> int:
    """`config.json` z korzenia (sprzed v0.3) → podkatalog nazwany slugiem z ustawień.

    Przenosimy też klucz (plik `credentials` na Linuksie, konto `api-key` w pęku na
    macOS). Jednostki usługi NIE ruszamy — wskazuje ona stary układ, więc trzeba ją
    przegenerować przez `sf-kit usluga` (mówimy to na końcu).
    """
    konf = wiersz.konf
    if konf is None:
        print(f"{wiersz.katalog / konfiguracja.PLIK} jest nieczytelny — popraw go ręcznie, "
              f"potem `sf-kit init` przeniesie go do podkatalogu.", file=sys.stderr)
        return 2
    nazwa = (konf.slug or "").strip()
    if not nazwa:
        print("Stary config.json nie ma pola „slug” — dopisz ręcznie slug agenta z SF, "
              "potem spróbuj ponownie.", file=sys.stderr)
        return 2
    korzen = magazyn_klucza.katalog_bazowy()
    cel = korzen / nazwa
    if cel.exists():
        print(f"Katalog {cel} już istnieje — nie przenoszę. Zajrzyj do obu miejsc ręcznie.",
              file=sys.stderr)
        return 2
    if not _potwierdz(f"Przenieść stary układ do podkatalogu „{nazwa}”? [t/N]"):
        print("Nic nie przeniosłem.")
        return 0

    # KLUCZ CZYTAMY PRZED PRZENOSINAMI CONFIGU: rozstrzyganie ścieżki (`sciezka_konfiguracji`)
    # traktuje stary układ jako katalog bazowy tylko póki `config.json` leży w korzeniu —
    # po przenosinach „stary” klucz przestałby być czytelny i zniknąłby w przenosinach.
    # Czytamy GO Wprost ze starego miejsca (plik w korzeniu; na macOS konto „api-key”
    # w pęku) — nie przez `wczytaj()`, bo to dałoby pierwszeństwo zmiennej `SF_KIT_KEY`,
    # a przenosiny mają dotyczyć klucza ZAPISANEGO, nie tego z otoczenia procesu.
    stary_plik = korzen / "credentials"
    wartosc = (stary_plik.read_text(encoding="utf-8").strip()
               if stary_plik.exists() else "") or None
    if not wartosc and magazyn_klucza.czy_macos():
        magazyn_klucza.ustaw_agenta(None)      # stary układ: konto „api-key” w pęku
        wartosc = magazyn_klucza.wczytaj()

    cel.mkdir(parents=True)
    (korzen / konfiguracja.PLIK).replace(cel / konfiguracja.PLIK)

    opis_klucza = "nie znalazłem klucza w starym miejscu — wpisz go w trybie edycji tego agenta"
    if wartosc:
        magazyn_klucza.ustaw_agenta(nazwa)
        opis_klucza = magazyn_klucza.zapisz(wartosc)
        stary_plik = korzen / "credentials"
        if stary_plik.exists():
            stary_plik.unlink()
        magazyn_klucza.usun_z_peku(magazyn_klucza.KONTO_JEDNEGO_AGENTA)

    print(f"\nPrzeniesiono do {cel}:")
    print(f"  config.json → tak")
    print(f"  klucz → {opis_klucza}")
    if konf.profil == "worker":
        print(f"\nJednostka usługi workera wskazuje stary układ — przegeneruj ją:")
        print(f"  {jak_wolac()} --agent {nazwa} usluga")
    return 0


# ── wejście ───────────────────────────────────────────────────────────────────


def jak_wolac_bez_parametru() -> str:
    """`sf-kit` albo `./sf-kit` — podpowiedź, która działa po wklejeniu (jak `cli`)."""
    import shutil

    return "sf-kit" if shutil.which("sf-kit") else "./sf-kit"


def polecenie(args, *, ochrona, jak_wolac=None) -> int:
    """Ekran startowy z listą agentów → tryb dodawania albo edycji.

    `ochrona` — callback włączający ochronę repozytorium (mieszka w `cli`, żeby ten
    moduł nie importował całego interfejsu poleceń). `jak_wolac` — podpowiedź końcowa.
    """
    if jak_wolac is None:
        jak_wolac = jak_wolac_bez_parametru
    try:
        # `--agent <slug> init` = edycja tego agenta od razu, bez listy.
        wskazany = (getattr(args, "agent", None) or "").strip()
        if wskazany:
            if wskazany in magazyn_klucza.agenci():
                return _tryb_edycji(wskazany, ochrona=ochrona, jak_wolac=jak_wolac)
            znani = magazyn_klucza.agenci()
            podpowiedz = (f"Skonfigurowani: {', '.join(znani)}."
                          if znani else "Na tej maszynie nie ma jeszcze żadnego agenta.")
            print(f"Nie ma agenta „{wskazany}” na tej maszynie. {podpowiedz}",
                  file=sys.stderr)
            return 2

        wiersze = _wiersze_agentow()
        if not wiersze:
            print("Na tej maszynie nie ma jeszcze żadnego agenta — zaczynam od dodawania.\n")
            return _tryb_dodawania(ochrona=ochrona, jak_wolac=jak_wolac)

        while True:
            _pokaz_liste(wiersze)
            try:
                wybor = input("[numer] edytuj agenta · [n] dodaj nowego · [q] wyjdź: "
                              ).strip()
            except EOFError:
                print("\nBrak wejścia — `init` jest interakcyjne, uruchom je w terminalu.",
                      file=sys.stderr)
                return 2
            if wybor.lower() == "q":
                return 0
            if wybor.lower() == "n":
                return _tryb_dodawania(ochrona=ochrona, jak_wolac=jak_wolac)
            if wybor.isdigit() and 1 <= int(wybor) <= len(wiersze):
                wiersz = wiersze[int(wybor) - 1]
                if wiersz.stary_uklad:
                    wynik = _przenies_stary_uklad(wiersz, jak_wolac=jak_wolac)
                else:
                    wynik = _tryb_edycji(wiersz.nazwa, ochrona=ochrona,
                                         jak_wolac=jak_wolac)
                # Po edycji/przenosinach lista może wyglądać inaczej — odświeżamy.
                wiersze = _wiersze_agentow()
                if not wiersze:
                    return wynik
                continue
            print(f"Nie rozumiem „{wybor}” — podaj numer z listy, n albo q.",
                  file=sys.stderr)
    except _KoniecWejscia:
        print("\nBrak wejścia — `init` jest interakcyjne, uruchom je w terminalu.",
              file=sys.stderr)
        return 2
