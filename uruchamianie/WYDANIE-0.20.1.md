SF Agent Kit 0.20.1: `sf-kit uwaga` — uwagi do Kita prosto z terminala, z wersją, systemem i ostatnim błędem (SF-506 pkt 1)

STAN: WYDANIE LOKALNE 09.11.2026 (kickoff Agaty, SF-506 „Kit do perfekcji do pt 14.11”, punkt 1: „jeśli Kit nie ma
endpointu do zgłaszania uwag — to punkt pierwszy”). Gałąź `klaudiusz/kit-0200-wydanie` = 0.20.0 + ta paczka. Tag `v0.20.1`
lokalny. Push i wydanie w SF (`GET /kit/version`) — klucz wdrożeniowy u seweryna; Damian #2458 = A (0.20 od razu).

## Po co

Alfatester (Wójt od 10.11, potem każdy nietechniczny użytkownik z agentem) trafia na coś, co nie działa. Do 0.20.0 miał
`zglos` (to „gotowa praca” w Organizacji klienta) albo pisanie do kogoś bez wersji i bez komunikatu błędu.

## Nowe

- **`sf-kit uwaga "co nie działa"`** (alias w pakietach: `feedback`) → nowa sprawa w Organizacji **`sf`** (SalesForge),
  autor = klucz testera. Tytuł „Uwaga do Kita: …”, kategoria `bug` (z dołączonym błędem) / `feedback`, tag Projekt: SalesForge.
  Opcje: `--plik ZRZUT…` (jednym wpisem), `--kontekst "co robiłem"`, `--bez-bledu`, `--sucho` (pokaż, nic nie wysyłaj),
  `--json`. Organizacja: `--org` > `SF_KIT_ORG_UWAG` > `sf`.
- **Ostatni błąd dołącza się sam.** Każde polecenie, które skończy się kodem ≠ 0 albo wyjątkiem, zostawia
  `ostatni-blad.json` obok konfiguracji agenta (0600): polecenie, kod, końcówka stderr ≤ 4 KB. Uwaga dołącza go, gdy
  ma < 24 h, i usuwa po wysłaniu. `uwaga` i `mcp` nie nadpisują błędu.
- **Sekrety.** Klucze `sk_…`, Bearer/Authorization, `HASLO=`/`PASSWORD:`/`token=`, hasło w adresie, `--klucz …` i wartość
  własnego klucza są wycinane przy zapisie błędu i drugi raz przy budowaniu treści. Słowa testera czyszczone łagodniej
  („hasło: nie przechodzi” zostaje, `HASLO=…` znika).
- **Nic nie przepada.** Brak członkostwa w `sf`, brak klucza, błąd API → treść w `<konfiguracja>/uwagi-niewyslane/*.md`,
  kod 1, ścieżka na ekranie.
- README („Coś nie działa albo czegoś brakuje”), tabela intencji w `sf-kit start` („zgłoś uwagę do Kita” → `uwaga`, nie `zglos`),
  manifest pakietów (Claude/Codex/Kimi/Gemini, MCP).

## Sprawdzone na żywo

09.11: pierwsza próba z kategorią `kit-uwaga` → 422 („Dozwolone: bug, feature, feedback, other, question”) — uwaga trafiła
do pliku, zgodnie z założeniem. Po poprawce SF-507 w `sf`: kategoria bug, tag SalesForge, załącznik, błąd z wersją 0.20.1;
sprawa testowa zamknięta.

## Do zrobienia poza Kitem

- Tester musi mieć członkostwo w `sf` z zakładaniem spraw (Wójt: pakiet alfatestera, SF-506 pkt 4).
- Właściwy tag `kit-uwaga` w taksonomii `sf` — zakłada admin; wtedy Kit może go nadawać zamiast polegać na prefiksie tytułu.

## Testy

`python3 -m unittest discover -s testy`: 839 (837 OK), w tym 20 nowych; 2 błędy `test_onboarding_960` były przed tą paczką (bez związku,
potwierdzone na czystym HEAD). Nowe: `test_uwaga_sf506.py`. `python3 -m sf_kit.pakiet --sprawdz`: zgodny.
