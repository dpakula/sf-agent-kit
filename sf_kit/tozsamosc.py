"""Kim jestem i w której Organizacji pracuję (SF Agent Kit v0.4, ADVERTPR-777).

v0.4 (15.09.2026) - APro Agents / borys-sf

PO CO TEN MODUŁ ISTNIEJE
Do v0.3 `init` kazał wpisać identyfikator Organizacji. Damian (15.09): *„nie najlepsze, żeby
kodować Organizację w init"* — i miał rację z dwóch niezależnych powodów. Po pierwsze, agent
dostaje klucz, a nie UUID; żeby wpisać Organizację, musiał ją skądś przepisać, zwykle z cudzej
wiadomości. Po drugie, jeden agent bywa członkiem kilku Organizacji i wtedy „ta jedna wpisana
w plik" jest wyborem zrobionym raz, na zawsze i po cichu.

Od 15.09 SF ma `GET /me` (ADVERTPR-796), które **działa bez nagłówka Organizacji**. Kit może
więc zapytać „kim jestem", zanim cokolwiek o Organizacjach wie.

ZASADA, KTÓRA RZĄDZI CAŁYM TYM PLIKIEM: NIGDY „PIERWSZA Z BRZEGU"
Organizacja domyślna jest **wygodą**, nie domyślnym zachowaniem przy wątpliwości. Gdy nie da
się jej wskazać jednoznacznie, Kit ODMAWIA i pokazuje listę — bo koszt pomyłki jest
asymetryczny: wpis Michała, który wyląduje w cudzej Organizacji, jest wyciekiem do klienta,
a nie niedogodnością. Cofnąć się go nie da.

    --org podane            → ta Organizacja (gdy nie ma jej na liście → odmowa z listą)
    Organizacja w pliku     → ta (migracja z 0.3: to, co było wpisane, jest domyślne)
    dokładnie jedna z nadaniami → ta, i mówimy o tym wprost
    kilka albo zero         → ODMOWA z listą i podpowiedzią `--org`

Osobno i twardo: **Organizacja z ZEREM nadań to odmowa**, nawet gdy jest jedyna i nawet gdy
stoi w pliku. Praca w niej i tak skończyłaby się odmową serwera — tyle że w połowie, po
założeniu części rzeczy.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: Uprawnienia, które wystarczają, żeby uznać Organizację za „moją" do pracy. Pusta lista
#: uprawnień znaczy „jestem członkiem, ale nic mi tu nie wolno" — i to jest stan do odmowy,
#: nie do pracy.
#:
#: Świadomie NIE sprawdzamy konkretnych nazw uprawnień: ich słownik żyje po stronie SF i będzie
#: rósł. Kit pyta „czy cokolwiek mi tu wolno", a o tym, czy wolno KONKRETNIE to polecenie,
#: rozstrzyga i tak serwer. Zawężanie tego warunku tutaj znaczyłoby drugą listę uprawnień
#: w drugim repozytorium — i pierwszą rzecz, która rozjedzie się po zmianie po tamtej stronie.
MINIMUM_NADAN = 1


class BrakWyboru(RuntimeError):
    """Nie da się jednoznacznie wskazać Organizacji. Komunikat jest gotowy do pokazania."""


@dataclass
class Organizacja:
    uuid: str
    slug: str
    nazwa: str
    rola: str | None = None
    kind: str | None = None
    agent_slug: str | None = None
    uprawnienia: list[str] = field(default_factory=list)

    @property
    def ma_nadania(self) -> bool:
        return len(self.uprawnienia) >= MINIMUM_NADAN

    def pasuje(self, wskazanie: str) -> bool:
        """Czy `--org` wskazuje tę Organizację. Po slugu ALBO po uuid, bez rozróżniania wielkości."""
        w = (wskazanie or "").strip().lower()
        return bool(w) and w in {self.slug.lower(), self.uuid.lower()}

    def opis(self) -> str:
        ile = len(self.uprawnienia)
        prawa = "bez nadań" if not ile else f"{ile} nadań"
        return f"{self.slug:<20} {self.nazwa:<28} ({prawa})"


@dataclass
class Tozsamosc:
    """Odpowiedź `GET /me` w kształcie, którego używa Kit."""
    konto_nazwa: str | None
    konto_kind: str | None
    klucz_prefiks: str | None
    klucz_scope: str | None
    klucz_zawezony: bool
    organizacje: list[Organizacja]
    #: Termin ważności klucza. `None` znaczy BRAK TERMINU (klucz bezterminowy), a nie „nie wiem"
    #: — to rozróżnienie jest po stronie SF i Kit nie ma go rozmywać.
    klucz_wygasa: str | None = None

    @property
    def z_nadaniami(self) -> list[Organizacja]:
        return [o for o in self.organizacje if o.ma_nadania]

    def znajdz(self, wskazanie: str) -> Organizacja | None:
        for o in self.organizacje:
            if o.pasuje(wskazanie):
                return o
        return None


def z_odpowiedzi(dane: dict) -> Tozsamosc:
    """Przetłumacz `GET /me` na `Tozsamosc`. Nieznane pola pomijamy — kontrakt może urosnąć."""
    konto = dane.get("konto") or {}
    klucz = dane.get("klucz") or {}
    return Tozsamosc(
        konto_nazwa=konto.get("nazwa") or konto.get("email"),
        konto_kind=konto.get("kind"),
        klucz_prefiks=klucz.get("prefiks"),
        klucz_scope=klucz.get("scope"),
        klucz_zawezony=bool(klucz.get("zawezony")),
        klucz_wygasa=klucz.get("wygasa"),
        organizacje=[
            Organizacja(
                uuid=str(o.get("tenant_uuid") or ""),
                slug=o.get("slug") or "",
                nazwa=o.get("nazwa") or "",
                rola=o.get("rola"),
                kind=o.get("kind"),
                agent_slug=o.get("agent_slug"),
                uprawnienia=list(o.get("uprawnienia_efektywne") or []),
            )
            for o in (dane.get("organizacje") or [])
        ],
    )


def lista_do_pokazania(organizacje: list[Organizacja]) -> str:
    """Lista Organizacji dla człowieka przy terminalu — z nadaniami na wierzchu."""
    if not organizacje:
        return "  (żadnej)"
    posortowane = sorted(organizacje, key=lambda o: (not o.ma_nadania, o.slug))
    return "\n".join(f"  {o.opis()}" for o in posortowane)


def wybierz(toz: Tozsamosc, *, wskazana: str = "", z_pliku: str = "") -> Organizacja:
    """Która Organizacja obowiązuje. Rzuca `BrakWyboru` z gotowym komunikatem.

    Kolejność jest ważniejsza niż sam wybór — patrz nagłówek modułu. `--org` bije plik, plik
    bije zgadywanie, a zgadywanie jest dozwolone TYLKO wtedy, gdy nie ma czego zgadywać
    (dokładnie jedna Organizacja z nadaniami).
    """
    if wskazana:
        org = toz.znajdz(wskazana)
        if org is None:
            raise BrakWyboru(
                f"Nie jesteś członkiem Organizacji „{wskazana}” albo taka nie istnieje.\n"
                f"Twoje Organizacje:\n{lista_do_pokazania(toz.organizacje)}"
            )
        return _sprawdz_nadania(toz, org, skad="--org")

    if z_pliku:
        org = toz.znajdz(z_pliku)
        if org is None:
            # Konfiguracja wskazuje Organizację, do której agent już nie należy. To jest stan
            # do NAZWANIA, nie do cichego przejścia na inną: ktoś odebrał członkostwo i praca
            # ma się zatrzymać, a nie przenieść gdzie indziej.
            raise BrakWyboru(
                f"W ustawieniach masz Organizację „{z_pliku}”, ale nie ma jej na Twojej liście "
                f"w SF — członkostwo mogło zostać odebrane.\nTwoje Organizacje:\n"
                f"{lista_do_pokazania(toz.organizacje)}\n"
                f"Wskaż inną przez --org albo popraw ustawienia."
            )
        return _sprawdz_nadania(toz, org, skad="ustawień")

    kandydaci = toz.z_nadaniami
    if len(kandydaci) == 1:
        return kandydaci[0]

    if not kandydaci:
        raise BrakWyboru(
            "W żadnej ze swoich Organizacji nie masz jeszcze nadanych uprawnień — "
            "nie ma gdzie pracować.\n"
            f"Twoje Organizacje:\n{lista_do_pokazania(toz.organizacje)}\n"
            "Poproś administratora o nadania na członkostwie."
        )

    raise BrakWyboru(
        f"Masz uprawnienia w {len(kandydaci)} Organizacjach — wskaż, w której pracujesz.\n"
        f"Twoje Organizacje:\n{lista_do_pokazania(toz.organizacje)}\n"
        f"Dodaj --org <slug> do polecenia albo ustaw domyślną przez `sf-kit init`."
    )


def _sprawdz_nadania(toz: Tozsamosc, org: Organizacja, *, skad: str) -> Organizacja:
    """Organizacja bez nadań = odmowa, nawet gdy wskazana wprost.

    Puszczenie jej dalej znaczyłoby pracę, która kończy się odmową serwera W POŁOWIE — po
    założeniu sprawy, przed dołożeniem załącznika. Lepiej nie zacząć.
    """
    if org.ma_nadania:
        return org
    gdzie = toz.z_nadaniami
    podpowiedz = (
        f"Masz uprawnienia w:\n{lista_do_pokazania(gdzie)}\nDodaj --org <slug>."
        if gdzie else
        "W żadnej ze swoich Organizacji nie masz jeszcze nadań — poproś administratora."
    )
    raise BrakWyboru(
        f"W Organizacji „{org.slug}” (z {skad}) nie masz żadnych uprawnień.\n{podpowiedz}"
    )
