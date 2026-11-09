# `sf-kit uwaga` → Kit 0.20.1 (SF-506, punkt 1) — projekt przed kodem

Stan: WYKONANE 09.11 (Kit 0.20.1, `WYDANIE-0.20.1.md`). Zmiana względem projektu: kategoria `kit-uwaga` odrzucona przez SF (422) → `bug`/`feedback` + prefiks tytułu.

## Polecenie

```
sf-kit uwaga "co nie działa / czego brakuje" [--plik P …] [--kontekst TEKST] [--bez-bledu] [--json]
sf-kit uwaga - < uwaga.md          # treść ze stdin
```

Nie mieszać z `zglos` (gotowa praca). `--kontekst` tu = wolny opis sytuacji, NIE strażnik SF-51.

## Gdzie ląduje

- Org `sf` (SalesForge) domyślnie; `--org` / zmienna `SF_KIT_ORG_UWAG` nadpisuje.
- Nowa sprawa: tytuł „Uwaga do Kita: <pierwsza linia, ≤80 zn.>”, autor = klucz testera.
- Tagu `kit-uwaga` w taksonomii `sf` NIE MA (09.11, `tag lista`), a agenci nie mają `taxonomy:write`
  → `kit-uwaga` jako KATEGORIA sprawy (jak nazwy spoza taksonomii w `zglos`) + tagi
  `Projekt: SalesForge` i `Kategoria: Błąd` (gdy dołączony błąd) / `Feedback`. Brak tagu = ostrzeżenie, nie porażka.
  Do zgłoszenia: właściwy tag `kit-uwaga` zakłada admin sf.
- Brak członkostwa w `sf` (np. Wójt dziś) → treść zapisana lokalnie
  (`<konfiguracja>/uwagi-niewyslane/<czas>.md`), jasny komunikat, kod 1. Nic nie ginie.
  → przy pakiecie Wójta (punkt 4): członkostwo w `sf` z `tickets:create`.

## Auto-kontekst (bez sekretów)

- Wersja Kita, Python, system (platform), profil, slug agenta, Organizacja domyślna.
- Ostatnie NIEUDANE polecenie: `_wykonaj` zapisuje `<konfiguracja>/ostatni-blad.json`
  (argv, kod wyjścia / wyjątek, końcówka stderr ≤ 4 KB, czas, wersja) — stderr przez tee
  z ograniczonym buforem. Dołączane gdy < 24 h i bez `--bez-bledu`; po wysłaniu uwagi plik
  znika (ten sam błąd nie jedzie dwa razy).
- Czyszczenie przed zapisem i przed wysyłką: `sk_live_…`/`sk_test_…`, `Bearer …`,
  `password=`/`pass=`/`PASS=`/`token=`, wartość własnego klucza wprost.

## Do zrobienia przy kodzie

- moduł `sf_kit/uwagi.py` (czyszczenie, zapis błędu, treść Markdown, zapis niewysłanych)
- parser + `polecenie_uwaga` w `cli.py`, hook w `_wykonaj` (także nieobsłużony wyjątek → zapis + re-raise)
- MCP tool + skille pakietów (strażnik manifestu), AGENT.md/README ściąga
- testy `testy/test_uwaga_sf506.py`; WERSJA 0.20.1
