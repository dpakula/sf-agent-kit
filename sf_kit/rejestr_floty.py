"""Migawka rejestru floty: `agents.json` → `PUT /api/v1/flota/rejestr` (SF-18).

v0.1 (24.09.2026) - APro Agents / borys-sf
Kontrakt po stronie SF: `docs/API-DASHBOARD-FLOTY-SF18.md` (trasa w `agents/router.py`,
model `WpisMigawki`: slug, nazwa, rodzaj, maszyna, katalog, aktywny).

PO CO
═════
Dashboard floty ma kolumnę „rodzaj silnika" i ostrzeżenie „rozjazd rejestru", a SF nie ma
z czego ich wypełnić: topologia floty mieszka WYŁĄCZNIE w rejestrze Agaty (`agents.json` na
macu, ten sam plik czyta tic). Kit zabiera stamtąd migawkę i oddaje ją SF. Polecenie jest
odpalane z maca (tic / worker-tick), dlatego ścieżka pliku jest PARAMETREM — na VPS pliku nie ma.

SKĄD SLUG — REGUŁA Z POMIARU, NIE Z NAZWY POLA
══════════════════════════════════════════════
`sf_agent_slug`, a gdy go brak — `id` wpisu. Sprawdzone 24.09 na kopii rejestru przeciw
`GET /agents` w advertpro-co i sf: tak wychodzą prawdziwe slugi (`kimi-mac`,
`kimi-autor-dpakula`, `kodeks-dpakula`, `borys-sf`). Pole `sf.agent_slug` NIE jest źródłem:
w pięciu wpisach ma tę samą wartość `codex-2-dpakula` (stare konto Kodeksa, skopiowane do
wpisów Kimi). Wzięcie go dałoby pięć wpisów z jednym slugiem, czyli migawkę, w której cztery
konta „znikają". Rozjazd między nim a slugiem pokazujemy jako OSTRZEŻENIE — to błąd rejestru,
który ma zobaczyć jego właścicielka, a nie coś, co Kit ma po cichu rozstrzygać.

CZEGO TEN MODUŁ NIE ROBI
Nie poprawia rejestru i nie wysyła niczego poza polami kontraktu: `instructions`, `notes`,
`launch_flags` i reszta zostają na macu. Migawka jest do porównania tożsamości, nie do kopii
konfiguracji — a treść notatek bywa wewnętrzna.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

#: Rodzaje silnika znane dashboardowi (kontrakt: `claude` / `codex` / `kimi`).
RODZAJE = ("claude", "codex", "kimi")

#: Po czym rozpoznajemy rodzinę Claude'a w polu `model` (alias rodziny, bez numeru — zob.
#: `_model_registry_note` w rejestrze).
_RODZINA_CLAUDE = ("claude", "opus", "sonnet", "haiku", "fable")

#: Nazwy maszyn, które nic nie mówią — wtedy bierzemy `location` z tego samego wpisu.
_BEZ_ZNACZENIA = {"", "localhost", "127.0.0.1"}

#: Sufit pola `zrodlo` po stronie SF (`max_length=120`).
_ZRODLO_MAX = 120


class ZlyRejestr(ValueError):
    """Plik nie jest rejestrem floty. Komunikat jest gotowy do pokazania."""


@dataclass
class Migawka:
    cialo: dict
    #: (id wpisu, slug, skąd slug) — do pokazania człowiekowi, NIE wysyłane.
    pochodzenie: list[tuple[str, str, str]] = field(default_factory=list)
    ostrzezenia: list[str] = field(default_factory=list)


def wczytaj(sciezka: str | Path) -> dict:
    """Rejestr z pliku albo `ZlyRejestr` z powodem."""
    plik = Path(sciezka).expanduser()
    try:
        dane = json.loads(plik.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ZlyRejestr(f"nie ma pliku {plik}. Rejestr floty leży na macu Agaty — "
                         f"polecenie odpala się tam albo z kopią pliku.") from None
    except json.JSONDecodeError as blad:
        raise ZlyRejestr(f"{plik} nie jest poprawnym JSON-em ({blad.msg}, "
                         f"linia {blad.lineno}).") from None
    if not isinstance(dane, dict) or not isinstance(dane.get("agents"), list):
        raise ZlyRejestr(f"{plik} nie wygląda na rejestr floty — brak listy `agents`.")
    return dane


def rodzaj_silnika(wpis: dict) -> str | None:
    """`claude` / `codex` / `kimi` albo `None`, gdy wpis nie mówi jednoznacznie.

    Z pól `model` i `runtime`, NIE z prefiksu sluga: `kimi-*` to konwencja nazewnicza,
    a dashboard ma pokazywać silnik, nie zgadywać go z nazwy (ta sama zasada co w SF).
    """
    tekst = f"{wpis.get('model') or ''} {wpis.get('runtime') or ''}".lower()
    trafione = {r for r in ("codex", "kimi") if r in tekst}
    if any(r in tekst for r in _RODZINA_CLAUDE):
        trafione.add("claude")
    return trafione.pop() if len(trafione) == 1 else None


def _maszyna(wpis: dict) -> str | None:
    host = (wpis.get("hostname") or "").strip()
    if host.lower() not in _BEZ_ZNACZENIA:
        return host
    return (wpis.get("location") or "").strip() or host or None


def _slug(wpis: dict) -> tuple[str, str]:
    """`(slug, skąd)`. Reguła i jej uzasadnienie — nagłówek modułu."""
    wlasny = (wpis.get("sf_agent_slug") or "").strip()
    if wlasny:
        return wlasny, "sf_agent_slug"
    return (wpis.get("id") or "").strip(), "id"


def zbuduj(dane: dict, *, teraz: datetime | None = None, nadawca: str = "") -> Migawka:
    """Ciało `PUT /flota/rejestr` z rejestru. CAŁA lista, także wycofani (`aktywny: false`).

    Wycofanych NIE pomijamy: kontrakt mówi „cała lista, nie różnica", a pominięcie znaczyłoby,
    że SF nie odróżni „wycofany" od „nigdy nie było". Flaga `aktywny` niesie tę różnicę.
    """
    teraz = teraz or datetime.now(timezone.utc)
    agenci: list[dict] = []
    pochodzenie: list[tuple[str, str, str]] = []
    ostrzezenia: list[str] = []
    widziane: dict[str, str] = {}

    for wpis in dane.get("agents") or []:
        if not isinstance(wpis, dict):
            ostrzezenia.append(f"pominięty wpis, który nie jest obiektem: {str(wpis)[:60]}")
            continue
        ident = (wpis.get("id") or "").strip() or "(bez id)"
        slug, skad = _slug(wpis)
        if not slug:
            ostrzezenia.append(f"{ident}: brak `sf_agent_slug` i `id` — wpis pominięty")
            continue
        if slug in widziane:
            # Dwa wpisy z jednym slugiem SF zlałby w jeden — i nie wiadomo, który wygrał.
            # Wysyłamy pierwszy, drugi nazywamy.
            ostrzezenia.append(f"{ident}: slug „{slug}” ma już wpis {widziane[slug]} — "
                               f"pominięty, popraw rejestr")
            continue
        widziane[slug] = ident

        stary = ((wpis.get("sf") or {}).get("agent_slug") or "").strip() \
            if isinstance(wpis.get("sf"), dict) else ""
        if stary and stary != slug:
            ostrzezenia.append(f"{ident}: `sf.agent_slug` = „{stary}”, a slug wpisu = „{slug}” "
                               f"— obiekt `sf` wygląda na skopiowany z innego wpisu")

        rodzaj = rodzaj_silnika(wpis)
        if rodzaj is None:
            ostrzezenia.append(f"{ident}: nie rozpoznaję silnika z "
                               f"model={wpis.get('model')!r}, runtime={wpis.get('runtime')!r}")

        agenci.append({
            "slug": slug,
            "nazwa": (wpis.get("name") or "").strip() or None,
            "rodzaj": rodzaj,
            "maszyna": _maszyna(wpis),
            "katalog": (wpis.get("agent_home") or wpis.get("claude_home") or None),
            "aktywny": (wpis.get("status") or "").strip().lower() != "retired",
        })
        pochodzenie.append((ident, slug, skad))

    wersja = dane.get("_version") or "?"
    zrodlo = f"agents.json v{wersja}" + (f" z {nadawca}" if nadawca else "")
    return Migawka(
        cialo={"agenci": agenci, "zrodlo": zrodlo[:_ZRODLO_MAX],
               "zebrano_o": teraz.isoformat()},
        pochodzenie=pochodzenie,
        ostrzezenia=ostrzezenia,
    )
