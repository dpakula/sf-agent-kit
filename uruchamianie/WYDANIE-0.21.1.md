# SF Agent Kit 0.21.1 — wydanie poprawkowe

Gałąź `seweryn/kit-0211-wydanie` = `main` (v0.21.0, `738bda2`) + kandydat borysa `09dcfa1` (trzy scalenia) + podbicie wersji.

## Co wchodzi
- **SF-576** (`ce3f232`): `--tresc` z tekstem dłuższym niż 255 B nie kończy się już `OSError: File name too long` (Linux; na macOS z Pythonem 3.14 błąd się nie ujawniał). Długi tekst idzie jako treść. Długa ścieżka, której nie ma, i `--opis` z za długą nazwą dają czytelny błąd z kodem 2. Dotyczy wszystkich poleceń z `--tresc`/`--odpowiedz`.
- **ADVERTPR-1395** (`8fead01`): pełna treść przy odczycie. `sprawa` i `sprawa --json` pokazują najnowsze wpisy także na sprawach z ponad 200 wpisami. `blok <id>` dociąga pełną treść zamiast 400 znaków z rdzenia. `wpis-wersje --pelne` zachowuje wiersze. Działa link `…/tickets/numer/<NUMER>?org=…`.
- **SF-551** (`a959472`): poziom widoczności wpisu brany z odpowiedzi SF.

## Bramka (seweryn, 24.11.2026)
- Pakiet (`python3 -m unittest discover -s testy`, macOS): 932 testy. W czystych worktree 12 pełnych biegów naprzemiennie 0.21.0 / 0.21.1: 0 padów poza 2 błędami `test_onboarding_960` (pęk kluczy macOS, takie same na `main`). Kandydat 09dcfa1: 4 biegi, raz FAIL `test_puls_sf87` pod load ok. 20, osobno 10/10 na obu rewizjach. W katalogu głównego klonu 2 z 9 biegów dały 10 F + 1 E (`test_slug_z_sf_32`, `test_decyzja_sf188`), osobno zielone; ten sam wzór miał pierwszy bieg przy 0.21.0. To stan katalogu, nie kod (ten sam commit w worktree: 0 z 6).
- Linux (b5c3, Python 3.13): `test_tresc_dluga_sf576` na 0.21.0 daje 5 błędów `OSError`, na kandydacie OK. W pełnym pakiecie FAIL `test_ramka_i_codex` jest taki sam na 0.21.0 (drzewo z `git archive`, bez repo git).
- Żywy SF (SF-576, Org sf): `--tresc` 500 i 4 500 znaków oraz `--tresc PLIK` zapisane i odczytane bajt w bajt. `blok`: 0.21.0 ucina do ok. 400 znaków, 0.21.1 pokazuje pełne 4 500. ADVERTPR-1420: 200 wpisów → 449, najnowsze widoczne. Link po numerze działa (na 0.21.0 „nie rozumiem”).
- Pakiety (plugin, Codex, Kimi, Gemini) wygenerowane na nowo (`python3 -m sf_kit.pakiet --zapisz`, `--sprawdz` zgodny). Zmienił się tylko numer wersji.

## Wydanie
1. `main` ← `seweryn/kit-0211-wydanie` (ff), tag `v0.21.1`, push `main` + tag.
2. Ogłoszenie w SF (superadmin): `PUT /api/v1/super-admin/kit/version` `{"latest": "0.21.1", "min": "0.20.2", "tag": "v0.21.1", …, "breaking": false}`. Dopiero potem `sf-kit update` na flocie.
