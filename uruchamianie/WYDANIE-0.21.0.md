SF Agent Kit 0.21.0: `sf-kit tura zamknij` (SF-574). Zamknięcie tury koordynatora jednym poleceniem Kita

STAN: DO BRAMKI 24.11.2026 (arek-sf, polecenie Agaty 24.11 01:54 po decyzji Damiana „materializować od razu, bez powrotu”).
Gałąź `arek/kit-0210-wydanie` = `main` (v0.20.2) + `arek/sf574-tura-zamknij` + podbicie wersji.
**Push `main` i tagu robi seweryn albo Damian.** Potem ogłoszenie w SF (`PUT /super-admin/kit/version`), dopiero wtedy `sf-kit update` na flocie.

## Dlaczego

Zamknięcie tury żyło w lokalnej komendzie koordynatorki (`/next-turn`), więc poza kontraktem Kita.
Inny koordynator, inna Organizacja albo inna maszyna nie miały go wcale. Kit miał tylko `krok nowy` i `krok zamknij`.
Damian 09.11: „wszystko, co dotyczy pracy agenta w SalesForge, ma być SF Kit”.

## Nowe

**`sf-kit --org <org konsoli> tura zamknij --opis stan.md`.** Stan to markdown: co robione, status, zrobione, delegowane.
Kit czyta z niego dwie sekcje: `## Następny krok` i `## Decyzje`. Można je też podać flagami `--nastepny` i `--decyzja` (wiele razy).
Turę bez decyzji oznacza się `--bez-decyzji`.

| # | co robi | skąd |
|---|---|---|
| 1 | **krok:** `--krok`, potem plik rozgrywki (ustawienie `rozgrywka`), potem najnowszy krok Organizacji w SF. Gdy krok jest już **zamknięty**, a po zamknięciu powstały kickoffy, bloki albo decyzje, Kit zakłada **nowy krok** i to on dostaje stan. Zamknięty krok bez pracy po nim dostaje dopisek bez zmiany statusu | `GET /tickets/{id}`, `GET /konsola/kroki`, `POST /kroki/dzis` |
| 2 | **kickoffy tury:** zadania założone przez Twoje konto od otwarcia kroku (`--od` zmienia początek), we wszystkich Organizacjach klucza | `GET /tasks?date_field=created_at&date_from=` + `created_by` |
| 3 | **pomiar:** to samo liczenie co `sf-kit status`. Bez `wskazniki.py` Kit bierze presję Organizacji z SF. Brak pomiaru nie przerywa tury | `wskazniki.py` / `GET /tasks/presja` |
| 4 | **ślad decyzji człowieka:** każdy punkt wskazuje `#blok`, `SPRAWA-N`, link sprawy albo `wpis <id>`. Bloki i sprawy Kit sprawdza w SF. Brak śladu = brak w wyniku (kod 3), nie przemilczenie | `GET /console/boxes?numer=`, lista spraw |
| 5 | **wpis zamykający** (wewnętrzny): stan, następny krok, kickoffy, decyzje ze stanem śladu, pomiar. Potem status `closed` | `POST /tickets/{id}/entries`, `PATCH /tickets/{id}` |
| 6 | **lokalnie, gdy ustawione:** `tura_plik_stanu` (punkt wznowienia dla drugiego okna), `tura_dziennik` (`{data}`), `tura_repo` + `tura_commit pliki\|wszystko`. Kit nigdy nie robi push i nie omija hooków | pliki, `git` |
| 7 | **wynik:** jedna linia `zapisane: … \| następny krok: …` (z brakami: `\| braki: … \|`). Kody: 0 · 1 SF nie przyjął wpisu albo statusu (plik stanu i tak powstaje) · 2 złe wejście, nic nie wysłane · 3 zapisane z brakami | — |

- `--sucho`: pokazuje wpis i plan, niczego nie zapisuje. Kod wyjścia jest taki jak w prawdziwym przebiegu.
- `--json`: cały wynik jako jeden obiekt.
- **Asystent:** `tura zamknij --sprawa <sprawa>` zapisuje stan jako wpis na sprawie, bez zmiany statusu. **Worker** tury nie ma.
- **Nowe ustawienia lokalne** (`sf-kit ustawienia <klucz> <wartość>`): `rozgrywka`, `tura_plik_stanu`, `tura_dziennik`,
  `tura_repo`, `tura_commit`. `rozgrywka` działa też w `konsola blok` / `blok nowy` zamiast sztywnego `~/tracking/rozgrywka.json`
  (`SF_KIT_ROZGRYWKA` nadal ma pierwszeństwo przed domyślną ścieżką).
- Przegląd (`sf-kit pomoc`, sekcja w CLAUDE.md po `start`): linia `krok | tura` i przykład. Koordynator ma 80 linii, czyli limit bramki.

## Wymaga SF

Nic nowego. Wszystkie trasy są na PROD (sprawdzone 24.11 01:0x na żywym SF przez `--sucho`: zadania od czasu, presja Org, sprawa).

## Bramka (24.11, ~02:30 PL)

- Pełny pakiet: **893 testy OK** (1 pominięty jak dotąd: TOML Gemini bez tomllib), 4 przebiegi.
- Nowe testy `testy/test_tura_sf574.py` (29). Mutacje: 11 z 12 zabitych. Dwunasta jest równoważna (`git add .` ≡ `git add -A`).
- Pakiety (plugin, Codex, Kimi, Gemini) wygenerowane na nowo (`python3 -m sf_kit.pakiet --zapisz`). Zmienił się tylko numer wersji.
- Połączenie z `origin/borys/advertpr1395-pelna-tresc` (ADVERTPR-1395, gotowe od 23.11): `merge-tree` bez konfliktu.
  Pakiet na połączeniu był zielony w 6 z 7 przebiegów. Pierwszy przebieg dał 10 F + 1 E przy czasie 40 s zamiast 10 s; tego nie odtworzyłem.
  Czy 1395 wchodzi do 0.21.0, decyduje seweryn albo Damian.

## Do wykonania przy wydaniu

1. `main` ← `arek/kit-0210-wydanie` (ff), tag `v0.21.0` z tym opisem (bez linii STAN), push `main` + tag.
2. Superadmin: `PUT /api/v1/super-admin/kit/version`
   `{"latest": "0.21.0", "min": "0.20.2", "tag": "v0.21.0", "commit": "<sha tagu>", "released_at": "<czas tagu UTC>",
     "notes_url": "https://github.com/dpakula/sf-agent-kit/releases/tag/v0.21.0", "breaking": false}`
3. Koordynatorka: `sf-kit update`, ustawienia `tura_*` i `rozgrywka`, lokalna `/next-turn` jako nakładka (wpis na SF-574).
