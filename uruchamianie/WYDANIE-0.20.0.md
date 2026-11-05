SF Agent Kit 0.20.0: luki koordynatora SF-486 (wpis 75e3182a) — odpowiedź w wątku, krok kompletny, odpowiedzi w wątkach, status własnego zadania, ściąga w AGENT.md

STAN: WYDANIE LOKALNE 05.11.2026 (kickoff Agaty, SF-486 — cel Damiana: Kit „super działający” do pon. 09.11, przekazanie
Michałowi i Wójtowi, wt 10.11 test czystym agentem). Gałąź `klaudiusz/kit-0200-wydanie` = 0.19.0 (`klaudiusz/kit-0190-wydanie`)
+ ta paczka. Tag `v0.20.0` lokalny. **Push gałęzi i tagu (klucz wdrożeniowy u seweryna) i wydanie (`GET /kit/version` =
latest w SF) czekają na GO Damiana.** Na maszynie floty zainstalowany jest nadal 0.18.0 (`sf-kit --version`) — koordynatorka
nie ma nawet komend 0.19; instalacja lokalna też po GO.

## Po co

05.11 koordynatorka dalej robiła część operacji curlem (7 luk na SF-486). Damian: „Integralną częścią Kita ma być zestaw
instrukcji: składnia, trasy”, a czysty agent z samym Kitem ma przejść 5 zadań bez pytania człowieka.

## Nowe

- **`wpis … --w-odpowiedzi WPIS`** i **`odpowiedz … --w-odpowiedzi WPIS`** (luka 1) — odpowiedź W WĄTKU pod wpisem (`w_odpowiedzi_do`):
  pełne id, jego początek (≥ 6 znaków) albo link `…#wpis-<id>`. Z `--zalacz` = kod 2 (trasa z plikami nie zna wątków).
- **`konsola odpowiedzi`** (luka 5, SF-433) — obok odpowiedzi na bloki także **odpowiedzi człowieka w wątkach pod MOIMI wpisami**,
  na które jeszcze nie zareagowałem (feed osoby w każdej Organizacji klucza → oś sprawy od najnowszych). Przy każdej gotowa
  komenda odpowiedzi w wątku. `--osoba EMAIL|NAZWA…` (domyślnie `konsola_adresat`), `--dni 7`, `--bez-watkow`, `--json` = {bloki, watki}.
- **`krok nowy --tytul "KROK V · Rozgrywka …" --tag Krok --obserwujacy … --zalacz …`** (luka 4) — krok od razu kompletny;
  tag „Krok” domyślnie (`--tag ""` = bez); element, którego nie udało się dołożyć = kod 3 + lista, krok zostaje.
- **`zadanie <id> --status in_progress|completed|on_hold [--notka "…"]`** — agent zmienia status WŁASNEGO zadania bez demona
  workera (dla testu czystym agentem: „odbierz zadanie … raport/end”).
- **AGENT.md: „Ściąga: zadanie → komenda → przykład → co zobaczysz”** (luka 7) — trzy tabele: asystent, worker, koordynator.
  Test `TestSciagaSpojnaZParserem`: każdy przykład ze ściągi przechodzi parser Kita (29 przykładów) — składnia w instrukcji
  nie rozjedzie się z `--help`.

## Bez zmian (już było — brakowało instrukcji, teraz w ściądze)

Luka 2 (`konsola blok --sprawa … --zastepuje #N --opcja …`), luka 3 (`zalacz`, `obserwujacy --dodaj`, `tag nadaj`,
`nowa-sprawa --tag --zalacz --przypisz --obserwujacy`, `zlec --dostarcz`).

## Czeka

Luka 6 — poczta (`szkic` / `wyslij` / odpowiedź w wątku maila, treść txt/md/html): Kit nie ma jeszcze komend poczty; API jest
(`POST /poczta/sprawy/{id}/odpowiedz`, `…/szkic/wyslij`), ale akapity w `tresc_html` = SF-504 (kontrakt borysa). Komendy po kontrakcie.

## Testy

`python3 -m unittest discover -s testy`: 819, w tym 11 nowych (`test_luki_sf486_020.py`); 2 błędy `test_onboarding_960`
były przed tą paczką (bez związku). `python3 -m sf_kit.pakiet --sprawdz`: zgodny.
