# SF Agent Kit 0.22.0 — zadania sprawy ze statusem, `zlec --json` (ADVERTPR-1420)

STAN: DO BRAMKI 24.11.2026 (klaudiusz-general, kickoff Agaty; propozycja arka z odbioru d1a5982a).
Gałąź lokalna `klaudiusz/kit-lista-zadan` = `origin/main` (v0.21.2, `fe8432b`) + ta paczka. Push `main` i tagu, a potem ogłoszenie
w SF (`PUT /super-admin/kit/version`), robi seweryn albo Damian. Zmiana niełamiąca, `min` bez zmian (0.20.2).

## Dlaczego

Podajnik toru czytał stan zadań z wpisów sprawy przez Kit 0.20.2, który oddaje 200 najstarszych wpisów: widział 6 zamkniętych
zadań z 32. `zlec` nie wypisywał UUID zadania (dziennik ładowania: 245 × NIEZNANY).

## Nowe

- **`sf-kit zadania <sprawa> [--status S,S] [--agent-slug A,A] [--pelne] [--json]`** — wszystkie zadania sprawy (też ludzi),
  wszystkie strony `GET /tasks?ticket_id=` po 200. JSON: `{ok, sprawa, razem, kompletne, liczby, pokazano, zadania[]}`.
  `liczby` o całej sprawie, filtry tylko o liście. Literówka w statusie = kod 2 bez zapytania (SF oddaje na nią 0 bez błędu).
  Kod 3 = lista nie zgodziła się z `total` mimo drugiego odczytu (zadania zmieniały się w trakcie) — ponów.
- **`zlec --json`** — `{ok, task_id, external_id, tytul, status, agent, sprawa, org, doreczone, uwagi}`. Po założeniu zadania
  kłopot z tagiem albo doręczeniem to `uwagi` przy kodzie 0 (ponowienie założyłoby drugie zadanie). Tekstowe `zlec` też pokazuje id.
- **`sprawa --wpis`** przyjmuje także id BLOKU z `os` (dotąd „nie ma wpisu”, choć wpis był: `5d122e78` → `6393f0a6`).

## Naprawione przy okazji

- Bramka `sprawa --status resolved|closed` i `odbierz` liczyły otwarte zadania tylko wśród pierwszych 200 zadań sprawy.

## Stronicowanie wpisów

Było już w 0.21.1/0.21.2 (nieogłoszone w SF, flota stoi na 0.20.2): `sprawa --json` dociąga cały dziennik, `os --wszystkie`
idzie kursorem. Sprawdzone 24.11 na 1420: 575 wpisów, ostatni 19:37 UTC; oś 576 wierszy. Tu bez zmian w kodzie.

## Testy

`python3 -m unittest discover -s testy`: 965, 0 padów, 2 błędy `test_onboarding_960` (pęk kluczy macOS, te same na `fe8432b`:
945). Nowe: `test_zadania_sprawy_1420.py` (20). `python3 -m sf_kit.pakiet --sprawdz`: zgodny. Przegląd koordynatora: 80 linii.
Żywy SF (odczyty): ADVERTPR-1420 291 z 291 zadań, `kompletne: true`. `zlec --json` tylko w testach z atrapą — klucz
klaudiusza-general nie ma `plans:write`; pierwszy prawdziwy przebieg u koordynatora.
