"""Uwagi do Kita prosto z terminala — `sf-kit uwaga "…"` (SF-506, Kit 0.20.1).

v1.0.0 (09.11.2026) - APro Agents / klaudiusz-general · punkt 1 SF-506: „jeśli Kit nie ma endpointu
do zgłaszania uwag — to punkt pierwszy” (Damian 09.11)

PO CO
═════
Alfatester (Wójt, potem każdy nietechniczny użytkownik z agentem) trafia na coś, co nie działa albo
czego brakuje. Do 0.20.0 miał dwie drogi i obie złe: `zglos` (to jest „gotowa praca”, ląduje
w Organizacji klienta) albo napisać do kogoś — bez wersji Kita, bez komunikatu błędu, bez systemu.
Pierwsza runda korespondencji szła na pytanie „która wersja i co dokładnie wyskoczyło”.

`uwaga` zakłada sprawę w Organizacji SalesForge (`sf`) — tam, gdzie żyje rozwój Kita — z kontekstem
dołożonym automatycznie: wersja Kita, system, Python, profil, slug agenta i OSTATNIE NIEUDANE
polecenie (argumenty, kod wyjścia, końcówka komunikatu błędu). Autor = klucz testera.

CO ZAPISUJEMY O BŁĘDZIE I DLACZEGO TAK MAŁO
════════════════════════════════════════════
`_wykonaj` w cli.py przepuszcza stderr przez `Lustro` (ograniczony bufor) i przy kodzie ≠ 0 albo
nieobsłużonym wyjątku zapisuje `ostatni-blad.json` obok konfiguracji agenta. Tylko stderr i tylko
końcówka: stdout bywa treścią spraw klientów, a uwaga idzie do innej Organizacji.

SEKRETY
═══════
Wszystko, co wychodzi z maszyny, przechodzi przez `wyczysc()` DWA razy: przy zapisie błędu i przy
budowaniu treści uwagi (plik mógł powstać w starszej wersji albo zostać poprawiony ręcznie).
Wzorce + wartość własnego klucza wprost. Lista wzorców jest z natury niepełna — dlatego zbieramy
mało (końcówka stderr, nie całe wyjście), a człowiek widzi treść przed wysłaniem w `--sucho`.
"""
from __future__ import annotations

import io
import json
import os
import platform
import re
import sys
import time
from pathlib import Path

#: Organizacja, w której lądują uwagi — tam żyje rozwój Kita (SF-486, SF-506).
ORG_UWAG = "sf"
ZMIENNA_ORG_UWAG = "SF_KIT_ORG_UWAG"
#: Kategoria sprawy — zamknięty zestaw SF (`bug, feature, feedback, other, question`; 422 na inną —
#: sprawdzone na żywo 09.11). Tagu `kit-uwaga` w taksonomii `sf` nie ma, agenci nie mają `taxonomy:write`,
#: więc uwagę rozpoznaje się po PREFIKSIE TYTUŁU i tagu Projekt: SalesForge.
KATEGORIA_BLAD = "bug"
KATEGORIA_UWAGA = "feedback"
PREFIKS_TYTULU = "Uwaga do Kita:"
#: Tagi z taksonomii `sf`; brak któregoś = ostrzeżenie, nie porażka (inna Organizacja przez env).
TAG_PROJEKTU = "SalesForge"
TAG_BLAD = "Błąd"
TAG_FEEDBACK = "Feedback"

PLIK_BLEDU = "ostatni-blad.json"
KATALOG_NIEWYSLANYCH = "uwagi-niewyslane"
#: Ile końcówki stderr trzymamy. Komunikat błędu Kita mieści się w kilkuset znakach; traceback w ~2 KB.
LIMIT_STDERR = 4000
#: Błąd starszy niż doba to już nie „to, co mi przed chwilą nie zadziałało”.
WAZNOSC_BLEDU_S = 24 * 3600
LIMIT_TYTULU = 80

_WZORCE = [
    (re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9_\-]{4,}"), "sk_…[ukryte]"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-+/=]{8,}"), r"\1 [ukryte]"),
    (re.compile(r"(?i)\b(authorization|x-api-key)\s*[:=]\s*\S+"), r"\1: [ukryte]"),
    (re.compile(r"(?i)\b([A-Z0-9_]*(?:pass(?:word)?|haslo|hasło|secret|sekret|token|api[_-]?key)[A-Z0-9_]*)"
                r"(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)"), r"\1\2[ukryte]"),
    (re.compile(r"(?i)(--(?:klucz|key|haslo|password|token))(=|\s+)\S+"), r"\1\2[ukryte]"),
    (re.compile(r"(?i)\b(\w+://[^:/\s]+:)[^@\s]+@"), r"\1[ukryte]@"),
]
#: Słowa testera: bez wzorca `nazwa: wartość` (zjadałby „hasło: nie przechodzi”); przy hasłach tylko `=`.
_WZORCE_PROZA = [w for i, w in enumerate(_WZORCE) if i != 3] + [
    (re.compile(r"(?i)\b([A-Z0-9_]*(?:pass(?:word)?|haslo|hasło|secret|sekret|token|api[_-]?key)[A-Z0-9_]*)"
                r"(\s*=\s*)(\"[^\"]*\"|'[^']*'|\S+)"), r"\1\2[ukryte]"),
]


def wyczysc(tekst: str, klucz: str | None = None, *, proza: bool = False) -> str:
    """Tekst bez sekretów: wzorce + wartość własnego klucza wprost (gdyby wyciekła w innym kształcie).

    `proza=True` (słowa testera): bez wzorca `hasło: …`, który zjadałby zdania w rodzaju
    „hasło: nie przechodzi”; `HASLO=…`, klucze, nagłówki i hasła w adresach dalej znikają."""
    if not tekst:
        return ""
    if klucz and len(klucz) >= 8:
        tekst = tekst.replace(klucz, "[klucz ukryty]")
    for wzorzec, zamiana in (_WZORCE_PROZA if proza else _WZORCE):
        tekst = wzorzec.sub(zamiana, tekst)
    return tekst


class Lustro(io.TextIOBase):
    """stderr, który pisze dalej normalnie i zapamiętuje końcówkę (bufor ograniczony — worker chodzi dniami)."""

    def __init__(self, cel, limit: int = LIMIT_STDERR):
        self._cel = cel
        self._limit = limit
        self._kawalki: list[str] = []
        self._dlugosc = 0

    def write(self, s: str) -> int:
        self._cel.write(s)
        self._kawalki.append(s)
        self._dlugosc += len(s)
        if self._dlugosc > 4 * self._limit:            # przycinamy rzadko, nie przy każdym zapisie
            calosc = "".join(self._kawalki)[-self._limit:]
            self._kawalki, self._dlugosc = [calosc], len(calosc)
        return len(s)

    def zapamietaj(self, s: str) -> None:
        """Do bufora, bez wypisania (komunikat, który Python wypisze sam przy `SystemExit`)."""
        self._kawalki.append(s)
        self._dlugosc += len(s)

    def flush(self) -> None:
        self._cel.flush()

    def isatty(self) -> bool:
        return bool(getattr(self._cel, "isatty", lambda: False)())

    @property
    def encoding(self):                                   # argparse i print pytają o kodowanie
        return getattr(self._cel, "encoding", "utf-8")

    def koncowka(self) -> str:
        return "".join(self._kawalki)[-self._limit:]


def system_teraz(wersja: str, *, profil: str = "", agent: str = "", org: str = "") -> dict:
    """Kontekst maszyny, który odpowiada na pierwsze pytanie przy każdym zgłoszeniu."""
    return {
        "kit": wersja,
        "system": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python": platform.python_version(),
        "profil": profil or "?",
        "agent": agent or "?",
        "org_domyslna": org or "—",
    }


def zapisz_blad(katalog: Path, *, argv: list[str], kod, stderr: str, wersja: str,
                klucz: str | None = None, teraz: float | None = None) -> Path | None:
    """`ostatni-blad.json` — nadpisuje poprzedni (interesuje nas OSTATNI). Porażka zapisu = cisza."""
    try:
        katalog.mkdir(parents=True, exist_ok=True)
        plik = katalog / PLIK_BLEDU
        dane = {
            "czas": teraz if teraz is not None else time.time(),
            "kit": wersja,
            "polecenie": wyczysc(" ".join(["sf-kit", *argv]), klucz),
            "kod": str(kod),
            "stderr": wyczysc(stderr[-LIMIT_STDERR:], klucz),
        }
        plik.write_text(json.dumps(dane, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            os.chmod(plik, 0o600)
        except OSError:
            pass
        return plik
    except OSError:
        return None


def ostatni_blad(katalog: Path, *, teraz: float | None = None) -> dict | None:
    """Ostatni błąd, jeśli świeży (< doba) i czytelny. Inaczej None."""
    plik = katalog / PLIK_BLEDU
    try:
        dane = json.loads(plik.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(dane, dict):
        return None
    wiek = (teraz if teraz is not None else time.time()) - float(dane.get("czas") or 0)
    return dane if 0 <= wiek <= WAZNOSC_BLEDU_S else None


def usun_blad(katalog: Path) -> None:
    """Po wysłaniu uwagi — ten sam błąd nie pojedzie drugi raz z następną."""
    try:
        (katalog / PLIK_BLEDU).unlink()
    except OSError:
        pass


def tytul(tekst: str) -> str:
    pierwsza = next((l.strip() for l in tekst.splitlines() if l.strip()), "bez treści")
    pierwsza = pierwsza.lstrip("#").strip()
    if len(pierwsza) > LIMIT_TYTULU:
        pierwsza = pierwsza[:LIMIT_TYTULU - 1].rstrip() + "…"
    return f"{PREFIKS_TYTULU} {pierwsza}"


def tresc(tekst: str, *, system: dict, blad: dict | None, kontekst: str = "",
          klucz: str | None = None) -> str:
    """Markdown sprawy: najpierw słowa testera, potem kontekst maszyny (zwinięty), na końcu błąd."""
    czesci = [wyczysc(tekst.strip(), klucz, proza=True)]
    if kontekst.strip():
        czesci.append(f"**Co robiłem:** {wyczysc(kontekst.strip(), klucz, proza=True)}")
    if blad:
        kiedy = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(blad.get("czas") or 0)))
        stderr = wyczysc(str(blad.get("stderr") or "").strip(), klucz) or "(pusto)"
        czesci.append(
            f"**Ostatnie nieudane polecenie** ({kiedy}, Kit {blad.get('kit', '?')}, kod {blad.get('kod', '?')}):\n"
            f"```\n{wyczysc(str(blad.get('polecenie') or ''), klucz)}\n```\n"
            f"Komunikat (końcówka):\n```\n{stderr.replace('```', 'ʼʼʼ')}\n```")
    wiersze = "\n".join(f"| {k} | {v} |" for k, v in system.items())
    czesci.append("<details><summary>Kontekst maszyny (dołożony przez Kita)</summary>\n\n"
                  f"| | |\n|---|---|\n{wiersze}\n\n</details>")
    return "\n\n".join(czesci)


def zapisz_niewyslana(katalog: Path, tytul_: str, tresc_: str, powod: str) -> Path | None:
    """Uwaga, która nie doszła — w pliku, żeby nic nie przepadło. → ścieżka albo None."""
    try:
        cel = katalog / KATALOG_NIEWYSLANYCH
        cel.mkdir(parents=True, exist_ok=True)
        plik = cel / time.strftime("uwaga-%Y%m%d-%H%M%S.md")
        plik.write_text(f"# {tytul_}\n\n> Nie wysłano: {powod}\n\n{tresc_}\n", encoding="utf-8")
        return plik
    except OSError:
        return None


def org_uwag(wskazana: str | None) -> str:
    """`--org` > zmienna środowiska > `sf`."""
    return (wskazana or os.environ.get(ZMIENNA_ORG_UWAG) or ORG_UWAG).strip()


def wczytaj_tekst(wartosc: str, stdin=None) -> str:
    """Treść uwagi: tekst wprost albo `-` = standardowe wejście."""
    if wartosc == "-":
        return (stdin or sys.stdin).read()
    return wartosc
