# SF Agent Kit 0.21.2 — wydanie poprawkowe (ADVERTPR-1440)

Gałąź `seweryn/kit-0212-wydanie` = `main` (v0.21.1, `b0d5d53`) + `borys/adv1440-dlugie-sprawy` (`cfed74e`) + podbicie wersji
i przebudowa pakietów. 0.21.1 nie zostało ogłoszone w SF — to wydanie je zastępuje (zawiera SF-576, ADVERTPR-1395, SF-551).

## Co wchodzi (ADVERTPR-1440, borys-sf)
- `os`: `--limit` > 200 pobiera kolejne strony (`next_cursor`, bez 422), `--wszystkie` = cała oś; z `--json` treść ≥ 400 zn.
  uzupełniona z dziennika sprawy (jeden przebieg).
- `blok --json`: pełna treść (`tresc_z_dziennika: true`).
- `sprawa --wpis <id|skrót>`: jeden wpis w całości; `sprawa --ostatnie N`: N najnowszych (`--json` bez `--ostatnie` bez zmian).

## Bramka (seweryn, 24.11.2026) — wyniki we wpisie na ADVERTPR-1440
