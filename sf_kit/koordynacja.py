"""Koordynator: status i rodzaj sprawy, rodzaj pracy, kroki rozgrywki, sweep kolejki, doręczenie zlecenia.

v0.1 (03.11.2026) - APro Agents / klaudiusz-general · SF-486 krok 3 (luki 4–6 z inwentarza cdd47b1e)

REGUŁA ROZWIĄZYWANIA SPRAWY (Agata 03.11, pkt 4 kickoffu kroku 3)
═════════════════════════════════════════════════════════════════
„Dziś 4 razy cofałam resolved ręcznie (612, SF-485, SF-486, SF-487), bo sprawa czekała na bramkę/front.”
Dlatego `sprawa --status resolved|closed` SPRAWDZA przed zmianą: otwarte zadania innych (queued/in_progress/
on_hold/pending) i tagi blokujące („czeka na wdrożenie / bramkę / klienta”). Którykolwiek = odmowa z powodem;
świadome obejście `--mimo-to`. Zamknięcie zadania (`odbierz`) sprawy nie rusza nigdy — mówi tylko, co z nią
dalej. Ta sama reguła siedzi w `scripts/sf/close-sf-task.sh` 1.4.0 (domknięcie przy /end-task).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import konsola
from .api import BladAPI, Klient

#: Typ taksonomii klasyfikujący pracę (decyzja Damiana 03.11: Rdzeń / Rozwojowe / Poboczne / Prywatne).
TYP_RODZAJU = "Rodzaj pracy"
#: Tagi, przy których sprawy nie rozwiązujemy (porównanie bez ogonków i wielkości liter).
TAGI_BLOKUJACE = ("czeka na wdrożenie", "czeka na bramkę", "czeka na klienta")
OTWARTE_ZADANIA = ("queued", "in_progress", "on_hold", "pending")
STATUSY_ZAMYKAJACE = ("resolved", "closed")
STATUSY_SPRAWY = ("new", "open", "in_progress", "waiting", "waiting_for_customer", "on_hold", "resolved", "closed")


def _czas(wartosc) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(wartosc).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def przeszkody_rozwiazania(klient: Klient, ticket_id: str, *, poza_zadaniem: str = "") -> list[str]:
    """Powody, dla których sprawy NIE należy rozwiązywać. Pusta lista = można. Błąd odczytu = powód."""
    powody: list[str] = []
    try:
        otwarte = [z for z in klient.zadania_sprawy(ticket_id)
                   if z.get("status") in OTWARTE_ZADANIA and str(z.get("id")) != poza_zadaniem]
    except BladAPI as blad:
        return [f"nie mogę odczytać zadań sprawy ({blad})"]
    if otwarte:
        kto = sorted({str(z.get("assigned_agent_slug") or z.get("assignee_name") or "?") for z in otwarte})
        powody.append(f"otwarte zadania: {len(otwarte)} ({', '.join(kto)})")
    try:
        nazwy = [str((g.get("tag") or {}).get("name") or g.get("name") or "") for g in klient.tagi_sprawy(ticket_id)]
    except BladAPI as blad:
        return powody + [f"nie mogę odczytać tagów sprawy ({blad})"]
    blok = {konsola._bez_ogonkow(t) for t in TAGI_BLOKUJACE}
    powody += [f"tag „{n}”" for n in nazwy if konsola._bez_ogonkow(n) in blok]
    return powody


def zmien_status(klient: Klient, sprawa: dict, status: str, *, mimo_to: bool = False) -> str:
    """Zmień status sprawy (idempotentnie). → opis wyniku. `ValueError` przy odmowie z powodem."""
    if status not in STATUSY_SPRAWY:
        raise ValueError(f"status sprawy: {', '.join(STATUSY_SPRAWY)}")
    obecny = sprawa.get("status")
    if obecny == status:
        return f"sprawa ma już status „{status}” — nic nie zmieniam"
    if status in STATUSY_ZAMYKAJACE and not mimo_to:
        powody = przeszkody_rozwiazania(klient, str(sprawa["id"]))
        if powody:
            raise ValueError(f"nie zmieniam na „{status}”: " + "; ".join(powody)
                             + " — świadomie: --mimo-to")
    klient.zmien_sprawe(str(sprawa["id"]), {"status": status})
    return f"status sprawy: {obecny or '?'} → {status}"


def nadaj_rodzaj(klient: Klient, ticket_id: str, rodzaj: str, *, zamien: bool = False) -> list[str]:
    """Tag typu „Rodzaj pracy” na sprawie. → co zrobiono."""
    tag, typ = konsola.znajdz_tag(konsola.typy_wszystkie(klient), rodzaj, typ=TYP_RODZAJU)
    return konsola.nadaj_tag(klient, ticket_id, tag, typ, zamien=zamien)


def wiek_w_dniach(tekst: str) -> float:
    """`14`, `14d`, `36h` → dni."""
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*([dh]?)\s*", tekst or "")
    if not m:
        raise ValueError(f"--stare „{tekst}”: podaj np. 14d albo 36h")
    ile = float(m.group(1).replace(",", "."))
    return ile / 24 if m.group(2) == "h" else ile


def stare(zadania: list[dict], dni: float, *, teraz: datetime | None = None) -> list[dict]:
    """Zadania bez ruchu dłużej niż `dni` (updated_at, a bez niego created_at)."""
    granica = (teraz or datetime.now(timezone.utc)) - timedelta(days=dni)
    out = []
    for z in zadania:
        t = _czas(z.get("updated_at") or z.get("created_at"))
        if t and t < granica:
            out.append(z)
    return sorted(out, key=lambda z: str(z.get("updated_at") or z.get("created_at") or ""))


def tresc_dostarczenia(zadanie: dict, sprawa: dict, *, baza: str, org_slug: str) -> str:
    """Wiadomość do sesji agenta po `zlec --dostarcz` — to, co dotąd wstrzykiwał kickoff.sh, tylko przez SF."""
    numer = f"{sprawa.get('ticket_prefix') or ''}-{sprawa.get('ticket_number') or ''}".strip("-")
    link = f"{baza.rstrip('/')}/tickets/{sprawa.get('id')}?org={org_slug}"
    return (f"Nowe zadanie {zadanie.get('external_id') or zadanie.get('id')}: {zadanie.get('title') or ''}\n"
            f"Sprawa {numer or sprawa.get('id')}: {link}\n"
            f"Odczytaj kontekst sprawy (`sf-kit sprawa {link}`), zanim zaczniesz; wynik zdaj wpisem na tej sprawie.")
