"""Co dana operacja potrafi i jakich pól wymaga — wiedza, którą Kit niesie ze sobą.

v0.6 (18.09.2026) - APro Agents / borys-sf

PO CO TEN PLIK ISTNIEJE
═══════════════════════
ADVERTPR-879, wymaganie 1: *„polecenie, które wypisuje, co dana operacja potrafi i jakich pól
wymaga — żeby nie trzeba było strzelać w adresy"*. Powód powstania sprawy jest twardy: trzy razy
w ciągu jednej doby koordynatorka ogłosiła „tego się nie da", a funkcja istniała pod adresem,
w który akurat nie strzeliła. Za każdym razem kosztem była fałszywa diagnoza wpisana do sprawy.

DLACZEGO KATALOG JEST TUTAJ, A NIE POBIERANY Z SERWERA
══════════════════════════════════════════════════════
Agata (18.09, wpis 19:34): *„narzędzie ma czytać kontrakt z serwera, a nie z plików rozjeżdżających
się między sobą o trzy tygodnie"*. Zgadzam się z zasadą i sprawdziłem, czy da się ją dziś spełnić:

    GET https://sf.dpakula.pl/openapi.json  →  HTTP 200 … i treścią jest STRONA FRONTU.

Kod 200 kłamie: `/openapi.json` łapie SPA, bo nginx nie przepuszcza tej ścieżki do backendu.
Sam dokument istnieje i jest poprawny — widać go pod `127.0.0.1:8010/openapi.json`, czyli tylko
z maszyny. Do czasu, aż ktoś dołoży `location` w nginksie (prośba do Seweryna, ADVERTPR-879),
Kit nie MOŻE czytać kontraktu z serwera i udawanie, że czyta, byłoby gorsze niż jego brak.

Dlatego układ jest taki: katalog operacji mieszka tutaj i działa bez sieci, a `kontrakt --sprawdz`
porównuje go z żywym `openapi.json`, gdy tylko ten stanie się osiągalny. **Zawartość tego pliku
jest więc kandydatem do rozjazdu i wie o tym** — dlatego każdy wpis niesie datę sprawdzenia
w kodzie, a nie w dokumentacji.

CZEGO TU ŚWIADOMIE NIE MA: DRUGIEJ BRAMKI
══════════════════════════════════════════
Kit NIE waliduje nazw uprawnień u siebie. Katalog nadawalnych uprawnień żyje po stronie SF
(`NADAWALNE_UPRAWNIENIA_AGENTA`) i trasa nadań odrzuca nieznane sama, 422 z nazwą uprawnienia
i pełną listą dozwolonych — czyli czytelnie. Druga kopia listy w drugim repozytorium byłaby
pierwszą rzeczą, która rozjedzie się po zmianie po tamtej stronie, i odrzucałaby uprawnienia,
które serwer już zna. Lista niżej jest PODPOWIEDZIĄ dla człowieka, nie warunkiem.

Bramka Kita stoi gdzie indziej i pilnuje czegoś innego: **pól, których trasa nie zna**
(wymaganie 3 ze sprawy). To jest pytanie o kształt żądania, a ten Kit zna — w odróżnieniu od
słownika wartości, który rośnie po stronie serwera.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: Dzień, w którym katalog przeszedł porównanie z kodem produkcyjnym
#: (`/var/www/apps/salesforge-prod/backend/app/modules/auth/`). Data stoi w kodzie, bo to ona
#: mówi, jak bardzo wolno temu plikowi wierzyć — a dokumentacja starzeje się cicho.
SPRAWDZONO = "2026-09-18"


@dataclass(frozen=True)
class Operacja:
    """Jedna operacja administracyjna: adres, pola, pułapki i sposób sprawdzenia, że wyszło."""

    nazwa: str
    tytul: str
    metoda: str
    trasa: str
    kto_moze: str
    #: Pola ciała żądania, bez których trasa odpowie 422.
    wymagane: tuple[str, ...] = ()
    #: Pola ciała żądania, które trasa przyjmie i użyje.
    opcjonalne: tuple[str, ...] = ()
    #: Pola, które ktoś rozsądnie może wysłać, a ta trasa ich NIE OBSŁUGUJE — z adresem tego,
    #: co naprawdę je przyjmuje. Klucz to nazwa pola, wartość to zdanie dla człowieka.
    odrzucane: dict[str, str] = field(default_factory=dict)
    #: Rzeczy, które wyglądają inaczej, niż działają. Idą do komunikatów, nie do tabeli.
    pulapki: tuple[str, ...] = ()
    #: Czym Kit DOMYKA operację. Kod 201 nie jest dowodem — dzisiejsza wpadka z `scope`
    #: polegała właśnie na tym, że serwer odpowiedział 201 na konfigurację, która nie działa.
    weryfikacja: str = ""

    def opis(self) -> str:
        linie = [
            f"{self.nazwa} — {self.tytul}",
            f"  {self.metoda} {self.trasa}",
            f"  kto może: {self.kto_moze}",
        ]
        if self.wymagane:
            linie.append(f"  pola wymagane:   {', '.join(self.wymagane)}")
        if self.opcjonalne:
            linie.append(f"  pola opcjonalne: {', '.join(self.opcjonalne)}")
        if self.odrzucane:
            linie.append("  pola, których ta trasa NIE obsługuje:")
            linie += [f"    {pole} — {powod}" for pole, powod in sorted(self.odrzucane.items())]
        if self.pulapki:
            linie.append("  pułapki:")
            linie += [f"    • {p}" for p in self.pulapki]
        if self.weryfikacja:
            linie.append(f"  Kit domyka to przez: {self.weryfikacja}")
        return "\n".join(linie)


#: Pułapka wspólna dla wszystkich tras administracyjnych — i jedyna, którą Kit USUWA, zamiast
#: o niej ostrzegać. Numer w ścieżce to `tenants.id` (liczba porządkowa), a nie `tenant_id`
#: (uuid) z nagłówka `X-Tenant-Id`. Koordynatorka nigdy go nie wpisuje: podaje slug albo nic,
#: a Kit tłumaczy go przez `GET /tenants` (ta trasa oddaje `id` obok `uuid` także zwykłemu
#: członkowi — sprawdzone kluczem członka 18.09, nie tylko superadminem).
PULAPKA_NUMERU = (
    "numer Organizacji w ścieżce to liczba porządkowa (`tenants.id`), a NIE uuid z nagłówka "
    "`X-Tenant-Id` — Kit tłumaczy slug na numer sam, nie wpisuj go z palca"
)

KATALOG: tuple[Operacja, ...] = (
    Operacja(
        nazwa="agent-dodaj",
        tytul="załóż konto agenta razem z członkostwem, nadaniami i kluczem",
        metoda="POST",
        trasa="/api/v1/tenants/{numer}/agents",
        kto_moze="wyłącznie superadmin SF",
        wymagane=("email", "full_name", "agent_slug"),
        opcjonalne=("permissions",),
        odrzucane={
            "scope": "zakres klucza ustala ta trasa sama (`user`) — nie da się go tu wybrać",
            "role": "rola członkostwa to zawsze `user` (najmniejsze uprawnienia); "
                    "zmiana roli to `PATCH /tenants/{numer}/users/{uuid}`",
            "password": "agent nie loguje się formularzem — kanałem jest klucz API",
            "board_root": "katalog boardu wynika ze sluga; nadpisanie to "
                          "`PATCH /tenants/{numer}/agents/{uuid}`",
        },
        pulapki=(
            PULAPKA_NUMERU,
            "`agent_slug` to nazwa KATALOGU boardu, nie etykieta — małe litery, cyfry "
            "i myślniki; dwa konta z tym samym slugiem w Organizacji to odmowa 409",
            "uprawnienia spoza katalogu serwera są ODSIEWANE po cichu, nie odrzucane — "
            "Kit porównuje to, o co prosiłaś, z polem `nadania` w odpowiedzi i mówi, co odpadło",
            "klucz wraca w odpowiedzi RAZ i nigdzie go potem nie odczytasz",
        ),
        weryfikacja="odczyt nadań (`nadaj --pokaz`) i próbne `GET /me` świeżym kluczem",
    ),
    Operacja(
        nazwa="nadaj",
        tytul="odczytaj albo ustaw uprawnienia konta w tej Organizacji",
        metoda="GET / PUT",
        trasa="/api/v1/tenants/{numer}/users/{uuid}/permissions",
        kto_moze="owner Organizacji u siebie, superadmin wszędzie",
        wymagane=("permissions",),
        opcjonalne=("ustaw_domyslne",),
        odrzucane={
            "scope": "nadania nie mają zakresu — zakres ma klucz "
                     "(`POST /api-keys`, pole `scope`)",
            "role": "rola to inna trasa: `PATCH /tenants/{numer}/users/{uuid}`",
            "agent_slug": "slug siedzi na członkostwie i zmienia go "
                          "`PATCH /tenants/{numer}/agents/{uuid}`",
        },
        pulapki=(
            PULAPKA_NUMERU,
            "to jest adres UŻYTKOWNIKA w Organizacji, nie agenta — pytanie pod "
            "`/agents/{uuid}/permissions` da 404 i wygląda jak „trasy nie ma”",
            "`ustaw_domyslne: true` WYGRYWA z listą w ciele — nie wysyłaj obu naraz",
            "PUT ZASTĘPUJE cały wycinek uprawnień agenta; żeby coś dołożyć, najpierw odczytaj",
            "uprawnienia spoza wycinka agenta (np. `console:*`) zostają nietknięte — "
            "tej trasy nie używa się do konsoli",
            "członkostwo zawieszone = 404, nie pusta lista: nadanie na nim i tak nic by nie dało",
        ),
        weryfikacja="odczyt GET po zapisie i pokazanie różnicy (nadane / odebrane)",
    ),
    Operacja(
        nazwa="klucz-wystaw",
        tytul="wystaw klucz API w tej Organizacji i sprawdź, że działa",
        metoda="POST",
        trasa="/api/v1/api-keys",
        kto_moze="admin Organizacji i wyżej (klucz `super_admin` — tylko superadmin)",
        wymagane=("source_name",),
        opcjonalne=("description", "permissions", "scope", "user_email", "expires_at",
                    "allowed_ips", "webhook_url"),
        odrzucane={
            "agent_slug": "klucz nie ma sluga — slug jest na członkostwie konta",
            "role": "klucz nie niesie roli; przy kluczu osobistym rolę bierze się "
                    "z członkostwa właściciela",
            "tenant_id": "Organizację klucza wyznacza nagłówek `X-Tenant-Id` żądania, "
                         "nie pole w ciele",
        },
        pulapki=(
            "`scope` i `permissions` to DWA RÓŻNE WYMIARY: `scope` mówi, jak daleko klucz "
            "sięga w Organizacjach, `permissions` — co nim wolno zrobić. `scope=user` "
            "z `permissions=null` to działająca konfiguracja, nie błąd",
            "`permissions: null` = brak zawężenia (pełne prawa właściciela); "
            "`permissions: []` = klucz, który nie może NIC. To nie jest to samo",
            "klucz osobisty (`scope=user`) potrzebuje `user_email` — bez właściciela "
            "nie ma czyich praw pożyczyć",
            "pełny klucz wraca RAZ, w odpowiedzi; drugi raz go nie zobaczysz",
        ),
        weryfikacja="próbne `GET /me` NOWYM kluczem — pokazuje właściciela, zakres "
                    "i Organizacje, w których klucz naprawdę działa",
    ),
    Operacja(
        nazwa="agent-napraw",
        tytul="popraw członkostwo ISTNIEJĄCEGO konta (slug, rodzaj, katalog boardu)",
        metoda="PATCH",
        trasa="/api/v1/tenants/{numer}/agents/{uuid}",
        kto_moze="wyłącznie superadmin SF",
        opcjonalne=("agent_slug", "kind", "board_root"),
        odrzucane={
            "permissions": "ta trasa NIE nadaje uprawnień — idą przez "
                           "`PUT /tenants/{numer}/users/{uuid}/permissions` (`sf-kit nadaj`)",
            "email": "adresu konta się tędy nie zmienia",
            "scope": "zakres dotyczy klucza, nie członkostwa",
        },
        pulapki=(
            PULAPKA_NUMERU,
            "to trasa NAPRAWY, nie zakładania — nieistniejące konto daje 404, "
            "bo założenie konta niesie klucz do przekazania",
            "`kind='agent'` bez `agent_slug` jest odrzucane 422: plakietka agenta bez "
            "katalogu boardu to delegacja, która wygląda na działającą i nie działa",
            "podanie nagłówka `X-Tenant-Id` innego niż numer w adresie to 400, nie "
            "ciche rozstrzygnięcie na korzyść jednego z nich",
        ),
        weryfikacja="odczyt stanu członkostwa z odpowiedzi trasy",
    ),
)

#: Rzeczy, o które koordynatorka pyta, a których tą drogą nie ma — z POWODEM. Bo „nie da się"
#: bez powodu wraca następnego dnia jako to samo pytanie, a wpisane do sprawy jest fałszywą
#: diagnozą do prostowania. Trzy pierwsze pozycje to wykluczenia z zakresu Kimiego (18.09).
CZEGO_NIE_MA: dict[str, str] = {
    "opinie": "opinie i rozliczenia są wyłącznie w panelu — API ich nie wystawia. "
              "To nie jest brak uprawnienia, więc nadanie niczego nie zmieni.",
    "rozliczenia": "patrz `opinie` — wyłącznie panel.",
    "leady": "moduł przed startem; trasy istnieją, ale kontraktu jeszcze nie ma "
             "i kształt może się zmienić bez zapowiedzi.",
    "kursy": "patrz `leady` — moduł przed startem.",
    "niezobaczone": "trasa niezobaczonych spraw jest CELOWO sesyjna (liczy się na sesję "
                    "człowieka). Klucz API dostanie 403 i to jest zachowanie zamierzone, "
                    "nie usterka do zgłoszenia.",
    "konsola": "boxy konsoli mają własne trasy i własną bramkę (`console:*`, nadawane "
               "osobno od uprawnień agenta). Kit ich jeszcze nie obsługuje — "
               "świadomie, ADVERTPR-879.",
    "plany": "plany i cele: trasy istnieją, Kit ich jeszcze nie obsługuje — "
             "świadomie, ADVERTPR-879.",
    "wiedza": "moduł Wiedza: brak źródeł kontraktu. Nie zgadujemy kształtu.",
}


def znajdz(nazwa: str) -> Operacja | None:
    """Operacja po nazwie. Bez dopasowania po podobieństwie — pomyłka ma być widoczna."""
    szukane = (nazwa or "").strip().lower()
    for op in KATALOG:
        if op.nazwa == szukane:
            return op
    return None


def podpowiedz_nie_ma(nazwa: str) -> str | None:
    """Czy pytanie trafia w coś, czego świadomie nie ma — i dlaczego."""
    szukane = (nazwa or "").strip().lower()
    for haslo, powod in CZEGO_NIE_MA.items():
        if haslo in szukane:
            return powod
    return None


def nieznane_pola(op: Operacja, dane: dict) -> list[tuple[str, str]]:
    """Pola, których ta trasa nie obsłuży — z powodem. Wymaganie 3 ze sprawy ADVERTPR-879.

    Odrzucamy PRZED wysłaniem, bo po wysłaniu jest za późno na rozpoznanie pomyłki: serwer
    albo takie pole cicho pominie (potwierdzona usterka `PATCH …/agents/{uuid}` z polem
    `permissions` — HTTP 200 i zero skutku), albo odpowie 422 bez wskazania, gdzie to pole
    naprawdę mieszka.

    Pole spoza katalogu, którego nie umiemy nazwać, też zgłaszamy — z ostrożniejszym zdaniem.
    Cisza jest tu gorsza od fałszywego alarmu: alarm kosztuje jedno spojrzenie, cisza kosztuje
    noc szukania, czemu nadanie „poszło", a agent dalej dostaje 403.
    """
    znane = set(op.wymagane) | set(op.opcjonalne)
    wynik: list[tuple[str, str]] = []
    for pole in dane:
        if pole in znane:
            continue
        powod = op.odrzucane.get(
            pole,
            f"trasa {op.metoda} {op.trasa} nie wymienia tego pola — "
            f"zostałoby przyjęte i zignorowane",
        )
        wynik.append((pole, powod))
    return sorted(wynik)


def spis() -> str:
    """Wszystkie operacje jedną linijką każda — punkt wejścia dla kogoś, kto nie zna nazw."""
    linie = [f"Operacje administracyjne, które Kit zna (stan katalogu: {SPRAWDZONO}):", ""]
    linie += [f"  {op.nazwa:<14} {op.tytul}" for op in KATALOG]
    linie += [
        "",
        "  sf-kit kontrakt <nazwa>     — pola, pułapki i sposób weryfikacji",
        "  sf-kit kontrakt --sprawdz   — porównaj katalog z żywym serwerem",
        "",
        "Czego tą drogą NIE ma (i dlaczego): " + ", ".join(sorted(CZEGO_NIE_MA)),
    ]
    return "\n".join(linie)
