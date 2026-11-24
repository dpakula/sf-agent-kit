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
#: Kategorie sprawy, które SF przyjmuje (enum `ticketcategory`; 422 „Dozwolone: bug, feature, feedback, other, question”).
KATEGORIE_SPRAWY = ("bug", "feature", "question", "feedback", "other")
#: Polskie nazwy, którymi ludzie i agenci podają kategorię (0.20.2, SF-486 pkt 3).
SYNONIMY_KATEGORII = {"blad": "bug", "błąd": "bug", "usterka": "bug", "funkcja": "feature", "nowa-funkcja": "feature",
                      "pytanie": "question", "uwaga": "feedback", "opinia": "feedback", "inne": "other", "inna": "other"}


TYP_KATEGORII = "ticket_category"


def kategorie_z_taksonomii(typy: list[dict]) -> dict[str, str]:
    """Kategorie TEJ Organizacji (typ systemowy `ticket_category`): {nazwa albo wartość małymi literami → wartość}."""
    mapa: dict[str, str] = {}
    for t in typy or []:
        if t.get("slug") != TYP_KATEGORII:
            continue
        for tag in t.get("tags") or []:
            wartosc = str(tag.get("value") or "").strip()
            if wartosc:
                mapa[wartosc.lower()] = wartosc
                if tag.get("name"):
                    mapa[str(tag["name"]).strip().lower()] = wartosc
    return mapa


def kategoria_sprawy(wartosc: str, dozwolone: dict[str, str] | None = None) -> str:
    """`Bug` → `bug`, `Pytanie` → `question` (SF-486 pkt 3). Nieznana = ZleWejscie z listą dozwolonych PRZED wysłaniem.

    Kategorie są taksonomią Organizacji (`ticket_category`); bez niej (stary SF, brak prawa) — pięć domyślnych."""
    mapa = dict(dozwolone or {}) or {k: k for k in KATEGORIE_SPRAWY}
    w = (wartosc or "").strip().lower()
    if w in mapa:
        return mapa[w]
    w = SYNONIMY_KATEGORII.get(w, w)
    if w in mapa:
        return mapa[w]
    lista = sorted(set(mapa.values()))
    raise ZleWejscie(f"„{wartosc}” nie jest tagiem tej Organizacji ani kategorią sprawy. Kategorie: "
                     f"{', '.join(lista)}; tagi: sf-kit tag lista — nic nie wysłałem")


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


#: Ile sekund czekać na PIERWSZE dane ze standardowego wejścia, gdy nie jest terminalem (0.20.2, SF-486 pkt 1).
ZMIENNA_CZEKAJ_STDIN = "SF_KIT_STDIN_CZEKAJ"
CZEKAJ_STDIN_S = 10.0


def wejscie_gotowe(stdin=None, czekaj_s: float | None = None) -> bool:
    """Czy czytanie ze stdin się skończy: terminal (człowiek pisze), dane/EOF w potoku albo atrapa bez deskryptora.

    0.20.2 (SF-486 pkt 1): agent uruchamia Kita z narzędzia, którego stdin jest OTWARTYM, pustym potokiem —
    `read()` czekał wtedy w nieskończoność („Kit wisi bez < /dev/null”). Bez terminala czekamy na pierwsze
    bajty (albo EOF) najwyżej `czekaj_s` sekund; potem wołający kończy kodem 2 zamiast wisieć.
    """
    stdin = stdin or sys.stdin
    if stdin is None:
        return False
    try:
        if stdin.isatty():
            return True
        fd = stdin.fileno()
    except (AttributeError, OSError, ValueError):
        return True                      # StringIO w testach, podmieniony strumień: read() nie zawiśnie
    if os.name == "nt":                  # select na Windows nie zna potoków — zostaje zachowanie jak dotąd
        return True
    if czekaj_s is None:
        try:
            czekaj_s = float(os.environ.get(ZMIENNA_CZEKAJ_STDIN) or CZEKAJ_STDIN_S)
        except ValueError:
            czekaj_s = CZEKAJ_STDIN_S
    import select
    try:
        gotowe, _, _ = select.select([fd], [], [], max(0.0, czekaj_s))
    except (OSError, ValueError):
        return True
    return bool(gotowe)


def czytaj_stdin(stdin=None, rola: str = "treść") -> str:
    """`-` = treść ze standardowego wejścia — bez wiszenia, gdy nikt jej nie podaje (SF-486 pkt 1)."""
    stdin = stdin or sys.stdin
    try:
        terminal = stdin.isatty()
    except (AttributeError, ValueError):
        terminal = False
    if terminal:
        print(f"Wpisz albo wklej {rola} i zakończ Ctrl-D (Windows: Ctrl-Z, Enter).", file=sys.stderr)
    elif not wejscie_gotowe(stdin):
        raise ZleWejscie(f"`-` = {rola} ze standardowego wejścia, a nic na nie nie przyszło — nic nie wysłałem. "
                         "Podaj treść potokiem (`… | sf-kit …` albo `<<'EOF'`), plikiem albo --tresc \"…\"")
    return stdin.read()


def _jest_plikiem(wartosc: str) -> bool:
    """`Path.is_file()` bez wyjątku: napis dłuższy niż limit nazwy (255 B, ENAMETOOLONG) albo z bajtem zerowym to
    na pewno nie plik, tylko tekst (SF-576: `wpis --tresc "<~400 znaków>"` kończył się tracebackiem OSError)."""
    try:
        return Path(wartosc).expanduser().is_file()
    except (OSError, ValueError):
        return False


def _plik(wartosc: str, rola: str) -> str:
    plik = Path(wartosc).expanduser()
    if not _jest_plikiem(wartosc):
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
        wynik = czytaj_stdin(stdin) if opis == "-" else _plik(opis, rola)
    elif tresc_arg is not None:
        if tresc_arg == "-":
            wynik = czytaj_stdin(stdin)
        elif _jest_plikiem(tresc_arg):
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
