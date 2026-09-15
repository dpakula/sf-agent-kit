"""Reakcje człowieka w trakcie zadania — czytane z komentarzy (ADVERTPR-807 C1).

v0.1 (16.09.2026) - APro Agents / borys-sf

PO CO
═════
Zadanie było dotąd atomowe: worker brał je i oddawał wynik, a człowiek przez ten czas nie miał
jak nic powiedzieć. Przy zadaniu na dwadzieścia minut to niewygoda; przy zadaniu na dwie
godziny, które poszło w złą stronę, to dwie stracone godziny i sprzątanie po nich.

Kanał jest już w SF i nie wymaga tam żadnej zmiany: `GET /tasks/{id}` oddaje `comments`.
Worker zagląda tam **między krokami** — nie w trakcie wywołania modelu, bo przerwanie go
w połowie zostawiłoby katalog w stanie, którego nikt nie opisał.

TRZY SŁOWA, RESZTA TO SZUM — I TO JEST DECYZJA, NIE UPROSZCZENIE
`przerwij`, `doprecyzuj:`, `kontekst:`. Komentarze pod zadaniem pisze też koordynator do
człowieka i człowiek do siebie; gdyby worker próbował rozumieć wszystko, reagowałby na zdania,
które nie były do niego. Nierozpoznane **liczymy** i pokazujemy w telemetrii — cisza o nich
znaczyłaby, że człowiek pisze do workera i nie wie, że worker tego nie czyta.

DLACZEGO PROGI CZASU, A NIE „PRZECZYTANE"
Nie mamy gdzie zapisać „ten komentarz już widziałem" (SF nie ma takiego pola, a dokładanie go
to zmiana API, której zadanie zabrania). Bierzemy więc komentarze **nowsze niż moment startu
kroku** i to wystarcza: worker czyta je raz, między krokami, a każdy kolejny krok ma późniejszy
znacznik. Skutek uboczny: komentarz napisany PRZED wzięciem zadania nie jest reakcją na pracę,
tylko częścią zlecenia — i słusznie go pomijamy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

#: Słowo otwierające polecenie przerwania. Bez dwukropka, bo to całe zdanie samo w sobie.
SLOWO_PRZERWIJ = "przerwij"

#: Przedrostki dokładające treść do następnego kroku. Dwukropek jest wymagany — „doprecyzuj"
#: bez niego to zdanie o pracy, a nie treść do przekazania modelowi.
PRZEDROSTKI_UWAG = ("doprecyzuj:", "kontekst:")


@dataclass
class Reakcje:
    """Co człowiek powiedział od ostatniego zajrzenia."""

    #: Kto kazał przerwać (`author_name` albo `author_email`); `None` = nikt nie kazał.
    przerwal: str | None = None
    #: Treści z `doprecyzuj:` / `kontekst:`, w kolejności napisania.
    uwagi: list[str] = field(default_factory=list)
    #: Ile komentarzy worker zobaczył, ale ich nie rozpoznał.
    nierozpoznane: int = 0

    @property
    def cos_jest(self) -> bool:
        return bool(self.przerwal or self.uwagi or self.nierozpoznane)


def _czas(wartosc) -> datetime | None:
    """`created_at` bywa stringiem z API i `datetime` w testach. Oba mają działać."""
    if isinstance(wartosc, datetime):
        return wartosc if wartosc.tzinfo else wartosc.replace(tzinfo=timezone.utc)
    if isinstance(wartosc, str):
        try:
            czas = datetime.fromisoformat(wartosc.replace("Z", "+00:00"))
        except ValueError:
            return None
        return czas if czas.tzinfo else czas.replace(tzinfo=timezone.utc)
    return None


def _autor(komentarz: dict) -> str:
    return (komentarz.get("author_name") or komentarz.get("author_email") or "ktoś").strip()


def rozpoznaj(komentarze: list[dict], *, po: datetime, autor_wlasny: str | None = None) -> Reakcje:
    """Przejrzyj komentarze nowsze niż `po` i powiedz, co z nich wynika.

    `autor_wlasny` to e-mail workera: **własne komentarze pomijamy**, bo worker sam pisze pod
    zadaniem telemetrię („krok N z M"). Bez tego pierwszy komentarz telemetrii policzyłby się
    jako nierozpoznana wypowiedź człowieka i worker meldowałby, że ktoś do niego mówi — sam
    do siebie, w kółko.
    """
    reakcje = Reakcje()
    po = po if po.tzinfo else po.replace(tzinfo=timezone.utc)

    for komentarz in komentarze:
        czas = _czas(komentarz.get("created_at"))
        if czas is None or czas <= po:
            continue
        if autor_wlasny and (komentarz.get("author_email") or "").lower() == autor_wlasny.lower():
            continue

        tresc = (komentarz.get("content") or "").strip()
        male = tresc.lower()

        if male.startswith(SLOWO_PRZERWIJ):
            # Pierwsze „przerwij" wygrywa: kolejne nic nie zmieniają, a nadpisanie autora
            # gubiłoby to, KTO podjął decyzję — a właśnie to idzie potem do wpisu.
            if reakcje.przerwal is None:
                reakcje.przerwal = _autor(komentarz)
            continue

        for przedrostek in PRZEDROSTKI_UWAG:
            if male.startswith(przedrostek):
                uwaga = tresc[len(przedrostek):].strip()
                if uwaga:                      # „doprecyzuj:" bez treści nie jest uwagą
                    reakcje.uwagi.append(uwaga)
                else:
                    reakcje.nierozpoznane += 1
                break
        else:
            reakcje.nierozpoznane += 1

    return reakcje


def opis_uwag(uwagi: list[str]) -> str:
    """Uwagi doklejane do ramki następnego kroku."""
    if not uwagi:
        return ""
    punkty = "\n".join(f"- {u}" for u in uwagi)
    return ("\n\nUWAGI OD CZŁOWIEKA, DOPISANE JUŻ PO ZLECENIU ZADANIA — mają pierwszeństwo "
            f"przed treścią powyżej, jeśli się z nią kłócą:\n{punkty}")


def opis_do_wpisu(uwagi: list[str]) -> str:
    """To samo, ale do sprawozdania — żeby czytający wiedział, że zadanie zmieniło się w locie."""
    if not uwagi:
        return ""
    punkty = "\n".join(f"- {u}" for u in uwagi)
    return f"**Uwzględnione uwagi** (dopisane po zleceniu):\n{punkty}"


def wpis_przerwania(zadanie: dict, przerwal: str, *, stan: str) -> str:
    """Sprawozdanie z przerwania — musi powiedzieć KTO i W JAKIM STANIE zostawiamy pracę.

    „Przerwane" bez stanu jest gorsze od milczenia: następna osoba nie wie, czy zaczynać
    od zera, czy sprzątać po połowie. Katalog roboczy ZOSTAJE i mówimy o tym wprost.
    """
    return (
        f"**Przerwane na polecenie: {przerwal}.**\n\n"
        f"Stan w chwili przerwania: {stan}\n\n"
        f"Katalog roboczy zostaje nietknięty — nic z niego nie kasuję, żeby dało się zobaczyć,\n"
        f"co zdążyło powstać. Zadanie wraca do kolejki i może je wziąć ktokolwiek, łącznie ze mną."
    )
