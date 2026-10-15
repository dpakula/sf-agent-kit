SF Agent Kit 0.18.0: `sf-kit status` jako ekran statusu (ADVERTPR-1075) + instrukcje rozdzielone na ludzi i agenta (SF-282)

STAN: PRZYGOTOWANE 15.10.2026 (kickoff Agaty). Gałąź: `borys/kit-018-wydanie` (main 0.17.1 + SF-203/SF-282 docs +
ADVERTPR-1075 klaudiusza-generala + poprawka bezpieczeństwa i wersja). Tag `v0.18.0` powstaje po bramce testów.

## Nowe

**`sf-kit status`: ekran statusu „jak w grze” (ADVERTPR-1075, klaudiusz-general).**
- Cztery paski tej samej szerokości: ✦ MANA, ↯ ENERGIA, 🔥 PRESJA i ♥ ZDROWIE, w procentach. Do tego tendencja HP i zapas limitów 5h/7d jako glify.
- Pod każdym parametrem są składowe (co ile zabrało), od kiedy tak jest i 1–3 podpowiedzi „co zrobić”.
- `--kto damian|agata|<agent>`, `--krotko` (same paski), `--kolor auto|zawsze|nigdy` (tak woła go /mood), alias `sf-kit postac`.
- Kit **niczego tu nie liczy**. Dane, rozbicia i podpowiedzi daje `scripts/lib/wskazniki.py --json` z repo AProAgents (jeden manifest wskaźników, wersja 2.1.0). Bez tego pliku Kit mówi, czego brakuje. Panel w SF to osobna sprawa, SF-289.

**Instrukcje: README dla ludzi, AGENT.md dla agenta (SF-282, decyzja Damiana A).**
- README to instrukcja dla człowieka (instalacja, pierwszy klucz, co robić, gdy nie działa).
- Pełny opis poleceń dla modelu jest w `AGENT.md`.
- README mówi też wprost, że Windows bez WSL nie jest już „w testach”, że Ctrl+V działa od 0.17.1 i że klucz agenta wystawiony z panelu ma `tickets:read` + `tickets:comment` (SF-203).

## Zmienione zachowanie (sprawdź, jeśli używasz)

**Dawny `sf-kit status` koordynatora (whoami + kolejka floty) to teraz `sf-kit status --kolejka`.**
- Z `--agent-slug` albo `--status` Kit sam wybiera dawny widok. Kto używał tych opcji, dostaje to samo co wcześniej.
- Samo `sf-kit status` rysuje nowy ekran. Nikt w AProAgents nie woła go w skryptach (sprawdzone 15.10). Zmieniły się też odesłania w instrukcjach: „czy klucz działa” to teraz `sf-kit whoami`, także w skillach Codexa, Kimi, Gemini i pluginu Claude.

## Poprawka bezpieczeństwa (przegląd wydania)

**`wskazniki.py` jest szukany tylko z jawnej ścieżki, z `SF_KIT_WSKAZNIKI` albo w górę od `$HOME`, a nie od bieżącego katalogu.**
- `sf-kit status` **uruchamia** znaleziony plik.
- W wersji z gałęzi ADVERTPR-1075 wystarczyło wpisać `sf-kit status` w sklonowanym cudzym repo, żeby Kit wykonał jego `scripts/lib/wskazniki.py`. To ta sama klasa ryzyka co hooki gita.
- Domy agentów leżą w repo AProAgents, więc szukanie od `$HOME` znajduje właściwy plik bez zmian u nich.
- Test `test_nie_uruchamia_wskaznikow_z_biezacego_katalogu`.

## Bez zmian

Pozostałe polecenia, `init`, klucz i aktualizacja działają jak w 0.17.1. Pakiety (plugin Claude, Codex, Kimi, Gemini) różnią się wersją i odesłaniem do `whoami`.

## Wymaga SF

Nic nowego. Ekran statusu nie woła SF, czyta lokalny `wskazniki.py`.

## Bramka

- Pakiet zgodny z manifestem (`python3 -m sf_kit.pakiet --sprawdz`).
- Testy Kitu: pełny przebieg `unittest` po 21:00 (na maszynie wydania w dzień nie uruchamiam testów). Wynik dopisuję tutaj przed tagiem.
