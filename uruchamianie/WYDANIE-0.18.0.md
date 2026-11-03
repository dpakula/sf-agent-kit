SF Agent Kit 0.18.0: konsola koordynatora (SF-486), ekran statusu (ADVERTPR-1075/1118/1167), instrukcje rozdzielone na ludzi i agenta (SF-282)

STAN: WYDANIE LOKALNE 03.11.2026 (kickoff Agaty, SF-486 krok 3). Gałąź `klaudiusz/kit-0180-wydanie`, czyli
main 0.17.1 + SF-282 docs + ADVERTPR-1075/1089/1118/1167 + SF-486 krok 2 + poprawka bezpieczeństwa borysa
(cherry-pick 5ece705 z `borys/kit-018-wydanie`, przygotowanie z 15.10). Tag `v0.18.0` jest lokalny. **Publikacja
(push gałęzi i tagu, wydanie na GitHubie, `GET /kit/version` w SF) czeka na GO.** Bez niej `sf-kit update` u innych
nadal widzi 0.17.1.

## Nowe

**Konsola koordynatora (SF-486, klaudiusz-general).** Koordynator nie potrzebuje już curla do bloków, wiadomości
i tagów:
- `konsola blok|lista|pokaz|zamknij|odpowiedzi` — bloki Konsoli A z bezpiecznikami biblioteki floty: dedup kotwicy 2 h,
  „Zastępuje” tylko z istniejącym `#N`, opcje decyzji z treści (etykieta ≤ 80), odmowa bez sprawy źródłowej, lustro
  przy wyłączonym kanale.
- `inbox --wszystkie-org` — nieodebrane ze wszystkich Organizacji klucza (skrzynka i dyspozycje na `session_target`),
  równolegle. Potwierdzenie po wykonaniu: `inbox --odebrane <id> --notka …`.
- `wpis --widocznosc konsola|team` (także z `--zalacz`), `wpis-widocznosc <sprawa> <wpis> <poziom>`.
- `tag lista|nadaj|zdejmij|pokaz`, `sprawy --bez-tagu-typu "<typ>"` (filtr po stronie SF).
- Dziennik audytu zapisów w formacie `sf_audit.log` floty (`SF_KIT_AUDIT_LOG` albo ustawienie `dziennik_audytu`);
  domyślnie wyłączony.
- Ustawienia lokalne `dziennik_audytu`, `konsola_adresat`.
- Luki 4–6 (SF-486 krok 3): `sprawa --status/--kind/--json` (rozwiązanie sprawdza otwarte zadania i tagi „czeka na…”,
  `--mimo-to`), `--rodzaj` przy `nowa-sprawa/zglos/zlec`, `zlec --dostarcz` (skrzynka SF), `krok nowy|zamknij`,
  `kolejka --stare`, `odbierz --hurt`. `odbierz` NIE rozwiązuje sprawy (Agata 03.11: 4× cofanie resolved).

**`sf-kit status`: ekran statusu „jak w grze” (ADVERTPR-1075, klaudiusz-general).**
- Domyślny widok jest zwięzły, ≤ 12 linii: 4 paski i pod każdym „powód → co zrobić”. Rozbicie pokazuje `--pelny`
  (ADVERTPR-1075/1167).
- Kolor paska to kolor tożsamości wskaźnika; czerwony oznacza stan zły (ADVERTPR-1167).
- Tendencja presji ↗ → ↘ z deltą 3 h i 24 h (ADVERTPR-1118); presja manifestu v4 (ADVERTPR-1089).
- Kit niczego tu nie liczy. Dane daje `scripts/lib/wskazniki.py --json` z repo AProAgents.

**Instrukcje: README dla ludzi, AGENT.md dla agenta (SF-282, decyzja Damiana A).**

## Zmienione zachowanie (sprawdź, jeśli używasz)

- Dawny `sf-kit status` koordynatora (whoami + kolejka floty) to teraz `sf-kit status --kolejka`. Z `--agent-slug`
  albo `--status` Kit sam wybiera dawny widok. „Czy klucz działa” sprawdza się przez `sf-kit whoami`.
- `inbox` bez `--wszystkie-org` działa jak dotąd: pokazuje wiadomości i potwierdza odbiór.
- `odbierz` przyjmuje kilka identyfikatorów tylko z `--hurt`; bez niego jak dotąd jedno zadanie.

## Poprawka bezpieczeństwa (borys-sf, 15.10)

`wskazniki.py` jest szukany tylko z jawnej ścieżki, z `SF_KIT_WSKAZNIKI` albo w górę od `$HOME`, a nie od bieżącego
katalogu. `sf-kit status` URUCHAMIA znaleziony plik: z cwd wykonałby skrypt z cudzego sklonowanego repo.

## Wymaga SF

Nic nowego. Wszystkie trasy już istnieją (OpenAPI 03.11).

## Bramka (03.11)

- Pakiet zgodny z manifestem (`python3 -m sf_kit.pakiet --sprawdz`).
- Testy: 782, z czego 779 OK i 1 pominięty. 2 błędy `test_onboarding_960` są znane i zależą od macOS: test oczekuje pliku klucza, a na macOS Kit pisze do pęku — i test zapisuje wtedy do PRAWDZIWEGO pęku (wpis `sf-agent-kit`/`kodeks-dpakula` = `sk_live_STARY`). Do poprawy: izolacja `MaszynaTestowa`.
- `claude plugin validate`: marketplace i plugin OK.
