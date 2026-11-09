# SF Kit: założenia

Wersja 1 (09.11.2026, SF-506 pkt 2). Kit 0.20.1. Dokument mówi, czym Kit ma być. Jak go używać, opisują
`README.md` (dla ludzi) i `AGENT.md` (dla agenta).

## Dla kogo

Dla **osoby nietechnicznej, która pracuje z agentem**: Claude Code, Codex, Gemini CLI albo Kimi Code. Nie
musi znać API, curla ani formatu JSON. Rozmawia z agentem po ludzku, a agent obsługuje SalesForge za pomocą
Kita.

W drugiej kolejności Kit służy agentom floty (worker, koordynator), które pracują w SalesForge bez człowieka
przy klawiaturze. Mają te same polecenia i te same zasady.

Kit nie jest przeznaczony dla programistów, którzy piszą własną integrację. Oni korzystają z API SalesForge
bezpośrednio (np. nakładka handlowców, SF-501). Kit to wejście od strony agenta, API to wejście od strony
kodu.

## Obietnica

> **Jedna instrukcja instalacji i agent obsługuje cały SalesForge.**

W praktyce oznacza to trzy rzeczy:

1. **Jedno polecenie instalacji**, potem pytanie o klucz i od razu potwierdzenie, że działa (`whoami`).
2. **Samouczek na start**: pierwsze 10 minut prowadzi użytkownika przez odebranie zadania testowego,
   dopisanie wpisu, załączenie pliku i zgłoszenie uwagi.
3. **Każda czynność w SalesForge ma polecenie Kita.** Gdy jakiegoś brakuje, to błąd Kita, który zgłasza się
   przez `sf-kit uwaga`. Agent nie obchodzi braku curlem.

## Zasady (nieopcjonalne)

| zasada | co znaczy w praktyce |
|---|---|
| **Klucz osobisty** | Każdy człowiek i każdy agent ma własny klucz. Wpis w SF podpisuje ten, kto go zrobił. Nie pożyczamy kluczy. |
| **Zero sekretów w czacie** | Klucz trafia do `sf-kit init` albo do pliku konfiguracji, nigdy do rozmowy z agentem. Kit wycina sekrety z błędów i uwag. |
| **Każda czynność zostawia ślad w SF** | Praca, decyzja i plik lądują na sprawie (wpis, załącznik, wersja treści). Co zostało tylko w terminalu, tego nie było. |
| **Sprawa ≠ Wiadomość** | Wiadomość to wątek maila od klienta (`kind=message`), dostaje tylko wersję treści do wysyłki. Praca, pliki i wpisy robocze idą na Sprawę (ADVERTPR-1273). |
| **Uprawnienia daje członkostwo** | Kod 403 nie oznacza złego klucza, tylko brak nadania w danej Organizacji. Kit mówi, czego brakuje i kogo poprosić. |
| **Wynik czyta człowiek** | Wpisy po polsku i po ludzku: najpierw sedno, szczegóły techniczne pod spodem. |
| **Brak = uwaga, nie obejście** | Jeśli Kit czegoś nie potrafi, `sf-kit uwaga "…"` zakłada sprawę w Org `sf` z wersją, systemem i ostatnim błędem. |

## Mapa flow: czytać · pracować · pytać

Praca w SalesForge to trzy czynności. Każde polecenie Kita jest przypisane do jednego kroku. Polecenia dla
określonych profili mają znacznik: [K] koordynator, [W] worker.

### 0. Wejście (raz)

| krok | polecenie | stan |
|---|---|---|
| zainstalować | `install.sh` / `install.ps1` → `instaluj` | ✅ jest, brak jednego polecenia „curl \| bash” (B3) |
| podać klucz | `init` (`--claude` = także plugin) | ✅ |
| sprawdzić, że działa | `whoami` | ✅ |
| przygotować folder agenta | `start` (CLAUDE.md, AGENTS.md, zgody) | ✅ jest, bez samouczka (B3) |
| podłączyć agenta | `plugin` · `codex` · `gemini` · `kimi` · `mcp` | ✅ |
| gdzie są instrukcje | `readme` | ✅ |
| aktualizacja | `update` / `aktualizuj` | ✅ |
| klucz przed wygaśnięciem | `rotate` | ✅ |
| ustawienia (powiadomienia) | `ustawienia` | ✅ |

### 1. Czytać

| co | polecenie | stan |
|---|---|---|
| co na mnie czeka (sprawy) | `sprawy` (`--tylko-moje`, `--tylko-czlowieka`, `--wszystkie`) | ✅ brak wyszukiwania po treści (B1) |
| moje zadania | `tasks` | ✅ |
| jedno zadanie | `zadanie <id>` | ✅ |
| karta sprawy z wpisami | `sprawa <link>` (`--wszystkie`, `--json`) | ✅ |
| oś sprawy (wszystko, co się działo) | `os <sprawa>` | ✅ |
| jeden wpis / blok | `blok <id>` | ⚠️ pokazuje skrót treści bez podpowiedzi, jak dostać całość (B4) |
| historia i pełna treść wpisu | `wpis-wersje <id>` | ✅ |
| pobrać załącznik | `zalacznik` | ✅ |
| powiązane sprawy | `relacje` | ✅ |
| kto obserwuje | `obserwujacy` | ✅ |
| wiadomości do mnie | `inbox` | ✅ |
| czy moje wysłane doszło | `outbox` | ✅ |
| Konsola A (bloki decyzji) [K] | `konsola lista` / `pokaz` / `odpowiedzi` | ✅ |
| flota i kolejka [K] | `flota`, `kolejka` | ✅ |
| co potrafi dana operacja | `kontrakt` | ✅ |

### 2. Pracować

| krok | polecenie | stan |
|---|---|---|
| odebrać zadanie | `zadanie <id> --status in_progress` | ✅ |
| dopisać postęp / notatkę | `wpis` (`--w-odpowiedzi`, `--widocznosc`) | ✅ |
| raport z blokami | `raport` | ✅ |
| załączyć pliki | `zalacz` | ✅ |
| odpowiedzieć klientowi | `odpowiedz` (`--wewn`, `--blok … --opcja`) | ✅ |
| kolejna wersja dokumentu | `tresc-wersja` | ✅ |
| poprawić wpis / opis | `wpis-edytuj`, `wpis-widocznosc`, `opis-sprawy` | ✅ |
| nowa sprawa z gotową pracą | `nowa-sprawa` / `zglos` | ✅ brak `--z-wiadomosci` (B5) |
| opublikować szkic | `publikuj --zgoda` | ✅ |
| powiązać sprawy | `przypnij`, `odepnij` | ✅ |
| obserwujący, tagi | `obserwujacy --dodaj`, `tag` [K] | ✅ |
| zamknąć zadanie / czekam | `zadanie --status completed` / `on_hold` | ✅ |
| potwierdzić odbiór wiadomości | `inbox --odebrane` | ✅ |
| wysłać maila ze sprawy | — | ❌ brak (B2, SF-504) |
| zlecić / odebrać / krok [K] | `zlec`, `odbierz`, `krok`, `konsola blok` / `zamknij` | ✅ `zlec` bez `plans:write` w Org klienta (B7) |
| konta, nadania, klucze [K] | `agent-dodaj`, `nadaj`, `agent-napraw`, `klucz-wystaw` | ✅ |
| praca w tle [W] | `worker`, `usluga`, `heartbeat` | ✅ |

### 3. Pytać

Na pytania „co u mnie?”, „jak stoi sprawa X?” i „gdzie jest Y?” agent odpowiada po przeczytaniu SF Kitem.

| pytanie | dziś | stan |
|---|---|---|
| „co u mnie?” | `sprawy --tylko-moje` + `tasks` + `inbox` (trzy polecenia) | ⚠️ brak jednego widoku (B6) |
| „jak stoi sprawa X?” | `sprawa <link>`, `os <sprawa>` | ✅ |
| „gdzie jest sprawa o …?” | — (API ma `search`, Kit go nie wystawia) | ❌ B1 |
| „co z moim kluczem / dostępem?” | `whoami` | ✅ |
| „jak flota / presja?” [K] | `status`, `kolejka` | ✅ (widok floty, nie dla użytkownika) |
| „Kit nie działa / czegoś brakuje” | `uwaga` | ✅ (0.20.1) |

## Braki: zadania na ten tydzień (do pt 14.11)

| # | brak | propozycja | kiedy |
|---|---|---|---|
| B1 | szukanie spraw po treści | `sprawy --szukaj "fraza"` (API już ma `search`) | 0.20.2 |
| B2 | mail ze sprawy (szkic / wysyłka) | `poczta szkic` / `poczta wyslij` po kontrakcie SF-504 | po SF-504 |
| B3 | jedno polecenie instalacji + samouczek | `curl … \| bash` → `init` → `whoami` → `start --samouczek` (10 min, 4 ćwiczenia) | SF-506 pkt 3 |
| B4 | `blok` ucina treść bez słowa | dopisek „skrót — całość: `sf-kit wpis-wersje <id>`” albo pełna treść z `--pelna` | 0.20.2 |
| B5 | praca z Wiadomości na Sprawę | `nowa-sprawa --z-wiadomosci <link>` (opis z linkiem, relacja); odmowa wpisów roboczych na `kind=message` | 0.20.2 (1273 C+D) |
| B6 | „co u mnie” jednym poleceniem | `sf-kit co-u-mnie`: moje sprawy + zadania + nieodebrane wiadomości + bloki czekające na mnie | 0.20.2 |
| B7 | `zlec` w Org klienta | nadanie `plans:write` albo komunikat z gotowym zdaniem do admina | rollout (pkt 5) |
| B8 | członkostwo testera w Org `sf` | Wójt i Ala: członkostwo z zakładaniem spraw, inaczej `uwaga` zapisuje się tylko lokalnie | pakiet alfatestera (pkt 4) |
| B9 | flota na starych wersjach | 0.20.x u wszystkich agentów, tabela adopcji `kit_version` | SF-506 pkt 5 |

Jak ustalać kolejność: najpierw to, na czym potknie się alfatester w pierwszych 10 minutach (B3, B8), potem to,
o co zapyta pierwszego dnia (B6, B1), na końcu wygoda (B4) i zależności zewnętrzne (B2).

## Jak sprawdzamy, że obietnica działa

- **Test czystym agentem** (`uruchamianie/TEST-CZYSTY-AGENT.md`, wt 10.11): 5 zadań, miara 5/5 bez pomocy.
- **Alfatest Wójta i Ali** (od 10.11 do 14.11): każda przeszkoda trafia do `sf-kit uwaga`. Sukces oznacza
  zero obejść curlem i zero sekretów w czacie.
- **Adopcja**: `kit_version` w GET /agents, wszyscy aktywni agenci na 0.20.x.
