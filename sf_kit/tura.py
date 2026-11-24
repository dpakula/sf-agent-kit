"""`sf-kit tura zamknij` — zamknięcie tury koordynatora jednym poleceniem Kita (SF-574).

v1.0.0 (24.11.2026) - APro Agents / arek-sf · SF-574 (decyzja Damiana 24.11 01:54: „bez powrotu do wersji lokalnej”)

SKĄD TO SIĘ WZIĘŁO
══════════════════
Zamknięcie tury żyło w lokalnej komendzie koordynatorki (`/next-turn`), czyli poza kontraktem Kita:
inny koordynator, inna Organizacja albo inna maszyna nie miały go wcale. Kit miał tylko `krok nowy`
i `krok zamknij`. Tu jest całość, a lokalna komenda ma być cienką nakładką, która woła Kita.

CO ROBI (kolejność = kolejność wykonania)
═════════════════════════════════════════
1. Krok: `--krok` → plik rozgrywki (ustawienie `rozgrywka`) → najnowszy krok z SF (`GET /konsola/kroki`).
   Krok ZAMKNIĘTY + praca po zamknięciu (kickoffy, bloki, decyzje) → nowy krok (`POST /kroki/dzis`)
   i to on dostaje stan. Zamknięty bez pracy po nim → stan jako dopisek na zamkniętym kroku.
   `--sprawa X` (asystent, sesja z człowiekiem) → stan jako wpis na sprawie X, bez zmiany statusu.
2. Kickoffy tury: zadania założone przez MOJE konto od otwarcia kroku, we wszystkich Organizacjach klucza.
3. Pomiar: to samo liczenie co `sf-kit status` (`wskazniki.py`); bez niego presja Organizacji z SF.
4. Decyzje człowieka: sekcja `## Decyzje` stanu (albo `--decyzja`). Każda musi wskazywać ślad
   (`#blok`, `SPRAWA-N`, link sprawy, `wpis <id>`); bloki i sprawy Kit sprawdza w SF. Braki = lista, kod 3.
5. Wpis zamykający (stan + następny krok + kickoffy + decyzje + pomiar) i status `closed`.
6. Lokalnie, gdy ustawione: plik stanu dla drugiego okna, akapit w dzienniku, commit w repozytorium.
7. Wynik: jedna linia „zapisane: … | następny krok: …”.

KODY WYJŚCIA
════════════
0 = wszystko · 1 = SF nie przyjął obowiązkowego zapisu (wpis/status) · 2 = złe wejście, nic nie wysłane ·
3 = zapisane, ale z brakami (decyzja bez śladu, nieudany krok lokalny, niepełna lista kickoffów).
"""
from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .api import BladAPI

STATUSY_ZAMKNIETE = ("closed", "resolved")
WATKI = 8
#: Ile znaków następnego kroku idzie do jednej linii wyniku i do wiadomości commita.
NASTEPNY_W_LINII = 160

_NAGLOWEK = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*#*\s*$")
_NASTEPNY_NAGLOWEK = re.compile(r"^(nast[eę]pny\s+krok|punkt\s+wznowienia|next)\b", re.I)
_NASTEPNY_LINIA = re.compile(r"^\s*(?:[-*]\s*)?\**(?:nast[eę]pny\s+krok|next)\**\s*[:：]\s*(.+)$", re.I)
_DECYZJE_NAGLOWEK = re.compile(r"^decyzje\b", re.I)
_PUNKT = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
_BRAK_DECYZJI = re.compile(r"^\(?\s*(brak|nie\s+by[łl]o|żadnych|zadnych|none)\b", re.I)

_SLAD_BLOK = re.compile(r"(?<![\w#])#(\d{2,})\b")
_SLAD_SPRAWA = re.compile(r"\b([A-Z][A-Z0-9]{0,15}-\d+)\b")
_SLAD_LINK = re.compile(r"https?://\S+/tickets/\S+")
_SLAD_WPIS = re.compile(r"\bwpis(?:u|ie)?\s+([0-9a-f]{8})\b", re.I)


# ── stan: następny krok i decyzje z treści ──────────────────────────────────

def _sekcje(tekst: str) -> list[tuple[str, list[str]]]:
    """[(nagłówek albo "", linie)] — markdown pocięty po nagłówkach."""
    wynik: list[tuple[str, list[str]]] = [("", [])]
    for linia in (tekst or "").splitlines():
        m = _NAGLOWEK.match(linia)
        if m:
            wynik.append((m.group(1).strip(), []))
        else:
            wynik[-1][1].append(linia)
    return wynik


def rozbierz_stan(tekst: str) -> tuple[str | None, list[str] | None]:
    """(następny krok, punkty decyzji). `None` przy decyzjach = sekcji nie ma; `[]` = jawnie „brak”."""
    nastepny, decyzje = None, None
    for naglowek, linie in _sekcje(tekst):
        if naglowek and _NASTEPNY_NAGLOWEK.match(naglowek) and nastepny is None:
            tresc = " ".join(" ".join(linie).split())
            nastepny = tresc or None
        elif naglowek and _DECYZJE_NAGLOWEK.match(naglowek):
            punkty = [m.group(1).strip() for m in map(_PUNKT.match, linie) if m and m.group(1).strip()]
            luzem = " ".join(" ".join(linie).split())
            if not punkty and luzem and _BRAK_DECYZJI.match(luzem):
                decyzje = []
            else:
                decyzje = [p for p in punkty if not _BRAK_DECYZJI.match(p)]
    if nastepny is None:
        for linia in (tekst or "").splitlines():
            m = _NASTEPNY_LINIA.match(linia)
            if m:
                nastepny = m.group(1).strip().strip("*").strip() or None
                break
    return nastepny, decyzje


def bez_sekcji_tury(tekst: str) -> str:
    """Stan bez sekcji „Następny krok” i „Decyzje” — wpis zamykający pokazuje je osobno, raz."""
    wynik: list[str] = []
    for naglowek, linie in _sekcje(tekst):
        if naglowek and (_NASTEPNY_NAGLOWEK.match(naglowek) or _DECYZJE_NAGLOWEK.match(naglowek)):
            continue
        if naglowek:
            wynik.append(f"## {naglowek}")
        wynik += linie
    tekst = "\n".join(wynik)
    tekst = "\n".join(l for l in tekst.splitlines() if not _NASTEPNY_LINIA.match(l))
    return re.sub(r"\n{3,}", "\n\n", tekst).strip()


@dataclass
class Decyzja:
    tekst: str
    slady: list[str] = field(default_factory=list)
    #: ok = ślad sprawdzony w SF · niesprawdzony = ślad jest, ale Kit nie umie go potwierdzić (wpis, link) ·
    #: brak = decyzja bez śladu · nie_znaleziono = wskazany blok / sprawa nie istnieje w żadnej Organizacji
    stan: str = "brak"
    uwaga: str = ""

    @property
    def ma_slad(self) -> bool:
        return self.stan in ("ok", "niesprawdzony")


def slady(tekst: str) -> list[str]:
    """Ślady w punkcie decyzji: `#2458`, `SF-574`, link sprawy, `wpis 7fd59229` — w kolejności wystąpienia."""
    znalezione: list[tuple[int, str]] = []
    for m in _SLAD_LINK.finditer(tekst):
        znalezione.append((m.start(), m.group(0).rstrip(").,;")))
    bez_linkow = _SLAD_LINK.sub(lambda m: " " * len(m.group(0)), tekst)
    for m in _SLAD_BLOK.finditer(bez_linkow):
        znalezione.append((m.start(), f"#{m.group(1)}"))
    for m in _SLAD_SPRAWA.finditer(bez_linkow):
        znalezione.append((m.start(), m.group(1)))
    for m in _SLAD_WPIS.finditer(bez_linkow):
        znalezione.append((m.start(), f"wpis {m.group(1).lower()}"))
    wynik: list[str] = []
    for _, s in sorted(znalezione):
        if s not in wynik:
            wynik.append(s)
    return wynik


def sprawdz_decyzje(punkty: list[str], *, jest_blok, jest_sprawa) -> list[Decyzja]:
    """Każdy punkt → Decyzja ze stanem śladu. `jest_blok("#N")` / `jest_sprawa("SF-1")` → True/False/None (nie wiem)."""
    wynik: list[Decyzja] = []
    for p in punkty:
        d = Decyzja(tekst=p, slady=slady(p))
        if not d.slady:
            d.stan, d.uwaga = "brak", "bez śladu (#blok, SPRAWA-N, link albo wpis <id>)"
            wynik.append(d)
            continue
        sprawdzone, niesprawdzone, zle = [], [], []
        for s in d.slady:
            if s.startswith("#"):
                ok = jest_blok(s)
            elif _SLAD_SPRAWA.fullmatch(s):
                ok = jest_sprawa(s)
            else:
                ok = None
            (sprawdzone if ok else zle if ok is False else niesprawdzone).append(s)
        if sprawdzone:
            d.stan = "ok"
        elif niesprawdzone:
            d.stan = "niesprawdzony"
        else:
            d.stan = "nie_znaleziono"
        if zle:
            d.uwaga = "nie ma w SF: " + ", ".join(zle)
        wynik.append(d)
    return wynik


# ── krok ─────────────────────────────────────────────────────────────────────

def czas(wartosc) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(wartosc).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def zamkniety(sprawa: dict) -> bool:
    return (sprawa.get("status") or "") in STATUSY_ZAMKNIETE


def zamkniety_o(sprawa: dict) -> datetime | None:
    """Kiedy krok się zamknął: `resolved_at`, a gdy go nie ma — ostatnia zmiana sprawy."""
    return czas(sprawa.get("resolved_at")) or czas(sprawa.get("updated_at"))


def najnowszy_krok(klient) -> str | None:
    """Id najnowszego kroku Organizacji z `GET /konsola/kroki` (dzień, potem numer)."""
    for dzien in klient.kroki_konsoli(dni=2):
        krok = dzien.get("krok") or {}
        if krok.get("id"):
            return str(krok["id"])
    return None


def bloki_kroku_po(klient, krok_id: str, od: datetime) -> list[dict]:
    """Bloki konsoli zakotwiczone w kroku, powstałe po chwili `od` (praca po zamknięciu kroku)."""
    wynik = []
    for dzien in klient.kroki_konsoli(dni=3):
        if str((dzien.get("krok") or {}).get("id")) != krok_id:
            continue
        for b in dzien.get("bloki") or []:
            t = czas(b.get("kiedy"))
            if t and t > od and b.get("rodzaj") != "rozstrzygniecie":
                wynik.append(b)
    return wynik


# ── kickoffy ─────────────────────────────────────────────────────────────────

def kickoffy(klienci: list[tuple[str, object]], od: datetime, email: str | None) -> tuple[list[dict], list[str]]:
    """Zadania założone przez konto `email` od chwili `od`, we wszystkich podanych Organizacjach.

    → (zadania z polem `_org`, problemy). Bez adresu konta nie ma jak odróżnić moich zadań od cudzych:
    wtedy pusta lista i problem, a nie wszystkie zadania Organizacji udające kickoffy."""
    if not email:
        return [], ["SF nie podał adresu konta — kickoffów nie da się odróżnić od cudzych zadań"]
    od_iso = od.astimezone(timezone.utc).isoformat()

    def jedna(para):
        slug, k = para
        try:
            return slug, k.zadania_od(od_iso), None
        except BladAPI as blad:
            return slug, [], f"{slug}: {blad}"

    zadania, problemy = [], []
    with ThreadPoolExecutor(max_workers=WATKI) as pula:
        for slug, lista, problem in pula.map(jedna, klienci):
            if problem:
                problemy.append(problem)
            for z in lista:
                if str(z.get("created_by") or "").lower() == email.lower():
                    zadania.append({**z, "_org": slug})
    zadania.sort(key=lambda z: str(z.get("created_at") or ""))
    return zadania, problemy


def wiersz_kickoffu(z: dict) -> str:
    kto = z.get("assigned_agent_slug") or z.get("assignee_name")
    tytul = " ".join(str(z.get("title") or "").split())[:90]
    sprawa = f"{z['ticket_ref']} · " if z.get("ticket_ref") else ""
    return f"{sprawa}{z.get('external_id') or str(z.get('id'))[:8]} → {kto or '?'} · {z.get('_org')} · {tytul}"


# ── pomiar ───────────────────────────────────────────────────────────────────

def pomiar(*, kto: str | None, wskazniki: str | None, klient=None) -> tuple[str, str]:
    """(linia, źródło). Najpierw to samo liczenie co `sf-kit status`; bez `wskazniki.py` — presja Org z SF.

    Pomiar nie jest obowiązkowy: jego brak to linia „n/d” z powodem, nie porażka tury."""
    from . import postac
    try:
        sciezka = postac.znajdz_wskazniki(wskazniki)
        if not sciezka:
            raise postac.BrakWskaznikow("brak wskazniki.py")
        dom, manifest = postac.dom_i_manifest(sciezka, kto)
        e = postac.Ekran(postac.pobierz(sciezka, dom, manifest), kolor=False)
        wartosci = {k: p for k, _, p, _, _ in e.wiersze_paskow(kto)}
        en, pr = wartosci.get("energia"), wartosci.get("presja")
        return (f"energia {'n/d' if en is None else f'{en} %'} · presja {'n/d' if pr is None else f'{pr} %'}",
                "status")
    except (postac.BrakWskaznikow, subprocess.TimeoutExpired, OSError) as blad:
        powod = str(blad).splitlines()[0] if str(blad) else "brak wskazniki.py"
    if klient is not None:
        try:
            p = klient.presja_zadan()
            if p:
                d, do = p.get("decide") or {}, p.get("do") or {}
                return (f"energia n/d · presja Org {p.get('razem', '?')} (decyzje {d.get('wazona', d.get('otwarte', '?'))}, "
                        f"praca {do.get('otwarte', '?')})", "sf")
        except BladAPI as blad:
            powod += f"; SF: {blad}"
    return f"pomiar n/d ({powod})", "brak"


# ── treść wpisu zamykającego ─────────────────────────────────────────────────

def wpis_zamykajacy(*, stan: str, nastepny: str, kickoffy_lista: list[dict], problemy_kickoffow: list[str],
                    decyzje: list[Decyzja] | None, pomiar_linia: str, kiedy: datetime,
                    dopiecie: str | None = None) -> str:
    linie = [f"**Zamknięcie tury** · {kiedy.astimezone():%d.%m.%Y %H:%M} · `sf-kit tura zamknij`", ""]
    if dopiecie:
        linie += [f"_{dopiecie}_", ""]
    linie += [bez_sekcji_tury(stan), "", f"**Następny krok:** {nastepny}", "",
              f"**Kickoffy tury ({len(kickoffy_lista)}):**"]
    linie += [f"- {wiersz_kickoffu(z)}" for z in kickoffy_lista] or ["- brak"]
    linie += [f"- UWAGA: {p}" for p in problemy_kickoffow]
    if decyzje is None:
        linie += ["", "**Decyzje człowieka:** nie podane (brak sekcji „Decyzje”)"]
    else:
        ze_sladem = sum(d.ma_slad for d in decyzje)
        linie += ["", f"**Decyzje człowieka ({ze_sladem}/{len(decyzje)} ze śladem):**"]
        znak = {"ok": "✓", "niesprawdzony": "~", "brak": "✗", "nie_znaleziono": "✗"}
        linie += [f"- {znak[d.stan]} {d.tekst}" + (f" — {d.uwaga}" if d.uwaga else "") for d in decyzje] or ["- brak"]
    linie += ["", f"**Pomiar:** {pomiar_linia}"]
    return "\n".join(linie).strip() + "\n"


# ── kroki lokalne ────────────────────────────────────────────────────────────

def zapisz_atomowo(sciezka: Path, tresc: str) -> None:
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    tmp = sciezka.with_name(sciezka.name + ".tmp")
    tmp.write_text(tresc, encoding="utf-8")
    tmp.replace(sciezka)


def plik_stanu(*, krok_opis: str, nastepny: str, wpis: str, kiedy: datetime) -> str:
    return (f"# Punkt wznowienia — tura zamknięta {kiedy.astimezone():%d.%m.%Y %H:%M}\n\n"
            f"KROK: {krok_opis}\nNASTĘPNY KROK: {nastepny}\n\n{wpis}")


def sciezka_dziennika(wzor: str, kiedy: datetime) -> Path:
    return Path(wzor.replace("{data}", f"{kiedy.astimezone():%Y-%m-%d}")).expanduser()


def akapit_dziennika(*, krok_opis: str, nastepny: str, podsumowanie: str, kiedy: datetime) -> str:
    return (f"\n## {kiedy.astimezone():%H:%M} — tura zamknięta ({krok_opis})\n"
            f"- {podsumowanie}\n- następny krok: {nastepny}\n")


def dopisz(sciezka: Path, tresc: str) -> None:
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    with sciezka.open("a", encoding="utf-8") as f:
        f.write(tresc)


def zatwierdz(repo: str, *, pliki: list[Path], tryb: str, wiadomosc: str) -> str:
    """Commit w repozytorium koordynatora → krótki sha albo „bez zmian”. `RuntimeError` z komunikatem gita.

    `pliki` = tylko to, co Kit zapisał (pliki spoza repo pomijamy); `wszystko` = `git add -A`.
    Nigdy nie wypycha i nigdy nie omija hooków."""
    katalog = Path(repo).expanduser().resolve()

    def git(*a):
        w = subprocess.run(["git", "-C", str(katalog), *a], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=60)
        if w.returncode != 0:
            raise RuntimeError((w.stderr or w.stdout).strip().splitlines()[-1:] or ["git: błąd"])
        return w.stdout

    git("rev-parse", "--is-inside-work-tree")
    if tryb == "wszystko":
        git("add", "-A")
    else:
        wewnatrz = []
        for p in pliki:
            try:
                wewnatrz.append(str(p.resolve().relative_to(katalog)))
            except ValueError:
                continue
        if not wewnatrz:
            return "bez zmian (zapisane pliki leżą poza repozytorium)"
        git("add", "--", *wewnatrz)
    if not git("diff", "--cached", "--name-only").strip():
        return "bez zmian"
    git("commit", "-q", "-m", wiadomosc)
    return git("rev-parse", "--short", "HEAD").strip()


# ── wynik ────────────────────────────────────────────────────────────────────

@dataclass
class Wynik:
    zapisane: list[str] = field(default_factory=list)
    braki: list[str] = field(default_factory=list)
    nastepny: str = ""
    kod: int = 0
    krok: dict = field(default_factory=dict)
    kickoffy: list[str] = field(default_factory=list)
    decyzje: list[dict] = field(default_factory=list)
    pomiar: str = ""

    def linia(self) -> str:
        n = " ".join(self.nastepny.split())
        if len(n) > NASTEPNY_W_LINII:
            n = n[: NASTEPNY_W_LINII - 1] + "…"
        czesci = [f"zapisane: {', '.join(self.zapisane) or 'nic'}"]
        if self.braki:
            czesci.append(f"braki: {'; '.join(self.braki)}")
        czesci.append(f"następny krok: {n}")
        return " | ".join(czesci)

    def json(self) -> str:
        return json.dumps({"ok": self.kod == 0, **asdict(self), "linia": self.linia()},
                          ensure_ascii=False, indent=2, default=str)
