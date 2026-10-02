"""Pakiet SF Kita dla asystentów — generator z JEDNEGO manifestu (SF-201, Kit 0.16.0).

v1.3.0 (02.10.2026) - APro Agents / borys-sf · pakiet GEMINI CLI jako rozszerzenie (SF-203)
v1.2.0 (02.10.2026) - APro Agents / borys-sf · pakiet KIMI CODE z tego samego manifestu (SF-203, Agata 14:12)
v1.1.0 (02.10.2026) - APro Agents / borys-sf · pakiet CODEX z tego samego manifestu (SF-203, Agata 14:00)
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

CODEX (dokumentacja Codex CLI, sprawdzone 02.10 — learn.chatgpt.com/docs: agents-md, build-skills,
custom-prompts)
══════════════════════════════════════════════════════════════════════════════════════
- Własne prompty (`~/.codex/prompts`) są PRZESTARZAŁE — Codex każe używać skilli. Komendy idą więc
  jako skille `sf-<nazwa>` (wywołanie `$sf-zglos`) z `agents/openai.yaml`
  `policy.allow_implicit_invocation: false` — odpowiednik „model sam nie wywołuje” z Claude Code.
- Skille wiedzy: `sf-<id>` (Codex nie ma przestrzeni nazw pluginu, prefiks jest konieczny).
- `codex/AGENTS.md` — sekcja Kita do globalnego `AGENTS.md` (CODEX_HOME): tabela komend z aliasami.
  Codex łączy pliki AGENTS.md do 32 KiB — strażnik pilnuje, żeby nasza sekcja była mała.

KIMI CODE (`@moonshot-ai/kimi-code`; dokumentacja moonshotai.github.io/kimi-code, czytane 02.10)
══════════════════════════════════════════════════════════════════════════════════════
- Instrukcje: globalny `AGENTS.md` w `KIMI_CODE_HOME` (domyślnie `~/.kimi-code`).
- Skille: `KIMI_CODE_HOME/skills/<nazwa>/SKILL.md` (wymagane `name` i `description`); wywołanie
  `/skill:<nazwa>`; w treści DZIAŁA `$ARGUMENTS`; `disable-model-invocation: true` = model sam nie wywoła.
- Osobnych komend poza pluginami Kimi nie ma — komendy idą jako skille, jak w Codexie.
- Binarki Kimi NIE uruchamiamy do sprawdzania formatu (decyzja Agaty 02.10: presja pamięci na b5c3).

GEMINI CLI (dokumentacja google-gemini/gemini-cli docs/: extensions/reference, cli/custom-commands,
cli/skills — czytane 02.10)
═══════════════════════════════════════════════════════════════════════════════════
- Pakiet = ROZSZERZENIE `gemini/` (odpowiednik pluginu Claude): `gemini-extension.json` (name = nazwa
  katalogu), `GEMINI.md` jako `contextFileName` — globalnego GEMINI.md użytkownika nie ruszamy.
- Komendy: `commands/sf/<nazwa>.toml` (`prompt`, `description`) → `/sf:<nazwa>`; podkatalog daje
  przestrzeń nazw, więc nie kolidujemy z komendami użytkownika. `{{args}}` = argumenty. Dokumentacja
  opisuje komendy jako wywoływane przez użytkownika.
- Skille wiedzy: `skills/<nazwa>/SKILL.md` (rozszerzenie może je nieść; Gemini aktywuje je za zgodą).

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
KATALOG_CODEX = Path("codex")
CODEX_START = "<!-- sf-kit:codex:start — sekcję zapisuje `sf-kit init --codex`; zmiany w niej nadpisze -->"
CODEX_KONIEC = "<!-- sf-kit:codex:end -->"
#: Nasza część globalnego AGENTS.md. Codex łączy WSZYSTKIE pliki AGENTS.md do 32 KiB (domyślnie);
#: sekcja Kita nie może zjeść tego budżetu cudzym instrukcjom.
CODEX_MAKS_BAJTOW = 8 * 1024
KATALOG_KIMI = Path("kimi")
KIMI_START = "<!-- sf-kit:kimi:start — sekcję zapisuje `sf-kit init --kimi`; zmiany w niej nadpisze -->"
KIMI_KONIEC = "<!-- sf-kit:kimi:end -->"
KATALOG_GEMINI = Path("gemini")
#: Serwer MCP Kita — ten sam wpis dla Claude (plugin), Kimi (mcp.json) i Gemini (rozszerzenie).
MCP_SERWER = {"mcpServers": {"sf-kit": {"command": "sf-kit", "args": ["mcp"]}}}

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
        for pole in ("tylko_odczyt", "mcp"):
            if not isinstance(k.get(pole), bool):
                bledy.append(f"komenda {kid}: pole `{pole}` musi być true/false (MCP: adnotacja i dostępność)")
        if k.get("mcp") and k.get("cli") in ("update", "aktualizuj", "init", "instaluj"):
            bledy.append(f"komenda {kid}: `sf-kit {k.get('cli')}` zmienia instalację Kita — nie może być narzędziem MCP")
        for sk in k.get("skille", []):
            if sk not in skille:
                bledy.append(f"komenda {kid}: skill „{sk}” nie istnieje w manifeście")
    if not bledy:
        rozmiar = len(agents_md_codex(manifest, "0.0.0").encode("utf-8"))
        if rozmiar > CODEX_MAKS_BAJTOW:
            bledy.append(f"Codex: sekcja AGENTS.md ma {rozmiar} B > {CODEX_MAKS_BAJTOW} B "
                         "(Codex łączy wszystkie AGENTS.md do 32 KiB)")
        rozmiar = len(agents_md_kimi(manifest, "0.0.0").encode("utf-8"))
        if rozmiar > CODEX_MAKS_BAJTOW:
            bledy.append(f"Kimi: sekcja AGENTS.md ma {rozmiar} B > {CODEX_MAKS_BAJTOW} B")
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
        KATALOG_PLUGINU / ".claude-plugin" / "plugin.json": plugin_json(manifest, wersja),
        # SF-203: serwer MCP Kita startuje z pluginem (dokumentacja: `.mcp.json` w korzeniu pluginu).
        # `sf-kit` z PATH, klucz z magazynu Kita — w konfiguracji pluginu nie ma żadnego sekretu.
        KATALOG_PLUGINU / ".mcp.json": json.dumps(MCP_SERWER, ensure_ascii=False, indent=2) + "\n"}
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


# ── Codex ──────────────────────────────────────────────────────────────────────────────────

def nazwa_codex(nazwa: str) -> str:
    return f"sf-{nazwa}"


def _codexuj(tekst: str, manifest: dict) -> str:
    """Treść z pakietu Claude → Codex: nazwy skilli z prefiksem, odwołania `/sf-kit:x` → `$sf-x`,
    bez `$ARGUMENTS` (to podstawienie promptów; skill dostaje prośbę człowieka, nie argumenty)."""
    tekst = tekst.replace("/sf-kit:", "$sf-").replace(" $ARGUMENTS`", " …` (argumenty z prośby człowieka)")
    for s in manifest["skille"]:
        tekst = tekst.replace(f"`{s['id']}`", f"`{nazwa_codex(s['id'])}`")
    return tekst


def _openai_yaml_komendy() -> str:
    return ("# wygenerowano z pakiet/komendy.json — komendę uruchamia człowiek ($nazwa), model sam jej nie wywołuje\n"
            "policy:\n  allow_implicit_invocation: false\n")


def agents_md_codex(manifest: dict, wersja: str) -> str:
    """Sekcja Kita do globalnego AGENTS.md Codexa — mała, bo Codex ma wspólny limit 32 KiB."""
    wiersze = [CODEX_START, NAGLOWEK.format(wersja=wersja), "",
               "## SalesForge przez SF Kit",
               "Pracujesz w SalesForge (SF) WYŁĄCZNIE poleceniami `sf-kit` w terminalu — nigdy surowym `curl` "
               "z kluczem. Uprawnienia ma klucz; odmowę (403) przekaż człowiekowi, nie obchodź jej.",
               "",
               "- `sf-kit odpowiedz` domyślnie pisze DO KLIENTA; notatka zespołu: `--wewn`. `sf-kit wpis` domyślnie wewnętrzny.",
               "- Wzmianka działa tylko pełnym adresem: `@anna@firma.pl`.",
               "- Praca jest oddana, gdy jest w SF (wpis/sprawa) — nie zgłaszaj sukcesu, którego nie widać w SF.",
               f"- Zasady pracy: skille {', '.join(f'`${nazwa_codex(s['id'])}`' for s in manifest['skille'])}.",
               "",
               "| skill (Codex) | po polsku | w terminalu | co robi |", "|---|---|---|---|"]
    for k in manifest["komendy"]:
        if k["rola"] != "wszyscy":
            continue
        pl = ", ".join(f"`${nazwa_codex(a)}`" for a in k.get("aliasy", [])) or "—"
        wiersze.append(f"| `${nazwa_codex(k['id'])}` | {pl} | `sf-kit {k['cli']}` | {k['opis']['pl']} |")
    wiersze += ["", CODEX_KONIEC]
    return "\n".join(wiersze) + "\n"


def generuj_codex(manifest: dict, wersja: str, korzen: Path = KORZEN, *, role=ROLE) -> dict[Path, str]:
    """Pakiet Codex: sekcja AGENTS.md + skille (komendy z wyłączonym wywołaniem przez model, wiedza)."""
    pliki: dict[Path, str] = {KATALOG_CODEX / "AGENTS.md": agents_md_codex(manifest, wersja)}
    for k in manifest["komendy"]:
        if k["rola"] not in role:
            continue
        for nazwa in [k["id"], *k.get("aliasy", [])]:
            n = nazwa_codex(nazwa)
            tresc = _codexuj(_komenda(k, nazwa, wersja), manifest)
            naglowek, cialo = tresc.split("---\n", 2)[1], tresc.split("---\n", 2)[2]
            pola = {"name": n}
            for linia in naglowek.splitlines():
                klucz = linia.split(":", 1)[0]
                if klucz == "description":
                    pola["description"] = json.loads(linia.split(":", 1)[1])
            if k.get("argumenty"):
                cialo = cialo.replace("(argumenty z prośby człowieka)",
                                      f"(argumenty z prośby człowieka; składnia: `{k['argumenty']}`)")
            pliki[KATALOG_CODEX / "skills" / n / "SKILL.md"] = _frontmatter(pola) + "\n" + cialo
            pliki[KATALOG_CODEX / "skills" / n / "agents" / "openai.yaml"] = _openai_yaml_komendy()
    for s in manifest["skille"]:
        if s["rola"] not in role:
            continue
        n = nazwa_codex(s["id"])
        tresc = _codexuj(_skill({**s, "id": n}, korzen, wersja), manifest)
        pliki[KATALOG_CODEX / "skills" / n / "SKILL.md"] = tresc
    return pliki


# ── Kimi Code ──────────────────────────────────────────────────────────────────────────────

def _kimiuj(tekst: str, manifest: dict) -> str:
    """Treść z pakietu Claude → Kimi Code: `/sf-kit:x` → `/skill:sf-x`, skille z prefiksem; `$ARGUMENTS` zostaje."""
    tekst = tekst.replace("/sf-kit:", "/skill:sf-")
    for s in manifest["skille"]:
        tekst = tekst.replace(f"`{s['id']}`", f"`{nazwa_codex(s['id'])}`")
    return tekst


def agents_md_kimi(manifest: dict, wersja: str) -> str:
    sekcja = agents_md_codex(manifest, wersja)
    sekcja = sekcja.replace(CODEX_START, KIMI_START).replace(CODEX_KONIEC, KIMI_KONIEC)
    sekcja = sekcja.replace("| skill (Codex) |", "| skill (Kimi Code) |")
    return re.sub(r"`\$(sf-[a-z0-9-]+)`", r"`/skill:\1`", sekcja)


def generuj_kimi(manifest: dict, wersja: str, korzen: Path = KORZEN, *, role=ROLE) -> dict[Path, str]:
    """Pakiet Kimi Code: sekcja AGENTS.md + skille (komendy z `disable-model-invocation`, wiedza)."""
    pliki: dict[Path, str] = {KATALOG_KIMI / "AGENTS.md": agents_md_kimi(manifest, wersja)}
    for k in manifest["komendy"]:
        if k["rola"] not in role:
            continue
        for nazwa in [k["id"], *k.get("aliasy", [])]:
            n = nazwa_codex(nazwa)
            tresc = _kimiuj(_komenda(k, nazwa, wersja), manifest)
            naglowek, cialo = tresc.split("---\n", 2)[1], tresc.split("---\n", 2)[2]
            pola = {"name": n}
            for linia in naglowek.splitlines():
                if linia.startswith("description:"):
                    pola["description"] = json.loads(linia.split(":", 1)[1])
            pola["disable-model-invocation"] = True
            pliki[KATALOG_KIMI / "skills" / n / "SKILL.md"] = _frontmatter(pola) + "\n" + cialo
    for s in manifest["skille"]:
        if s["rola"] not in role:
            continue
        n = nazwa_codex(s["id"])
        pliki[KATALOG_KIMI / "skills" / n / "SKILL.md"] = _kimiuj(_skill({**s, "id": n}, korzen, wersja), manifest)
    return pliki


# ── Gemini CLI (rozszerzenie) ──────────────────────────────────────────────────────────────

def _toml_napis(tekst: str) -> str:
    """Podstawowy napis TOML: JSON-owe ucieczki są jego podzbiorem (\\n, \\", \\\\); polskie znaki wprost."""
    return json.dumps(tekst, ensure_ascii=False)


def _geminiuj(tekst: str, manifest: dict) -> str:
    tekst = tekst.replace("/sf-kit:", "/sf:").replace(" $ARGUMENTS`", " {{args}}`")
    for s in manifest["skille"]:
        tekst = tekst.replace(f"`{s['id']}`", f"`{nazwa_codex(s['id'])}`")
    return tekst


def generuj_gemini(manifest: dict, wersja: str, korzen: Path = KORZEN, *, role=ROLE) -> dict[Path, str]:
    """Rozszerzenie Gemini CLI: manifest, GEMINI.md (kontekst), komendy TOML `/sf:…`, skille wiedzy."""
    p = manifest["plugin"]
    rozszerzenie = {"name": p["name"], "version": wersja, "description": p["description"],
                    "contextFileName": "GEMINI.md",
                    # SF-203: serwer MCP Kita z rozszerzeniem (dokumentacja: `mcpServers` w manifeście).
                    "mcpServers": MCP_SERWER["mcpServers"]}
    kontekst = agents_md_codex(manifest, wersja)
    kontekst = kontekst.replace("| skill (Codex) |", "| komenda (Gemini) |")
    # Osobny plik kontekstu rozszerzenia, nie sekcja w cudzym pliku — znaczniki sekcji tu tylko mylą.
    kontekst = kontekst.replace(CODEX_START + "\n", "").replace("\n" + CODEX_KONIEC, "")
    kontekst = re.sub(r"`\$(sf-[a-z0-9-]+)`", lambda m: (
        f"`{m.group(1)}`" if any(m.group(1) == nazwa_codex(s["id"]) for s in manifest["skille"])
        else f"`/sf:{m.group(1)[3:]}`"), kontekst)
    pliki: dict[Path, str] = {
        KATALOG_GEMINI / "gemini-extension.json": json.dumps(rozszerzenie, ensure_ascii=False, indent=2) + "\n",
        KATALOG_GEMINI / "GEMINI.md": kontekst,
    }
    for k in manifest["komendy"]:
        if k["rola"] not in role:
            continue
        for nazwa in [k["id"], *k.get("aliasy", [])]:
            tresc = _geminiuj(_komenda(k, nazwa, wersja), manifest)
            naglowek, cialo = tresc.split("---\n", 2)[1], tresc.split("---\n", 2)[2]
            opis = next(json.loads(l.split(":", 1)[1]) for l in naglowek.splitlines() if l.startswith("description:"))
            if k.get("argumenty"):
                opis += f" — {k['argumenty']}"
            pliki[KATALOG_GEMINI / "commands" / "sf" / f"{nazwa}.toml"] = (
                f"# {NAGLOWEK.format(wersja=wersja)[5:-4]}\n"
                f"description = {_toml_napis(opis)}\n"
                f"prompt = {_toml_napis(cialo.split(chr(10), 2)[2] if cialo.startswith('<!--') else cialo)}\n")
    for s in manifest["skille"]:
        if s["rola"] not in role:
            continue
        n = nazwa_codex(s["id"])
        pliki[KATALOG_GEMINI / "skills" / n / "SKILL.md"] = _geminiuj(_skill({**s, "id": n}, korzen, wersja), manifest)
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
    oczekiwane = {**generuj(manifest, WERSJA, korzen), **generuj_codex(manifest, WERSJA, korzen),
                  **generuj_kimi(manifest, WERSJA, korzen), **generuj_gemini(manifest, WERSJA, korzen)}
    for sciezka, tresc in oczekiwane.items():
        plik = korzen / sciezka
        if not plik.is_file():
            wynik.append(f"brak {sciezka}")
        elif plik.read_text(encoding="utf-8") != tresc:
            wynik.append(f"różni się {sciezka}")
    for katalog in (KATALOG_PLUGINU, KATALOG_CODEX, KATALOG_KIMI, KATALOG_GEMINI):
        for plik in (korzen / katalog).rglob("*") if (korzen / katalog).exists() else []:
            if plik.is_file() and plik.relative_to(korzen) not in oczekiwane:
                wynik.append(f"nadmiarowy {plik.relative_to(korzen)} (nie ma go w manifeście)")
    readme = (korzen / "README.md").read_text(encoding="utf-8")
    if wstaw_do_readme(readme, tabela_readme(manifest)) != readme:
        wynik.append("README: tabela poleceń nie zgadza się z manifestem")
    return wynik


def zapisz(korzen: Path = KORZEN) -> list[Path]:
    from . import WERSJA
    manifest = wczytaj(korzen)
    oczekiwane = {**generuj(manifest, WERSJA, korzen), **generuj_codex(manifest, WERSJA, korzen),
                  **generuj_kimi(manifest, WERSJA, korzen), **generuj_gemini(manifest, WERSJA, korzen)}
    for kat in (KATALOG_PLUGINU, KATALOG_CODEX, KATALOG_KIMI, KATALOG_GEMINI):
        katalog = korzen / kat
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
