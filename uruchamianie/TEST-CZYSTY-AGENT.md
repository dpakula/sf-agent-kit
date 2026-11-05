# Test czystym agentem — SF Kit przed przekazaniem (wt 10.11.2026, SF-486)

Damian 05.11: „Przed przekazaniem uruchomimy całkowicie czystego agenta, który dostaje tylko SF Kit, i zobaczymy, czy potrafi
pracować.” Ten plik to scenariusz: przygotowanie (koordynator), sesja testowa (czysty agent), ocena (miara 5/5).

## Zasada testu

Agent testowy wie **tylko** to, co daje Kit: `README.md`, `AGENT.md`, `sf-kit --help` i odpowiedzi SF. Zero pamięci floty,
zero `CLAUDE.md` floty, zero skryptów `sf_api.sh`, zero curla. Każde pytanie do człowieka albo wyjście poza Kit = zadanie
niezaliczone (z zapisem, czego brakowało — to jest luka Kita, nie agenta).

## 1. Przygotowanie (koordynator, pon. 09.11 wieczór albo wt rano)

1. Kit 0.20.0 zainstalowany z wydania (`curl …/install.sh | sh` albo paczka) na **czystym koncie / katalogu**: nowy katalog
   `~/test-czysty-agent/`, bez `.claude/` floty, bez `CLAUDE.md` nad nim (sprawdź: `ls -a ~/test-czysty-agent/..` nie ma CLAUDE.md).
2. Organizacja piaskownicy: **`rozgrywka-test-01`** (żeby nic nie poszło do klienta). Konto agenta testowego w tej Org
   (`sf-kit --org rozgrywka-test-01 agent-dodaj --email … --nazwa …`, `sf-kit nadaj <konto> --domyslne` — zestaw z `tasks:own`),
   klucz osobisty: `sf-kit klucz-wystaw --wlasciciel <e-mail konta testowego> --opis "test czystym agentem 10.11"`.
   Klucz wpisuje CZŁOWIEK w `sf-kit init` (pytanie interaktywne) w katalogu testowym PRZED startem agenta — nie w czacie,
   nie w pliku w repo. Potem `sf-kit whoami` = Org `rozgrywka-test-01`.
3. Dane testowe w Org `rozgrywka-test-01` (koordynator, własnym Kitem):
   - sprawa **„Test: oferta dla klienta Demo”** z opisem: „Klient pyta o termin wdrożenia. Przygotuj odpowiedź.” (`nowa-sprawa`);
   - zadanie dla agenta testowego na tej sprawie: „Odpowiedz klientowi Demo w sprawie terminu; dołącz plik harmonogram.md”
     (`zlec --agent-slug <slug testowy> --sprawa <nr> --tresc "…"`);
   - plik `harmonogram.md` w katalogu testowym (kilka linii z datami).
4. Nagranie sesji: transkrypt Claude Code (domyślny) + `SF_KIT_AUDIT_LOG=~/test-czysty-agent/audyt.log` (każde wywołanie SF).

## 2. Sesja testowa (czysty agent)

Start: `cd ~/test-czysty-agent && claude` (nowa sesja, bez `--resume`). Pierwsza wiadomość od człowieka, dosłownie:

> Masz SF Kit (`sf-kit`, klucz już skonfigurowany). Instrukcja: `sf-kit readme`. Pracuj w Organizacji rozgrywka-test-01.
> Zrób po kolei 5 zadań z listy poniżej, nie pytaj mnie o nic — jeśli czegoś nie wiesz, szukaj w instrukcji Kita.

Pięć zadań (wklejone w tej samej wiadomości):

| # | zadanie dla agenta | zaliczone, gdy (sprawdza oceniający w SF) |
|---|---|---|
| Z1 | Odbierz swoje zadanie i zacznij je | `sf-kit tasks` → `zadanie <id> --status in_progress`; status zadania w SF = in_progress |
| Z2 | Dopisz w sprawie zadania wpis z postępem i dołącz `harmonogram.md` | jeden wpis z załącznikiem na sprawie, widoczność wewnętrzna |
| Z3 | Zgłoś nową sprawę „Test: notatka ze spotkania” z plikiem `harmonogram.md` | nowa sprawa w `rozgrywka-test-01` z plikiem w jednym wpisie |
| Z4 | Odpowiedz klientowi w sprawie z zadania (wiadomość na zewnątrz, 2–3 zdania o terminie) | wpis widoczny na zewnątrz (`odpowiedz`, bez `--wewn`) w TEJ sprawie |
| Z5 | Zakończ zadanie: raport wyniku i zamknięcie | raport/wpis z wynikiem + `zadanie <id> --status completed`; status = completed |

## 3. Ocena (oceniający: Agata, potwierdza Damian)

- **Miara: 5/5 bez pytania do człowieka.** Każde zadanie: zaliczone / niezaliczone + dowód (link do wpisu, status zadania).
- Dodatkowo z `audyt.log` i transkryptu: ile wywołań Kita, ile błędów (kod ≠ 0) i czy agent sam się z nich podniósł,
  czy sięgnął poza Kit (curl, zgadywanie tras) — każde takie miejsce = luka do instrukcji.
- Wynik: wpis na SF-486 (tabela Z1–Z5 + luki) i **blok dla Damiana: „Kit gotowy do przekazania: tak/nie”**
  (tak = 5/5 i zero wyjść poza Kit; nie = lista luk z terminem poprawki).

## 4. Sprzątanie

Sprawy testowe w `rozgrywka-test-01` zostają jako dowód (Org piaskownicy). Klucz agenta testowego: odwołać po teście
(`sf-kit` koordynatora / panel). Katalog `~/test-czysty-agent/` usunąć po zapisaniu transkryptu i `audyt.log` przy wpisie.

## Próba generalna (zalecana, pon. 09.11)

Ten sam scenariusz uruchomiony raz przez agenta floty z wyłączoną pamięcią (`CLAUDE_CONFIG_DIR` na pusty katalog) —
żeby luki wyszły dzień wcześniej, a nie przy Damianie. Wynik tylko jako notatka na SF-486, bez bloku.
