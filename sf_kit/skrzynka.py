"""Skrzynka wiadomości agenta — odbiór przez PULL (ADVERTPR-812, zakres D).

v0.1 (16.09.2026) - APro Agents / borys-sf

PO CO
═════
Agent dowiadywał się o rzeczach dotyczących jego pracy czterema półkanałami (mail, wiadomość
konsoli z guardem tmux, box, `tmux-say`) i żaden nie miał cyklu „wysłana → dostarczona →
odebrana → odpowiedziana". Trzy incydenty z jednej doby: 816 (sprawa z formularza bez maila
i bez konsoli), 801 (wpis Kodeksa do Agaty nieodebrany), SECO-176 (GO Damiana po 40 minutach).

Od 812 SF ma skrzynkę ze statusem PER ADRESAT. Kit robi z niej to, co robi z zadaniami:
**pobiera w swoim takcie i potwierdza odbiór**. Most tic zostaje budzikiem dla sesji, które
akurat nic nie robią — nie jedynym sposobem dowiedzenia się czegokolwiek.

DWIE RZECZY, KTÓRE TU PILNUJĘ
═════════════════════════════
1. **Potwierdzam odbiór DOPIERO gdy treść trafiła do agenta.** Potwierdzenie przy samym
   odczycie znaczyłoby „odebrane" dla wiadomości, która poszła w powietrze razem z procesem.
   Kolejność jest ta sama, co przy bramce floty: najpierw zapis/pokazanie, potem ack.
2. **Skrzynka nie ma prawa zatrzymać pracy.** Błąd odczytu, 503 przed rewizją, klucz bez
   właściciela — wszystko to znaczy „dziś bez skrzynki", a nie „nie pracuj". Zadanie wykona
   się tak jak przed 812.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .api import BladAPI, Klient

#: Statusy, w których wiadomość CZEKA na agenta. `replied` i `consumed` są już za nim.
STANY_DO_ODEBRANIA = ("new", "delivered", "failed")

#: Ile wiadomości bierzemy w jednym takcie. Nie „wszystkie": skrzynka z zaległościami po
#: tygodniowej przerwie potrafi mieć ich setki, a wstrzyknięcie setki treści do jednego prompta
#: nie jest przekazaniem informacji, tylko jej utopieniem. Reszta zostaje w SF i przyjdzie
#: w następnym takcie — dlatego skrzynka oddaje `razem`, żeby dało się powiedzieć „i 47 dalej".
LIMIT_TAKTU = 5


@dataclass
class Odebrane:
    """Co przyszło w tym takcie i co z tego wynikło."""

    #: Wiadomości przekazane agentowi (już potwierdzone).
    wiadomosci: list[dict] = field(default_factory=list)
    #: Ile jest w skrzynce RAZEM (cała skrzynka, nie ten takt).
    razem: int = 0
    #: Ile czeka dłużej niż próg zaległości — liczone przez SF, nie przez Kit.
    zalegle: int = 0
    #: Wiadomości, których nie udało się potwierdzić (przekazane, ale ack nie przeszedł).
    niepotwierdzone: list[str] = field(default_factory=list)
    #: Powód, dla którego skrzynki dziś nie ma. `None` = skrzynka działa.
    powod_braku: str | None = None

    @property
    def cos_jest(self) -> bool:
        return bool(self.wiadomosci)

    @property
    def ile_dalej(self) -> int:
        """Ile zostało w skrzynce po tym takcie. Zero = wzięliśmy wszystko."""
        return max(0, self.razem - len(self.wiadomosci))


def pobierz(klient: Klient, *, slug: str = "", limit: int = LIMIT_TAKTU,
           dni: int | None = None) -> Odebrane:
    """Nieodebrane wiadomości z MOJEJ skrzynki. Nie potwierdza — to osobny krok.

    Rozdzielenie pobrania od potwierdzenia jest celowe: między jednym a drugim treść musi
    trafić do agenta. Funkcja, która robiłaby oba naraz, potwierdzałaby odbiór rzeczy, której
    nikt jeszcze nie zobaczył.
    """
    try:
        dane = klient.skrzynka(session_target=slug, dni=dni, limit=limit,
                               tylko_nieodebrane=True)
    except BladAPI as blad:
        # 503 = tabela adresatów jeszcze nie istnieje (rewizja po stronie SF). 422 = klucz bez
        # właściciela albo konto bez sluga agenckiego. Oba są stanem konfiguracji, nie awarią
        # — i oba mają brzmieć jak stan, żeby nikt nie szukał usterki w Kicie.
        return Odebrane(powod_braku=str(blad))
    except Exception as blad:       # noqa: BLE001 — patrz punkt 2 w nagłówku pliku
        # DLACZEGO TAK SZEROKO, I DLACZEGO Z NAZWĄ WYJĄTKU W POWODZIE
        # ══════════════════════════════════════════════════════════
        # Skrzynka jest dodatkiem do pracy, nie jej warunkiem — obietnica z nagłówka tego pliku.
        # Pierwsza wersja łapała tylko `BladAPI` i `AttributeError` ze starszego klienta (bez
        # metody `skrzynka`) **zatrzymywał worker w połowie zadania**: 16 testów kitu zapaliło
        # się od razu, i dobrze, bo na produkcji byłby to worker, który przestał brać zadania
        # po podniesieniu samego SF.
        #
        # Ale fail-soft potrafi POŁKNĄĆ LITERÓWKĘ (`NameError` wygląda wtedy jak „nie ma
        # skrzynki"), więc nazwa wyjątku wchodzi do `powod_braku` — a wołający ją loguje.
        # Cisza byłaby tu gorsza niż przerwanie.
        return Odebrane(powod_braku=f"{type(blad).__name__}: {blad}")

    return Odebrane(
        wiadomosci=[w for w in (dane.get("wiadomosci") or [])
                    if w.get("status") in STANY_DO_ODEBRANIA],
        razem=int(dane.get("nieodebrane") or 0),
        zalegle=int(dane.get("zalegle") or 0),
    )


def potwierdz(klient: Klient, odebrane: Odebrane, *, status: str = "consumed") -> Odebrane:
    """Potwierdź odbiór wiadomości, które JUŻ trafiły do agenta.

    Potwierdzamy każdą osobno i porażkę pojedynczej zapisujemy, zamiast przerywać całość:
    wiadomość przekazana i niepotwierdzona wróci w następnym takcie (to zła rzecz, ale mała),
    a przerwanie pętli po pierwszym błędzie zostawiłoby nieodebrane wszystkie następne.
    """
    for w in odebrane.wiadomosci:
        mid = str(w.get("message_id") or "")
        if not mid:
            continue
        try:
            klient.potwierdz_odbior(mid, status=status)
        except Exception:       # noqa: BLE001 — jak wyżej: brak ack jest mały, brak pracy duży
            odebrane.niepotwierdzone.append(mid)
    return odebrane


def opis(odebrane: Odebrane) -> str:
    """Skrzynka jako tekst do wstrzyknięcia w prompt albo wypisania w terminalu.

    Treść wiadomości jest tu DOSŁOWNA — nagłówek kontekstu skleja SF (`console/naglowek.py`),
    żeby ta sama wiadomość wyglądała identycznie w tmuxie, w API i tutaj. Kit niczego nie
    dokleja do cudzej treści i niczego nie skraca.
    """
    if not odebrane.wiadomosci:
        return ""
    czesci = [f"── SKRZYNKA ({len(odebrane.wiadomosci)} nowych) ──"]
    for w in odebrane.wiadomosci:
        znacznik = (w.get("utworzono") or "")[:16].replace("T", " ")
        zalega = " [ZALEGA]" if w.get("zalega") else ""
        czesci.append(f"[{znacznik}] od {w.get('nadawca') or '?'}{zalega}\n{w.get('body') or ''}")
    if odebrane.ile_dalej:
        czesci.append(f"(i {odebrane.ile_dalej} dalej w skrzynce — przyjdą w następnym takcie)")
    return "\n\n".join(czesci)
