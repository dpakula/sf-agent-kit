"""Pakiet SF Kita dla asystentów — generator z JEDNEGO manifestu (SF-201, Kit 0.16.0).

v1.0.0 (02.10.2026) - APro Agents / borys-sf · projekt: wpis 33cda66a na SF-201; GO Damiana 02.10 (SF-203)

PO CO
═════
Asystent w Claude Code ma mieć SalesForge „w swoich narzędziach”, a nie w README. Pakiet to:
komendy (cienkie nakładki na podkomendy `sf-kit`) i skille (wiedza „jak pracować w SF”).
Żeby wiedza nie żyła w trzech miejscach (README, Podręcznik, skille), źródła są DWA i tylko dwa:

- `pakiet/komendy.json` — manifest: komendy (id EN, aliasy PL, podkomenda CLI, rola, opis) i skille;
- `pakiet/wiedza/*.md` — treść skilli.

Z nich ten moduł GENERUJE plugin Claude Code (`plugin/`) i tabelę poleceń w README. Pliki
wygenerowane są w repozytorium (plugin instaluje się z gita), a test pilnuje, że zgadzają się
z manifestem — ręczna poprawka w `plugin/` zapali strażnika, zamiast cicho rozjechać źródła.

FORMAT (dokumentacja Claude Code „Plugins”, sprawdzone 02.10)
═════════════════════════════════════════════════════════════
- `plugin/.claude-plugin/plugin.json` — wymagane tylko `name`; `version` = wersja Kita.
- `plugin/commands/<nazwa>.md` → `/sf-kit:<nazwa>`; komendy i skille dzielą przestrzeń nazw
  pluginu, więc nazwy nie mogą się pokrywać (strażnik), a prefiks `sf-` byłby podwójny.
- `plugin/skills/<nazwa>/SKILL.md` z `description` we frontmatter (po nim Claude dobiera skill).
- Alias = osobny plik z TĄ SAMĄ wygenerowaną treścią (Claude Code nie ma aliasów komend).

Uruchomienie: `python3 -m sf_kit.pakiet --sprawdz` (CI/test) albo `--zapisz` (po zmianie manifestu).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parents[1]
MANIFEST = Path("pakiet/komendy.json")
KATALOG_PLUGINU = Path("plugin")
#: Marketplace = to samo repozytorium (dokumentacja: jedno repo może być marketplace'em i trzymać
#: plugin pod ścieżką względną). Instalacja: `/plugin marketplace add dpakula/sf-agent-kit`,
#: potem `/plugin install sf-kit@sf-plugins`. Osobne repo marketplace'u — pytanie Q-A na SF-201.
MARKETPLACE = Path(".claude-plugin/marketplace.json")
NAZWA_MARKETPLACE = "sf-plugins"
ROLE = ("wszyscy", "asystent", "agent")
KONCE = ("wpis", "blok", "nic")
NAZWA = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
README_START = "<!-- sf-kit:polecenia:start — tabelę generuje `python3 -m sf_kit.pakiet --zapisz` -->"
README_KONIEC = "<!-- sf-kit:polecenia:end -->"
NAGLOWEK = "<!-- wygenerowano z pakiet/komendy.json przez sf-kit {wersja}; nie edytuj ręcznie -->"
NARZEDZIA = "Bash(sf-kit:*), PowerShell(sf-kit *)"

ZAMKNIECIE = {
    "wpis": "Zamknij pracę WPISEM w sprawie według skilla `wpis-czytelny` i podaj człowiekowi link "
            "do sprawy. Nie zgłaszaj sukcesu, którego nie widać w SF.",
    "blok": "Pokaż człowiekowi treść i adresata bloku; jeśli trzeba odpowiedzieć, zrób to "
            "`sf-kit odpowiedz <sprawa> --blok #NUMER`.",
    "nic": "Pokaż wynik człowiekowi zwięźle; nie dopisuj niczego do SF bez jego prośby.",
}


class BladManifestu(ValueError):
    pass


def wczytaj(korzen: Path = KORZEN) -> dict:
    return json.loads((korzen / MANIFEST).read_text(encoding="utf-8"))


def waliduj(manifest: dict, podkomendy: set[str], korzen: Path = KORZEN) -> list[str]:
    """Strażnik manifestu — lista błędów (pusta = w porządku). Nic nie wywraca, żeby test pokazał wszystkie naraz."""
    bledy: list[str] = []
    nazwy: dict[str, str] = {}

    def zajmij(nazwa: str, czyje: str) -> None:
        if not NAZWA.match(nazwa or ""):
            bledy.append(f"{czyje}: nazwa „{nazwa}” — dozwolone małe litery, cyfry i myślnik")
        if nazwa in nazwy:
            bledy.append(f"{czyje}: nazwa „{nazwa}” zajęta już przez {nazwy[nazwa]} (komendy i skille "
                         "dzielą przestrzeń nazw pluginu)")
        nazwy[nazwa] = czyje

    skille = {s.get("id") for s in manifest.get("skille", [])}
    for s in manifest.get("skille", []):
        zajmij(s.get("id", ""), f"skill {s.get('id')}")
        if not (s.get("opis") or "").strip():
            bledy.append(f"skill {s.get('id')}: brak opisu (po nim Claude dobiera skill)")
        if s.get("rola") not in ROLE:
            bledy.append(f"skill {s.get('id')}: rola „{s.get('rola')}” spoza {ROLE}")
        if not (korzen / (s.get("zrodlo") or "")).is_file():
            bledy.append(f"skill {s.get('id')}: brak pliku źródłowego {s.get('zrodlo')}")
    for k in manifest.get("komendy", []):
        kid = k.get("id", "")
        zajmij(kid, f"komenda {kid}")
        for alias in k.get("aliasy", []):
            zajmij(alias, f"alias {alias} komendy {kid}")
        if k.get("cli") not in podkomendy:
            bledy.append(f"komenda {kid}: podkomendy `sf-kit {k.get('cli')}` nie ma w CLI")
        if k.get("rola") not in ROLE:
            bledy.append(f"komenda {kid}: rola „{k.get('rola')}” spoza {ROLE}")
        if k.get("konczy_sie") not in KONCE:
            bledy.append(f"komenda {kid}: konczy_sie „{k.get('konczy_sie')}” spoza {KONCE}")
        if not (k.get("opis") or {}).get("pl"):
            bledy.append(f"komenda {kid}: brak opisu po polsku")
        for sk in k.get("skille", []):
            if sk not in skille:
                bledy.append(f"komenda {kid}: skill „{sk}” nie istnieje w manifeście")
    return bledy


def _frontmatter(pola: dict) -> str:
    wiersze = ["---"]
    for klucz, wartosc in pola.items():
        if wartosc in (None, ""):
            continue
        wiersze.append(f"{klucz}: {json.dumps(wartosc, ensure_ascii=False)}")
    wiersze.append("---")
    return "\n".join(wiersze)


def _komenda(k: dict, nazwa: str, wersja: str) -> str:
    alias_od = None if nazwa == k["id"] else k["id"]
    opis = k["opis"]["pl"] + (f" — to samo co /sf-kit:{alias_od}" if alias_od else "")
    skille = ", ".join(f"`{s}`" for s in k.get("skille", []))
    tresc = [
        _frontmatter({"description": opis, "argument-hint": k.get("argumenty") or None,
                      "allowed-tools": NARZEDZIA,
                      # Komendę uruchamia CZŁOWIEK. Model sam jej nie odpali: `odpowiedz` domyślnie
                      # pisze do klienta, a 25 opisów w kontekście każdej sesji to ~1,3 tys. tokenów
                      # (pomiar `claude plugin details`, 02.10). Wiedzę model bierze ze skilli.
                      "disable-model-invocation": True}),
        NAGLOWEK.format(wersja=wersja),
        "",
        f"Uruchom w terminalu: `sf-kit {k['cli']} $ARGUMENTS`",
        "",
        "- Gdy człowiek nie podał wszystkiego, czego polecenie wymaga, zapytaj go jednym zdaniem — "
        "nie zgaduj numeru sprawy ani adresu.",
        "- Gdy masz kilka Organizacji, dodaj `--org <slug>` (sprawdzisz w `sf-kit whoami`).",
        "- Odmowę (403) przekaż człowiekowi wprost: uprawnienia ma klucz, nie obchodź jej inną drogą.",
        f"- {ZAMKNIECIE[k['konczy_sie']]}",
    ]
    if skille:
        tresc.append(f"- Zasady pracy: {'skille' if len(k.get('skille', [])) > 1 else 'skill'} {skille}.")
    return "\n".join(tresc) + "\n"


def _skill(s: dict, korzen: Path, wersja: str) -> str:
    wiedza = (korzen / s["zrodlo"]).read_text(encoding="utf-8").strip()
    return "\n".join([_frontmatter({"name": s["id"], "description": s["opis"]}),
                      NAGLOWEK.format(wersja=wersja), "", wiedza]) + "\n"


def plugin_json(manifest: dict, wersja: str) -> str:
    p = manifest["plugin"]
    dane = {"name": p["name"], "version": wersja, "description": p["description"], "author": p["author"]}
    return json.dumps(dane, ensure_ascii=False, indent=2) + "\n"


def marketplace_json(manifest: dict, wersja: str) -> str:
    p = manifest["plugin"]
    dane = {"name": NAZWA_MARKETPLACE, "owner": p["author"],
            "description": "Pluginy SalesForge dla asystentów (APro Agents)",
            "plugins": [{"name": p["name"], "source": f"./{KATALOG_PLUGINU.as_posix()}",
                         "description": p["description"], "version": wersja}]}
    return json.dumps(dane, ensure_ascii=False, indent=2) + "\n"


def generuj(manifest: dict, wersja: str, korzen: Path = KORZEN, *, role=ROLE) -> dict[Path, str]:
    """Wszystkie pliki pakietu: ścieżka względna od korzenia repo → treść. Deterministycznie."""
    pliki: dict[Path, str] = {
        MARKETPLACE: marketplace_json(manifest, wersja),
        KATALOG_PLUGINU / ".claude-plugin" / "plugin.json": plugin_json(manifest, wersja)}
    for k in manifest["komendy"]:
        if k["rola"] not in role:
            continue
        for nazwa in [k["id"], *k.get("aliasy", [])]:
            pliki[KATALOG_PLUGINU / "commands" / f"{nazwa}.md"] = _komenda(k, nazwa, wersja)
    for s in manifest["skille"]:
        if s["rola"] not in role:
            continue
        pliki[KATALOG_PLUGINU / "skills" / s["id"] / "SKILL.md"] = _skill(s, korzen, wersja)
    return pliki


def tabela_readme(manifest: dict) -> str:
    wiersze = [README_START, "",
               "| w Claude Code | po polsku | w terminalu | co robi |", "|---|---|---|---|"]
    for k in manifest["komendy"]:
        pl = ", ".join(f"`/sf-kit:{a}`" for a in k.get("aliasy", [])) or "—"
        wiersze.append(f"| `/sf-kit:{k['id']}` | {pl} | `sf-kit {k['cli']}` | {k['opis']['pl']} |")
    wiersze += ["", README_KONIEC]
    return "\n".join(wiersze)


def wstaw_do_readme(readme: str, tabela: str) -> str:
    """Podmień sekcję między znacznikami; bez znaczników — dopisz na końcu (pierwsze wygenerowanie)."""
    if README_START in readme and README_KONIEC in readme:
        przed = readme.split(README_START, 1)[0]
        po = readme.split(README_KONIEC, 1)[1]
        return przed + tabela + po
    return readme.rstrip("\n") + "\n\n## Polecenia w Claude Code (plugin `sf-kit`)\n\n" + tabela + "\n"


def roznice(korzen: Path = KORZEN) -> list[str]:
    """Czym repozytorium różni się od tego, co wygenerowałby manifest. Pusta lista = zgodne."""
    from . import WERSJA
    manifest = wczytaj(korzen)
    wynik = []
    oczekiwane = generuj(manifest, WERSJA, korzen)
    for sciezka, tresc in oczekiwane.items():
        plik = korzen / sciezka
        if not plik.is_file():
            wynik.append(f"brak {sciezka}")
        elif plik.read_text(encoding="utf-8") != tresc:
            wynik.append(f"różni się {sciezka}")
    for plik in (korzen / KATALOG_PLUGINU).rglob("*") if (korzen / KATALOG_PLUGINU).exists() else []:
        if plik.is_file() and plik.relative_to(korzen) not in oczekiwane:
            wynik.append(f"nadmiarowy {plik.relative_to(korzen)} (nie ma go w manifeście)")
    readme = (korzen / "README.md").read_text(encoding="utf-8")
    if wstaw_do_readme(readme, tabela_readme(manifest)) != readme:
        wynik.append("README: tabela poleceń nie zgadza się z manifestem")
    return wynik


def zapisz(korzen: Path = KORZEN) -> list[Path]:
    from . import WERSJA
    manifest = wczytaj(korzen)
    oczekiwane = generuj(manifest, WERSJA, korzen)
    katalog = korzen / KATALOG_PLUGINU
    if katalog.exists():
        for plik in sorted(katalog.rglob("*"), reverse=True):
            if plik.is_file() and plik.relative_to(korzen) not in oczekiwane:
                plik.unlink()
    for sciezka, tresc in oczekiwane.items():
        (korzen / sciezka).parent.mkdir(parents=True, exist_ok=True)
        (korzen / sciezka).write_text(tresc, encoding="utf-8")
    readme = korzen / "README.md"
    readme.write_text(wstaw_do_readme(readme.read_text(encoding="utf-8"), tabela_readme(manifest)),
                      encoding="utf-8")
    return sorted(oczekiwane)


def _podkomendy() -> set[str]:
    from . import cli
    parser = cli.zbuduj_parser()
    return {n for a in parser._actions if isinstance(a, argparse._SubParsersAction) for n in a.choices}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m sf_kit.pakiet",
                                 description="Generator pakietu SF Kita (plugin Claude Code) z manifestu")
    tryb = ap.add_mutually_exclusive_group(required=True)
    tryb.add_argument("--sprawdz", action="store_true", help="tylko porównaj; kod 1 przy rozjeździe")
    tryb.add_argument("--zapisz", action="store_true", help="wygeneruj plugin/ i tabelę w README")
    args = ap.parse_args(argv)
    bledy = waliduj(wczytaj(), _podkomendy())
    if bledy:
        print("Manifest ma błędy:\n  " + "\n  ".join(bledy), file=sys.stderr)
        return 2
    if args.zapisz:
        for p in zapisz():
            print(f"  {p}")
        return 0
    rozjazd = roznice()
    if rozjazd:
        print("Pakiet nie zgadza się z manifestem (uruchom `--zapisz`):\n  " + "\n  ".join(rozjazd),
              file=sys.stderr)
        return 1
    print("Pakiet zgodny z manifestem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
