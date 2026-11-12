SF Agent Kit 0.20.2: wydanie poprawkowe SF-486. Usterki z dnia pracy koordynatorki, przegląd Kita generowany z poleceń, wersje floty

STAN: WYDANIE LOKALNE 12.11.2026 (arek, przejęte od borysa-sf 12.11, decyzja Damiana „poprawki SF Kita urgent”).
Gałąź `arek/kit-0202-wydanie` = 0.20.1 (`klaudiusz/kit-0200-wydanie`, nieopublikowane 0.20.0 i 0.20.1) + ta paczka.
Tag `v0.20.2` lokalny. **Push `main` i tagu robi Damian albo seweryn.** Potem ogłoszenie w SF
(`PUT /super-admin/kit/version`: latest = min = 0.20.2), dopiero wtedy `sf-kit update` na flocie.

## Dlaczego 0.20.2, a nie 0.18.1 / 0.19.1

`origin/main` = v0.19.0, SF ogłasza 0.18.0, a 0.20.0 i 0.20.1 leżały gotowe lokalnie (Damian #2458 = A, 09.11).
Wydanie z `main` jako 0.19.1 zgubiłoby je, a numery 0.20.x zostałyby zajęte przez wersje, których nikt nie ma.
Flota dostaje więc za jednym razem 0.19 + 0.20.0 + 0.20.1 + tę paczkę.

## Usterki (wpis Agaty 89d84c40, 12.11)

| # | było | jest |
|---|---|---|
| 1 | Kit wisi bez `< /dev/null` | `--opis -` / `--tresc -` / `uwaga -` przy otwartym, pustym stdin (narzędzie agenta) kończą się po 10 s kodem 2 z komunikatem (`SF_KIT_STDIN_CZEKAJ`). Na terminalu podpowiedź „Ctrl-D”. `init` bez terminala: komunikat i kod 2 zamiast `input()` w nieskończoność. Podprocesy (`security`, `git`, `update`) dostają `stdin=DEVNULL` |
| 2 | `sprawa FIX-40` → „nie znalazłem”, gdy to Lead | numer szukany drugim pytaniem w `widok=leady`. Nowe **`sf-kit leady`** (lista zakładki Leady, `--szukaj`) i **`leady <numer>`** (osoba, źródło, zgody, **stan przekazania do CRM** z `GET /tickets/{id}/lead`) |
| 3 | `nowa-sprawa --tag Bug` → 422 | kategoria normalizowana: wielkość liter, polskie nazwy, nazwy i wartości z taksonomii `ticket_category` tej Organizacji. Nieznana = kod 2 z listą dozwolonych, zanim cokolwiek pójdzie do SF. Tag typu kategoria nie jest nadawany jako zwykły tag |
| 4 | dwóch obserwujących → „dołóż brakujących” | własne konto pomijane z komunikatem („jako autor obserwujesz od założenia”), 409 „already exists” = już obserwuje, nie porażka |
| 5 | `/end-task` zamyka sprawę wieloetapową | **nie Kit**, tylko `scripts/sf/close-sf-task.sh` floty (decyzja Agaty, propozycja na SF-486). W Kicie: `zadanie --status completed` nigdy nie zamyka sprawy, a przegląd i AGENT.md mówią to wprost |
| 6 | `sprawa --status resolved` odmawia bez listy | odmowa wypisuje otwarte zadania (id, status, wykonawca, tytuł) i polecenia: `zadanie … --status completed`, `odbierz …`, `odbierz … --hurt` |
| 7 | `wpis --do` nie budzi sesji | pomoc, przegląd i AGENT.md: to wiadomość do skrzynki (`inbox`), nie zlecenie; zlecenie = `zlec --dostarcz` |

## Dokumentacja (15–17) i instrukcja dwupoziomowa (18)

- **15:** `https://sales-forge.pl` w AGENT.md, w podpowiedzi linku i w **adresie domyślnym konfiguracji** (`config.py`; tam też stał stary adres).
- **16, 18:** **`sf-kit pomoc`** = przegląd generowany z parsera (`sf_kit/przeglad.py`): pięć zasad, polecenia po jednej linii pogrupowane po rolach (ze znaczników `[rola]` w pomocy), dla koordynatora 10 najczęstszych operacji z przykładami. Długość: koordynator 79, worker 53, asystent 48 linii.
  - Poziom 2: `sf-kit pomoc <polecenie>` (pełna pomoc z podpoleceniami + sekcje AGENT.md, w których polecenie występuje), `sf-kit pomoc "<temat>"` (sekcja AGENT.md po nagłówku), `sf-kit pomoc --tematy`.
  - **`sf-kit start`** wkleja przegląd do sekcji Kita w `CLAUDE.md` / `AGENTS.md`. Nagłówek zależy od profilu: asystent ma tabelę „człowiek mówi → polecenie”, agent ma start z `whoami` i `tasks`. Katalog jest zapamiętywany (`start-katalogi.json`), a **`sf-kit update` odświeża przegląd sam** (`start --odswiez` na nowym kodzie).
  - **Bramka (test):** polecenie bez opisu albo bez `[rola]`, przegląd > 80 linii, polecenie nieobecne w przeglądzie albo przykład niezgodny z parserem = czerwone testy.
- **17:** README „Aktualizacja”: `sf-kit update` jako oficjalna droga, `--check`, `--version`, `flota wersje`.

## Z próby generalnej testu odbioru (pkt 19, 12.11, przed wydaniem)

Czysta sesja Claude Code: osobny katalog z samym `sf-kit start` (0.20.2), bez ustawień i pamięci użytkownika, bez MCP,
dozwolone tylko `sf-kit`. Zadanie tylko do odczytu na SF-486 (5 pytań o stan wydania). Wynik: **5/5 poprawnie**, zero zejść do
API, zero pytań do człowieka, 21 tur. Agent sam wypisał braki. Dwa poprawione w tej paczce:
- **`tasks`** pokazywał tylko zadania w kolejce („Twoje w kolejce: 0”), a zadanie agenta było w toku. Agent szukał jego id
  w `sprawa --json`. Teraz `tasks` pokazuje kolejkę, zadania w toku i wstrzymane, ze statusem przy każdym (`--status` zawęża).
- **`sprawa`** obcinała długie wpisy do 1500 znaków, a komunikat obcięcia odsyłał do… `sf-kit sprawa`. Teraz `sprawa` (droga
  doczytania) daje treść w całości. Obcięcie zostaje tylko w kontekście doklejanym na starcie zadania i wskazuje
  `sprawa <numer> --wszystkie`.

Do 0.21.0: identyfikatory wierszy z `os --json` nie działają w `wpis-wersje` (to id osi, nie wpisu), więc agent pobierał id z `sprawa --json`.

## Pomiar wersji

**`sf-kit flota wersje [--ponizej] [--json]`**: agent, wersja, kiedy widziany, stan (aktualna / nieaktualna / PONIŻEJ WYMAGANEJ /
nie widziany). Czyta `kit_version`, `kit_seen_at`, `kit_outdated`, `kit_below_min` z `GET /agents` (SF od ADVERTPR-960,
wersja z `User-Agent`, Redis 45 dni). Bez zmian w SF.

## Pakiety

Manifest: `help` (`pomoc`) i `leads` (`leady`) w pakietach Claude / Codex / Kimi / Gemini i w MCP. Wersja 0.20.2 w `WERSJA`,
pakietach, `marketplace.json` i instalatorach (`install.sh`, `install.ps1`).

## Testy (bramka)

- `python3 -m unittest discover -s testy`: 864, w tym 25 nowych (`test_wydanie_0202_sf486.py`). Zostają 2 błędy `test_onboarding_960`, które były już przed paczką (bazowy przebieg 839 testów na czystym 0.20.1: te same 2).
- Zmieniony 1 test: `test_nawyki_sf496` zakładał kategorię „makieta”, której PROD nie przyjmuje (422). Teraz sprawdza `Bug` → `bug`.
- `python3 -m sf_kit.pakiet --sprawdz`: zgodny. `claude plugin validate plugin` i `.`: passed.
- Na żywo (odczyt): `leady` w autera/formarketing, `leady AUTERA-53` (karta), `sprawa AUTERA-53 --id` (lead po numerze), `-` przy otwartym stdin: kod 2 po limicie.

## Po wydaniu

1. `sf-kit update` na każdej instancji (Mac: wspólna instalacja `~/.local/share/sf-kit`; b5c3: każda u siebie).
2. Pierwszy raz: `sf-kit start --katalog <katalog pracy agenta>` (wcześniej nikt we flocie nie miał sekcji Kita).
   Kolejne aktualizacje odświeżą przegląd same.
3. Raport „agent → przed → po” z `sf-kit flota wersje`.
4. Test odbioru (SF-486 pkt 19): świeża sesja bez pamięci, scenariusz `uruchamianie/TEST-CZYSTY-AGENT.md`.
