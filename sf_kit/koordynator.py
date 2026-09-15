"""Profil KOORDYNATOR — zlecanie pracy flocie i odbieranie jej (SF Agent Kit v0.4, część C).

v0.4 (15.09.2026) - APro Agents / borys-sf

CZYM SIĘ RÓŻNI OD DWÓCH POZOSTAŁYCH PROFILI
`worker` CIĄGNIE zadania z kolejki, `autor` PCHA do SF gotową pracę człowieka, a koordynator
**rozdaje pracę innym i ją odbiera**. Jedyny z trzech, który działa na cudzych zadaniach —
i dlatego jedyny, w którym pomyłka kosztuje czyjś dzień pracy, a nie własny.

Z tego biorą się trzy zasady tego pliku:

1. **Zadanie ZAWSZE ma sprawę.** Twarda strona polityki „twardo przy zakładaniu, miękko przy
   wykonaniu" (Damian, 15.09). Zadanie bez sprawy da się wykonać, ale jego wynik nie ma gdzie
   wylądować — koordynator nie ma go zakładać ani przez przypadek, ani „na chwilę".
2. **Sprawa musi być dostępna WYKONAWCY**, nie tylko zlecającemu. Zlecenie pracy na sprawie,
   której agent nie zobaczy, kończy się zadaniem niewykonalnym — a wygląda na wysłane.
3. **`odbierz` sprawdza, czy wynik JEST, zanim zamknie.** Zamknięcie na słowo znaczy, że
   „zrobione" przestaje cokolwiek znaczyć: zadania schodzą z tablicy niezależnie od tego,
   czy coś po nich zostało.

GATING — PO UPRAWNIENIU Z `/me`, NIE PO POLU `profil` W PLIKU
Profil w konfiguracji jest deklaracją człowieka („tak zamierzam pracować"). O tym, co wolno,
rozstrzyga klucz — a od 15.09 widać to wprost (`GET /me`, ADVERTPR-796). Polecenie, które
pokazuje się w pomocy i kończy 403, jest gorsze od polecenia, którego nie ma: pierwsze każe
zgadywać, czy to usterka narzędzia, czy brak prawa.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Uprawnienie, które NAPRAWDĘ gatuje zakładanie zadań w SF (`POST /api/v1/tasks` →
#: `_require_manager` → `PERM_PLANS_WRITE`). Sprawdzone w kodzie SF 15.09, nie zgadnięte —
#: `task.yml` przewidywał `tasks:write`/`tasks:assign` i takich uprawnień w SF nie ma.
#: Gdyby Kit gatował po nieistniejącej nazwie, ukrywałby polecenia PRZED wszystkimi.
UPRAWNIENIE_ZLECANIA = "plans:write"

#: Statusy zadań, które znaczą „jeszcze się dzieje". Lista mieszka tutaj, bo to koordynator
#: pyta „co jest w toku", a nie SF.
W_TOKU = ("queued", "in_progress", "on_hold")


class Odmowa(RuntimeError):
    """Nie da się tego zrobić — i komunikat mówi, co zrobić zamiast tego."""


@dataclass(frozen=True)
class Agent:
    user_id: str
    slug: str | None
    nazwa: str
    email: str

    @property
    def wolalny(self) -> bool:
        """Czy da się do niego zlecić. Członkostwo bez sluga = agent widoczny, ale nie do zawołania."""
        return bool(self.slug)

    def opis(self) -> str:
        if not self.wolalny:
            return f"{'(bez sluga)':<22} {self.nazwa:<28} ⚠ nie da się zlecić"
        return f"{self.slug:<22} {self.nazwa:<28} {self.email}"


def czy_wolno_zlecac(uprawnienia: list[str]) -> bool:
    """Czy w TEJ Organizacji ten klucz może zakładać zadania."""
    return UPRAWNIENIE_ZLECANIA in (uprawnienia or [])


def flota(klient) -> list[Agent]:
    """Agenci Organizacji, w kolejności: najpierw ci, których da się zawołać."""
    agenci = [
        Agent(user_id=str(a.get("user_id") or ""), slug=a.get("agent_slug"),
              nazwa=a.get("full_name") or a.get("email") or "(bez nazwy)",
              email=a.get("email") or "")
        for a in klient.agenci()
    ]
    return sorted(agenci, key=lambda a: (not a.wolalny, (a.slug or a.nazwa).lower()))


def znajdz_agenta(agenci: list[Agent], wskazanie: str) -> Agent:
    """Agent po slugu albo identyfikacie konta. Rzuca `Odmowa` z listą do wyboru.

    Po slugu, nie po nazwisku ani mailu: slug jest tym, co wskazuje board agenta, i tym, co
    człowiek widzi w SF. Dopasowanie po nazwie bywa niejednoznaczne — dwoje ludzi o tym samym
    imieniu to nie jest przypadek teoretyczny, a zadanie wysłane nie temu, komu trzeba, wygląda
    jak wysłane.
    """
    w = (wskazanie or "").strip().lower()
    if not w:
        raise Odmowa("Nie wiadomo, komu zlecić — podaj slug agenta (`--agent-slug`).")
    trafienia = [a for a in agenci if w in {(a.slug or "").lower(), a.user_id.lower()}]
    if not trafienia:
        lista = "\n".join(f"  {a.opis()}" for a in agenci) or "  (żadnego)"
        raise Odmowa(f"W tej Organizacji nie ma agenta „{wskazanie}”.\nFlota:\n{lista}")
    agent = trafienia[0]
    if not agent.wolalny:
        raise Odmowa(
            f"Agent „{agent.nazwa}” nie ma ustawionego sluga w tej Organizacji, więc nie ma "
            f"jak wskazać jego boardu. Poproś administratora o uzupełnienie członkostwa."
        )
    return agent


def sprawdz_sprawe_dla_wykonawcy(klient, *, ticket_id: str, agent: Agent) -> None:
    """Czy WYKONAWCA zobaczy tę sprawę. Rzuca `Odmowa` z podpowiedzią.

    Sprawdzamy to, czego da się sprawdzić z tej strony: czy sprawa w ogóle istnieje w tej
    Organizacji. Pełnej odpowiedzi „czy zobaczy ją TEN agent" Kit nie ma jak dać — widoczność
    zależy od uprawnień agenta i od poziomu wpisów, a tego z zewnątrz nie policzy. Dlatego
    mówimy dokładnie tyle, ile wiemy, i podpowiadamy wyjście, zamiast udawać pewność.
    """
    from .api import BladAPI

    try:
        klient.wpisy_sprawy(ticket_id, limit=1)
    except BladAPI as blad:
        raise Odmowa(
            f"Nie mogę odczytać tej sprawy w bieżącej Organizacji ({blad}).\n"
            f"Jeśli sprawa należy do innej Organizacji niż ta, w której pracuje "
            f"„{agent.slug}” — załóż sprawę pomocniczą w JEGO Organizacji i zleć na niej. "
            f"Zadanie na niewidocznej sprawie jest niewykonalne, a wygląda na wysłane."
        ) from None


#: Statusy przeszukiwane przy szukaniu zadania po identyfikatorze — w kolejności od
#: najbardziej prawdopodobnego. Odbiera się zwykle to, co właśnie się skończyło.
STATUSY_SZUKANIA = ("in_progress", "completed", "queued", "on_hold")


@dataclass(frozen=True)
class Znalezione:
    """Wynik szukania zadania. `urwane` znaczy, że NIE przejrzeliśmy wszystkiego."""
    zadanie: dict | None
    przejrzano: int
    urwane: bool

    def powod_braku(self, wskazanie: str) -> str:
        """Zdanie do pokazania, gdy nie znaleziono — rozróżnia „nie ma" od „nie doszedłem"."""
        if self.urwane:
            return (f"Nie znalazłem zadania „{wskazanie}” wśród {self.przejrzano} "
                    f"przejrzanych — ale kolejka jest dłuższa, więc to NIE znaczy, że go nie ma. "
                    f"Podaj pełny identyfikator albo sprawdź w panelu.")
        return (f"Nie znalazłem zadania „{wskazanie}” w tej Organizacji "
                f"(przejrzanych: {self.przejrzano}). Sprawdź identyfikator albo wskaż inną "
                f"Organizację przez --org.")


def znajdz_zadanie(klient, wskazanie: str) -> Znalezione:
    """Zadanie po `external_id` albo identyfikatorze — przez CAŁĄ kolejkę, nie pierwszą stronę.

    Pierwsza wersja `odbierz` brała jedną stronę na status. Przy dłuższej kolejce znaczyłoby to
    „nie znalazłem zadania", choć zadanie istnieje — czyli odmowę odbioru pracy, która JEST
    zrobiona, z komunikatem sugerującym literówkę. Ta sama pułapka, którą worker miał w 0.1
    (zadanie na pozycji 51 nie istniało dla agenta) i która wygląda na spokój, nie na usterkę.

    Gdy bezpiecznik stron przerwie przeglądanie, mówimy to wprost — brak dowodu nie jest
    dowodem braku.
    """
    from .api import NA_STRONE, STRON_NAJWYZEJ

    w = (wskazanie or "").strip()
    if not w:
        raise Odmowa("Podaj identyfikator zadania.")

    przejrzano_razem = 0
    urwane = False
    for status in STATUSY_SZUKANIA:
        przejrzano = 0
        for _ in range(STRON_NAJWYZEJ):
            strona = klient.zadania(status=status, limit=NA_STRONE, offset=przejrzano)
            pozycje = strona.get("items") or []
            wszystkich = int(strona.get("total") or 0)
            przejrzano += len(pozycje)
            przejrzano_razem += len(pozycje)
            for z in pozycje:
                if w in {str(z.get("external_id") or ""), str(z.get("id") or "")}:
                    return Znalezione(zadanie=z, przejrzano=przejrzano_razem, urwane=False)
            if not pozycje or przejrzano >= wszystkich:
                break
        else:
            urwane = True
    return Znalezione(zadanie=None, przejrzano=przejrzano_razem, urwane=urwane)


def wynik_jest_na_sprawie(klient, *, ticket_id: str, external_id: str) -> tuple[bool, str]:
    """Czy na sprawie widać ślad po tym zadaniu. Zwraca `(jest, co_znaleziono)`.

    Szukamy po `external_id` zadania w treści wpisów ALBO po jakimkolwiek załączniku dołożonym
    po jego stronie. Worker wpisuje identyfikator zadania w sprawozdaniu (v0.1) i od v0.4
    dokłada pliki — więc jedno z dwojga musi być.

    Świadomie NIE ufamy samemu statusowi zadania: `completed` mówi, że ktoś je zamknął, a nie
    że cokolwiek z niego zostało. Właśnie po to `odbierz` istnieje.
    """
    from .api import BladAPI

    try:
        dziennik = klient.wpisy_sprawy(ticket_id, limit=100)
    except BladAPI as blad:
        return False, f"nie udało się odczytać dziennika sprawy ({blad})"

    pozycje = dziennik.get("pozycje") or []
    zalaczniki = 0
    for wpis in pozycje:
        tresc = str(wpis.get("content") or wpis.get("tresc") or "")
        pliki = wpis.get("attachments") or wpis.get("zalaczniki") or []
        if external_id and external_id in tresc:
            return True, (f"wpis z {len(pliki)} załącznikami" if pliki else "wpis bez załączników")
        zalaczniki += len(pliki)

    ukryte = int(dziennik.get("ukryte") or 0)
    if ukryte:
        # Wpisy poza naszym poziomem widoczności mogą zawierać wynik — nie twierdzimy, że go nie ma.
        return False, (f"nie widzę śladu po {external_id}, ale {ukryte} wpisów jest poza moim "
                       f"poziomem widoczności — sprawdź w panelu")
    if zalaczniki:
        return False, (f"na sprawie są załączniki ({zalaczniki}), ale żaden wpis nie wskazuje "
                       f"{external_id}")
    return False, f"na sprawie nie ma wpisu wskazującego {external_id}"
