"""Nawyki koordynatorki w Kicie: treść inline, `blok nowy`, krok z rozgrywki, zamknięcie bloku z notką, błędy z kodem.

v0.1 (04.11.2026) - APro Agents / klaudiusz-general · SF-496 (Kit 0.19, pkt 1–5 i 11)

SKĄD TO SIĘ WZIĘŁO
══════════════════
04.11 Agata zrobiła ~140 operacji SF przez curl / sf_api.sh, a przez Kita 2. Komendy w większości BYŁY (0.18), ale
nie w kształcie, w jakim koordynatorka pisze: `blok nowy` zamiast `konsola blok`, `--tresc "tekst"` zamiast pliku,
krok z `tracking/rozgrywka.json` zamiast `--krok`, zamknięcie bloku z odpowiedzią jednym poleceniem. Ten moduł
trzyma te tłumaczenia w jednym miejscu, żeby `cli.py` tylko je wpinał.

KODY WYJŚCIA (pkt 11, wszystkie komendy z tej paczki)
═════════════════════════════════════════════════════
0 = zrobione · 1 = SF odmówił / częściowo (np. sprawa jest, załącznik nie) · 2 = złe wejście (brak pliku, pusta treść,
sprzeczne flagi) — nic nie wysłane. Treść NIGDY nie wraca na stdout jako „sukces”; błąd idzie na stderr, a przy
`--json` dodatkowo `{"ok": false, "blad": …, "kod": …}` na stdout dla skryptów.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

#: Rozszerzenia, po których `--tresc X` uznajemy za ścieżkę (nie tekst), gdy pliku nie ma.
ROZSZERZENIA_TRESCI = (".md", ".txt", ".html", ".htm", ".json", ".csv", ".yml", ".yaml")
#: Priorytety skrótowe koordynatorki → priorytet sprawy SF.
PRIORYTETY_SPRAWY = {"low": "low", "med": "medium", "medium": "medium", "high": "high", "urgent": "urgent"}
#: Rodzaje sprawy (SF-361). SF przyjmuje dowolny napis 2–20 znaków; spoza listy — ostrzeżenie, nie odmowa.
RODZAJE_SPRAWY = ("case", "document", "message", "lead")


class ZleWejscie(ValueError):
    """Złe wejście użytkownika — kod wyjścia 2, nic nie wysłane."""


# ── treść: --opis PLIK|- i --tresc TEKST|PLIK|- ─────────────────────────────

def wyglada_na_sciezke(wartosc: str) -> bool:
    """Jedno „słowo” z `/` albo znanym rozszerzeniem = ktoś miał na myśli plik, nie tekst."""
    w = (wartosc or "").strip()
    if not w or any(z.isspace() for z in w):
        return False
    return "/" in w or w.startswith("~") or w.lower().endswith(ROZSZERZENIA_TRESCI)


def _plik(wartosc: str, rola: str) -> str:
    plik = Path(wartosc).expanduser()
    if not plik.is_file():
        raise ZleWejscie(f"nie ma pliku {rola}: {plik} — nic nie wysłałem (tekst wprost: --tresc \"…\")")
    return plik.read_text(encoding="utf-8")


def tresc(*, opis: str | None = None, tresc_arg: str | None = None, rola: str = "z treścią",
          stdin=None, wymagana: bool = False) -> str | None:
    """Treść z `--opis` (plik albo `-`) albo z `--tresc` (tekst wprost, plik albo `-`). None = nie podano.

    `--tresc` przyjmuje tekst (04.11: inline był cichą porażką), ale napis wyglądający na ścieżkę, której nie ma,
    to BŁĄD — inaczej literówka w nazwie pliku poszłaby na sprawę jako treść „raport.md”.
    Pusta treść: decyduje wołający (np. `odpowiedz --opcja` bez komentarza jest poprawna); `wymagana=True` = błąd.
    """
    if opis and tresc_arg:
        raise ZleWejscie("podaj --opis ALBO --tresc, nie oba")
    stdin = stdin or sys.stdin
    if opis:
        wynik = stdin.read() if opis == "-" else _plik(opis, rola)
    elif tresc_arg is not None:
        if tresc_arg == "-":
            wynik = stdin.read()
        elif Path(tresc_arg).expanduser().is_file():
            wynik = Path(tresc_arg).expanduser().read_text(encoding="utf-8")
        elif wyglada_na_sciezke(tresc_arg):
            raise ZleWejscie(f"--tresc „{tresc_arg}” wygląda na plik, a go nie ma — nic nie wysłałem")
        else:
            wynik = tresc_arg
    else:
        return None
    if wymagana and not wynik.strip():
        raise ZleWejscie("pusta treść — nic nie wysłałem")
    return wynik


# ── `blok nowy` → `konsola blok` ─────────────────────────────────────────────

GLOBALNE_Z_WARTOSCIA = ("--agent", "--org")


def przetlumacz_argv(argv: list[str]) -> list[str]:
    """`sf-kit [--org X] blok nowy …` → `sf-kit [--org X] konsola blok …` (Agata pisze tak od 04.11).

    `blok <id>` (SF-7, podgląd bloku osi) zostaje: identyfikator „nowy” nie istnieje, więc nie ma kolizji.
    """
    argv = list(argv)
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in GLOBALNE_Z_WARTOSCIA:
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        if a == "blok" and i + 1 < len(argv) and argv[i + 1] == "nowy":
            return argv[:i] + ["konsola", "blok"] + argv[i + 2:]
        return argv
    return argv


def krok_z_rozgrywki(sciezka: str | None = None) -> str | None:
    """Sprawa bieżącego kroku: `tracking/rozgrywka.json` → `ostatni_ticket_id` (to samo, co sf_box_sprawa floty).

    Ścieżka: argument → `SF_KIT_ROZGRYWKA` → `$HOME/tracking/rozgrywka.json`. Puste / „null” = brak (SF-473).
    """
    p = Path(sciezka or os.environ.get("SF_KIT_ROZGRYWKA") or Path.home() / "tracking" / "rozgrywka.json")
    try:
        wartosc = json.loads(p.read_text(encoding="utf-8")).get("ostatni_ticket_id")
    except (OSError, ValueError, AttributeError):
        return None
    wartosc = str(wartosc or "").strip()
    return None if wartosc.lower() in ("", "null", "none", "undefined") else wartosc


# ── sprawa ───────────────────────────────────────────────────────────────────

def priorytet_sprawy(wartosc: str | None) -> str:
    w = (wartosc or "medium").strip().lower()
    if w not in PRIORYTETY_SPRAWY:
        raise ZleWejscie(f"priorytet: {', '.join(PRIORYTETY_SPRAWY)}")
    return PRIORYTETY_SPRAWY[w]


def adresy(wartosci: list[str] | None) -> list[str]:
    """`--obserwujacy a,b c` → [a, b, c] (przecinki i spacje, bez dubli, kolejność zachowana)."""
    out: list[str] = []
    for w in wartosci or []:
        for a in re.split(r"[,\s]+", w):
            if a and a not in out:
                out.append(a)
    return out


# ── bloki: lista z kotwicą i wiekiem, zamknięcie z notką ─────────────────────

def _czas(wartosc) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(wartosc).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def wiek(wartosc, teraz: datetime | None = None) -> str:
    t = _czas(wartosc)
    if not t:
        return "?"
    s = max(0, int(((teraz or datetime.now(timezone.utc)) - t).total_seconds()))
    if s < 3600:
        return f"{s // 60} min"
    if s < 86400:
        return f"{s // 3600} h"
    return f"{s // 86400} d"


def wiersz_bloku(b: dict, teraz: datetime | None = None) -> str:
    """`#2364  action high  15min  3 h  [open]  kotwica 46aea40a  tytuł…` — to, czego Agata szukała curlem."""
    stan = b.get("status") or "?"
    if b.get("replied_at"):
        stan += ", odp." + ("" if b.get("reply_seen_at") else " NIEODEBRANA")
    kotwica = b.get("context_anchor") or {}
    k = str(kotwica.get("numer") or kotwica.get("id") or "—")[:8]
    tytul = b.get("tytul") or " ".join(str(b.get("body") or "").split())[:70]
    return (f"{b.get('numer') or '?':>6}  {b.get('kind') or '?':<6} {b.get('priority') or '':<4} "
            f"{b.get('effort_tag') or '—':<7} {wiek(b.get('created_at'), teraz):>6}  [{stan}]  kotwica {k}  {tytul}")


def notka_zamkniecia(numer: str, notka: str) -> str:
    return f"**Blok konsoli {numer} zamknięty** — {notka.strip()}"


def zamknij_blok(klient, blok: dict, *, status: str = "closed", notka: str | None = None,
                 org_kotwicy: str | None = None) -> list[str]:
    """PATCH status (+ `reply_seen`, gdy była odpowiedź), a notka → wpis wewnętrzny na sprawie kotwicy.

    `BoxPatch` (OpenAPI 04.11) nie ma pola na treść zamknięcia; zamiast obchodzić kontrakt, notka ląduje tam,
    gdzie człowiek i tak czyta (oś sprawy). Pole w bloku = prośba do borysa (SF-496).
    """
    zrobione: list[str] = []
    cialo: dict = {}
    if blok.get("status") != status:
        cialo["status"] = status
    if blok.get("replied_at") and not blok.get("reply_seen_at"):
        cialo["reply_seen"] = True
    if cialo:
        klient.zmien_blok(str(blok["id"]), cialo)
        zrobione.append(f"{blok.get('numer')}: {blok.get('status')} → {status}"
                        + (" (odpowiedź odebrana)" if cialo.get("reply_seen") else ""))
    else:
        zrobione.append(f"{blok.get('numer')}: już „{status}”")
    if notka:
        sprawa = str((blok.get("context_anchor") or {}).get("id") or "")
        if not sprawa:
            raise ValueError(f"{blok.get('numer')}: blok bez sprawy w kotwicy — notki nie mam gdzie zapisać")
        k = klient.w_organizacji(org_kotwicy) if org_kotwicy and org_kotwicy != klient.organizacja else klient
        k.wpis(sprawa, notka_zamkniecia(str(blok.get("numer")), notka), widocznosc="internal")
        zrobione.append(f"{blok.get('numer')}: notka na sprawie kotwicy {sprawa[:8]}")
    return zrobione


# ── błędy i --json (pkt 11) ──────────────────────────────────────────────────

def blad(args, tekst: str, kod: int = 1) -> int:
    """Czytelny błąd na stderr (+ JSON na stdout przy `--json`) → kod wyjścia ≠ 0."""
    print(f"Błąd: {tekst}", file=sys.stderr)
    if getattr(args, "json", False):
        print(json.dumps({"ok": False, "blad": tekst, "kod": kod}, ensure_ascii=False))
    return kod


def wynik_json(dane: dict) -> str:
    return json.dumps({"ok": True, **dane}, ensure_ascii=False, indent=2, default=str)
