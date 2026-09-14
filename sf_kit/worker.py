"""Pętla workera: weź zadanie → wykonaj → zdaj sprawozdanie → zamknij.

v0.1 (14.09.2026) - APro Agents / borys-sf

CZTERY ZASADY, KTÓRE RZĄDZĄ TYM PLIKIEM
═══════════════════════════════════════
1. **Nie zgaduj kontekstu.** Zadanie bez treści albo bez katalogu roboczego jest ODRZUCANE
   z wpisem, a nie wykonywane „mniej więcej". Zgadnięty kontekst to praca na cudzych plikach.
2. **Nie kończ zadania, którego nie zrobiłeś.** `completed` znaczy „zrobione". Niepowodzenie
   wraca na `queued` z wpisem mówiącym, na czym stanęło — bo zadanie oznaczone jako zrobione
   znika ludziom z widoku, a niedokończone ma wrócić do człowieka.
3. **Sprawozdanie przed zamknięciem.** Najpierw wpis, potem zmiana statusu. Odwrotna kolejność
   przy padzie sieci zostawia zadanie zamknięte bez śladu, co zrobiono — czyli dokładnie to,
   przed czym cały ten kanał ma bronić.
4. **Jedno zadanie na przebieg pętli.** Nie bierzemy pięciu naraz: agent, który przyjął pięć
   zadań i padł, zostawia pięć zadań w `in_progress`, których nikt nie tknął.

CZEGO TU NIE MA
Ponawiania nieudanego zadania. Zadanie wraca do kolejki i następny przebieg je zobaczy — ale
worker NIE liczy prób i nie odpuszcza po trzeciej. To jest świadome uproszczenie v0.1 i jego
cena jest znana: zadanie, które wywraca się zawsze, będzie brane w kółko. Widać to w wpisach
(każda próba zostawia ślad), więc człowiek to zauważy. Licznik prób wymaga miejsca na stan,
a stan po stronie Kitu to pierwsza rzecz, która rozjeżdża się z SF.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from .api import BladAPI, BrakUprawnienia, Klient, ZlyKlucz
from .config import Konfiguracja
from . import ramka
from .wykonawcy import katalog_zadania, wybierz

#: Ile znaków wyjścia wykonawcy wchodzi do wpisu. Reszta jest obcinana z jawną adnotacją —
#: wpis ma być do przeczytania przez człowieka, a nie zrzutem konsoli.
LIMIT_WYJSCIA = 4000


def _teraz() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def _log(tekst: str) -> None:
    print(f"[{_teraz()}] {tekst}", flush=True)


def _skroc(tekst: str) -> str:
    if len(tekst) <= LIMIT_WYJSCIA:
        return tekst
    return (tekst[:LIMIT_WYJSCIA]
            + f"\n\n[…obcięte — całość miała {len(tekst)} znaków]")


#: Nagłówki, po których poznajemy, że wykonawca oddał sprawozdanie w umówionym układzie.
#: Wystarczy pierwszy — modele bywają kreatywne w interpunkcji, a nie o interpunkcję tu chodzi.
NAGLOWKI_SPRAWOZDANIA = ("**Sedno**", "**Co zrobiono**")


def czy_sprawozdanie(wyjscie: str) -> bool:
    """Czy wykonawca oddał sprawozdanie po ludzku, czy surowy dziennik pracy.

    Rozstrzyga o tym, czy wpis na sprawie idzie TAK, JAK JEST, czy trzeba go opakować.
    Sprawdzamy oba nagłówki, nie jeden: „**Sedno**" samo w sobie bywa cytatem z promptu,
    który model przepisał, nie pisząc sprawozdania.
    """
    tekst = wyjscie or ""
    return all(naglowek in tekst for naglowek in NAGLOWKI_SPRAWOZDANIA)


def wpis_sukces(zadanie: dict, wyjscie: str, *, wykonawca: str) -> str:
    """Sprawozdanie z wykonanego zadania.

    DWIE DROGI, I TO JEST SEDNO ZMIANY 0.2
    ══════════════════════════════════════
    Jeśli wykonawca oddał sprawozdanie w umówionym układzie (o który prosi go ramka promptu),
    **wpis to sprawozdanie** — bez naszej obwódki, bez bloku kodu, bez zdania „poniżej wyjście
    wykonawcy, bez zmian". Bo wpis na sprawie czyta CZŁOWIEK i ma się z niego dowiedzieć, co
    zostało zrobione, a nie oglądać dziennik pracy maszyny.

    Jeśli nie oddał — opakowujemy, żeby wpis w ogóle miał jakiś kształt. Ale wtedy mówimy
    wprost, że układu zabrakło, zamiast udawać sprawozdanie. Zdanie „poniżej wyjście wykonawcy,
    bez zmian" znikło stąd dlatego, że przy sprawozdaniu było nieprawdą, a przy jego braku —
    usprawiedliwieniem.
    """
    if czy_sprawozdanie(wyjscie):
        stopka = (f"\n\n---\n*Zadanie `{zadanie.get('external_id', zadanie.get('id'))}` "
                  f"wykonane przez agenta (`{wykonawca}`).*")
        return _skroc(wyjscie.strip()) + stopka

    return (
        f"**Sedno** — zadanie „{zadanie.get('title', '?')}” wykonane.\n\n"
        f"**Co zrobiono** — zadanie odebrane z kolejki i wykonane przez `{wykonawca}`. "
        f"Wykonawca nie oddał sprawozdania w umówionym układzie, więc poniżej jest to, "
        f"co wypisał.\n\n"
        f"**Szczegóły techniczne**\n\n"
        f"Zadanie: `{zadanie.get('external_id', zadanie.get('id'))}`\n\n"
        f"```\n{_skroc(wyjscie)}\n```"
    )


def wpis_niepowodzenie(zadanie: dict, powod: str, *, wykonawca: str) -> str:
    """Sprawozdanie z zadania, które się nie udało. Zadanie WRACA do kolejki."""
    return (
        f"**Sedno** — utknąłem na zadaniu „{zadanie.get('title', '?')}”. "
        f"Zadanie wraca do kolejki, NIE jest zrobione.\n\n"
        f"**Co się stało** — {powod}\n\n"
        f"**Szczegóły techniczne**\n\n"
        f"Zadanie: `{zadanie.get('external_id', zadanie.get('id'))}`, wykonawca: `{wykonawca}`."
    )


def wpis_odrzucenie(zadanie: dict, powod: str) -> str:
    """Zadanie, którego NIE DA SIĘ wykonać bez zgadywania. Nie ruszamy go wcale."""
    return (
        f"**Sedno** — nie mam czego wykonać w zadaniu „{zadanie.get('title', '?')}”, "
        f"więc go nie ruszam.\n\n"
        f"**Czego brakuje** — {powod}\n\n"
        f"**Szczegóły techniczne**\n\n"
        f"Zadanie: `{zadanie.get('external_id', zadanie.get('id'))}`. Zostaje w kolejce "
        f"ze statusem `queued` — uzupełnij je i zostanie wzięte przy następnym przebiegu.\n\n"
        f"Nie zgaduję kontekstu świadomie: praca wykonana „mniej więcej” trafiłaby na pliki, "
        f"których nikt mi nie wskazał."
    )


def _zdaj_sprawozdanie(klient: Klient, zadanie: dict, tresc: str) -> bool:
    """Wpis na sprawie. `False` = nie udało się (i wtedy NIE zamykamy zadania).

    Zadanie bez sprawy nie ma gdzie dostać sprawozdania. Mówimy o tym w logu i traktujemy jak
    niepowodzenie wpisu — bo zamknięcie zadania, o którym nigdzie nie ma śladu, jest gorsze
    niż zadanie niezamknięte.
    """
    ticket_id = zadanie.get("ticket_id")
    if not ticket_id:
        _log("   zadanie nie ma przypiętej sprawy — nie mam gdzie zdać sprawozdania")
        return False
    try:
        klient.wpis(str(ticket_id), tresc)
        return True
    except BladAPI as blad:
        _log(f"   nie udało się zapisać wpisu: {blad}")
        return False


def obsluz_zadanie(klient: Klient, konf: Konfiguracja, zadanie: dict) -> str:
    """Jedno zadanie od początku do końca. Zwraca krótki opis wyniku (do logu)."""
    tytul = zadanie.get("title", "?")
    zid = str(zadanie.get("id"))
    _log(f"→ {zadanie.get('external_id')}: {tytul}")

    # 1. Czy jest co wykonywać. PRZED przyjęciem zadania — przyjęte i odrzucone zadanie
    #    zostawiałoby ślad „ktoś to wziął i oddał", którego nikt nie prosił.
    tresc = (zadanie.get("body_md") or "").strip()
    if not tresc:
        _zdaj_sprawozdanie(klient, zadanie,
                           wpis_odrzucenie(zadanie, "zadanie ma pustą treść (`body_md`)"))
        return "odrzucone: pusta treść"

    katalog, powod = katalog_zadania(zadanie, domyslny=konf.katalog_roboczy)
    if powod:
        _zdaj_sprawozdanie(klient, zadanie, wpis_odrzucenie(zadanie, powod))
        return f"odrzucone: {powod}"

    wykonawca = wybierz(konf.runtime)
    dostepny, czemu = wykonawca.dostepny()
    if not dostepny:
        # To NIE jest wina zadania — nie piszemy wpisu o odrzuceniu, bo zadanie jest w porządku.
        # Worker ma stanąć i powiedzieć człowiekowi, że jest źle skonfigurowany.
        raise SystemExit(f"Wykonawca „{konf.runtime}” nie jest gotowy: {czemu}")

    # 2. Przyjmij zadanie. Tu najczęściej pada 403 — i to jest moment, w którym worker ma
    #    powiedzieć wprost, czego brakuje, zamiast kręcić się w pętli.
    try:
        klient.ustaw_status(zid, "in_progress", wersja=zadanie.get("version"))
    except BrakUprawnienia as blad:
        raise SystemExit(
            f"Nie mogę przyjąć zadania: {blad}\n\n"
            f"Worker zatrzymuje się celowo — bez tego uprawnienia wykonałby pracę, której "
            f"nie da się zamknąć, a zadanie wyglądałoby na nietknięte.") from None
    except BladAPI as blad:
        _log(f"   nie udało się przyjąć zadania: {blad}")
        return f"pominięte: {blad}"

    # 3. Wykonaj. Wykonawca dostaje treść zadania W RAMCE — kim jest, gdzie pracuje, czego
    #    nie wolno i co ma oddać na końcu. Samo `body_md` było pisane przez człowieka do
    #    człowieka i nie mówi modelowi żadnej z tych rzeczy.
    _log(f"   wykonuję przez `{wykonawca.nazwa}` w {katalog} (limit {konf.limit_zadania_s} s)")
    polecenie = (ramka.zbuduj(zadanie, slug=konf.slug, katalog=katalog)
                 if wykonawca.chce_ramke else tresc)
    wynik = wykonawca.wykonaj(polecenie, katalog=katalog, limit_s=konf.limit_zadania_s)

    # 4. Sprawozdanie PRZED zmianą statusu — patrz zasada 3 w nagłówku.
    if not wynik.udalo_sie:
        _zdaj_sprawozdanie(klient, zadanie,
                           wpis_niepowodzenie(zadanie, wynik.powod_niepowodzenia,
                                              wykonawca=wykonawca.nazwa))
        _wroc_do_kolejki(klient, zid)
        return f"niepowodzenie: {wynik.powod_niepowodzenia[:120]}"

    zapisano = _zdaj_sprawozdanie(
        klient, zadanie, wpis_sukces(zadanie, wynik.wyjscie, wykonawca=wykonawca.nazwa))
    if not zapisano:
        # Praca wykonana, sprawozdania nie ma. NIE zamykamy: zadanie zamknięte bez śladu
        # wygląda jak zrobione i nikt nie wie, co się stało.
        _wroc_do_kolejki(klient, zid)
        return "wykonane, ale bez sprawozdania — zadanie wróciło do kolejki"

    # 5. Zamknij.
    try:
        klient.ustaw_status(zid, "completed")
    except BladAPI as blad:
        _log(f"   praca zrobiona i opisana, ale nie mogę zamknąć zadania: {blad}")
        return "wykonane, niezamknięte"
    return "zrobione"


def _wroc_do_kolejki(klient: Klient, zid: str) -> None:
    """Odłóż zadanie z powrotem. Błąd tutaj tylko logujemy — praca i tak jest opisana."""
    try:
        klient.ustaw_status(zid, "queued")
    except BladAPI as blad:
        _log(f"   nie udało się oddać zadania do kolejki: {blad}")


def przebieg(klient: Klient, konf: Konfiguracja) -> int:
    """Jeden przebieg: weź NAJWYŻEJ JEDNO zadanie.

    Zwraca liczbę obsłużonych zadań (0 albo 1) albo **-1**, gdy nie udało się nawet pobrać
    kolejki. Trzecia wartość jest tu po to, żeby `--once` mógł zakończyć się kodem błędu:
    „nie miałem co robić" i „nie dodzwoniłem się do SF" to dwie różne rzeczy, a proces, który
    na obie odpowiada zerem, nie nadaje się do niczyjego nadzoru (cron, launchd, systemd).
    """
    try:
        # Jedno zadanie na przebieg, więc szukamy do pierwszego trafienia — przy kolejce
        # liczonej w setkach zwykle kończy się to na jednej stronie.
        wynik = klient.moje_zadania(slug=konf.slug, ile_najwyzej=1)
    except ZlyKlucz as blad:
        raise SystemExit(f"Klucz przestał działać: {blad}") from None
    except BladAPI as blad:
        _log(f"nie mogę pobrać zadań: {blad}")
        return -1

    if not wynik:
        if wynik.urwane:
            # Cisza z powodu bezpiecznika wygląda jak cisza z powodu braku pracy. Mówimy
            # o tym wprost, bo to jedyny moment, w którym da się to zauważyć.
            _log(f"brak moich zadań w przejrzanych {wynik.przejrzano} z {wynik.wszystkich} "
                 f"pozycji kolejki — przeglądanie urwał bezpiecznik stron")
        return 0
    _log(f"   wynik: {obsluz_zadanie(klient, konf, wynik.zadania[0])}")
    return 1


#: Ile najwyżej czekamy między próbami, gdy SalesForge nie odpowiada. Kwadrans: dłuższe
#: milczenie i tak wymaga człowieka, a krótsze nie odciąża serwera, który właśnie ma awarię.
MAX_ODSTEP_AWARII_S = 900


def odstep_po_awarii(odstep_bazowy: int, nieudanych: int) -> int:
    """Ile czekać po `nieudanych` nieudanych próbach pobrania kolejki.

    PO CO WYCOFYWANIE
    ═════════════════
    Bez niego worker pyta co minutę niezależnie od tego, czy serwer ma chwilową czkawkę, czy
    leży od trzech godzin. Przy kilku agentach na jednej instalacji daje to stały ostrzał
    maszyny, która właśnie ma awarię — czyli dokładnie wtedy, gdy najmniej go potrzebuje.
    README mówił o zwiększaniu odstępu (30 s, 60 s, 120 s) jako o instrukcji dla człowieka
    wołającego API ręcznie; worker sam tego nie robił.

    Podwajanie od odstępu bazowego, z sufitem. `nieudanych=0` (czyli po udanej próbie) wraca
    do odstępu bazowego natychmiast — awaria, która minęła, nie ma prawa spowalniać pracy
    przez następne pół godziny.
    """
    if nieudanych <= 0:
        return odstep_bazowy
    # Wykładniczo, ale bez wchodzenia w astronomiczne liczby przy długiej awarii: sufit
    # obcina to zanim `2 ** nieudanych` zacznie cokolwiek znaczyć.
    return min(odstep_bazowy * (2 ** min(nieudanych, 10)), MAX_ODSTEP_AWARII_S)


def uruchom(klient: Klient, konf: Konfiguracja, *, raz: bool = False) -> int:
    """Pętla workera. `raz=True` robi jeden przebieg i kończy."""
    _log(f"worker startuje: agent „{konf.slug}”, wykonawca `{konf.runtime}`, "
         f"odstęp {konf.odstep_s} s, {konf.adres}")
    if raz:
        return 0 if przebieg(klient, konf) >= 0 else 1

    nieudanych = 0
    while True:
        wynik = przebieg(klient, konf)
        if wynik < 0:
            nieudanych += 1
            odstep = odstep_po_awarii(konf.odstep_s, nieudanych)
            # Mówimy o tym w dzienniku, bo worker, który nagle pyta co kwadrans zamiast co
            # minutę, wygląda z zewnątrz na zepsuty. Tu widać, że to decyzja, nie usterka.
            _log(f"   nie mogę pobrać kolejki ({nieudanych}. raz z rzędu) — "
                 f"następna próba za {odstep} s")
        else:
            if nieudanych:
                _log(f"   połączenie wróciło po {nieudanych} nieudanych próbach — "
                     f"odstęp z powrotem {konf.odstep_s} s")
            nieudanych = 0
            odstep = konf.odstep_s
        time.sleep(odstep)
