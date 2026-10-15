"""Ekran statusu „jak w grze” — MANA, ENERGIA, PRESJA, ZDROWIE z rozbiciem i podpowiedziami.

v0.1.1 (15.10.2026) - APro Agents / borys-sf — wydanie 0.18.0: `wskazniki.py` tylko z jawnej ścieżki, env albo nad $HOME
v0.1 (15.10.2026) - APro Agents / klaudiusz-general (ADVERTPR-1075)

SKĄD LICZBY
═══════════
Kit NICZEGO tu nie liczy. Wszystkie wartości, rozbicia i podpowiedzi „co zrobić” daje
`scripts/lib/wskazniki.py --json` (repo AProAgents), który czyta jeden manifest wskaźników
(`homes/agata/config/wskazniki.json`). Zmiana wzoru albo tekstu podpowiedzi = zmiana manifestu,
a ekran pokaże ją bez wydania Kitu. Drugi wzór tutaj byłby drugą prawdą — dokładnie tym,
czego manifest ma zapobiegać (zasada z 13.10: „liczy się w jednym miejscu”).

Ten sam ekran wołają /mood i /samopoczucie Agaty (`sf-kit status --kolor nigdy`) — jeden rysunek.
W SalesForge ten sam ekran ma być panelem konsoli (SF-289); do tego czasu działa tylko tam,
gdzie leży repo AProAgents z `wskazniki.py`.

KTO
═══
  (domyślnie) / damian — widok status line Agaty: mana i energia terminala Agaty, presja i HP Damiana,
  agata               — mana, energia, presja Agaty; HP nie dotyczy (liczone dla człowieka),
  <agent>             — dom `homes/<agent>`: mana i energia z jego plików; presji i HP brak do SF-289.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

RESET, SZARY, POGRUB = "\033[0m", "\033[90m", "\033[1m"
#: Kolory pasków — manifest § 6 (`wyglad.kolory`): mana niebieska, energia żółta (0 % czerwona),
#: presja pomarańczowa, HP czerwone. Te same kody 256 kolorów co status line Agaty.
KOLOR = {"mana": "\033[38;5;39m", "energia": "\033[38;5;220m", "presja": "\033[38;5;208m",
         "hp": "\033[38;5;196m", "wyczerpana": "\033[38;5;196m"}
KOLOR_ZAPASU = {"zielony": "\033[32m", "zolty": "\033[33m", "czerwony": "\033[31m"}
PELNE, PUSTE = "█", "░"

#: Nazwy z kluczy manifestu (bez polskich znaków w JSON-ie) — tylko do wyświetlenia.
NAZWY = {"swieza": "świeża", "rozgrzana": "rozgrzana", "zmeczona": "zmęczona", "wymaga_odpoczynku": "wymaga odpoczynku",
         "wyczerpana": "wyczerpana", "zielony": "zielony", "pomaranczowy": "pomarańczowy", "czerwony": "czerwony"}


class BrakWskaznikow(Exception):
    """Nie ma skąd wziąć liczb — ekran bez danych nie udaje, że wszystko jest w porządku."""


# ───────────────────────── źródło danych ─────────────────────────

def znajdz_wskazniki(jawna: str | None = None) -> Path | None:
    """`--wskazniki` > env SF_KIT_WSKAZNIKI > w górę od $HOME (domy agentów leżą w repo AProAgents).

    0.18.0 (borys-sf, bramka wydania): BEZ szukania od bieżącego katalogu. `pobierz()` URUCHAMIA znaleziony plik,
    a `sf-kit status` wpisany w sklonowanym cudzym repo wykonałby jego `scripts/lib/wskazniki.py` — ta sama klasa
    co hooki gita. Bieżący katalog wskazuje człowiek przypadkiem, `$HOME` i jawna ścieżka — świadomie.
    """
    for kandydat in (jawna, os.environ.get("SF_KIT_WSKAZNIKI")):
        if kandydat:
            p = Path(kandydat).expanduser()
            return p if p.is_file() else None
    d = Path.home().resolve()
    for katalog in (d, *d.parents):
        p = katalog / "scripts" / "lib" / "wskazniki.py"
        if p.is_file():
            return p
    return None


def dom_i_manifest(wskazniki: Path, kto: str | None) -> tuple[Path, Path]:
    """Repo = trzy poziomy nad scripts/lib/wskazniki.py. Manifest zawsze jeden: dom Agaty."""
    repo = wskazniki.resolve().parents[2]
    agata = repo / "homes" / "agata"
    manifest = agata / "config" / "wskazniki.json"
    if kto in (None, "", "damian", "agata"):
        return agata, manifest
    dom = repo / "homes" / kto
    if not dom.is_dir():
        raise BrakWskaznikow(f"Nie znam agenta „{kto}” — brak katalogu {dom}.")
    return dom, manifest


def pobierz(wskazniki: Path, dom: Path, manifest: Path, *, limit_s: int = 30) -> dict:
    wynik = subprocess.run([sys.executable, str(wskazniki), "--json", "--dom", str(dom), "--manifest", str(manifest)],
                           capture_output=True, text=True, timeout=limit_s)
    if wynik.returncode != 0:
        raise BrakWskaznikow(f"wskazniki.py zakończył się błędem:\n{wynik.stderr.strip()[-800:]}")
    try:
        return json.loads(wynik.stdout)
    except ValueError as blad:
        raise BrakWskaznikow(f"wskazniki.py oddał coś, co nie jest JSON-em: {blad}") from None


# ───────────────────────── rysunek ─────────────────────────

def _szer(s: str) -> int:
    """Szerokość w kolumnach terminala (🔥 = 2, ✦ ↯ ♥ = 1), bez kodów ANSI."""
    n, esc = 0, False
    for ch in s:
        if ch == "\033":
            esc = True
            continue
        if esc:
            esc = ch != "m"
            continue
        if unicodedata.combining(ch) or ch == "️":
            continue
        n += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return n


def _dopelnij(s: str, szer: int) -> str:
    return s + " " * max(0, szer - _szer(s))


def _l(x) -> str:
    x = round(float(x), 1)
    return str(int(x)) if x == int(x) else str(x).replace(".", ",")


def _nazwa(klucz) -> str:
    return NAZWY.get(str(klucz or ""), str(klucz or "").replace("_", " "))


def _znak(x) -> str:
    """+5 / −5 / 0 — typograficzny minus, jak w tekstach manifestu."""
    x = round(float(x), 1)
    return ("+" if x > 0 else "−" if x < 0 else "") + _l(abs(x))


def _wypelnienie(procent: int, n: int) -> int:
    p = round(max(0, min(100, procent)) / 100.0 * n)
    return 1 if procent > 0 and p == 0 else p              # cokolwiek > 0 = widać choć jedną kratkę


def _data(iso: str | None) -> str:
    if not iso:
        return "?"
    try:
        t = datetime.fromisoformat(str(iso))
    except ValueError:
        return str(iso)
    return t.strftime("%d.%m %H:%M") if "T" in str(iso) else t.strftime("%d.%m")


class Ekran:
    def __init__(self, dane: dict, *, kolor: bool):
        self.d = dane
        self.kolor = kolor
        w = dane.get("wyglad") or {}
        self.n = int(w.get("pola_paska", 9))
        self.ikony = {"mana": "✦", "energia": "↯", "presja": "🔥", "hp": "♥", **(w.get("ikony") or {})}
        self.glify = sorted(((float(k), v) for k, v in (w.get("glify_zapasu") or
                             {"90": "●", "65": "◕", "35": "◑", "10": "◔", "0": "○"}).items()), reverse=True)
        self.kolory_zapasu = sorted(((float(k), v) for k, v in (w.get("kolory_zapasu") or
                                    {"50": "zielony", "20": "zolty", "0": "czerwony"}).items()), reverse=True)

    def _k(self, kod: str, s: str) -> str:
        return f"{kod}{s}{RESET}" if self.kolor and kod else s

    def pasek(self, procent, kolor: str) -> str:
        """Każda kratka manifestu rysowana podwójnie — ta sama skala co status line, tylko większa."""
        if procent is None:
            return self._k(SZARY, "[" + PUSTE * 2 * self.n + "]")
        p = _wypelnienie(procent, self.n)
        return self._k(kolor, "[" + PELNE * 2 * p + PUSTE * 2 * (self.n - p) + "]")

    def zapas(self, etykieta: str, procent) -> str:
        if procent is None:
            return f"{etykieta} n/d"
        glif = next(g for prog, g in self.glify if procent >= prog)
        kol = next(k for prog, k in self.kolory_zapasu if procent >= prog)
        return self._k(KOLOR_ZAPASU.get(kol, ""), f"{etykieta} {glif} {procent} %")

    # ───── wiersze ─────

    def wiersze_paskow(self, kto: str | None) -> list[tuple[str, str, object, str, str]]:
        """[(klucz, etykieta, procent, kolor, dopisek)] — cztery paski w stałej kolejności."""
        d = self.d
        mana = (d.get("mana") or {}).get("procent")
        en = d.get("energia") or {}
        kol_en = KOLOR["wyczerpana"] if en.get("procent") == 0 else KOLOR["energia"]
        dop_en = f"{en.get('pola')}/{en.get('pola_max')} · {_nazwa(en.get('poziom'))}" if en else ""

        pres_all = d.get("presja") or {}
        inny = kto not in (None, "", "damian", "agata")
        klucz_p, litera = ("agent", " A") if kto == "agata" else ("damian", "" if inny else " D")
        pr = None if kto not in (None, "", "damian", "agata") else pres_all.get(klucz_p)
        if pr:
            dop_p = f"{_l(pr['dni'])} dni · {_nazwa(pr['kolor'])} · {pr['pozycji']} poz."
            if pres_all.get("co_najmniej") and klucz_p == "damian":
                dop_p = "≥ " + dop_p
            if not pres_all.get("swieze"):
                dop_p += " · dane z cache (SF nie odpowiedział)"
        else:
            dop_p = "brak danych (presja agentów — SF-289)" if kto not in (None, "", "damian", "agata") \
                else "brak danych (cache status line Agaty)"

        hp = d.get("hp") or {}
        if kto in (None, "", "damian") and hp.get("procent") is not None:
            t = hp.get("tendencja") or {}
            hp_proc = hp["procent"]
            dop_hp = f"{t.get('strzalka', '')} {_nazwa(hp.get('poziom'))} · doba {_data(hp.get('data'))}".strip()
            if hp.get("alarm"):
                dop_hp += " · ALARM"
        else:
            hp_proc, dop_hp = None, "nie dotyczy (HP liczone dla człowieka)" if kto not in (None, "", "damian") \
                else "brak historii HP"
        return [("mana", "MANA", mana, KOLOR["mana"], "" if mana is not None else "brak danych okna"),
                ("energia", "ENERGIA", en.get("procent"), kol_en, dop_en),
                ("presja", f"PRESJA{litera}", pr["procent"] if pr else None, KOLOR["presja"], dop_p),
                ("hp", "ZDROWIE", hp_proc, KOLOR["hp"], dop_hp)]

    def rysuj(self, kto: str | None, *, rozbicie: bool = True) -> str:
        d = self.d
        kim = {None: "Damian · terminal Agaty", "": "Damian · terminal Agaty", "damian": "Damian · terminal Agaty",
               "agata": "Agata"}.get(kto, kto)
        out = [self._k(POGRUB, f"STATUS · {kim}"), ""]
        wiersze = self.wiersze_paskow(kto)
        for klucz, etykieta, procent, kolor, dopisek in wiersze:
            ik = self.ikony.get(klucz, "")
            wart = "  n/d" if procent is None else ("100%+" if procent > 100 else f"{procent:>3} %")
            lewa = _dopelnij(f"  {ik} {etykieta}", 15)
            dop = (f"  {self._k(SZARY, dopisek) if procent is None else dopisek}") if dopisek else ""
            out.append(f"{lewa}{self.pasek(procent, kolor)} {self._k(kolor if procent is not None else SZARY, wart)}{dop}")
        lim = d.get("limity") or {}
        out.append("")
        out.append(f"  {self.zapas('5h', lim.get('5h'))}    {self.zapas('7d', lim.get('7d'))}"
                   + self._k(SZARY, "    (zapas limitów, nie zużycie)"))
        if rozbicie:
            for klucz, etykieta, procent, kolor, _ in wiersze:
                out += self.sekcja(klucz, etykieta, procent, kolor, kto)
        out += ["", self._k(SZARY, f"manifest v{d.get('manifest')} · wskazniki.py · {datetime.now():%d.%m %H:%M}")]
        return "\n".join(out)

    def _wglad(self, klucz: str, kto: str | None) -> dict | None:
        d = self.d
        if klucz == "presja":
            if kto not in (None, "", "damian", "agata"):
                return None
            return ((d.get("presja") or {}).get("agent" if kto == "agata" else "damian") or {}).get("wglad")
        if klucz == "hp" and kto not in (None, "", "damian"):
            return None
        return (d.get(klucz) or {}).get("wglad")

    def sekcja(self, klucz: str, etykieta: str, procent, kolor: str, kto: str | None) -> list[str]:
        w = self._wglad(klucz, kto)
        if not w or procent is None:
            return []
        ik = self.ikony.get(klucz, "")
        wart = "100%+" if procent > 100 else f"{procent} %"
        out = ["", self._k(kolor, f"{ik} {etykieta} {wart}") + self._trend(klucz, w.get("trend"))]
        for s in w.get("skladowe") or []:
            out.append("   · " + self._skladowa(klucz, s))
        if klucz == "hp":
            pod = w.get("podglad_dzis") or {}
            if pod.get("zmiana") is not None:
                out.append(f"   · dziś do teraz {_znak(pod['zmiana'])} ({pod.get('godzin') or 0} h z próbek;"
                           " sen, kroki i kalendarz dolicza /sleep-time)")
            if w.get("alarm"):
                out.append("   " + self._k(KOLOR["hp"], "! " + w["alarm"]))
        podp = w.get("podpowiedzi") or []
        if klucz == "presja" and w.get("reakcja"):
            podp = podp + [w["reakcja"]]
        out += [f"   → {p}" for p in podp] or [self._k(SZARY, "   → nic do zrobienia")]
        return out

    def _trend(self, klucz: str, t) -> str:
        if not t:
            return ""
        if klucz == "hp":
            s = f"  {t.get('strzalka', '')} od {t.get('od_dni')} dób, {_znak(t.get('roznica', 0))} pkt vs średnia 7 dób"
            if t.get("przyczyna"):
                s += f"; ciągnie: {t['przyczyna'].get('opis')}"
            return self._k(SZARY, s)
        pref = "co najmniej " if t.get("co_najmniej") else ""
        return self._k(SZARY, f"  · tak {pref}od {_data(t.get('od'))} ({_l(t.get('dni', 0))} dnia)")

    @staticmethod
    def _skladowa(klucz: str, s: dict) -> str:
        if klucz == "energia":
            if "ubytek" in s:
                u = s["ubytek"]
                ile = f"−{u} {'pole' if u == 1 else 'pola' if 2 <= u <= 4 else 'pól'}" if u else "0"
                return f"{_dopelnij(s['nazwa'], 20)} {_dopelnij(ile, 8)} {s.get('opis', '')}"
            proc = s.get("procent")
            return f"{_dopelnij(s['nazwa'], 20)} {_dopelnij('n/d' if proc is None else f'{proc} %', 8)} {s.get('opis', '')}"
        if klucz == "presja":
            return f"{_dopelnij(s.get('opis', ''), 40)} {_dopelnij(_l(s['punkty']) + ' pkt', 10)} = {_l(s['dni'])} dni"
        if klucz == "hp":
            return f"{_dopelnij(s['nazwa'], 40)} {_znak(s['punkty'])}"
        return f"{s.get('nazwa', '')}: {s.get('opis', '')}"


def czy_kolor(tryb: str) -> bool:
    if tryb == "zawsze":
        return True
    if tryb == "nigdy":
        return False
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def ekran(*, kto: str | None, wskazniki: str | None = None, kolor: str = "auto", rozbicie: bool = True,
          dane: dict | None = None) -> str:
    """Cały ekran jako tekst. `dane` = gotowy wynik `wskazniki.py --json` (testy, SF-289 w przyszłości)."""
    if dane is None:
        sciezka = znajdz_wskazniki(wskazniki)
        if not sciezka:
            raise BrakWskaznikow(
                "Ekran statusu potrzebuje scripts/lib/wskazniki.py z repo AProAgents (jedno źródło wzorów).\n"
                "Podaj ścieżkę: `sf-kit status --wskazniki <…/scripts/lib/wskazniki.py>` albo env SF_KIT_WSKAZNIKI.\n"
                "Panel w SalesForge (bez repo) — SF-289.")
        dom, manifest = dom_i_manifest(sciezka, kto)
        dane = pobierz(sciezka, dom, manifest)
    return Ekran(dane, kolor=czy_kolor(kolor)).rysuj(kto, rozbicie=rozbicie)
