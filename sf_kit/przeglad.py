"""Instrukcja dwupoziomowa Kita: krótki przegląd GENEROWANY Z PARSERA + szczegóły na żądanie (SF-486 pkt 18).

v1.0.0 (12.11.2026) - APro Agents / arek · Kit 0.20.2

PO CO
═════
AGENT.md ma ponad 2000 linii. Agent go nie doczyta, więc nie używał poleceń, które Kit miał
(dzień koordynatorki 12.11: zejścia do surowego API przy operacjach, które istniały). Decyzja
Damiana 12.11: poziom 1 to krótki przegląd (≤ 80 linii), który każdy agent ma w kontekście od
startu (`sf-kit start` wkleja go do CLAUDE.md / AGENTS.md). Poziom 2 to szczegóły na żądanie:
`sf-kit pomoc <polecenie|temat>`.

JEDNO ŹRÓDŁO
════════════
Lista poleceń NIE jest pisana ręcznie. Powstaje z `zbuduj_parser()`, czyli z tych samych
definicji, z których korzysta `--help`. Rola pochodzi ze znacznika `[rola]` na początku pomocy
polecenia. Test (`testy/test_wydanie_0202_sf486.py`) jest czerwony, gdy:
- polecenie nie ma opisu albo roli,
- przegląd przekracza `MAKS_LINII`,
- przykład w przeglądzie nie przechodzi parsera.
Nowe polecenie bez opisu nie przejdzie więc bramki wydania.
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

MAKS_LINII = 80

#: Role ze znaczników `[rola]` w pomocy poleceń → grupa przeglądu (kolejność = kolejność w przeglądzie).
GRUPY = (
    ("wszyscy", "Każdy: konto, Kit, ustawienia"),
    ("praca", "Praca na sprawie (asystent, agent, wykonawca)"),
    ("koordynator", "Koordynator"),
    ("worker", "Worker (demon zadań)"),
)
ROLA_NA_GRUPE = {"wszyscy": "wszyscy", "asystent": "praca", "agent": "praca", "wykonawca": "praca",
                 "koordynator": "koordynator", "worker": "worker"}
#: Polecenia techniczne — mają opis i rolę, ale nie trafiają do przeglądu (woła je instalator / klient MCP).
WEWNETRZNE = "wewnętrzne"
#: Które grupy widzi który profil (profil z konfiguracji agenta). Koordynator widzi wszystko.
GRUPY_PROFILU = {
    "asystent": ("wszyscy", "praca"),
    "worker": ("wszyscy", "praca", "worker"),
    "koordynator": ("wszyscy", "praca", "koordynator", "worker"),
}

#: Pokrewne polecenia w JEDNEJ linii przeglądu (limit 80 linii). Test sprawdza, że każda nazwa istnieje w parserze.
LACZONE = (
    (("tasks", "zadania"), "moje zadania (`tasks`) / wszystkie zadania sprawy ze statusem (`zadania <sprawa> --json`)"),
    (("plugin", "codex", "kimi", "gemini"), "pakiet Kita dla Claude Code / Codex / Kimi / Gemini: stan, --zainstaluj, --odswiez"),
    (("relacje", "przypnij", "odepnij"), "sprawa w sprawie: co sprawa zawiera i czego jest częścią; przypnij / odepnij relację"),
    (("kontrakt", "blok-przyznane", "blok-przyznaj", "blok-odbierz"),
     "co operacja administracyjna przyjmuje (`kontrakt <nazwa>`); superadmin: bloki stron Organizacji "
     "(`blok-przyznane|przyznaj|odbierz <rodzina/nazwa> --dla <slug>`, SF-517)"),
    (("krok", "tura"), "kroki rozgrywki (nowy, zamknij) i zamknięcie tury jednym poleceniem: stan, kickoffy, pomiar, "
                       "ślad decyzji, closed, dziennik, commit"),
)

ZASADY = (
    "**Organizacja zawsze jawna:** `--org <slug>` przed poleceniem albo link sprawy z `?org=…`. "
    "Domyślna Organizacja to wygoda, nie reguła.",
    "**Widoczność wpisu:** domyślnie `internal` (zespół). `--widocznosc external` widzi klient, "
    "więc używaj jej świadomie.",
    "**Kończysz zadanie, nie sprawę:** `zadanie <id> --status completed`, gdy wynik jest wpisem na sprawie. "
    "Sprawę rozwiązuje koordynator albo człowiek (`sprawa … --status resolved`). `wpis --do` to wiadomość, "
    "nie zlecenie (nie budzi sesji). Zlecenie: `zlec --dostarcz`.",
    "**Aktualizacja tylko przez `sf-kit update`**, potem `sf-kit start` w katalogu pracy (odświeża ten przegląd). "
    "Wersja: `sf-kit --version`.",
    "**Szczegóły:** `sf-kit pomoc <polecenie|temat>`, `sf-kit pomoc --tematy`. Nie wołaj API SF ręcznie: "
    "jeśli Kit czegoś nie umie, zgłoś to przez `sf-kit uwaga \"…\"` i powiedz człowiekowi.",
)

#: Najczęstsze operacje koordynatora (SF-486 pkt 16). Każdy przykład sprawdza test, przepuszczając go przez parser.
PRZYKLADY_KOORDYNATORA = (
    ("zleć zadanie agentowi i doręcz", "zlec --sprawa SF-486 --agent-slug arek-localhost --tytul \"…\" --tresc - --dostarcz"),
    ("co flota ma w toku / stare", "kolejka --stare 14d"),
    ("odbierz wynik / sprzątnij kolejkę", "odbierz <zadanie> | odbierz <id> <id> --hurt --notka \"…\""),
    ("blok decyzji dla człowieka", "konsola blok --rodzaj action --sprawa <link> --tresc \"…\" --opcja A=\"…\" --opcja B=\"…\" --rekomendowana A"),
    ("odpowiedzi człowieka", "konsola odpowiedzi | konsola odpowiedzi --odebrane '#2364' --notka \"zrobione\""),
    ("nowa sprawa jednym poleceniem", "nowa-sprawa --tytul \"…\" --tresc - --tag bug --przypisz a@b.pl --obserwujacy c@d.pl --json"),
    ("rozwiąż sprawę (sprawdza otwarte zadania)", "sprawa SF-486 --status resolved"),
    ("rodzaj pracy / tag", "tag nadaj SF-486 Rdzeń --typ \"Rodzaj pracy\" --zamien"),
    ("wersje Kita we flocie", "flota wersje"),
    ("krok rozgrywki", "krok nowy --tytul \"KROK V · Rozgrywka …\" --tresc - --obserwujacy a@b.pl"),
    ("zamknij turę (stan z „## Następny krok” i „## Decyzje”)", "--org sf tura zamknij --opis stan.md"),
)

_REF = re.compile(r"\s*\((?:[^()]*?(?:SF|ADVERTPR|FM|v?\d+\.\d+)[-\s]?\d*[^()]*)\)")


def _rola_i_opis(pomoc: str | None) -> tuple[str | None, str]:
    tekst = " ".join((pomoc or "").split())
    m = re.match(r"\[([^\]]+)\]\s*(.*)", tekst)
    if not m:
        return None, tekst
    return m.group(1).strip().lower(), m.group(2).strip()


def _bez_referencji(opis: str) -> str:
    """„karta sprawy (SF-38)” → „karta sprawy” — numery spraw są historią, nie instrukcją."""
    return _REF.sub("", opis).strip()


def _podparser(parser: argparse.ArgumentParser) -> argparse._SubParsersAction | None:
    for akcja in parser._actions:
        if isinstance(akcja, argparse._SubParsersAction):
            return akcja
    return None


def polecenia(parser: argparse.ArgumentParser) -> list[dict]:
    """Polecenia najwyższego poziomu: nazwa, aliasy, rola, opis, argumenty pozycyjne, podpolecenia."""
    sub = _podparser(parser)
    if sub is None:
        return []
    wynik: list[dict] = []
    po_funkcji: dict = {}
    for akcja in sub._choices_actions:
        nazwa = akcja.dest
        p = sub.choices[nazwa]
        rola, opis = _rola_i_opis(akcja.help)
        funkcja = p.get_default("funkcja")
        # Ta sama funkcja pod drugą nazwą (aktualizuj = update, zglos = nowa-sprawa) — jedna linia z aliasem.
        if funkcja is not None and funkcja in po_funkcji and nazwa not in ("flota",):
            po_funkcji[funkcja]["aliasy"].append(nazwa)
            continue
        poz = [a.metavar or a.dest for a in p._actions
               if not a.option_strings and not isinstance(a, argparse._SubParsersAction)
               and a.dest != "help" and a.help != argparse.SUPPRESS]
        podsub = _podparser(p)
        pod = list(podsub.choices) if podsub else []
        aliasy = [k for k, v in sub.choices.items() if v is p and k != nazwa]
        wpis = {"nazwa": nazwa, "aliasy": aliasy, "rola": rola, "opis": opis, "pozycyjne": poz, "pod": pod,
                "parser": p}
        wynik.append(wpis)
        if funkcja is not None:
            po_funkcji[funkcja] = wpis
    return wynik


def _linia(p: dict) -> str:
    if p.get("polaczone"):
        return f"- `{' | '.join([p['nazwa'], *p['polaczone']])}`: {p['opis']}"
    nazwa = "|".join([p["nazwa"], *p["aliasy"]])
    if p["pod"]:
        nazwa += " " + "|".join(p["pod"])
    arg = " ".join(f"<{a}>" if not str(a).startswith("<") else str(a) for a in p["pozycyjne"]
                   if a not in ("co",))
    opis = _bez_referencji(p["opis"])
    if len(opis) > 95:
        opis = opis[:94].rstrip(" ,;—") + "…"
    return f"- `{nazwa}{(' ' + arg) if arg else ''}`: {opis}"


def przeglad(parser: argparse.ArgumentParser, *, profil: str | None = None, wersja: str = "") -> str:
    """Poziom 1: role, polecenia po jednej linii, 5 zasad. Profil zawęża grupy (None = wszystkie)."""
    grupy = GRUPY_PROFILU.get(profil or "", tuple(g for g, _ in GRUPY))
    lista = [p for p in polecenia(parser) if p["rola"] != WEWNETRZNE]
    linie = [f"## SF Kit{(' ' + wersja) if wersja else ''}: przegląd (generowany z Kita, `sf-kit pomoc`)",
             "",
             "Wszystko w SalesForge robisz poleceniem `sf-kit [--org <slug>] <polecenie>`. "
             "Opcje polecenia: `sf-kit pomoc <polecenie>`.",
             "",
             "### Pięć zasad"]
    linie += [f"{i}. {z}" for i, z in enumerate(ZASADY, 1)]
    po_nazwie = {p["nazwa"]: p for p in lista}
    for nazwy, opis in LACZONE:
        pierwszy = po_nazwie.get(nazwy[0])
        if pierwszy is None:
            continue
        pierwszy.update(opis=opis, polaczone=[n for n in nazwy[1:] if n in po_nazwie])
        for n in nazwy[1:]:
            if n in po_nazwie:
                po_nazwie[n]["pominiete"] = True
    for klucz, tytul in GRUPY:
        if klucz not in grupy:
            continue
        w_grupie = [p for p in lista if ROLA_NA_GRUPE.get(p["rola"] or "") == klucz and not p.get("pominiete")]
        if not w_grupie:
            continue
        linie += ["", f"### {tytul}"]
        linie += [_linia(p) for p in w_grupie]
    if "koordynator" in grupy:
        linie += ["", "### Koordynator: najczęstsze operacje"]
        linie += [f"- {co}: `sf-kit {jak}`" for co, jak in PRZYKLADY_KOORDYNATORA]
    return "\n".join(linie) + "\n"


def bez_roli(parser: argparse.ArgumentParser) -> list[str]:
    """Polecenia bez opisu albo bez znacznika roli — dla testu bramki."""
    zle = []
    for p in polecenia(parser):
        if not p["opis"] or p["rola"] is None:
            zle.append(p["nazwa"])
        elif p["rola"] != WEWNETRZNE and p["rola"] not in ROLA_NA_GRUPE:
            zle.append(f"{p['nazwa']} (nieznana rola „{p['rola']}”)")
    return zle


# ── poziom 2: szczegóły na żądanie ───────────────────────────────────────────

def _klucz(tekst: str) -> str:
    t = unicodedata.normalize("NFKD", tekst.lower().replace("ł", "l"))
    return "".join(z for z in t if not unicodedata.combining(z))


def sekcje(agent_md: str) -> list[tuple[int, str, str]]:
    """AGENT.md → [(poziom, nagłówek, treść sekcji aż do następnego nagłówka tego samego lub wyższego poziomu)]."""
    wiersze = agent_md.splitlines()
    naglowki = []
    w_kodzie = False
    for i, w in enumerate(wiersze):
        if w.startswith("```"):
            w_kodzie = not w_kodzie
        m = None if w_kodzie else re.match(r"^(#{2,4})\s+(.*)$", w)
        if m:
            naglowki.append((i, len(m.group(1)), m.group(2).strip()))
    wynik = []
    for n, (i, poziom, tytul) in enumerate(naglowki):
        koniec = len(wiersze)
        for j, p2, _ in naglowki[n + 1:]:
            if p2 <= poziom:
                koniec = j
                break
        wynik.append((poziom, tytul, "\n".join(wiersze[i:koniec]).rstrip()))
    return wynik


def tematy(agent_md: str) -> list[str]:
    return [("  " * (p - 2)) + t for p, t, _ in sekcje(agent_md)]


def temat(agent_md: str, zapytanie: str) -> list[tuple[str, str]]:
    """Sekcje, których nagłówek zawiera zapytanie (bez względu na ogonki i wielkość liter)."""
    k = _klucz(zapytanie)
    return [(t, tresc) for _, t, tresc in sekcje(agent_md) if k in _klucz(t)]


def sekcje_z_poleceniem(agent_md: str, nazwa: str) -> list[str]:
    """Nagłówki najniższego poziomu, w których treści pada `sf-kit … <nazwa>` — gdzie doczytać o poleceniu."""
    wzorzec = re.compile(r"sf-kit(?:\s+--\S+(?:\s+\S+)?)*\s+" + re.escape(nazwa) + r"\b")
    trafione = []
    for poziom, t, tresc in sekcje(agent_md):
        if wzorzec.search(tresc) and not any(wzorzec.search(tr) for p2, _, tr in sekcje(tresc) if p2 > poziom):
            trafione.append(t)
    return trafione


def pomoc_polecenia(parser: argparse.ArgumentParser, nazwa: str) -> str | None:
    sub = _podparser(parser)
    if sub is None or nazwa not in sub.choices:
        return None
    p = sub.choices[nazwa]
    tekst = p.format_help()
    podsub = _podparser(p)
    if podsub:
        for pod_nazwa, pod_p in podsub.choices.items():
            tekst += f"\n── {nazwa} {pod_nazwa} ──\n" + pod_p.format_help()
    return tekst


def czytaj_agent_md(sciezka: Path) -> str:
    try:
        return sciezka.read_text(encoding="utf-8")
    except OSError:
        return ""
