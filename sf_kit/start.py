"""`sf-kit start` — przygotuj bieżący katalog do pracy z asystentem (ADVERTPR-987, 0.15.1).

v1.0.0 (30.09.2026) - APro Agents / borys-sf

PO CO
═════
Do 0.15.0 człowiek po `sf-kit init` uruchamiał `claude` i WKLEJAŁ tekst startowy z README.
Nowicjusz na szkoleniu (Windows, pierwszy raz w terminalu) gubi się na tym kroku najczęściej:
nie wie, co skopiować, zapomina wpisać slug Organizacji, a potem Claude Code przy KAŻDYM
poleceniu Kita pyta „Do you want to proceed?”. `start` zapisuje w katalogu pracy trzy pliki,
które Claude Code i Codex czytają same:

- `CLAUDE.md` (Claude Code) i `AGENTS.md` (Codex, Kimi): krótka instrukcja asystenta
  z wpisaną Organizacją i ścieżką do pełnego README,
- `.claude/settings.json`: reguła `Bash(sf-kit:*)`, dzięki której polecenia Kita nie wymagają
  potwierdzenia. Reguła obejmuje WYŁĄCZNIE `sf-kit`, a to, co Kit może zrobić, i tak
  rozstrzygają uprawnienia klucza po stronie SalesForge.

CUDZA TREŚĆ ZOSTAJE
═══════════════════
Nasza sekcja siedzi między znacznikami `<!-- sf-kit:start -->` i `<!-- sf-kit:end -->`.
Ponowne `start` podmienia tylko ją; resztę pliku zostawia bajt w bajt. `settings.json`
czytamy i dopisujemy regułę; zepsutego JSON-a NIE nadpisujemy (człowiek mógł tam mieć
coś ważnego) — mówimy, co dopisać ręcznie.
"""
from __future__ import annotations

import json
from pathlib import Path

ZNACZNIK_START = "<!-- sf-kit:start — tę sekcję zapisuje `sf-kit start`; zmiany w niej nadpisze -->"
ZNACZNIK_KONIEC = "<!-- sf-kit:end -->"
#: Claude Code ma DWA narzędzia powłoki i reguły są osobne (dokumentacja „permissions”, sekcja
#: PowerShell): na Windows bez Git for Windows polecenia idą przez PowerShell i `Bash(…)` ich nie
#: obejmuje — kursant ForMarketing dostałby pytanie przy każdym poleceniu Kita (0.15.2).
REGULY = ("Bash(sf-kit:*)", "PowerShell(sf-kit *)")
PLIKI_INSTRUKCJI = ("CLAUDE.md", "AGENTS.md")


def instrukcja(*, org_slug: str, org_nazwa: str, readme: Path, agent: str | None) -> str:
    """Treść sekcji — dla Claude Code, Codexa i Kimi ta sama."""
    k = "sf-kit" + (f" --agent {agent}" if agent else "") + f" --org {org_slug}"
    return f"""{ZNACZNIK_START}
# Praca w SalesForge (SF Agent Kit)

Jesteś asystentem człowieka, który z Tobą rozmawia. W SalesForge działasz WYŁĄCZNIE poleceniem
`sf-kit` — nie wchodzisz na stronę SF i nie wołasz API ręcznie.

- **Organizacja:** {org_nazwa} — w każdym poleceniu podawaj `--org {org_slug}` (przed nazwą polecenia).
- **Pełna instrukcja:** `sf-kit readme --tresc` (sekcja „Dla agenta”; plik: `{readme}`). Gdy nie wiesz,
  jak coś zrobić — przeczytaj ją tym poleceniem, nie zgaduj. Czytaj ją poleceniem, nie z pliku:
  plik leży poza tym katalogiem i Claude Code pytałby człowieka o zgodę na odczyt.
- **Na początku rozmowy** uruchom `{k} whoami` i powiedz człowiekowi zwykłym językiem, kim jesteś w SF i co możesz.

## Człowiek mówi → Ty robisz

| człowiek mówi | polecenie |
|---|---|
| „pokaż sprawy” | `{k} sprawy` (ostatnie sprawy całej Organizacji, nie tylko tej osoby — tak to powiedz) |
| „co jest w sprawie <link albo numer>” | `{k} sprawa <link albo numer>` |
| „zgłoś sprawę: …” | `{k} zglos --tytul "…" --opis -` + treść (niżej) |
| „odpowiedz w tej sprawie: …” | `{k} odpowiedz <link> --opis -` (wiadomość widoczna na zewnątrz) albo z `--wewn` (notatka dla zespołu) |
| „dopisz postęp / notatkę” | `{k} wpis <link> --opis -` |
| „załącz plik” | `{k} zalacz <link> plik [plik…]` |

**Treść podawaj przez standardowe wejście, w tym samym poleceniu** — bez zakładania plików
(każdy nowy plik Claude Code każe człowiekowi osobno zatwierdzić):

```
{k} zglos --tytul "Ankieta po szkoleniu" --opis - <<'EOF'
## Co trzeba zrobić
…
EOF
```

W PowerShellu (Windows bez Git Bash) heredoc nie istnieje — ten sam tekst podaj rurą:

```
@'
## Co trzeba zrobić
…
'@ | {k} zglos --tytul "Ankieta po szkoleniu" --opis -
```

## Zasady

1. Człowiek podał link do sprawy → pracujesz w TEJ sprawie. Nową zakładasz tylko, gdy żadnej nie ma.
2. **Zanim cokolwiek zapiszesz w SF** (sprawa, odpowiedź, wpis, załącznik), pokaż człowiekowi,
   co wyślesz, i zapytaj o zgodę. Przy `odpowiedz` zapytaj też: do klienta czy notatka dla zespołu (`--wewn`)?
3. Po zapisie podaj człowiekowi numer i link, które wypisał Kit.
4. Nie pytaj o klucz i nie proś o wklejenie go w rozmowie — klucz wpisuje człowiek sam w `sf-kit init`.
5. Kit odmówił (brak uprawnienia, brak Organizacji)? Powiedz zwykłym językiem, czego brakuje
   i kogo poprosić. Nie obchodź odmowy innym poleceniem.
{ZNACZNIK_KONIEC}
"""


def wstaw_sekcje(istniejacy: str | None, sekcja: str) -> str:
    """Plik z naszą sekcją: podmiana między znacznikami albo dopisanie na końcu."""
    if not istniejacy:
        return sekcja
    poczatek = istniejacy.find(ZNACZNIK_START)
    koniec = istniejacy.find(ZNACZNIK_KONIEC, poczatek if poczatek >= 0 else 0)
    if poczatek >= 0 and koniec > poczatek:
        koniec += len(ZNACZNIK_KONIEC)
        if istniejacy[koniec:koniec + 1] == "\n":
            koniec += 1
        return istniejacy[:poczatek] + sekcja + istniejacy[koniec:]
    return istniejacy.rstrip("\n") + "\n\n" + sekcja


class ZepsutyPlik(Exception):
    """`settings.json` istnieje, ale nie jest obiektem JSON — nie nadpisujemy go."""


def dopisz_regule(istniejacy: str | None) -> tuple[str, bool]:
    """`(nowa treść, czy coś zmieniono)`. Rzuca `ZepsutyPlik`, gdy nie umiemy bezpiecznie dopisać."""
    if istniejacy is None or not istniejacy.strip():
        dane: dict = {}
    else:
        try:
            dane = json.loads(istniejacy)
        except ValueError:
            raise ZepsutyPlik("to nie jest poprawny JSON") from None
        if not isinstance(dane, dict):
            raise ZepsutyPlik("oczekiwałem obiektu JSON")
    uprawnienia = dane.setdefault("permissions", {})
    if not isinstance(uprawnienia, dict):
        raise ZepsutyPlik("pole `permissions` nie jest obiektem")
    dozwolone = uprawnienia.setdefault("allow", [])
    if not isinstance(dozwolone, list):
        raise ZepsutyPlik("pole `permissions.allow` nie jest listą")
    brakujace = [r for r in REGULY if r not in dozwolone]
    if not brakujace:
        return istniejacy or "", False
    dozwolone.extend(brakujace)
    return json.dumps(dane, ensure_ascii=False, indent=2) + "\n", True


def przygotuj(katalog: Path, *, org_slug: str, org_nazwa: str, readme: Path,
              agent: str | None) -> list[str]:
    """Zapisz pliki w `katalog`. Zwraca linie raportu dla człowieka (co zrobiono)."""
    raport: list[str] = []
    sekcja = instrukcja(org_slug=org_slug, org_nazwa=org_nazwa, readme=readme, agent=agent)
    for nazwa in PLIKI_INSTRUKCJI:
        plik = katalog / nazwa
        stary = plik.read_text(encoding="utf-8") if plik.exists() else None
        nowy = wstaw_sekcje(stary, sekcja)
        if nowy != stary:
            plik.write_text(nowy, encoding="utf-8")
        raport.append(f"  {nazwa:<22} {'zapisany' if stary is None else ('bez zmian' if nowy == stary else 'zaktualizowana sekcja Kita')}")

    ustawienia = katalog / ".claude" / "settings.json"
    stary = ustawienia.read_text(encoding="utf-8") if ustawienia.exists() else None
    try:
        nowy, zmiana = dopisz_regule(stary)
    except ZepsutyPlik as blad:
        raport.append(f"  .claude/settings.json  NIE ZMIENIONY ({blad}) — dopisz ręcznie "
                      f"do \"permissions\": {{\"allow\": [...]}} reguły {', '.join(chr(34) + r + chr(34) for r in REGULY)}")
        return raport
    if zmiana:
        ustawienia.parent.mkdir(parents=True, exist_ok=True)
        ustawienia.write_text(nowy, encoding="utf-8")
    raport.append(f"  .claude/settings.json  {'dopisane reguły ' + ', '.join(REGULY) if zmiana else 'reguły już były'}")
    return raport
