# SF Agent Kit

## Dla użytkownika

**SF API Kit** łączy Twojego agenta AI (Claude Code, Codex, Kimi) z SalesForge. Agent przyjmuje od Ciebie zadania, pracuje na sprawach Twojej Organizacji i zostawia ślad każdej czynności, więc widzisz, co zrobił i dlaczego.

**Jak zacząć.** Masz konto w SalesForge i Twój agent też (jeśli nie, poproś administratora swojej Organizacji). Zainstaluj Kit jednym poleceniem, a potem wklej agentowi tekst startowy. Resztę tego dokumentu agent przeczyta sam. Jak pracować z agentem na co dzień, opisuje **Podręcznik SalesForge** (w przygotowaniu).

**Instalacja** (w terminalu, na komputerze, na którym pracuje agent):

```
git clone https://github.com/dpakula/sf-agent-kit.git && cd sf-agent-kit && ./sf-kit init
```

`init` zapyta o adres SalesForge i **klucz agenta** — wpisz go sam, nie podawaj go agentowi w rozmowie. Potrzebny jest tylko Python 3.9+ i git.

**Tekst startowy — wklej go agentowi:**

```
W katalogu sf-agent-kit przeczytaj README.md, sekcję „Dla agenta”, i postępuj według niej.
Moja Organizacja w SalesForge to: fm-x-advertpro   (podawaj ją zawsze jako --org)
1. Uruchom ./sf-kit whoami i powiedz mi zwykłym językiem, co widzisz.
2. Jeśli czegoś brakuje, powiedz mi, o co poprosić administratora.
3. Gdy dam Ci link do sprawy, odpowiadaj w tej sprawie. Nową sprawę zakładaj tylko wtedy, gdy żadnej nie ma.
Nie pytaj mnie o klucz i nie wpisuj go w rozmowie.
```

**Tryb pracy agenta:** worker (sam bierze zadania z kolejki), **asystent** (pracuje z Tobą — najczęstszy) albo koordynator (rozdziela pracę innym agentom). Szczegóły opisze Podręcznik SalesForge (w przygotowaniu).

**Organizację podajesz zawsze jawnie** (`--org`, np. `--org fm-x-advertpro`) — Kit nie zgaduje, w której Organizacji zapisać Twoją pracę.

---

## Dla agenta

### Start

**Start.** Uruchom `sf-kit whoami`. Sprawdź, czy wynik wskazuje Organizację użytkownika i czy klucz ma uprawnienia potrzebne do zadania. Jeśli czegoś brakuje, zatrzymaj się i zgłoś to użytkownikowi, wskazując brakujące uprawnienie; nie próbuj go obchodzić.

**Zasada pierwsza.** Pracuj zawsze w sprawie, której dotyczy zadanie. Gdy w poleceniu jest link do sprawy, odpowiadaj w niej (`sf-kit odpowiedz <link> --opis plik.md`). Nową sprawę zakładaj tylko wtedy, gdy żadnej jeszcze nie ma.

**Organizacja.** Podawaj ją przy każdym zapisie jawnie: `sf-kit --org <slug> <polecenie>` (opcja stoi przed poleceniem) albo link do sprawy z `?org=`. Bez tego Kit odmówi (od v0.13.0) — nie obchodź odmowy, zapytaj użytkownika, o którą Organizację chodzi.

**Treść.** Gdy rozwijasz dłuższą treść (analizę, umowę, plan), oddawaj ją w wersjach: `sf-kit --org <slug> tresc-wersja <sprawa> <plik.md>`. Opisu sprawy nie nadpisuj długim tekstem — Kit zatrzyma takie polecenie.

**Szkic.** Gdy Kit ostrzeże, że sprawa jest szkicem, powiedz użytkownikowi, że nikt poza zespołem jej nie zobaczy do publikacji. Publikuj tylko wtedy, gdy jesteś koordynatorem i masz zgodę człowieka: `sf-kit publikuj <sprawa> --zgoda <wpis>`.

### Tryby pracy

Stara nazwa profilu `autor` (sprzed 0.13.2) działa dalej jako `asystent` — Kit wypisze przypomnienie, żeby zmienić ją w `config.json` albo przez `sf-kit init`.

Sprawdź w `sf-kit whoami` i w konfiguracji (`sf-kit init`), w którym trybie pracujesz:

| tryb (profil w Kicie) | co robisz | polecenia |
|---|---|---|
| **asystent** (`asystent`) | pracujesz z człowiekiem: odpowiadasz w sprawach, oddajesz jego pracę | `odpowiedz`, `wpis`, `zalacz`, `tresc-wersja`, `zglos`, `sprawy`, `sprawa` |
| **worker** (`worker`) | bierzesz zadania z kolejki i wykonujesz je w tle | `tasks`, `worker` |
| **koordynator** (`koordynator`) | rozdzielasz pracę flocie i odbierasz wyniki; publikujesz szkice na zgodę | `flota`, `zlec`, `kolejka`, `odbierz`, `status`, `publikuj` |

Profil nie nadaje uprawnień — te są po stronie SalesForge. Jeśli polecenie odpowie brakiem uprawnienia, zatrzymaj się i przekaż użytkownikowi, czego brakuje.

### Gdy coś nie działa

Zgłoś problem wpisem na sprawie, przy której pracujesz. Gdy klucz jeszcze nie działa, wskaż użytkownikowi formularz pomocy: **https://sf.dpakula.pl/pomoc** (bez logowania; odpowiedź przychodzi na podany adres). Uprawnienia nadaje i klucze wystawia **administrator SalesForge** — do niego kieruj prośby o dostęp.

Poza tym plikiem jest katalog [`uruchamianie/`](uruchamianie/README.md) — gotowce na uruchomienie workera w tle.

---

### 1. Pierwsze uruchomienie krok po kroku

Ta sekcja jest dla kogoś, kto **nie zna SalesForge, nie zna gita i nie zna Pythona**,
a korzysta z Codexa. Sześć poleceń po kolei; przy każdym napisane, czego się spodziewać.

#### Czego potrzebujesz przed startem

| rzecz | jak sprawdzić | czego brakuje, gdy nie ma |
|---|---|---|
| Codex CLI | `codex --version` wypisuje numer | instalacja wg dokumentacji OpenAI; potem `codex login` |
| …**zalogowany** | `codex exec "napisz OK"` odpowiada, nie prosi o logowanie | `codex login` |
| Python 3.9+ | `python3 --version` wypisuje numer | macOS: `brew install python3`; Linux: z menedżera pakietów |
| git | `git --version` wypisuje numer | macOS: `xcode-select --install`; Linux: z menedżera pakietów |

**Nie ma nic do zainstalowania poza tym.** Kit korzysta wyłącznie z biblioteki standardowej
Pythona, więc `pip install` nie jest potrzebny — po pobraniu od razu działa.

**System: macOS albo Linux.** Na Windows **poza WSL** Kit nie jest bezpieczny i nie należy
go tam uruchamiać — z dwóch konkretnych powodów, nie z ostrożności:

- **klucz nie byłby chroniony prawami pliku.** Na macOS klucz idzie do pęku kluczy, na Linuksie
  do pliku z prawami `600` (czyta tylko twoje konto). Na Windows `chmod` ustawia jedynie atrybut
  „tylko do odczytu" i **nie ogranicza tego, kto plik przeczyta** — klucz leżałby otwarty dla
  innych programów tego konta. Kit mówi o tym wprost przy zapisie, zamiast obiecywać „prawa 600";
- **ochrona przed zapisaniem klucza w repozytorium by się nie włączyła** — instalator haka jest
  skryptem powłoki i bez niej nie ma czym go uruchomić. Kit zgłosi to ostrzeżeniem.

**Na Windows użyj WSL** (Linux wewnątrz Windowsa) — wewnątrz WSL obowiązuje wszystko, co ten
dokument mówi o Linuksie. Samego WSL nikt tego Kitu jeszcze nie przetestował end-to-end, więc
przy pierwszym uruchomieniu tam warto zerknąć na wynik `sf-kit whoami` uważniej niż zwykle.

#### Co dostajesz od administratora SalesForge

| dane | przykład | uwaga |
|---|---|---|
| adres SalesForge | `https://sf.dpakula.pl` | Kit ma ten adres wpisany jako domyślny — potwierdź go mimo to |
| slug agenta | `codex-formarketing` | po nim rozpoznawane są zadania agenta. Od v0.9 `init` **sprawdza go w SF sam** i ostrzega, gdy wpisany jest inny |
| **klucz API** | `sk_live_…` | **osobnym kanałem, nie mailem** — to hasło do konta |

Jeśli któregoś z tych trzech brakuje, nie ma sensu zaczynać. Poproś administratora o komplet.

**Identyfikatora Organizacji już nie potrzebujesz** (zmiana v0.4). Kit odczytuje go z SalesForge
sam — razem z listą wszystkich Organizacji, do których należysz, i z tym, co w każdej wolno ci
robić. Do v0.3 trzeba go było przepisać skądś ręcznie, zwykle z cudzej wiadomości.

Czego administrator musi natomiast dopilnować: **nadań na twoim członkostwie**. Konto może
należeć do Organizacji i nie mieć w niej żadnych uprawnień — Kit pokaże ją wtedy na liście
z adnotacją „bez nadań" i odmówi w niej pracy, zamiast pozwolić ci dojść do połowy i dostać
odmowę z serwera.

#### Sześć poleceń

**1. Pobierz Kit**

```bash
git clone https://github.com/dpakula/sf-agent-kit.git
cd sf-agent-kit
```

Adres `https://` działa bez konta GitHub i bez konfigurowania kluczy SSH. Powinien pojawić
się katalog `sf-agent-kit`.

**Uruchom to w swoim katalogu domowym** (czyli tam, gdzie terminal startuje domyślnie).
Gotowce z katalogu [`uruchamianie/`](uruchamianie/README.md) zakładają ścieżkę
`~/sf-agent-kit`; przy innym miejscu trzeba je będzie poprawić.

**O zapisie `./sf-kit`:** kropka z ukośnikiem znaczy „program z tego katalogu", więc wszystkie
polecenia poniżej działają **po wejściu do `sf-agent-kit`**. Jeśli wolisz wołać `sf-kit`
z dowolnego miejsca:

```bash
mkdir -p ~/.local/bin && ln -sf "$PWD/sf-kit" ~/.local/bin/sf-kit
```

(o ile `~/.local/bin` jest w twoim `PATH` — sprawdzisz to poleceniem `echo $PATH`).
Dalej w dokumencie pisane jest krótkie `sf-kit`; jeśli nie zakładałeś skrótu, dopisuj `./`
i pracuj w katalogu Kitu.

**2. Zapisz klucz i ustawienia**

```bash
./sf-kit init
```

Polecenie zadaje pięć pytań, a na końcu prosi o klucz — **wpisywany bez pokazywania na
ekranie** (to normalne, nie jest zepsute). Co wpisać:

| pytanie | co wpisać |
|---|---|
| Adres SalesForge | to, co dał administrator; Enter zostawia wartość w nawiasie |
| Identyfikator Organizacji | długi ciąg od administratora |
| slug agenta w SF | slug od administratora, np. `codex-formarketing` |
| Katalog roboczy | katalog, w którym agent ma pracować, np. `/Users/ty/praca-sf`. **Musi istnieć** — zadanie ze wskazanym nieistniejącym katalogiem zostanie odrzucone |
| Wykonawca | `codex` (`shell` jest trybem testowym administratora — §10) |

Kończy się liniami „Klucz … zapisany" i „Ochrona przed zapisaniem klucza w repozytorium:
włączona".

**Uruchomienie `init` po raz drugi nadpisuje poprzedni klucz** — to jest właściwy sposób
poprawienia literówki albo wpisania nowego klucza. Enter przy każdym pytaniu zostawia
dotychczasową wartość, więc można zmienić sam klucz.

> **To polecenie wykonuje człowiek, sam, w terminalu.** Nie przez model, nie przez wklejenie
> klucza w czat. Powód jest w §4.

**3. Sprawdź, czy klucz działa**

```bash
./sf-kit whoami
```

Spodziewany wynik:

```
agent:        codex-formarketing   profil: worker
ustawienia:   ~/.config/sf-kit/codex-formarketing.json
klucz:        sk_live_…a7f2
adres:        https://sf.dpakula.pl
konto:        Codex (FORmarketing) · agent
klucz w SF:   sk_live_a1b2 · scope user

Organizacje:
  formarketing         FORmarketing sp. z o.o.      (3 nadań)
  advertpro-co         ADVERTpro                    (bez nadań)

pracuję w:    formarketing (FORmarketing sp. z o.o.)
uprawnienia:  tickets:read, tickets:comment, tasks:own
slug w SF:    codex-formarketing

odczyt zadań: działa
zadania:      Twoje w kolejce: 3 · przejrzano zadań Organizacji: 100 z 518
ważny do:     2026-10-15T09:00:00+00:00 (za 28 dni)

Zmian statusu nie sonduję — README, sekcja „Kiedy coś nie działa”.
```

**Ważność klucza i ostrzeżenie (v0.5.5).** Przy dacie stoi, ile to jest dni — bo sama data
każe liczyć w głowie, a liczenia w głowie się nie robi i stąd klucze wygasające „nagle".
To samo mówi **worker**: przy starcie i raz na dobę sprawdza własny termin i na siedem dni
przed nim pisze w dzienniku, że klucz wygasa i kogo poprosić o przedłużenie. Po terminie mówi
wprost, że **to nie jest awaria SalesForge** — bo z zewnątrz wygaśnięcie wygląda dokładnie
jak awaria: worker przestaje brać zadania i w dzienniku stoi odmowa serwera. Klucz bez terminu
(`wygasa: null`) nie generuje żadnego szumu: brak terminu to brak terminu, nie „nie wiem".

Wszystko poniżej linii `konto:` przychodzi **z SalesForge**, nie z Twojego pliku. To jest cała
zmiana v0.4: do v0.3 `whoami` wypisywał zawartość konfiguracji i sondował klucz próbą odczytu,
więc odebrane członkostwo wyglądało dokładnie tak samo jak działające.

Gdy klucz nie działa, ostatnia ważna linia wygląda tak:

```
odczyt zadań: NIE DZIAŁA — klucz nie został przyjęty (401). Uruchom `sf-kit init` …
```

**Cały ten wynik można bezpiecznie pokazać komuś przy diagnozie** — w linii `klucz:` jest
tylko skrót (stały początek i cztery ostatnie znaki), po którym da się odróżnić dwa klucze
od siebie, a nie da się żadnego użyć.

Kody błędów i co z nimi zrobić: §7.

**4. Zobacz swoje zadania**

```bash
./sf-kit tasks
```

Wypisuje zadania czekające w kolejce dla sluga agenta:

```
Zadania w kolejce dla „codex-formarketing” (1 z 518 pozycji kolejki):

  ADVERTPR-901
    Uporządkuj katalog raportów
    sprawa: ADVERTPR-777   id: 8a1f…
```

„Brak zadań" na tym etapie jest normalny — znaczy, że nikt jeszcze nic nie przypisał.
Liczba w nawiasie („z 518 pozycji kolejki") mówi, ile zadań w ogóle przejrzano; gdy pojawi
się przy niej ostrzeżenie o bezpieczniku, wynik NIE jest pewnym „brak zadań".

> **Uwaga na literówkę w slugu.** Slug wpisany w `init` musi zgadzać się **znak w znak**
> z tym, który administrator ustawił na koncie agenta. Przy pomyłce wszystko wygląda
> poprawnie — `whoami` mówi „działa" — a `tasks` pokazuje „brak zadań" **nieodróżnialnie
> od stanu, w którym naprawdę nic nie przypisano**. Gdy zadanie zostało przypisane,
> a lista jest pusta, sprawdź slug w pierwszej kolejności: `sf-kit whoami` wypisuje go
> w linii `mój slug:`; poproś administratora o porównanie z kontem.

**5. Wykonaj jedno zadanie próbnie**

```bash
./sf-kit worker --once
```

Bierze **najwyżej jedno** zadanie, wykonuje je, pisze sprawozdanie na sprawie i zamyka
zadanie. Na ekranie widać każdy z tych kroków.

**Zrób to pierwszy raz na zadaniu testowym.** Zadania nie zakłada się samemu — poproś
administratora, żeby przypisał ci jedno próbne (np. „wypisz zawartość katalogu roboczego")
przy sprawie, na której nie przeszkadza dodatkowy wpis. Pierwszy przebieg na prawdziwej
sprawie klienta zostawia ślad, którego nie da się cofnąć.

Gdy nie ma żadnego zadania, `--once` kończy się bez pracy i bez błędu — wypisuje tylko
wiersz startowy workera.

**6. Zostaw workera pracującego**

```bash
./sf-kit worker
```

Pętla: co minutę sprawdza, czy jest coś nowego. Działa tak długo, jak otwarte jest okno
terminala — **zamknięcie okna zatrzymuje workera i nikt o tym nie informuje**. Żeby przeżył
zamknięcie terminala i restart komputera, użyj gotowych plików z katalogu
[`uruchamianie/`](uruchamianie/README.md) (tmux, launchd dla macOS, systemd dla Linuksa).

---

### 2. Cztery pojęcia

Tyle wystarczy, żeby pracować. Pełniejszy słownik jest na końcu dokumentu.

| pojęcie | czym jest | z czym to porównać |
|---|---|---|
| **Organizacja** | firma albo projekt, w którego ramach toczy się praca. Wszystko, co widać, należy do jednej Organizacji. | przestrzeń robocza |
| **Sprawa** | kontener na temat: opis problemu, historia rozmowy, załączniki, decyzje. Żyje długo. | wątek / zgłoszenie |
| **Zadanie** | jednostka pracy do wykonania. Ma tytuł, opis, status i wykonawcę. Zwykle wisi przy sprawie. | pozycja na tablicy kanban |
| **Wpis** | wiadomość dopisana do sprawy. Tak rozmawia się z ludźmi: co zrobione, o co pytanie. | komentarz w wątku |

Cykl pracy: **zadanie → wykonanie → wpis na sprawie → zadanie zamknięte.**

#### Statusy zadania

- `queued` — czeka, nikt się nim nie zajmuje. **To są zadania do wzięcia.**
- `in_progress` — ktoś właśnie nad nim pracuje.
- `on_hold` — wstrzymane, czeka na coś z zewnątrz.
- `completed` — zrobione.

---

### 3. Pętla pracy

`sf-kit worker` robi to za ciebie. Warto jednak wiedzieć, co się dzieje — bo przy błędzie
trzeba wskazać krok, na którym stanęło.

```
  1. Weź swoje zadania   GET   /api/v1/tasks?assignee_kind=agent&status=queued
                         → odsiej po swoim slugu (pole `assigned_agent_slug`)
  2. Przyjmij zadanie    PATCH /api/v1/tasks/{id}    {"status": "in_progress"}
  3. Zrób robotę         (Kit uruchamia tu Codexa w katalogu roboczym)
  4. Zdaj sprawozdanie   POST  /api/v1/tickets/{ticket_id}/entries
  5. Zamknij zadanie     PATCH /api/v1/tasks/{id}    {"status": "completed"}
```

**Krok 1 działa inaczej, niż mogłoby się wydawać.** SalesForge nie ma filtru „zadania agenta
o slugu X" — parametr `assignee` przyjmuje wewnętrzny numer konta, którego posiadacz klucza
nie zna. Kit pobiera więc zadania agentów **stronami po 200** i odsiewa je u siebie po polu
`assigned_agent_slug`, aż przejrzy całą kolejkę albo znajdzie pierwsze swoje zadanie.

Ma to znaczenie praktyczne: przy kolejce liczonej w setkach zadań pytanie o samą pierwszą
stronę pokazywałoby „brak zadań" komuś, kto zadanie ma. Braki tego rodzaju są opisane
w §11.

**Krok 4 — wpis idzie na SPRAWĘ, nie na zadanie.** Zadanie ma pole `ticket_id`; to jego
się używa. Zadanie bez sprawy nie ma gdzie dostać sprawozdania — patrz §8.

**Nagłówek `X-Tenant-Id` idzie przy KAŻDYM żądaniu.** Jego wartość to identyfikator
Organizacji, który podaje administrator. Bez niego SalesForge nie wie, o czyje dane chodzi.

---

### 4. Klucz — skąd się bierze i jak go trzymać

Klucz API dostaje się **raz**, od administratora SalesForge. Zaczyna się od `sk_live_`.
Jest to **hasło do konta**: kto go ma, ten jest tobą.

#### Jak go zapisać

```bash
sf-kit init
```

Polecenie pyta o klucz **bez pokazywania go na ekranie** i zapisuje:

- **macOS** → do pęku kluczy (`security add-generic-password`),
- **Linux** → do `~/.config/sf-kit/credentials` z prawami `600` (czyta tylko twoje konto).

#### Trzy rzeczy, których z kluczem nie wolno

**1. Nie podawać go modelowi.** Klucz należy do programu, który uruchamia model, nie do
modelu. Model, który zna klucz, może go powtórzyć w dowolnej odpowiedzi — także w takiej,
którą ktoś skopiuje dalej. Dlatego `sf-kit init` wykonuje **człowiek, sam, w terminalu**.

**2. Nie wklejać go do polecenia.** Argumenty procesu widzi każdy użytkownik maszyny
(`ps aux`), a historia powłoki zapisuje je na dysk. `sf-kit init` istnieje po to, żeby
nie było takiej potrzeby.

**3. Nie zapisywać go w repozytorium.** Kit broni przed tym sam: `sf-kit init` włącza
sprawdzanie plików przy każdym `git commit` **w katalogu Kitu** i przerywa zapis, jeśli
znajdzie w nich ciąg zaczynający się od `sk_live_`.

Włączenie ręczne i sprawdzenie, czy ochrona naprawdę działa:

```bash
./hooks/install.sh                  # włącz sprawdzanie przy commitach w tym katalogu
bash hooks/pre-commit --autotest    # sprawdź w obie strony: łapie klucz, przepuszcza resztę
```

Drugie polecenie jest tam z konkretnego powodu. Taka ochrona ma dwa sposoby na to, żeby
wyglądać na działającą, nie działając: może przepuszczać klucze (i wtedy nic nie chroni)
albo blokować wszystko (i wtedy zostaje wyłączona przy pierwszym pośpiechu). `--autotest`
sprawdza **oba** kierunki jednym poleceniem, więc odpowiedź na pytanie „czy to naprawdę
działa" zajmuje sekundę, a nie wieczór.

Ochrona obejmuje **tylko katalog Kitu**. W innych repozytoriach nic nie pilnuje.

**Jeśli klucz gdziekolwiek wyciekł** — powiedz administratorowi od razu i poproś o nowy.
Wyciek plus milczenie jest gorszy niż sam wyciek.

#### Ważność i samoodnowienie (od v0.7)

Klucz agenta jest ważny **30 dni** (ADVERTPR-779). Kit robi z tym dwie rzeczy:

**Ostrzega z wyprzedzeniem.** Na siedem dni przed terminem worker pisze w dzienniku, że klucz
wygasa i kogo poprosić o przedłużenie; po terminie mówi wprost, że **to nie jest awaria
SalesForge**. `sf-kit whoami` pokazuje przy dacie, ile to jest dni.

**Wymienia sekret sam, jeśli wolno.**

```bash
sf-kit rotate        # ręcznie, w oknie siedmiu dni przed terminem
```

Worker robi to samo raz na dobę, bez pytania. Żeby odnowienie przeszło, muszą zajść **oba**
warunki (decyzja Damiana z 14.09):

- konto ma nadanie **`keys:self-renew`** w tej Organizacji (nadaje owner/admin albo superadmin,
  np. `sf-kit nadaj`),
- klucz **nie jest zawężony** — albo jest, ale ma to uprawnienie wypisane w swoim zakresie.

Reguły, które liczy SalesForge (Kit ich nie powtarza — próbuje i pokazuje odpowiedź):

| reguła | co się dzieje poza nią |
|---|---|
| okno **7 dni** przed terminem | 409 „za wcześnie" — normalny stan przez pierwsze trzy tygodnie |
| **jedno** odnowienie na okno | 429 — drugie znaczy, że nowy sekret nie został zapisany |
| sufit **180 dni** od ostatniego przedłużenia **przez człowieka** | 409 — dalej musi wejść człowiek |

**Stary sekret umiera w chwili odpowiedzi** („jeden żywy sekret naraz"). Kit zapisuje nowy
w pęku, zanim zrobi z odpowiedzią cokolwiek innego — ale jeśli proces zginie dokładnie w tej
szczelinie, dostęp przepada i trzeba poprosić człowieka o nowy klucz. Dlatego rotacja chodzi
w oknie siedmiu dni, a nie w ostatniej godzinie.

---

### 5. Uprawnienia — co widzisz, co to znaczy, co powiedzieć użytkownikowi

Ta sekcja jest po to, żeby agent umiał **rozpoznać problem po objawie** i powiedzieć
człowiekowi, o co poprosić. Nie trzeba jej znać na pamięć — trzeba do niej wrócić, gdy
coś odmówi.

#### Zasada, z której wynika cała reszta

> **Uprawnienia nie mieszkają na kluczu. Mieszkają na członkostwie użytkownika
> w Organizacji.**

Prawa to suma trzech rzeczy: rola systemowa + tagi roli + nadania wpisane wprost na
członkostwie. Klucz osobisty czyta to wszystko w chwili każdego żądania.

Praktyczny skutek, który zmienia odpowiedź udzielaną użytkownikowi: **brakującego
uprawnienia nie naprawia się wymianą klucza.** Administrator dodaje je na członkostwie
— jedno kliknięcie w panelu — i działa natychmiast, tym samym kluczem.

#### Co jest potrzebne do pracy

| czynność | endpoint | dodatkowe uprawnienie |
|---|---|---|
| odczyt listy zadań | `GET /api/v1/tasks` | – |
| odczyt szczegółów zadania | `GET /api/v1/tasks/{id}` | – |
| komentarz do zadania | `POST /api/v1/tasks/{id}/comments` | – |
| wpis na sprawie | `POST /api/v1/tickets/{id}/entries` | `tickets:comment` |
| **przyjęcie i zamknięcie zadania** | `PATCH /api/v1/tasks/{id}` | `tasks:own` |

`tasks:own` znaczy dokładnie tyle: wolno zmienić **status zadania, którego jest się
wykonawcą**. Nie cudzego, nie nieprzypisanego, i tylko status — nie tytuł ani termin.
Zakładanie i kasowanie zadań to inne uprawnienie, którego worker nie potrzebuje.

Zestaw wystarczający do pracy: **`tickets:read`, `tickets:comment`, `tasks:own`**.
Konto agenta zakładane z panelu dostaje go automatycznie.

#### Rozpoznawanie po objawie

| co widzisz | co to znaczy | co zrobić |
|---|---|---|
| `401` przy każdym żądaniu | klucz nieznany, wygasły albo niewysłany | `sf-kit whoami`. Jeśli nie działa — klucz jest zły lub odwołany. Nie ponawiaj w pętli |
| `403` przy `PATCH /tasks/{id}` | brak `tasks:own` **albo** to nie jest twoje zadanie | sprawdź w `sf-kit tasks`, czy zadanie jest na twojej liście. Jest → brakuje uprawnienia. Nie ma → to nie twoje zadanie |
| `403` przy wpisie na sprawie | brak `tickets:comment` | prośba do administratora (zdanie niżej) |
| `404` na zadaniu, które istnieje | brak dostępu do tej Organizacji albo do tej sprawy | sprawdź, czy `X-Tenant-Id` to ta Organizacja, o którą chodzi |
| odczyt działa, zapis odmawia | klucz działa, ale nadań brakuje | to nie jest problem z kluczem — patrz zasada wyżej |
| wszystko odmawia mimo świeżego klucza | klucz może nie być osobisty | patrz „Zasięg klucza" niżej |

#### Gotowe zdanie do przekazania użytkownikowi

Gdy przyczyną jest brak nadania, człowiek nie musi rozumieć modelu uprawnień. Wystarczy,
że przekaże administratorowi to:

> „Proszę o nadanie uprawnienia **`tasks:own`** na członkostwie **konta agenta o slugu
> `<slug>`** w tej Organizacji w SalesForge. To jedno kliknięcie w panelu, klucza nie
> trzeba wymieniać."

W miejsce `<slug>` wstaw slug z `sf-kit whoami`, a w miejsce `tasks:own` — uprawnienie,
którego brakuje (`tickets:comment` przy wpisach).

> **Uwaga, łatwo tu wskazać złą osobę.** Uprawnienie nadaje się na członkostwie **konta
> agenta**, a nie na koncie człowieka, który uruchamia Kit. To są dwa różne konta: agent
> ma własne, z własnym slugiem, i to jemu wystawiono klucz. Prośba napisana w pierwszej
> osobie („na moim członkostwie") potrafi skończyć się nadaniem uprawnienia człowiekowi,
> po którym `403` nie zniknie — i wtedy szuka się przyczyny tam, gdzie jej nie ma.

#### Zasięg klucza — rozpoznanie, nie wykład

Klucz może być wystawiony na osobę, na członkostwo albo na całą Organizację. Klucz agenta
ma być **osobisty** (`scope=user`). Objawy mówią, kiedy jest inaczej:

- **nadanie dodane przez administratora nic nie zmieniło** — klucz najprawdopodobniej niesie
  własną, zamrożoną listę uprawnień. Lista na kluczu działa jak **sufit**: uprawnienia
  efektywne to prawa właściciela **przecięte** z nią. Dopisanie czegoś na członkostwie nie
  przebije klucza, który tego nie ma;
- **działania nie są podpisane kontem agenta** albo klucz nie ma właściciela — to klucz
  Organizacji, czyli klucz integracji, nie osoby;
- **odmawiają bramki pytające o rolę**, choć pojedyncze uprawnienia są nadane — klucz nie
  niesie roli właściciela.

W każdym z tych przypadków właściwą reakcją jest **prośba o klucz osobisty**, nie szukanie
obejścia. Obejście działa do pierwszej zmiany uprawnień i psuje się bez ostrzeżenia.

---

### 6. Endpointy, z przykładami

Każde wywołanie potrzebuje dwóch nagłówków:

```
Authorization: Bearer sk_live_...
X-Tenant-Id: <identyfikator Organizacji>
```

**`X-Tenant-Id` podaje się zawsze — poza jednym wyjątkiem.** Bez niego SalesForge nie wie,
o czyje dane chodzi.

Wyjątkiem jest `GET /api/v1/me` (od 15.09, ADVERTPR-796): działa **bez** tego nagłówka i po to
istnieje — agent czyta go, ZANIM wie, co miałby w nim wpisać. Oddaje konto, klucz (prefiks,
zasięg, czy jest zawężony, termin ważności) i wszystkie Organizacje z rolą oraz uprawnieniami
**efektywnymi**, czyli dokładnie tymi, które policzy bramka przy żądaniu.

```bash
curl -s -H "Authorization: Bearer $SF_KEY" \
  "$SF_URL/api/v1/me"
```

To jest jedyne wiarygodne źródło odpowiedzi na „kim jestem i co mi wolno". Wcześniej Kit
zgadywał to po skutku — próbował odczytu zadań i wnioskował z tego, czy klucz żyje.

> W przykładach klucz jest w zmiennej `$SF_KEY`, a nie wpisany wprost — patrz §4.

#### Zadania do wzięcia

```bash
curl -sS "$SF_URL/api/v1/tasks?assignee_kind=agent&status=queued&limit=200&offset=0" \
  -H "Authorization: Bearer $SF_KEY" \
  -H "X-Tenant-Id: $SF_TENANT"
```

Odpowiedź: `{"items": [...], "total": 518, "limit": 200, "offset": 0}`.

`total` mówi, ile zadań jest **w całej kolejce**, a nie ile przyszło na tej stronie. Gdy
`total` jest większe niż `limit`, trzeba pytać dalej, zwiększając `offset` — inaczej zadanie
stojące dalej w kolejce nie zostanie zauważone (`sf-kit` robi to za ciebie).

Każda pozycja ma m.in. `id`, `title`, `body_md` (treść zadania — **to jest polecenie do
wykonania**), `status`, `assigned_agent_slug`, `ticket_id`, `ticket_ref`, `version`.

#### Przyjęcie zadania

```bash
curl -sS -X PATCH "$SF_URL/api/v1/tasks/$TASK_ID" \
  -H "Authorization: Bearer $SF_KEY" -H "X-Tenant-Id: $SF_TENANT" \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress"}'
```

#### Wpis na sprawie (sprawozdanie)

```bash
curl -sS -X POST "$SF_URL/api/v1/tickets/$TICKET_ID/entries" \
  -H "Authorization: Bearer $SF_KEY" -H "X-Tenant-Id: $SF_TENANT" \
  -H "Content-Type: application/json" \
  -d '{"entry_type": "note", "content": "**Sedno** — ...", "visibility": "internal"}'
```

`visibility`: `internal` (widzi zespół) albo `public` (widzi też klient). **W razie wątpliwości
zawsze `internal`** — treści, której klient nie miał zobaczyć, nie da się odzobaczyć.

#### Zamknięcie zadania

```bash
curl -sS -X PATCH "$SF_URL/api/v1/tasks/$TASK_ID" \
  -H "Authorization: Bearer $SF_KEY" -H "X-Tenant-Id: $SF_TENANT" \
  -H "Content-Type: application/json" \
  -d '{"status": "completed"}'
```

#### Komentarz do samego zadania (rzadziej potrzebny)

```bash
curl -sS -X POST "$SF_URL/api/v1/tasks/$TASK_ID/comments" \
  -H "Authorization: Bearer $SF_KEY" -H "X-Tenant-Id: $SF_TENANT" \
  -H "Content-Type: application/json" \
  -d '{"content": "treść", "is_internal": true}'
```

Pole nazywa się `content`, nie `body`. Pomyłka daje `422`.

---

### 7. Kody odpowiedzi

| kod | co znaczy | co zrobić |
|---|---|---|
| **200 / 201** | udało się | nic |
| **401** | klucz nieznany, wygasł albo niewysłany | `sf-kit whoami`; jeśli nie działa — poproś o nowy. Nie ponawiaj w pętli |
| **403** | klucz dobry, ale operacja niedozwolona | patrz §5, tabela objawów |
| **404** | nie ma takiego obiektu **albo** brak do niego dostępu | te dwie rzeczy wyglądają tak samo celowo. Sprawdź identyfikator; jeśli jest dobry — obiekt nie należy do tej Organizacji |
| **409** | ktoś zmienił obiekt przed tobą | pobierz zadanie od nowa i spróbuj jeszcze raz. Nie nadpisuj na siłę |
| **422** | zły kształt żądania | odpowiedź mówi, którego pola brakuje. Najczęstsza pomyłka: `body` zamiast `content` |
| **429 / 5xx** | przeciążenie albo awaria serwera | odczekaj i ponów, zwiększając odstęp (30 s, 60 s, 120 s) |

---

### 8. Zasady, które nie są opcjonalne

**Nie zgaduj kontekstu.** Zadanie z pustą treścią, bez wskazanego katalogu albo bez sprawy
nie nadaje się do wykonania. Wpis „nie mam czego wykonać, bo…" i zostawienie zadania
w kolejce jest właściwą reakcją. Zgadnięty kontekst to praca na cudzych plikach.

**Nie kończ zadania, którego nie zrobiłeś.** `completed` znaczy „zrobione i sprawdzone".
Przy niepowodzeniu: wpis z opisem, status z powrotem na `queued` albo `on_hold`. Zadanie
oznaczone jako zrobione znika ludziom z widoku.

**Sprawozdanie pisz po polsku i po ludzku.** Wpis czyta człowiek, często ktoś, kto nie
widział tej pracy i nie zna użytych narzędzi. Układ:

```
**Sedno** — jedno zdanie: co się udało (albo czego nie i dlaczego).

**Co zrobiono** — 2-5 zdań zwykłym językiem, bez ścieżek i nazw poleceń.

**Szczegóły techniczne** — pliki, polecenia, liczby. Dla tego, kto będzie to sprawdzał.
```

Worker prosi o ten układ w każdym zadaniu i sam go pilnuje: sprawozdanie w tej postaci
trafia na sprawę **bez zmian**, a wyjście w innej postaci zostaje opakowane z adnotacją,
że układu zabrakło.

**Nie wysyłaj sekretów.** Żadnych haseł, kluczy ani zawartości plików `.env` we wpisach.
Gdy trzeba zgłosić błąd konfiguracji — podaj **nazwę** zmiennej, nigdy jej wartość.

---

### 9. Prowadzisz użytkownika

Agent jest tu przewodnikiem: człowiek po drugiej stronie najczęściej nie zna SalesForge
i nie ma powodu go poznawać. Kilka rzeczy, które ułatwiają tę rolę.

**Przy pierwszym uruchomieniu u nowej osoby** — zacznij od sprawdzenia, czy ma komplet
czterech danych od administratora (§1). Brak choćby jednej z nich zatrzyma pracę na kroku 2,
a wygląda to wtedy jak usterka narzędzia.

**Czego nie robić za człowieka:** klucz wpisuje **on sam**, w terminalu, poleceniem
`sf-kit init`. Nie proś o klucz w rozmowie i nie proponuj, że go wpiszesz — nawet gdy to
przyspieszy sprawę. Powód: §4, punkt 1.

**Jak wytłumaczyć pojęcia komuś, kto nigdy nie widział SalesForge** — najkrócej przez
porównanie do rzeczy znanych:

- **Organizacja** to przestrzeń robocza jednej firmy. Wszystko, co widać, jest w środku.
- **Sprawa** to wątek o jednym temacie: opis, rozmowa, załączniki, decyzje. Żyje tygodniami.
- **Zadanie** to jedna rzecz do zrobienia, wisząca zwykle przy sprawie.
- **Wpis** to wiadomość dopisana do sprawy — tak zdaje się sprawozdanie i tak zadaje pytania.

**Kiedy odesłać do administratora:** przy każdym `403`, którego przyczyną jest brak nadania,
przy `401` z kluczem, który przestał działać, i przy podejrzeniu, że klucz nie jest osobisty.
Gotowe zdanie do przekazania jest w §5 — użyj go zamiast tłumaczyć model uprawnień.

**Czego nie obiecywać:** że zadanie zostanie zauważone natychmiast (worker odpytuje co
minutę) i że wynik pojawi się w powiadomieniu (Kit pisze na sprawie — tam trzeba zajrzeć).

#### Gdzie człowiek zobaczy wynik pracy

Wynik to **wpis na sprawie** w SalesForge i tam trzeba po niego pójść — nie przychodzi
mailem ani powiadomieniem. Drugim śladem jest samo zadanie: zmienia status na `completed`
i znika z kolejki.

**Od v0.4 przy wpisie wiszą PLIKI, a nie ścieżki.** Do v0.3 worker pisał w sprawozdaniu, gdzie
na jego maszynie leży wynik — co dla każdego, kto tej maszyny nie ma, znaczyło dokładnie nic.
Teraz plik jest do kliknięcia w sprawie. Worker bierze:

1. **to, co zadanie nazwało wynikiem** — linia `WYNIK: <ścieżka>` w treści zadania (może ich
   być kilka). Sama nazwa pliku jest szukana kolejno w `work/zadania/`, `work/`, `outgoing/`
   i katalogu roboczym;
2. **oraz wszystkie nowe pliki z katalogów wynikowych** — domyślnie `work/zadania/`
   i `outgoing/`, tylko te zmienione PO rozpoczęciu zadania. Jeden wpis mieści 20 plików.

**Obie drogi naraz — od v0.5.6.** Wcześniej wskazanie `WYNIK:` wygrywało i katalogów nie
czytaliśmy wcale. Zmieniło się, bo wykonawca potrafi zapisać wynik gdzie indziej niż zapowiedział
i wtedy **praca przepadała po cichu** — a cisza jest gorsza niż jeden załącznik za dużo.
Przed doklejeniem cudzego wyniku nadal bronią trzy granice: tylko pliki zmienione po starcie
zadania, tylko spod katalogu roboczego i sufit 20 plików. Pliki z poprzednich zadań zostają
na miejscu: doklejenie ich znaczyłoby wynik jednego klienta w sprawie drugiego.

Czego SalesForge nie przyjmuje, Kit wysyła mimo to — praca jest zrobiona, więc nie może przepaść
przez rozszerzenie. `.py` i `.json` idą jako kopia `.txt` (to tekst, więc nazwa nie kłamie),
a zmiana nazwy jest opisana we wpisie. Wszystko inne, na przykład `.html` czy plik wideo,
**pakujemy do `.zip`** — binarium przemianowane na `.txt` byłoby plikiem, którego odbiorca
nie otworzy. Archiwum i kopie powstają poza katalogiem roboczym i znikają po wysłaniu;
oryginał zostaje tam, gdzie był.

W sprawozdaniu wymienione są też pliki, których **nie** załączono, razem z powodem („nie ma
takiego pliku", „poza katalogiem roboczym", „powyżej limitu"). Cisza o nich byłaby stratą.

**Zadanie, które obiecało wynik i go nie oddało, nie zamyka się jako zrobione** (v0.5.7).
Gdy treść zadania zawiera `WYNIK: <plik>`, a pliku po pracy nie ma (albo jest pusty, albo leży
poza katalogiem roboczym), worker zdaje sprawozdanie i oznacza zadanie jako **nieudane**
(`failed`), zamiast je domknąć. Bramka jest wąska celowo: zadanie bez linii `WYNIK:` — na
przykład „sprawdź i opisz" — zamyka się normalnie, bo jego produktem jest sprawozdanie.
Starsza instalacja SF, która nie zna statusu `failed`, dostaje zadanie z powrotem do kolejki —
gorzej, ale bez kłamstwa.

**Nieudane zadanie ma najwyżej trzy próby** (v0.5.6): kolejna po 10 minutach, następna po 60,
a potem zadanie dostaje status `failed` i przestaje wracać. Licznik i termin następnej próby
są trwałe (`state.json` obok konfiguracji), więc restart workera ich nie zeruje. Gdy człowiek
ruszy status zadania, licznik kasuje się sam — zmiana wersji zadania znaczy „ktoś się tym zajął".

**Od v0.5.2 model DOWIADUJE SIĘ o `outgoing/` z polecenia** (ADVERTPR-850). Wcześniej katalog
był konwencją znaną Kitowi, ale nieznaną wykonawcy — więc model zapisywał wynik tam, gdzie mu
było wygodnie, `outgoing/` zostawał pusty i wpis szedł bez załącznika. Objawu nie było: worker
nie zgłaszał błędu, bo z jego punktu widzenia po prostu nie powstał żaden plik. Wyszło dopiero
na ADVERTPR-846, gdzie sprawozdanie mówiło „raport zapisany jako `audyt-fm-dev-r14.md`",
a wpis miał zero załączników i plik trzeba było dołożyć ręcznie.

Ramka mówi teraz wprost: pliki wynikowe do `{katalog roboczy}/outgoing/`, warsztat (skrypty,
pobrane strony, stan pośredni) poza nim. Jeśli piszesz zadanie, które ma dać konkretny plik,
i tak warto podać `WYNIK: <ścieżka>` — jawne wskazanie wygrywa z konwencją.

### Profil koordynator — rozdajesz pracę flocie

Sześć poleceń. Wszystkie wymagają uprawnienia `plans:write` w wybranej Organizacji; bez niego
Kit odmawia na wejściu i mówi, gdzie to uprawnienie masz.

```bash
sf-kit flota                      # kto może dostać zadanie
sf-kit flota rejestr agents.json [--pokaz]   # migawka rejestru floty do SF (v0.10)
sf-kit zlec --tytul "…" --agent-slug kodeks --sprawa AUT-12 --opis zadanie.md
sf-kit kolejka [--agent-slug kodeks] [--status in_progress]
sf-kit odbierz zadanie-abc-20260915
sf-kit status                     # kim jestem + kolejka floty
```

**`zlec` zawsze wymaga sprawy.** To twarda strona zasady „twardo przy zakładaniu, miękko przy
wykonaniu": zadanie bez sprawy da się wykonać, ale jego wynik nie ma gdzie wylądować. Jeśli
sprawa jest w Organizacji, do której wykonawca nie ma dostępu, Kit odmówi i podpowie, żeby
założyć sprawę pomocniczą w jego Organizacji — zadanie na niewidocznej sprawie jest
niewykonalne, a wygląda na wysłane.

**`flota` pokazuje też agentów bez sluga**, z adnotacją „nie da się zlecić". Takie członkostwo
jest błędem konfiguracji po stronie administratora; ukrycie go znaczyłoby, że nikt nie wie,
że jest co naprawić.

**`odbierz` nie zamyka na słowo.** Najpierw sprawdza, czy na sprawie widać ślad po tym zadaniu
— wpis wskazujący jego identyfikator albo załącznik przy takim wpisie. Jeśli nie widzi, odmawia
i mówi dlaczego. Zamykanie bez sprawdzenia znaczyłoby, że status „zrobione" przestaje cokolwiek
znaczyć: zadania schodzą z tablicy niezależnie od tego, czy coś po nich zostało.

Jeden przypadek jest opisany osobno: gdy część wpisów na sprawie jest **poza twoim poziomem
widoczności**, Kit powie to wprost, zamiast twierdzić, że wyniku nie ma. Brak dowodu to nie
dowód braku.

#### Migawka rejestru floty — `flota rejestr` (v0.10, SF-18)

Dashboard floty w SF pokazuje **rodzaj silnika** (`claude`/`codex`/`kimi`) i **rozjazdy
rejestru**, ale SF nie ma ich skąd wziąć: topologia floty mieszka wyłącznie w rejestrze
`agents.json` na macu (ten sam plik czyta tic). To polecenie zabiera stamtąd migawkę:

```bash
sf-kit --org advertpro-co flota rejestr /ścieżka/do/agents.json --pokaz   # co by poszło
sf-kit --org advertpro-co flota rejestr /ścieżka/do/agents.json           # wyślij
```

- **Ścieżka jest parametrem**, bo polecenie odpala tic albo worker-tick na macu, a na VPS
  rejestru nie ma.
- **Slug:** `sf_agent_slug`, a gdy go brak — `id` wpisu. Pole `sf.agent_slug` **nie** jest
  źródłem: w rejestrze z 24.09 pięć wpisów ma tam tę samą, skopiowaną wartość. Rozjazd między
  nim a slugiem Kit pokazuje jako `UWAGA`, bo to błąd rejestru do poprawienia u źródła.
- **Idzie cała lista**, także wycofani (z `aktywny: false`). SF zastępuje migawkę w całości,
  więc powtórzenie niczego nie psuje i tic może wołać polecenie po każdej zmianie pliku.
- **Wychodzą tylko pola kontraktu** (`slug`, `nazwa`, `rodzaj`, `maszyna`, `katalog`,
  `aktywny`). Instrukcje, notatki i flagi uruchomienia zostają na macu.
- **Odpowiedź niesie rozjazdy** wobec rejestru SF, pogrupowane po rodzaju (konto bez wpisu,
  wpis bez konta, inna nazwa). Kod wyjścia to 0 także przy rozjazdach, bo rozjazd jest
  wiadomością dla człowieka, a nie awarią wysyłki. 1 oznacza, że nie wysłano (np. 404, gdy
  serwer nie ma jeszcze tej trasy), a 2 oznacza zły plik.

Migawka jest **per Organizacja** — wybierz tę, w której flota ma konta (`--org`). Wpisy
agentów z innych Organizacji wrócą jako „wpis lokalny bez konta w SF".

#### Zadanie bez sprawy — co się wtedy dzieje

Zadanie może nie mieć przypiętej sprawy. Wtedy **nie ma osi, na której dałoby się zostawić
ślad** — a praca bywa już wykonana.

`sf-kit tasks` oznacza takie zadanie z góry:

```
  zadanie-bez-sprawy-20260915
    Przygotuj zestawienie
    ⚠ bez sprawy — wynik trafi tylko do komentarza zadania
```

Worker takie zadanie **wykona** (do v0.3 odmawiał — i praca przepadała po fakcie), a wynik
odłoży w komentarzu zadania razem ze zdaniem mówiącym wprost, że nie ma go na żadnej osi.
Jeśli wynik ma być widoczny dla klienta albo dla zespołu — zadanie trzeba przepiąć do sprawy
i poprosić o powtórzenie.

**Do panelu SalesForge człowiek potrzebuje własnego dostępu.** Klucz wpisany w `sf-kit init`
należy do **konta agenta** — to nie jest login człowieka i nie otworzy nim przeglądarki.
To osobna rzecz do poproszenia administratora, obok czterech danych z §1:

> „Proszę o dostęp do panelu SalesForge dla mnie osobiście, żebym mógł/mogła oglądać sprawy
> i wpisy agenta w przeglądarce."

Bez tego powstaje stan dość absurdalny: agent pracuje, a osoba, która go uruchomiła, nie widzi
efektów. Warto załatwić to od razu, a nie po pierwszym wykonanym zadaniu.

Adres sprawy wygląda tak: `<adres SalesForge>/tickets/<identyfikator sprawy>`. Identyfikator
bierze się z pola `ticket_id` zadania (`sf-kit tasks` pokazuje obok zadania jego sprawę —
`ticket_ref` to nazwa czytelna dla człowieka, `ticket_id` to identyfikator do adresu).

#### Czego te zadania w ogóle dotyczą

Wykonawcą jest Codex pracujący **na plikach w katalogu roboczym** — więc zadania są tego
rodzaju: uporządkuj katalog, przygotuj zestawienie z plików, popraw treść, wygeneruj
raport, sprawdź dane w arkuszu. Nie są to zadania wymagające klikania w cudzych systemach
ani dostępu do rzeczy spoza tego katalogu; takie Kit odrzuci, zamiast improwizować.

**Uwaga o kosztach:** każde wykonane zadanie zużywa limit konta Codexa osoby, która
uruchomiła workera. Przy wyczerpanym limicie albo wygasłym logowaniu zadania zaczną kończyć
się niepowodzeniem — i będą wracać do kolejki z wpisem mówiącym, na czym stanęły.

---

### Profil koordynator — warstwa administracyjna: konta, nadania, klucze

Cztery polecenia. Powstały z jednej doby (18.09.2026, ADVERTPR-879), w której koordynatorka
**trzy razy ogłosiła „tego się nie da"**, a funkcja istniała pod adresem, w który akurat nie
strzeliła. Za każdym razem kosztem był czas i fałszywa diagnoza wpisana do sprawy, którą potem
trzeba było prostować.

```bash
sf-kit kontrakt                       # spis operacji, które Kit zna
sf-kit kontrakt nadaj                 # pola, pułapki, sposób weryfikacji
sf-kit agent-dodaj arek-sf --email arek@x.pl --nazwa "Arek"
sf-kit nadaj <uuid-konta> --pokaz
sf-kit nadaj <uuid-konta> --uprawnienie tickets:read --uprawnienie tickets:write
sf-kit klucz-wystaw "Integracja X" --zakres user --wlasciciel arek@x.pl
```

#### Numeru Organizacji nie wpisujesz. Nigdzie

Trasy administracyjne mają w ścieżce **liczbę porządkową** (`tenants.id`, np. `7`), a nagłówek
żądania niesie **uuid** tej samej Organizacji. Dwa identyfikatory jednego bytu w jednym żądaniu
— i żaden z nich nie jest oczywisty.

Kit nie ostrzega przed tą pułapką, tylko ją **usuwa**: podajesz `--org <slug>` albo nic (wtedy
Organizacja bieżąca), a tłumaczenie robi `GET /tenants`. Ta trasa oddaje `id` obok `uuid`
także zwykłemu członkowi — nie trzeba być superadminem, żeby ją odczytać.

#### Każde polecenie kończy się sprawdzeniem, nie kodem odpowiedzi

To jest sedno tej rundy. Wpadka z 18.09 nie polegała na tym, że coś odpowiedziało błędem —
polegała na tym, że **serwer odpowiedział 201 na konfigurację, która nie działa** (klucz z polem
`scope`, przyjętym i zignorowanym). Wyszło po pół nocy pracy.

Dlatego `agent-dodaj` i `klucz-wystaw` po wystawieniu sekretu wołają nim `GET /me` i pokazują,
czy działa i w których Organizacjach. `nadaj` po zapisie odczytuje stan i pokazuje różnicę
(co nadane, co odebrane). Wyłącznik jest — `--bez-proby` — ale domyślnie Kit sprawdza.

#### Pole, którego trasa nie zna, zatrzymuje się przed wysyłką

`sf-kit kontrakt <operacja>` wypisuje nie tylko pola wymagane i opcjonalne, ale też **pola,
których ta trasa NIE obsługuje — z adresem tej, która je obsługuje**. Te same zdania wracają
jako odmowa, gdy spróbujesz takie pole wysłać.

Powód jest konkretny: `PATCH /tenants/{id}/agents/{uuid}` z polem `permissions` odpowiadał do
18.09 **200 i nie robił nic** (poprawione po stronie API tego samego dnia). Sukces bez skutku
jest droższy od odmowy, bo przyczyny szuka się potem w zupełnie innym miejscu.

#### Czego Kit świadomie nie obsługuje — i jak to sprawdzić

```bash
sf-kit kontrakt opinie          # → „wyłącznie panel, API tego nie wystawia"
sf-kit kontrakt niezobaczone    # → „403 dla klucza jest zamierzone, nie usterka"
sf-kit kontrakt plany           # → „trasy istnieją, Kit ich jeszcze nie obsługuje"
```

Odpowiedź „nie ma" zawsze niesie **powód**. Bez powodu to samo pytanie wraca nazajutrz, a
wpisane do sprawy jest fałszywą diagnozą do prostowania — dokładnie tym, od czego ta sprawa
się zaczęła.

#### Skąd Kit wie, co która trasa przyjmuje

Katalog operacji siedzi w `sf_kit/kontrakt.py` i działa **bez sieci**. Jest to kopia kształtu,
który żyje po stronie SalesForge — czyli kandydat do cichego rozjazdu. Dlatego:

```bash
sf-kit kontrakt --sprawdz       # porównaj katalog z żywym openapi.json serwera
```

porównuje trasy, nazwy pól i pola wymagane, i **wypisuje różnicę w obie strony** („serwer
przyjmuje, Kit odrzuci" jest groźniejsze niż odwrotność, bo blokuje pracę).

Docelowo kontrakt ma być czytany z serwera, nie z katalogu. Dziś się nie da:
`https://sf.dpakula.pl/openapi.json` oddaje **HTTP 200 i stronę frontu** — nginx nie przepuszcza
tej ścieżki do backendu, choć sam dokument istnieje i jest poprawny. Do czasu przepuszczenia tej
ścieżki `--sprawdz` mówi to wprost, zamiast udawać, że sprawdził.

#### Uprawnienia do tych czterech poleceń

Kit **nie odsiewa** ich po uprawnieniu — rozstrzyga serwer, a Kit dba tylko o to, żeby jego
odmowę dało się przeczytać. Powód: `agent-dodaj` wymaga superadmina SF, `nadaj` roli owner,
`klucz-wystaw` roli admin, a żadne z nich nie ma nic wspólnego z `plans:write`, po którym
odsiewane są polecenia zlecania. Bramka po cudzym uprawnieniu odebrałaby polecenie komuś,
kto ma prawo je wykonać.

---

### 9a. Scenariusze profilu ASYSTENT

Ta sekcja jest dla agenta, który pracuje **obok człowieka** i zgłasza wyniki do SalesForge.

#### „Makieta gotowa" — krok po kroku

Człowiek mówi: *skończyłam, wyślij to*. Od tego momentu prowadzisz.

**1. Zbierz, co ma pójść.** Trzy rzeczy, w tej kolejności ważności:
- **sama praca** — pliki makiety (HTML, CSS, obrazy). **Spakuj je do jednego `.zip`**;
  SalesForge nie przyjmuje pojedynczych plików `.html`, a spakowana makieta i tak jest
  lepsza, bo trzyma się w całości razem z CSS-em i obrazami (§11);
- **zrzuty ekranu** — jak to wygląda. `.png` przechodzi bez pakowania;
- **notatka** — dla kogo to jest, co obejmuje, czego NIE obejmuje. `.md` albo `.txt`.

**2. Napisz opis.** Kit podpowie szkielet, jeśli podasz sam tytuł, ale **uzupełnij go**:

```
**Sedno** — makieta strony głównej dla Klienta X gotowa do przeglądu.

**Co jest** — trzy widoki (desktop, tablet, telefon), statyczny HTML + CSS,
bez podpięcia do CMS-a i bez treści docelowych (lorem ipsum w sekcji „O nas").

**Jak odebrać** — rozpakuj `makieta.zip`, otwórz `index.html` w przeglądarce.
Zrzuty w załączniku pokazują, jak to ma wyglądać na telefonie.
```

Trzy nagłówki nie są ozdobą: to trzy pytania, na które odbiorca i tak musi odpowiedzieć
sobie sam, gdy ich nie ma — a wtedy pyta człowieka, którego właśnie chcieliśmy odciążyć.

**3. Zgłoś.**

```bash
sf-kit zglos --tytul "Makieta strony głównej dla Klienta X" \
             --opis opis.md --tag makieta \
             --zalacz makieta.zip zrzut-desktop.png zrzut-telefon.png
```

**3a. Nie jesteś pewien, czy to ma iść w świat? `--szkic` (v0.5.4).**

```bash
sf-kit zglos --tytul "Propozycja zmian w cenniku" --opis opis.md --szkic
```

Sprawa powstaje jako **wersja robocza**: nie wychodzi żadne powiadomienie, nie ma jej na
listach ani w licznikach, a obserwujący siedzą w niej od początku i pocztę dostaną dopiero
w chwili publikacji. **Publikuje człowiek** — koordynator poleceniem `sf-kit publikuj
--zgoda <wpis>` (na zgodę ownera/admina z tej Organizacji) albo przyciskiem „Opublikuj" w
SF (SF-51); sam z siebie Kit szkicu nie opublikuje i to jest cały sens szkicu: Ty
przygotowujesz, człowiek wpuszcza do obiegu. Wpisy dopisujesz do szkicu normalnie, też po
cichu.

**4. Podaj człowiekowi numer i adres.** Kit wypisuje oba. To jest jedyne, co człowiek
ma potem powiedzieć albo wkleić komuś innemu — powiedz mu to wprost:

> „Zgłoszone jako **FM-12**: https://sf.dpakula.pl/tickets/… . Od tej chwili pytania
> i uwagi do tej makiety idą wpisami na tej sprawie — dopisuję je stąd, wystarczy,
> że powiesz."

**5. Od tej chwili rozmowa toczy się na sprawie.** Nowa wersja, odpowiedź na uwagę,
poprawka — wszystko `sf-kit wpis`, nie nowe zgłoszenie. Druga sprawa o tej samej makiecie
rozdziela rozmowę na dwa miejsca i nikt już nie wie, gdzie jest aktualny stan.

#### „Postęp" — w trakcie pracy

Po każdym większym etapie, gdy człowiek chce, żeby było to widać:

```bash
sf-kit wpis FM-12 --opis postep.md --zalacz podglad.png
```

Nie po każdej zmianie pliku. Wpis ma odpowiadać na pytanie „co się zmieniło od ostatniego
razu", a nie odtwarzać historię edycji — od tego jest repozytorium, nie sprawa.

#### Poprawianie własnych wpisów (v0.11, ADVERTPR-782)

Wpis na sprawie da się poprawić. SalesForge **zachowuje poprzednią wersję** i nikt, także
superadmin, nie może jej skasować. Przy wpisie widać „edytowano”, a historia jest do
przejrzenia w panelu i w Kicie.

```bash
sf-kit wpis-edytuj ADVERTPR-782 dba3ae21 --plik poprawiony.md --powod "zła liczba w tabeli"
sf-kit wpis-wersje ADVERTPR-782 dba3ae21          # bieżąca treść + poprzednie wersje
```

- **Wpis wskazujesz** pełnym identyfikatorem albo jego początkiem (co najmniej 6 znaków).
  Tak pokazują go Kit i wpisy. Gdy początek pasuje do dwóch wpisów, Kit odmawia i wypisuje
  oba: poprawienie nie tego wpisu zostawia ślad w historii cudzej wypowiedzi.
- **Treść najlepiej podać plikiem** (`--plik`, albo `-` ze standardowego wejścia). `--tresc`
  jest na krótkie poprawki, bo argument polecenia widzi `ps` na maszynie.
- **`--powod`** trafia do historii. Jest opcjonalny, ale pomaga czytającemu.
- **Historię czytaj tak:** każda wersja to stan **sprzed** zmiany, a „zastąpiona … przez X”
  mówi, kto i kiedy ją podmienił. Nie mówi, kto ją napisał.

**Kiedy edytować, a kiedy dopisać nowy wpis.** Edytuj, gdy poprawiasz własny błąd, którego
nikt jeszcze nie przeczytał albo który nie zmienia sensu: literówkę, złą liczbę, zły link.
**Dopisz nowy wpis**, gdy zmienia się stan rzeczy („jednak nie działa”, „nowe ustalenie”)
albo gdy ktoś już odpowiedział na starą treść. Edycja nie wysyła powiadomień, więc obserwujący
nie dowiedzą się o zmianie sensu, a odpowiedź pod wpisem straci swój kontekst.

**Kto może edytować:** autor wpisu, administrator Organizacji i superadmin. Klucz API
z rolą administratora Organizacji albo superadmina może edytować każdy wpis tej Organizacji.
Wpisów systemowych (zmiana statusu, zmiana pola, założenie sprawy, załącznik) nie edytuje nikt.

**Własny wpis pisany kluczem.** Od wdrożenia 782 na serwerze SalesForge (D5) wpis zapisany
kluczem niesie znacznik, **którym kluczem go napisano i kto jest właścicielem klucza**. Za
własny uznaje go ten sam klucz albo nowy klucz tego samego właściciela, więc rotacja nie
odbiera własności. **Wpisy sprzed wdrożenia** znacznika nie mają i nie są niczyje: poprawi je
tylko administrator albo superadmin. Przy odmowie Kit mówi, co zrobić: dopisać nowy wpis
z korektą albo poprosić administratora.

#### Dla agenta — odpowiadaj w sprawie, treść oddawaj w wersjach (SF-51, ADVERTPR-948)

Te reguły wzięły się z incydentu z 25.09: prowadzący sprawę założył **nową** sprawę w złej
Organizacji zamiast odpowiedzieć w istniejącej. Stąd dwie twarde zasady: **zapis wymaga
jawnej Organizacji** i **prowadzoną rozmowę prowadzisz w jej sprawie, nie obok niej**.

**Odpowiadaj w sprawie, którą prowadzisz.** Wklejasz link — i tyle:

```bash
sf-kit odpowiedz "https://sf.dpakula.pl/tickets/<id>?org=advertpro-co" --opis odpowiedz.md
sf-kit odpowiedz "…ten sam link…" --opis notatka.md --wewn      # notatka wewnętrzna
```

Bez `--wewn` odpowiedź jest **wiadomością widoczną na zewnątrz**. Organizację Kit bierze
z parametru `?org=` linku; przy numerze zamiast linku podaj ją przez `--org`.

**Przy każdym zapisie wskaż Organizację jawnie.** Dwie drogi: `--org <slug>` albo link
do sprawy z `?org=…`. Gdy zabraknie obu, Kit **odmawia** i wypisuje, co podać — nigdy nie
wybiera „pierwszej z brzegu", bo wpis w cudzej Organizacji to wyciek do klienta, nie
niedogodność.

**Gdy w kontekście zadania stoi link do istniejącej sprawy — nie zakładaj nowej.**
`sf-kit nowa-sprawa` (dotychczasowe `zglos`) czyta kontekst z `--kontekst` albo ze zmiennej
`SF_KIT_KONTEKST`; gdy znajdzie w nim link do sprawy, **odmawia** z podpowiedzią
„odpowiedz w sprawie X". Druga sprawa obok prowadzonej rozmowy rozdziela ją na dwa miejsca
i nikt już nie wie, gdzie jest aktualny stan.

**Długą treść oddawaj w wersjach, nie w opisie.**

```bash
sf-kit tresc-wersja FM-12 raport.md                    # załącznik raport-vN.md + wpis „co się zmieniło”
sf-kit tresc-wersja FM-12 raport.md --zmiany opis.md   # opis zmian z pliku
```

Numer wersji Kit liczy z historii załączników na sprawie (najwyższy `raport-vN` + 1), a gdy
nie podasz `--zmiany`, sam skleja streszczenie z różnicy względem poprzedniej wersji.
**Strażnik opisu:** `sf-kit opis-sprawy` z tekstem dłuższym niż próg z `config.json`
(`straznik_opisu_max`, domyślnie 1500 znaków) na sprawie, która już opis ma, zatrzymuje
polecenie i proponuje `tresc-wersja` — bo nadpisanie długim tekstem ucina historię tego,
co było. `--mimo-to` znaczy: „przeczytałem ostrzeżenie i świadomie nadpisuję".

**Publikuj szkic ze zgodą człowieka.**

```bash
sf-kit publikuj FM-12 --zgoda 7d7767ce-bef7-…     # pełny identyfikator wpisu z zgodą
sf-kit publikuj FM-12 --zgoda cd1c19ae            # albo początek ≥ 6 znaków z TEJ sprawy
```

`--zgoda` to wpis, w którym człowiek z rolą owner/admin wyraża zgodę na publikację — z
DOWOLNEJ sprawy tej Organizacji (w tym z okna rozmowy z koordynatorem), nie starszy niż
7 dni. Pełny identyfikator Kit przekazuje bez rozwijania; skrót rozwija na publikowanej
sprawie. Trasa wymaga śladu zgody i bez niego odmawia — komunikat odmowy (`detail`)
pochodzi z serwera i Kit pokazuje go bez zmian. Publikuje wyłącznie klucz osobisty
koordynatora; bez wdrożonego na PROD backendu SF-51 trasa odpowie 403/422 i Kit poda ten
powód jako stan serwera, nie jako własny błąd.

**Zapis na szkicu zawsze ostrzega.** Przy każdym zapisie na sprawie-roboczej Kit dopisuje:
„szkic nie wychodzi do obiegu; członkowie Organizacji widzą go tylko po linku" — dopóki
sprawy nie opublikuje koordynator (`sf-kit publikuj --zgoda <wpis>`) albo człowiek w panelu,
nikt poza wskazanymi linkiem tego nie zobaczy.

#### Czego NIE robić

- **Nie zakładaj sprawy „na próbę".** Każda powiadamia obserwujących; sprawa testowa to
  mail do ludzi, którzy nie prosili o test. Jeśli musisz — tytuł zaczyna się od `[TEST]`
  i zamykasz ją od razu po sprawdzeniu.
- **Nie wysyłaj `--widocznosc external` bez pytania.** `internal` widzi zespół, `external`
  widzi też klient — a treści, której klient nie miał zobaczyć, nie da się odzobaczyć.
- **Nie zgaduj, co człowiek chciał wysłać.** Brakujący plik zgłoś, zamiast wysyłać niepełną
  paczkę: zgłoszenie z połową makiety wygląda na kompletne.

### 10. `sf-kit` — polecenia

#### Nowe w 0.13.0 — skrót

| polecenie | co robi |
|---|---|
| `sf-kit odpowiedz <link> --opis plik.md [--wewn]` | odpowiedź w istniejącej sprawie (domyślnie wiadomość na zewnątrz, `--wewn` = wewnętrzna); Organizacja z `?org=` w linku |
| `sf-kit --org <slug> tresc-wersja <sprawa> <plik.md> [--zmiany plik]` | kolejna wersja treści: załącznik `nazwa-vN.md` + wpis „co się zmieniło" |
| `sf-kit --org <slug> opis-sprawy <sprawa> --plik opis.md` | krótki opis sprawy; długi na sprawie, która już ma opis → odmowa (obejście `--mimo-to`) |
| `sf-kit publikuj <sprawa> --zgoda <wpis>` | koordynator publikuje szkic na zgodę owner/admina (wpis ≤ 7 dni) |
| `sf-kit --org <slug> zglos --tytul … --opis plik.md` | nowa sprawa — **wymaga jawnej Organizacji** (od 0.13.0) |

`--org` jest opcją globalną — stoi **przed** nazwą polecenia. Zapis bez jawnej Organizacji (`--org` albo link z `?org=`) Kit odrzuca z instrukcją. Szczegóły i scenariusze: sekcja 9a.

#### `sf-kit inbox` — moje wiadomości (v0.5.1)

```bash
sf-kit inbox                 # pokaż i POTWIERDŹ odbiór (domyślnie)
sf-kit inbox --podejrzyj     # pokaż, nie potwierdzaj — wiadomości zostają w kolejce
sf-kit inbox --limit 10 --dni 30
```

Potwierdzanie jest domyślne, bo skrzynka bez potwierdzania to czwarty półkanał: wygląda jak
dostarczone i nikt nie wie, czy ktokolwiek to przeczytał.

Co przychodzi tą drogą: przypisanie sprawy, dodanie Cię jako obserwatora, odpowiedź na Twojego
boxa, sprawa z formularza bez prowadzącego, wpis konsoli z adresatem. **Nie budzi sesji** —
to kolejka do odebrania w swoim takcie, nie wstrzyknięcie do tmuxa.

Kody: `3` = skrzynka niedostępna (503 przed rewizją bazy albo `422` — klucz bez właściciela
lub konto bez sluga agenckiego), `1` = pokazano, ale nie udało się potwierdzić odbioru
(wiadomości wrócą w następnym takcie).

#### `sf-kit outbox` — czy to, co wysłałem, doszło (v0.5.1)

```bash
sf-kit outbox                # moje wysyłki z okna, z rozbiciem na adresatów
sf-kit outbox --zalegle      # tylko te, których ktoś nie odebrał po progu
```

Pokazuje `2/3 odebrało` zamiast listy stanów: pytanie jest jedno („doszło?"), więc odpowiedź
też ma być jedna.


**Wspólne:**

```bash
sf-kit --version                # która wersja Kitu jest zainstalowana
sf-kit init                     # zapisz klucz (bez echa) i ustawienia
sf-kit whoami                   # kim jesteś, czy klucz działa, gdzie leżą ustawienia
sf-kit rotate                   # wymień sekret klucza przed wygaśnięciem (okno 7 dni)
sf-kit heartbeat                # czy worker tego agenta żyje (0/1 — pod czujkę)
sf-kit usluga [--pokaz]         # jednostka systemd dla workera
sf-kit --agent <slug> …         # gdy na tej maszynie jest kilku agentów
sf-kit --org <slug|uuid> …      # w której Organizacji ma działać TO polecenie
```

`--org` jest **globalne** — stoi przed nazwą polecenia i działa przy każdym z nich. Przy
**odczycie** bez niego obowiązuje domyślna z ustawień, a gdy domyślnej nie ma i Organizacji
z nadaniami jest więcej niż jedna, Kit **odmawia i wypisuje kandydatki**. Przy **zapisie**
(SF-51) domyślnej nie ma wcale: wymagana jest jawna Organizacja — `--org` albo link do sprawy
z `?org=…` — i przy jej braku Kit odmawia z instrukcją, co podać. Nie zgaduje: wpis dopisany
do sprawy w cudzej Organizacji wygląda dokładnie jak poprawna praca.

**Profil `worker` — ciągniesz zadania z kolejki:**

```bash
sf-kit tasks                    # pokaż zadania w kolejce dla sluga agenta
sf-kit worker                   # pętla: bierz zadania, wykonuj, raportuj
sf-kit worker --runtime kimi    # wykonawca: codex (domyślnie) | kimi | shell
sf-kit worker --once            # jeden przebieg zamiast pętli
sf-kit worker --interval 60     # co ile sekund odpytywać (domyślnie 60)
```

**Profil `asystent` — pchasz do SalesForge gotową pracę człowieka:**

```bash
sf-kit zglos --tytul "…" [--opis plik.md|-] [--tag makieta] [--zalacz plik…] [--szkic]
sf-kit nowa-sprawa --tytul "…" [--kontekst TEKST]            # jak zglos + strażnik kontekstu (SF-51)
sf-kit wpis <sprawa> [--opis plik.md|-] [--zalacz plik…] [--widocznosc internal|external]
sf-kit odpowiedz <link|numer> [--opis plik.md|-] [--wewn]    # odpowiedź w istniejącej sprawie (SF-51)
sf-kit tresc-wersja <sprawa> <plik.md> [--zmiany plik.md|-]  # treść w wersjach (SF-51)
sf-kit opis-sprawy <sprawa> --plik plik.md [--mimo-to]       # zmiana opisu pod strażnikiem (SF-51)
sf-kit publikuj <sprawa> --zgoda <wpis>                      # publikacja szkicu ze zgodą ownera/admina (SF-51)
sf-kit zalacz <sprawa> <plik…> [--notka "…"]
sf-kit sprawy [--limit 50]
sf-kit wpis-edytuj <sprawa> <wpis> (--plik plik.md|- | --tresc "…") [--powod "…"]   # v0.11
sf-kit wpis-wersje <sprawa> <wpis> [--pelne] [--json]                                 # v0.11
```

**Profil `koordynator` — rozdajesz pracę flocie i odbierasz ją:**

```bash
sf-kit flota                                    # kto w tej Organizacji może dostać zadanie
sf-kit flota rejestr agents.json [--pokaz]      # migawka rejestru floty → SF (dashboard)
sf-kit zlec --tytul "…" --agent-slug kodeks --sprawa AUT-12 --opis zadanie.md \
            [--priorytet low|medium|high|urgent] [--termin 2026-09-20T18:00:00Z]
sf-kit kolejka [--agent-slug kodeks] [--status in_progress]
sf-kit odbierz <id-zadania>                     # zamknij PO sprawdzeniu, że wynik jest na sprawie
sf-kit status                                   # whoami + kolejka floty
```

Te polecenia pokazują się tylko wtedy, gdy klucz ma `plans:write` **w wybranej Organizacji** —
sprawdzane przez `GET /me`, nie przez pole `profil` w pliku. Polecenie, które widać w pomocy,
a kończy się `403` w środku pracy, jest gorsze od polecenia, którego nie ma.

**Profil `koordynator` — warstwa administracyjna (v0.6):**

```bash
sf-kit kontrakt [operacja] [--sprawdz]          # co dana operacja potrafi i jakich pól wymaga
sf-kit agent-dodaj <slug> --email … --nazwa …   # konto agenta + nadania + klucz, jednym aktem
            [--uprawnienie NAZWA …] [--bez-proby]
sf-kit nadaj <uuid-konta> [--pokaz]             # uprawnienia konta w tej Organizacji
            [--uprawnienie NAZWA …] [--domyslne]
sf-kit klucz-wystaw <nazwa> [--zakres tenant|user|super_admin] [--wlasciciel MAIL]
            [--uprawnienie NAZWA …] [--opis "…"] [--bez-proby]
```

Tych czterech Kit **nie odsiewa po uprawnieniu** — wymagają praw, które nie mają nic wspólnego
z `plans:write` (superadmin, owner, admin). Rozstrzyga serwer; Kit dba o to, żeby odmowę dało
się przeczytać. Szczegóły i pułapki: rozdział „Profil koordynator — warstwa administracyjna".

`<sprawa>` to **numer** (`FM-12`, `fm-12`, samo `12`), identyfikator **albo link** do sprawy
z `?org=…` — link niesie własną Organizację. Sam numer działa, dopóki jest jednoznaczny — gdy
pasuje do kilku spraw, Kit odmówi i wypisze kandydatów, bo dopisanie postępu do niewłaściwej
sprawy wygląda dokładnie jak poprawna praca.

Opis idzie **plikiem** (`--opis notatka.md`) albo standardowym wejściem (`--opis -`),
nigdy argumentem: opisy są długie i wielolinijkowe, a argumenty procesu widzi każdy
na maszynie.

Ustawienia leżą w `~/.config/sf-kit/<slug>/config.json` — wszystko poza kluczem: adres SF,
slug agenta, katalog roboczy, limit czasu na zadanie i **domyślna** Organizacja (pusta znaczy
„pytaj SF i wymagaj `--org`, gdy jest z czego wybierać").

Aktualizacja Kitu:

```bash
cd sf-agent-kit && git pull
```

Klucz i ustawienia leżą **poza** katalogiem Kitu, więc `git pull` ich nie dotyka. Wydania
są oznaczane tagami (`v0.1.0`, `v0.2.0`, `v0.3.0`, `v0.4.0`, `v0.5.0`); żeby stanąć na konkretnym:
`git fetch --tags && git checkout v0.5.0`.

#### Co Codex dostaje do wykonania

Treść zadania idzie do Codexa **w ramce**: kim jest (agent o twoim slugu), gdzie wolno mu
pracować (katalog roboczy i nic poza nim), czego nie wolno (sekrety, wyjście poza katalog)
i co ma oddać na końcu (sprawozdanie w układzie z §8). Sama treść zadania jest w środku
i nie jest zmieniana.

Wywołanie: `codex exec --sandbox workspace-write` — Codex pisze w katalogu roboczym i nie
może poza nim. Kit dokłada `--ask-for-approval never`, **sprawdziwszy wcześniej, czy ta
instalacja Codexa przyjmuje tę flagę** (obsługa różni się między wydaniami). Bez niej Codex
potrafi czekać na zatwierdzenie polecenia, którego przy workerze nikt nie kliknie — a objawem
jest „przekroczony limit czasu", czyli mylący trop. Gdy katalog roboczy nie jest repozytorium
gita, dochodzi `--skip-git-repo-check`; w repozytorium ta ochrona zostaje.

Prompt idzie na **wejście standardowe**, nie w argument: treść zadania bywa długa,
a argumenty procesu widzi każdy na maszynie.

#### Wykonawca `kimi`

Od v0.5 Kit umie też **Kimi Code CLI** (Moonshot). Wybór jak przy Codexie — `--runtime kimi`
albo `runtime` w ustawieniach. Kimi, tak jak Codex, dostaje treść zadania **w ramce**, bo model
ją czyta; powłoka by ją wykonała.

Wywołanie (v0.9, Kimi Code): `kimi --prompt "<ramka>" --output-format text` w katalogu zadania.
Tryb `--prompt` **sam** jest bezobsługowy — nie pyta człowieka o zgodę — i **odrzuca** `--yolo`
oraz `--auto` („Cannot combine --prompt with --yolo"). Sprawdzone na Kimi Code 0.43.1 i 2.0.1:
obie wersje mają tę samą składnię.

Do v0.8 Kit wołał `kimi --prompt … --print … --yolo` — składnię **starego** `kimi-cli`
(Python). Kimi Code odpowiada na nią `unknown option '--print'` i żadne zadanie nie ruszało
(SF-32). Kit nadal umie starą składnię, gdyby gdzieś stał stary produkt — wybiera ją sam,
patrz niżej.

Zanim Kit weźmie zadanie, sprawdza `kimi --version` **i `kimi --help`**, a nie tylko obecność
polecenia w `PATH`. Z pomocy rozpoznaje, którą składnię ta instalacja przyjmuje (`--prompt` →
Kimi Code, `--print` → stary `kimi-cli`) — po pomocy, nie po numerze wersji, bo oba produkty
numerują się od zera. Zepsuta instalacja albo pomoc bez żadnej z tych flag kończy się odmową
**przed** wzięciem zadania, a nie trzema nieudanymi próbami na cudzej sprawie.

> **Jedna różnica względem Codexa, o której warto wiedzieć.** Kimi Code przyjmuje prompt
> wyłącznie jako argument (`--prompt`; pustego nie przyjmuje, więc stdin odpada), a **argumenty procesu widzi `ps` każdy
> użytkownik maszyny**. Treść zadania jest więc na czas przebiegu widoczna dla wszystkich na tym
> serwerze — przy Codexie nie jest, bo tam prompt idzie na wejście standardowe. Jeśli pracujesz
> na współdzielonej maszynie z cudzymi danymi, weź to pod uwagę przy wyborze wykonawcy.

Logowanie: `kimi login` (OAuth w przeglądarce, subskrypcja Kimi Code) — jak `codex login`.
Bez niego `kimi --prompt` kończy się „No model configured" — to jest brak logowania, nie błąd Kitu.

#### Kolejka należy do workera, nie do sesji (v0.5.3)

Każdy wykonawca ma **dwa konta w SalesForge**: `{nazwa}-worker` (usługa, chodzi sama)
i `{nazwa}` (sesja, przy której siedzi człowiek). Tak stoi Kimi i tak samo Kodeks.
To nie jest kosmetyka administracyjna — z tego podziału wynika jedna zasada:

> **Kolejka SF należy do workera.** Sesja bierze zadanie z kolejki **tylko na wyraźne
> polecenie człowieka** i zanim cokolwiek zrobi, **ustawia je w toku** (`in_progress`).

Powód jest mechaniczny, nie umowny: worker bierze **pierwsze** zadanie z kolejki i robi to
co takt. Sesja, która zaczyna pracę nad zadaniem, nie zmieniając mu statusu, wykonuje je
równolegle z workerem — dwa razy ta sama praca, dwa sprawozdania na jednej sprawie i dwa
zestawy plików, z których jeden nadpisze drugi. Ustawienie `in_progress` jest jedyną rzeczą,
która wyjmuje zadanie z pola widzenia workera.

**Wpisy podpisujemy tym, kto naprawdę pracował:**

| prefiks | kto | kiedy |
|---|---|---|
| `worker:` | usługa (`{nazwa}-worker`) | zadanie wzięte z kolejki automatycznie |
| `sesja:` | człowiek przy modelu (`{nazwa}`) | zadanie wzięte na polecenie, praca interaktywna |

Bez prefiksu wpisy z obu źródeł wyglądają identycznie, a pytanie „czy to zrobił automat, czy
ktoś przy klawiaturze" wraca przy każdej reklamacji — i nie ma na nie odpowiedzi w danych.

**Tętno jest per worker, nie per konto systemowe** (v0.5.3): `~/.sf-kit/heartbeat-{slug}`.
Dwa konta jednego wykonawcy chodzą zwykle na tej samej maszynie i do v0.5.2 nadpisywały sobie
ślad życia — czujka widziała jedno tętno, uznawała oba za żywe i nie zauważała, że jeden leży.

#### Kontekst sprawy i miejsce wyniku (v0.12.0, SF-38)

**Przed startem** zadania przy sprawie worker (dla wykonawców `codex` i `kimi`):

1. pobiera załączniki wpisów sprawy do `inbox/<external_id>/` w katalogu roboczym, nazwy
   `01-<nazwa>`, `02-…` w kolejności wpisów (zdjęcia dokumentu zostają w kolejności stron);
   linków nie pobiera, druga próba tego samego zadania nie pobiera drugi raz; sufity:
   50 MB na plik, 300 MB na zadanie — nad nimi plik jest wymieniony jako „NIE pobrano",
2. dokleja do polecenia blok `KONTEKST SPRAWY`: opis, ostatnie 15 wpisów (wewnętrzne
   i publiczne — **w zakresie klucza Kita**, filtruje serwer), listę ścieżek i to, czego nie
   pobrano,
3. wypisuje w logu, z których katalogów zbierze wyniki.

Wykonawca doczytuje w trakcie pracy **bez klucza w prompcie**:

```bash
sf-kit sprawa ADVERTPR-927 [--wszystkie]     # karta sprawy tym samym formatem + id załączników
sf-kit zalacznik <id> --do inbox/plik.pdf     # jeden załącznik
```

**Gdzie trafia wynik.** Domyślnie — na sprawę zadania, jak dotąd. Autor zadania może wskazać
inną sprawę (np. główną w Organizacji klienta, gdy zadanie stoi przy pomocniczej):

```
SPRAWA_WYNIKU: 0a63a13e-186d-4492-9ddc-b208a01d04b2
ORGANIZACJA_WYNIKU: <uuid Organizacji>      # opcjonalnie, gdy sprawa jest w innej
```

Worker pisze wynik (z plikami) tam, a na sprawie zadania zostawia notkę z odnośnikiem. Gdy
wskazana sprawa odmówi (klucz nie ma tam dostępu), wynik zostaje przy sprawie zadania z powodem
odmowy — nie przepada.

**Jawność wysyłki.** Po wysłaniu wyniku log mówi, ile załączników SF POTWIERDZIŁ w odpowiedzi
(`SF potwierdził załączniki: 2 z 2`). Gdy przyjął mniej, niż wysłano, na sprawę idzie notka
„Załącznik NIE dołączony" z nazwami — zamiast cichego sukcesu.

#### Reakcja w trakcie zadania — co możesz powiedzieć workerowi

Do v0.4 zadanie było atomowe: worker je brał i oddawał wynik, a ty przez ten czas nie miałeś
jak nic powiedzieć. Od v0.5 worker **czyta komentarze pod zadaniem** i reaguje na trzy rzeczy.
Piszesz je normalnie, w komentarzu zadania w SalesForge:

| co wpiszesz | co się stanie |
|---|---|
| `przerwij` | worker kończy i **oddaje zadanie do kolejki**; katalog roboczy zostaje nietknięty |
| `doprecyzuj: <treść>` | treść trafia do następnego kroku i do sprawozdania jako „uwzględnione uwagi" |
| `kontekst: <treść>` | to samo co wyżej — inna nazwa dla tego samego |
| cokolwiek innego | **nic**; worker to policzy i napisze w logu, ale nie zareaguje |

Trzy słowa, a nie „worker rozumie polecenia", i to jest decyzja, nie ograniczenie: pod zadaniem
piszą też ludzie do siebie i koordynator do człowieka. Worker próbujący rozumieć wszystko
reagowałby na zdania, które nie były do niego — a fałszywe „przerwij" kosztuje tyle samo,
co przeoczone.

**Kiedy worker to czyta.** Między krokami: po przyjęciu zadania (zanim ruszy model) i po
wykonaniu (zanim zamknie). **Nie w trakcie pracy modelu** — przerwanie go w połowie zostawiłoby
katalog w stanie, którego nikt nie opisał. Przy krótkim zadaniu możesz więc nie zdążyć;
przy długim, o które tu chodzi, zdążysz spokojnie.

**„Przerwij" po wykonaniu nie kasuje pracy.** Jeśli napiszesz je wtedy, gdy model już skończył,
worker i tak zapisze wynik na sprawie — ale **nie zamknie zadania**, tylko odda je do kolejki
z adnotacją, kto prosił o przerwanie. Skasowanie gotowej pracy byłoby gorsze niż zignorowanie
polecenia; tak możesz zobaczyć, co powstało, i sam zdecydować.

**Komentarz sprzed wzięcia zadania nie liczy się jako reakcja** — to część zlecenia, którą
worker już ma w treści.

#### Skąd wiesz, że worker żyje — „krok N z M"

Zadanie w toku wygląda tak samo jak zawieszone: `in_progress` i cisza. Od v0.5 worker dopisuje
pod zadaniem `krok N z M: <co robi>` przy każdej zmianie kroku (odbiór → wykonanie →
sprawozdanie → zamknięcie), **najwyżej raz na minutę**. Przy zadaniu na dziesięć sekund
zobaczysz więc jeden wpis, a nie cztery.

Wyjątek: **zadanie bez sprawy nie dostaje telemetrii w ogóle**. Tam komentarz zadania jest
jedynym miejscem, gdzie ląduje wynik, i nie ma go co przykrywać.

#### Tryb testowy `shell` (tylko dla administratora)

`--runtime shell` wykonuje treść zadania **jako polecenie powłoki**. Służy wyłącznie do
sprawdzenia, czy cała pętla (odbiór → wykonanie → wpis → zamknięcie) działa **bez modelu** —
i do niczego więcej.

Jest wyłączony. Włącza się go świadomie, dopisując do `~/.config/sf-kit/config.json`:

```json
"zezwol_shell": true
```

Bez tego `--runtime shell` odmawia i wyjaśnia dlaczego. Dwa kroki zamiast jednego są tu
celowo: w tym trybie treść dowolnego zadania z kolejki staje się poleceniem wykonanym na
tej maszynie.

#### Zadanie odrzucone trafia na `on_hold` (v0.5.2)

Zadanie, którego nie da się wykonać bez zgadywania (pusta treść, brak katalogu roboczego),
dostaje wpis z powodem i **ląduje na `on_hold`** — nie zostaje w kolejce.

Do v0.5.1 zostawało jako `queued` i to był błąd, który widać dopiero przy szybkim takcie:
worker bierze PIERWSZE zadanie z kolejki, więc odrzucone i pozostawione tam wracało przy
każdym przebiegu, dopisując ten sam wpis w kółko. `on_hold` znaczy „czeka na człowieka" i jest
jedynym statusem w SalesForge, który mówi o takim zadaniu prawdę — `rejected` ani `failed`
w systemie nie ma, a `completed` liczyłoby się do domknięć jako praca wykonana.

Żeby wróciło do obiegu: uzupełnij zadanie i przestaw je na `queued`.

#### Co worker robi przy kłopotach

Ważne przy zostawianiu go bez nadzoru — i inne dla każdego rodzaju kłopotu:

| sytuacja | co robi worker |
|---|---|
| **403 przy przyjmowaniu zadania** | **zatrzymuje się i kończy pracę**, wypisując, czego brakuje. Nie kręci się w kółko na zadaniu, którego nie może przyjąć |
| **401 (klucz przestał działać)** | zatrzymuje się i kończy pracę |
| brak zadań | nic; czeka do następnego przebiegu |
| nie udało się pobrać kolejki (sieć, 5xx) | zapisuje to w dzienniku i **wycofuje się**: odstęp podwaja się z każdą kolejną nieudaną próbą (60 s → 120 s → 240 s…), najwyżej do 15 minut. Po pierwszej udanej próbie wraca natychmiast do zwykłego odstępu. Obie zmiany widać w dzienniku, żeby worker pytający raz na kwadrans nie wyglądał na zepsuty |
| **zadanie przekroczyło limit czasu** (domyślnie 30 min) | pisze na sprawie, na czym stanęło, i **oddaje zadanie do kolejki** (`queued`). Zadanie nie zostaje zawieszone w `in_progress` |
| wykonanie się nie powiodło | to samo: wpis z powodem i zadanie z powrotem w kolejce |
| praca zrobiona, ale wpisu nie udało się zapisać | zadanie **nie jest zamykane** i wraca do kolejki — zadanie zamknięte bez śladu wygląda jak zrobione i nikt nie wie co |
| zadanie bez przypiętej sprawy | nie ma gdzie zdać sprawozdania; zadanie zostaje w kolejce |

Workera uruchomionego w terminalu zatrzymuje **Ctrl+C**. Uruchomionego w tle — sposobem
właściwym dla wybranego mechanizmu ([`uruchamianie/`](uruchamianie/README.md)).

#### Worker jako usługa — żeby nie znikał razem z terminalem

Worker uruchomiony ręcznie żyje tak długo, jak sesja SSH. Po rozłączeniu, po restarcie maszyny
albo po jednym nieobsłużonym wyjątku po prostu znika — i **nikt się o tym nie dowiaduje**, bo
brak workera wygląda z zewnątrz dokładnie tak samo jak brak zadań w kolejce.

Od v0.5 Kit generuje jednostkę systemd:

```bash
sf-kit usluga --pokaz     # zobacz, co powstanie, zanim cokolwiek zapiszesz
sf-kit usluga             # zapisz jednostkę i dostań instrukcję włączenia
```

Kit **pisze plik i mówi, co dalej** — nie włącza usługi sam. Polecenie, które z własnej woli
uruchamia usługę na cudzej maszynie, jest trudne do cofnięcia przez kogoś, kto nie wiedział,
że je uruchamia.

Włączenie (usługa użytkownika, bez `sudo`):

```bash
systemctl --user daemon-reload
systemctl --user enable --now sf-kit-worker@<slug-agenta>.service
systemctl --user status sf-kit-worker@<slug-agenta>.service
sudo loginctl enable-linger $USER    # żeby chodził też, gdy nie jesteś zalogowany
```

Jednostka ma `Restart=always` i `RestartSec=30`, a limit startów jest **zdjęty**: worker pada
najczęściej na sieci, a domyślny limit wyłączyłby go na dobre dokładnie wtedy, gdy sieć wraca
za dziesięć minut.

**Klucza w jednostce nie ma.** Idzie przez `EnvironmentFile`, bo plik jednostki czyta się
szerzej niż katalog agenta — `systemctl cat` pokaże go każdemu na maszynie, a sekret raz tam
przepisany zostaje na zawsze.

#### Tętno — skąd wiadomo, że worker naprawdę chodzi

Worker przy każdym takcie pętli zapisuje `~/.sf-kit/heartbeat`. Sprawdzenie:

```bash
sf-kit heartbeat          # kod wyjścia 0 = żyje, 1 = nie
```

Do czujki (np. w tic) jest gotowy skrypt `scripts/collect/worker-heartbeat.sh <slug>`.

**Na macOS worker chodzi jako agent launchd** (v0.5.3). `sf-kit usluga` rozpoznaje system sam
i pisze `~/Library/LaunchAgents/pl.dpakula.sf-kit.worker.{slug}.plist`; `--system linux|macos`
przydaje się tylko wtedy, gdy przygotowujesz plik dla innej maszyny niż ta, na której stoisz.

```bash
sf-kit usluga                                  # zapisuje plik dla TEGO systemu
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/pl.dpakula.sf-kit.worker.<slug>.plist
tail -f ~/Library/Logs/sf-kit/worker-<slug>.log
```

Trzy rzeczy w tym pliku, które nie są ozdobą: `KeepAlive` (odpowiednik `Restart=always`),
`ThrottleInterval` 30 s (bez niego awaria sieci daje setki startów na minutę i log, w którym
nie da się znaleźć przyczyny) i **jawny `PATH`** — launchd nie czyta profilu powłoki, więc
proces bez tego nie znajduje ani `codex`, ani `kimi`, ani samego `sf-kit`. To jest najczęstsza
przyczyna „usługa wstała i nic nie robi" na macOS.
Bez `--restartuj` tylko raportuje — tak się to sprawdza na żywej maszynie, zanim wpuści się
czujkę z prawem do restartu.

Dwie rzeczy, które warto wiedzieć, zanim ustawisz własny próg:

- **Worker sam mówi, jak długo bieżący stan może trwać.** Zadanie z limitem trzydziestu minut
  nie odświeża tętna w trakcie wykonania; stały próg dwóch minut kazałby czujce zrestartować
  workera w połowie pracy modelu, czyli zrobić dokładnie tę szkodę, przed którą ma chronić.
- **Tętno jest plikiem, nie zapytaniem do SF** — i to jest wybór, nie brak. Worker bez
  łączności z SalesForge nadal je zapisuje, więc da się odróżnić „worker padł" od „worker żyje,
  ale nie ma jak tego powiedzieć". To dwie różne awarie i wymagają czego innego.

#### Kilku agentów na jednej maszynie

Jeden człowiek może prowadzić kilku agentów — po jednym na profil albo na Organizację.
Kit trzyma wtedy **osobną konfigurację i osobny klucz dla każdego**:

```
~/.config/sf-kit/<slug>/config.json     ← ustawienia tego agenta
~/.config/sf-kit/<slug>/credentials     ← jego klucz (Linux; na macOS: pęk kluczy,
                                           konto = slug agenta)
```

**Przy jednym agencie nie trzeba nic robić** — żadnej flagi, żadnego przenoszenia.
Dotyczy to też tych, którzy skonfigurowali Kit przed wersją 0.3: stary układ
(`~/.config/sf-kit/config.json`) działa dalej, bez zmian.

Drugi agent powstaje przez zwykłe `sf-kit init` — pierwsze pytanie brzmi o slug i to on
wskazuje, gdzie wszystko wyląduje. Od tej chwili każde polecenie chce wiedzieć, o którego
agenta chodzi:

```bash
sf-kit --agent codex-formarketing sprawy
sf-kit --agent kodeks-dpakula worker
```

Bez tej flagi Kit **odmówi i wypisze listę agentów** — zamiast wybrać któregoś. Wybranie
„pierwszego z brzegu" znaczyłoby pisanie do cudzej Organizacji cudzym kluczem, a tego nie
widać ani w wyniku, ani w dzienniku.

Alternatywa dla flagi: `SF_KIT_HOME=/ścieżka/do/katalogu sf-kit …` — wskazuje katalog
wprost i wygrywa ze wszystkim. Przydaje się w kontenerze i przy uruchamianiu w tle
(jeden proces na agenta — patrz [`uruchamianie/`](uruchamianie/README.md)).

#### `sf-kit os` — oś sprawy (v0.8)

Oś to ciąg **bloków**: wpisów, wiadomości, zmian pól, zdarzeń. Kit pokazuje ją tak samo,
jak panel — łącznie z domyślką, bo dwa widoki tej samej sprawy różniące się domyślnie
kończą się rozmową „widzę osiem, a ty pięć", której nie da się rozstrzygnąć.

```bash
sf-kit os SF-7                       # pełna oś, wiersz po wierszu (domyślnie)
sf-kit os SF-7 --zwinieta            # ciągi zmian technicznych zwinięte w wiersze-grupy
sf-kit os SF-7 --rozwin 296dad5c     # rozwiń JEDNĄ grupę (identyfikator z nawiasu)
sf-kit os SF-7 --limit 100 --json    # surowa odpowiedź dla skryptu
```

Zwinięta oś wygląda tak (fragment prawdziwej sprawy SF-7):

```
── 2026-09-17 ────────────────────────────────────────
        15:32  notatka      api:borys-sf@dpakula.pl ## SF-7 „Blok" — design gotowy…
        15:21  notatka      api:borys-sf@dpakula.pl ## Plan pracy — SF-7 „Blok"…
        12:08  ⋯  3 zmian technicznych (2× pole, 1× system) · 2 autorzy      [296dad5c]

28 pozycji = 32 wierszy osi (2 grupy zwinięte; rozwiń przez `--rozwin <id>`)
```

Trzy rzeczy warto wiedzieć, zanim się na to popatrzy dłużej:

- **licznik mówi o WIERSZACH, nie o pozycjach listy.** „28 pozycji = 32 wiersze" znaczy, że
  dwie pozycje to grupy, które zastąpiły po kilka wierszy. Zwijanie niczego nie usuwa;
- **identyfikator w nawiasie wystarczy w skrócie** — Kit dopasuje go sam. Gdy skrót pasuje
  do dwóch grup, Kit **odmawia i pokazuje kandydatów**, bo rozwinięcie nie tej grupy wygląda
  identycznie jak rozwinięcie właściwej;
- **grupy żyją tylko na TEJ stronie.** Przy innym `--limit` ten sam ciąg bywa pokazany jako
  dwie grupy albo wcale — nic nie ginie, zwinięcia jest po prostu mniej.

Jeśli serwer jest starszy niż zwijanie (E4a), `--zwinieta` nie zadziała, a SalesForge **nie
zaprotestuje** — odda pełną oś ze statusem 200. Kit rozpoznaje to i mówi wprost: „pełna oś,
serwer nie zwija".

#### `sf-kit blok` — jeden blok w całości (v0.8)

```bash
sf-kit blok typy                     # katalog rodzajów: stany i akcje z uprawnieniami
sf-kit blok 72e73823-6c9e-4fdf-…     # jeden blok: sedno, treść, kotwica, stan, odpowiedzi
sf-kit blok 72e73823-… --json
```

Identyfikator bierze się z nawiasu przy wierszu osi albo z adresu wpisu w panelu. Wpis żyje
dziś na dwóch powierzchniach (rdzeń i dziennik sprawy) i ma na nich **różne identyfikatory** —
Kit przyjmuje oba, bo rozwiązuje je SalesForge, nie człowiek.

`404` znaczy tu naraz „nie ma" i „nie dla ciebie" — świadomie, bo rozróżnienie zdradzałoby
istnienie bloku ponad poziomem pytającego. Przy literówce Kit nie wysyła zapytania w ogóle:
mówi, że to nie wygląda na identyfikator.

`503` znaczy „ten serwer nie ma jeszcze rdzenia Bloku" (rewizja E1). To stan instalacji,
nie Twój błąd — i czekanie tu nie pomoże, pomoże migracja.

#### Kiedy coś nie działa

Objawy, które już widzieliśmy, z przyczyną i poprawką. Najpierw zawsze `sf-kit whoami` — jego
wynik można w całości wkleić do wpisu na sprawie (klucz jest w nim tylko skrótem).

**Worker chodzi, tętno bije, a zadań „nie ma", choć `whoami` pokazuje konto.**
Slug w ustawieniach różni się od sluga w SF — worker odsiewa zadania po slugu, więc cudzy slug
znaczy pustą kolejkę. Przykład z SF-32: na macu `init` zapisał `kimi-mac-dpakula` (konwencja
z VPS), a konto w SF ma `kimi-mac`. Od v0.9:
- `init` bierze slug z SF (`GET /me`) i mówi, gdy wpisana nazwa jest inna;
- `whoami` pokazuje `slug w SF:` i ostrzega przy rozjeździe;
- worker z rozjechanym slugiem **odmawia startu** i mówi, co wpisać.

Poprawka: `sf-kit init` (Enter wszędzie — slug poprawi się sam) albo pole `"slug"` w pliku
ustawień. **Nazwa katalogu ustawień się nie zmienia** i nie musi: katalog, usługa (`launchd`,
`systemd`), log i plik tętna nazywają się jak agent *na tej maszynie*, a pole `slug` to slug
*w SF*. Po poprawce wystarczy restart usługi — bez ponownego `sf-kit usluga`.

**Zadanie wraca do kolejki, we wpisie `unknown option '--print'` albo `Cannot combine --prompt
with --yolo`.** Kit starszy niż 0.9 z Kimi Code — zaktualizuj Kit (`git pull`) i zrestartuj
usługę. Szczegóły: „Wykonawca `kimi`" wyżej.

**Worker nie startuje: „w `kimi --help` nie ma ani `--prompt`, ani `--print`".** Kimi zmienił
składnię w sposób, którego Kit nie zna. Zgłoś wersję (`kimi --version`) wpisem na sprawie;
do tego czasu `--runtime codex`.

**`kimi` odpowiada „No model configured".** Kimi nie jest zalogowany na koncie, na którym
chodzi worker — `kimi login` (albo `/login` w `kimi`) jako ten sam użytkownik systemu.

**Worker zatrzymuje się na pierwszym zadaniu: „Nie mogę przyjąć zadania".** Brakuje uprawnienia
do zmiany statusu zadania. `whoami` tego nie sprawdza — jedyną próbą byłaby prawdziwa zmiana
statusu na czyimś zadaniu, więc mówi o tym dopiero worker, zanim cokolwiek wykona. Poprawka
po stronie administratora (nadanie na członkostwie).

#### Zmiana ustawień po `init`

Najprościej uruchomić `sf-kit init` jeszcze raz (Enter zostawia dotychczasowe wartości).
Można też poprawić plik `~/.config/sf-kit/config.json` — nazwy pól:

```json
{
  "adres": "https://sf.dpakula.pl",
  "organizacja": "289cef06-…",
  "slug": "codex-formarketing",
  "katalog_roboczy": "/Users/ty/praca-sf",
  "runtime": "codex",
  "odstep_s": 60,
  "limit_zadania_s": 1800,
  "zezwol_shell": false
}
```

`slug` — slug agenta **w SF** (po nim worker odsiewa zadania); `init` wpisuje go z SF.
`odstep_s` — co ile sekund sprawdzać kolejkę. `limit_zadania_s` — po ilu sekundach przerwać
wykonanie jednego zadania (1800 = 30 minut).

**Katalog roboczy**: bierze się z konfiguracji. Zadanie może wskazać własny (pole
`katalog_roboczy`) i wtedy wygrywa; gdy nie ma ani jednego, ani drugiego — albo wskazany
katalog nie istnieje — zadanie zostaje odrzucone z wpisem, zamiast być wykonane byle gdzie.

#### Testy

```bash
python3 -m unittest discover -s testy
```

Chodzą na atrapie SalesForge — bez sieci i bez dotykania czyichkolwiek spraw.

---

### 11. Ograniczenia wersji 0.11

Najpierw to, co **przestało** być ograniczeniem w tej wersji — bo poprzednie wydanie mówiło
tu coś, co dziś jest nieprawdą:

- ~~Nie ma endpointu „kim jestem"~~ → **jest**. `whoami` czyta konto, Organizacje i uprawnienia
  efektywne z `GET /me`, zamiast wnioskować o kluczu z udanego odczytu.
- ~~Jeden klucz, jedna Organizacja~~ → **`--org` przy każdym poleceniu**. Kit zna wszystkie
  Organizacje z nadaniami i przy niejednoznaczności **odmawia**, zamiast wziąć pierwszą z brzegu.
- ~~Worker odmawia wykonania zadania bez sprawy~~ → **wykonuje**, a wynik odkłada jako komentarz
  zadania i mówi wprost, że nie ma go na żadnej osi (§„Zadanie bez sprawy").
- ~~Wynik pracy to ścieżki w sprawozdaniu~~ → **pliki wiszą przy wpisie** jako załączniki.
- ~~Data ważności klucza niewidoczna dla posiadacza~~ → **`whoami` ją pokazuje**, też z `/me`.
  Pusta wartość znaczy teraz „bezterminowy", a nie „nie wiem" — to dwie różne rzeczy i przez
  cztery dni README twierdził pierwszą, mając na myśli drugą.

- ~~Zadanie atomowe: w trakcie nie da się nic powiedzieć~~ → **worker czyta komentarze**
  (`przerwij`, `doprecyzuj:`, `kontekst:`) między krokami, a o sobie mówi „krok N z M".
- ~~Worker znika razem z terminalem~~ → **jednostka systemd** (`sf-kit usluga`) z tętnem
  w `~/.sf-kit/heartbeat` i gotową czujką.
- ~~Jeden model (Codex)~~ → **`--runtime kimi`** obok `codex` i `shell`.
- ~~O rzeczach dotyczących własnej pracy dowiadujesz się, gdy sam zajrzysz~~ → **skrzynka
  wiadomości** (v0.5.1, ADVERTPR-812): `sf-kit inbox` pokazuje i potwierdza odbiór, `outbox`
  mówi, czy to, co wysłałeś, doszło, a worker zagląda do skrzynki w tym samym punkcie
  kontrolnym, w którym czyta komentarze.

- ~~Konta agentów, nadania i klucze wyłącznie przez panel albo curlem z palca~~ → **cztery
  polecenia** (`kontrakt`, `agent-dodaj`, `nadaj`, `klucz-wystaw`, v0.6, ADVERTPR-879), a numeru
  Organizacji nie wpisuje się już nigdzie — Kit tłumaczy go ze sluga.
- ~~Pole, którego trasa nie zna, jedzie i przepada~~ → **zatrzymuje się przed wysyłką**,
  z adresem trasy, która danym polem naprawdę się zajmuje.
- ~~Klucz wygasa i wygląda to jak awaria SalesForge~~ → **worker odnawia go sam** w oknie
  siedmiu dni (v0.7, ADVERTPR-779), a gdy nie wolno — mówi, kogo poprosić. Uczciwie: do 19.09
  samo OSTRZEŻENIE też nie działało na prawdziwym kliencie (worker wołał metodę, której `Klient`
  nie miał, a fail-soft połykał błąd); testy były zielone, bo atrapa tę metodę miała.

- ~~Osi sprawy nie da się zobaczyć z terminala~~ → **`sf-kit os`**, z tą samą domyślką
  co panel i ze zwijaniem ciągów zmian technicznych (`--zwinieta`, `--rozwin`).
- ~~`blok` umie tylko wypisać katalog rodzajów~~ → **`sf-kit blok <id>`** czyta pojedynczy
  blok przez rdzeń: sedno, treść, kotwicę, stan, odpowiedzi i adresatów.

Co ogranicza nadal:

- **Zapisu przez `blok` nie ma.** `sf-kit blok odpowiedz` odmawia i mówi, na co czeka:
  odpowiedź-dziecko powstaje etapem E3 sprawy SF-7. Do tego czasu odpowiada się wpisem
  na sprawie (`sf-kit wpis`).
- **Licznik odpowiedzi i lista adresatów bywają puste i to nie jest usterka.** Kolumny
  rewizji E1 istnieją, ale zapis do nich zaczyna się dopiero w E3 — a blok bez lustra
  w rdzeniu (18,5 % ruchu na 22.09) nie ma ich skąd wziąć. Kit mówi o tym wprost przy
  takim wpisie, zamiast pokazywać pustkę bez wyjaśnienia.
- **Samoodnowienie nie da się wyłączyć dla POJEDYNCZEGO klucza bez zawężenia.** „Flagą per
  klucz" jest jego zakres, więc klucz bez zawężenia idzie za nadaniem konta. Wyłączenie
  dotyczy albo całego konta (zdjęcie `keys:self-renew`), albo klucza zawężonego. Osobny
  wyłącznik per klucz wymagałby kolumny w bazie — do decyzji, gdy okaże się potrzebny.
- **Między odpowiedzią SF a zapisem sekretu jest szczelina.** Stary klucz jest już martwy;
  proces zabity dokładnie w tej chwili zostawia agenta bez dostępu. Kit zapisuje sekret jako
  pierwszą czynność po odpowiedzi, ale szczeliny nie da się zamknąć bez odnowienia
  dwufazowego (propozycja czeka na decyzję).

- **Skrzynka wymaga, żeby SF wiedział, jakim slugiem się nazywasz.** Pomiar z 16.09 (pętlą po
  Organizacjach, z kontekstem): `memberships.agent_slug` ma **58 członkostw ze slugiem
  w 11 Organizacjach** — w tym `borys-sf`, `arek-sf`, `agata`, `kodeks-dpakula`. Czyli
  dla większości floty skrzynka zadziała od razu. Bez sluga zostają 3 członkostwa agenckie
  (wszystkie w `fixforum`) i te dostaną `422 — konto bez sluga agenckiego`; slugi dla nich
  nadaje `backend/scripts/slugi_agentow_812.py` po podaniu par `--slug adres=slug`
  (skrypt ich NIE zgaduje z adresu — slug jest tożsamością, nie etykietą).
- **Rejestr flot jest dziś nieaktywny.** Plik `/etc/salesforge/fleet-rejestr.json` istnieje,
  ale `FLEET_REJESTR_PLIK` nie jest ustawione ani w środowisku usługi, ani w `.env`, więc
  aplikacja go nie czyta. Dla skrzynki to tylko drugie źródło sluga (pierwszym jest
  członkostwo), ale dla bramki floty `/fleet/*` znaczy „wyłączona" — warte sprawdzenia
  przez kogoś, kto na nią czeka.
- **`sf-kit wpis --do <slug>` wymaga uprawnienia `console:write`, którego nie ma żaden klucz
  agencki.** Pomiar z 16.09: to uprawnienie ma **1 aktywny klucz na 31** — poller mostu.
  Polecenie jest gotowe i odbije się o `403` z komunikatem mówiącym, o co poprosić.

- **Nie ma filtru zadań po slugu agenta** po stronie serwera. Kit przegląda kolejkę stronami
  i odsiewa u siebie (§3). Dlatego `kolejka` mówi, gdy widzi tylko część („widzę 100 z 340") —
  licznik pokazujący 12 zadań, gdy jest ich 130, kłamie w jedyną stronę, która przy planowaniu
  pracy ma znaczenie. *(zgłoszone)*
- **Nie ma powiadomienia o nowym zadaniu.** Worker odpytuje co minutę; zadanie dodane
  o 12:00 zostanie zauważone najpóźniej o 12:01.
- **Pobieranie** plików ze sprawy — nieobsługiwane. Wysyłka działa (v0.4); w drugą stronę nie.
- **`odbierz` potrafi powiedzieć „nie wiem", nie tylko „nie ma".** Wpisy poza poziomem
  widoczności klucza są dla niego niewidoczne, więc brak dowodu na wynik nie jest dowodem
  jego braku — i Kit nazywa to wprost, zamiast zamknąć zadanie albo odmówić bez wyjaśnienia.
- **Agent bez sluga jest niezlecalny.** `flota` **pokazuje** takiego agenta z adnotacją, zamiast
  go ukryć — ukryty wygląda jak nieistniejący i nikt nie wie, że jest co naprawić. Na produkcji
  jest dziś jeden taki.
- **Kontraktu nie da się dziś przeczytać z serwera.** `https://sf.dpakula.pl/openapi.json`
  oddaje **HTTP 200 i stronę frontu** — nginx nie przepuszcza tej ścieżki do backendu, choć sam
  dokument istnieje (widać go z maszyny, pod `127.0.0.1:8010`). Katalog operacji siedzi więc
  w `sf_kit/kontrakt.py` i jest kopią kształtu z drugiej strony; `sf-kit kontrakt --sprawdz`
  porówna go z żywym opisem, gdy tylko ta ścieżka zostanie przepuszczona. *(zgłoszone,
  ADVERTPR-879)*
- **Warstwa administracyjna obejmuje konta, nadania i klucze — nie plany, cele ani konsolę.**
  To nie jest brak czasu, tylko brak incydentu: żadna z trzech wpadek, które założyły
  ADVERTPR-879, nie dotyczyła tamtych modułów, a polecenie budowane bez obserwacji, jak się
  go używa, jest zgadywaniem kształtu. `sf-kit kontrakt plany` mówi to wprost.
- **Windows poza WSL** — nieobsługiwany, patrz „System" w §1.
- **SalesForge nie przyjmuje plików `.html`** (ani `.css`, ani `.js`) jako załączników.
  Dozwolone są obrazy, PDF, dokumenty Office, `.txt`, `.csv`, `.md` oraz **`.zip`**. Makietę
  wysyła się więc spakowaną — Kit mówi o tym **przed** wysyłką i podpowiada spakowanie,
  zamiast pozwolić serwerowi odmówić kodem `403` (który wszędzie indziej znaczy „brak
  uprawnień" i wysyła człowieka szukać winy w kluczu).
- **Obserwujących trzeba wpisać identyfikatorami kont** do konfiguracji agenta — nie ma
  odczytu listy kont dla klucza agenta ani dopisywania po adresie. *(zgłoszone)*
- **Nie ma odczytu sprawy po numerze** — `sf-kit` rozwiązuje `FM-12` przeglądając listę
  spraw Organizacji. Działa; jest to obejście.

Administrator znajdzie odsyłacze do zgłoszonych spraw w sekcji poniżej.

Brakuje czegoś do pracy? Napisz wpis na sprawie, przy której pracujesz — to jest właściwy
kanał także na pytania o sam Kit.

---

### 12. Dla administratora SalesForge

Ta sekcja jest dla osoby, która zakłada konta agentów i nadaje uprawnienia. Agent pracujący
Kitem nie musi jej czytać.

#### Zakładanie konta agenta z panelu

1. **Użytkownicy → Dodaj → Agent.** Podaj nazwę i **slug** (np. `codex-formarketing`) —
   slug jest tym, po czym agent rozpoznaje swoje zadania i musi być unikalny w Organizacji.
2. Konto agenta zakładane tą drogą dostaje **zestaw domyślny**: `tickets:read`,
   `tickets:comment`, `tasks:own`. Do pracy Kitem to wystarczy.
3. **Klucze API → Nowy klucz**, zasięg **osobisty (`scope=user`)**, właściciel = konto
   agenta. Klucz pokazywany jest **raz** — przekaż go kanałem innym niż poczta.
4. Przypisz agentowi zadanie (pole wykonawcy) — dopiero wtedy `sf-kit tasks` cokolwiek
   pokaże.
5. **Załóż jedno zadanie testowe** przy sprawie, na której nie przeszkadza dodatkowy wpis
   (np. „wypisz zawartość katalogu roboczego"). Pierwszy przebieg u nowej osoby ma pójść
   na nim, nie na sprawie klienta.
6. **Zadbaj o dostęp do panelu dla człowieka**, który będzie agenta uruchamiał. Klucz agenta
   nie jest jego loginem — bez własnego konta nie zobaczy wpisów, które agent pisze.

**Slug musi się zgadzać znak w znak** z tym, co człowiek wpisze w `sf-kit init`. Literówka
nie daje żadnego błędu: `whoami` mówi „działa", a `tasks` pokazuje „brak zadań" —
nieodróżnialnie od stanu, w którym nic jeszcze nie przypisano.

#### Zestawy uprawnień per profil

| profil | uprawnienia na członkostwie | po co |
|---|---|---|
| **worker** | `tickets:read`, `tickets:comment`, `tasks:own` | czyta zadania, pisze sprawozdania, zmienia status SWOICH zadań |
| **asystent** | `tickets:read`, `tickets:comment`, **`tickets:write`**, `context:read` | jak wyżej plus **zakładanie spraw** |
| **koordynator** | jak asystent plus **`plans:write`** | **zleca zadania flocie**, przegląda kolejkę, odbiera wyniki |

**`tickets:write` to jedyna różnica** między workerem a asystentem i jedyne, co trzeba dodać
istniejącemu agentowi, żeby mógł zgłaszać. Zestaw domyślny konta zakładanego z panelu
**go nie zawiera** — dodaje się go jednym kliknięciem na członkostwie, bez wymiany klucza.

**`plans:write` nazywa się myląco**, bo bramkuje zakładanie ZADAŃ, nie planów: `POST /tasks`
przechodzi przez `_require_manager`, a ten pyta o `PERM_PLANS_WRITE`. Uprawnień `tasks:write`
ani `tasks:assign` w SalesForge **nie ma** — gdyby Kit bramkował po nich, polecenia koordynatora
byłyby ukryte przed wszystkimi, łącznie z osobami mającymi pełne prawo je wydawać. Nazwa jest
sprawdzona w kodzie SF, nie wzięta z nazewnictwa, które wydaje się sensowne.

**Uprawnienie rozstrzyga o widoczności poleceń, nie pole `profil` w konfiguracji.** Profil
w pliku jest deklaracją człowieka; o tym, co wolno, rozstrzyga klucz. Kit sprawdza to przez
`GET /me` w **wybranej Organizacji** — ta sama osoba bywa koordynatorem w jednej i workerem
w drugiej.

**Załączniki nie mają własnego uprawnienia.** Wysyłka plików idzie tą samą trasą co wpis
i bramkuje ją `tickets:comment`. Kto może napisać wpis, może dołączyć do niego pliki.

#### Obserwujący sprawy zakładane przez agenta

Backend **nie dopisuje nikogo poza samym autorem**, gdy sprawa powstaje kluczem API. Sprawa
założona przez agenta spoza floty nie powiadomiłaby więc **nikogo** — leżałaby, wyglądając
na zgłoszoną.

Dlatego Kit podaje obserwujących jawnie, z konfiguracji agenta:

```json
"obserwatorzy_domyslni": ["<id konta>", "<id konta>"]
```

To są **identyfikatory kont**, nie adresy — i wpisuje je administrator, bo agent nie ma ich
jak odczytać (lista kont jest dla jego klucza niedostępna). Znajdziesz je w panelu, w adresie
profilu użytkownika. Jest to znana niedogodność, nie docelowy kształt (§11).

#### Zmiana uprawnień bez wymiany klucza

Uprawnienia nadaje się **na członkostwie użytkownika w Organizacji**, nie na kluczu.
Dodanie nadania działa natychmiast i tym samym kluczem — agent nie musi nic u siebie
zmieniać.

Jedyny przypadek, w którym to nie zadziała: klucz z **własną listą uprawnień**. Taka lista
jest sufitem (uprawnienia efektywne = prawa właściciela ∩ lista na kluczu), więc każde
potrzebne uprawnienie musi być wtedy w **obu** miejscach. Dla kluczy agentów prościej
jest listy na kluczu nie ustawiać.

#### Zasięgi kluczy

| zasięg | dla kogo | uwaga |
|---|---|---|
| **osobisty** (`user`) | **agenci i ludzie** | uprawnienia liczone w locie z konta; niesie rolę właściciela |
| członkostwo (`member`) | rzadkie przypadki szczególne | zamrożona lista uprawnień — nie nadąża za zmianami na koncie |
| Organizacja (`tenant`) | integracje bez właściciela | brak podpisu osoby; nie dla agenta |

Klucz `member` albo `tenant` u agenta to błąd konfiguracji, a jego objawy (§5) łatwo pomylić
z brakiem uprawnień.

#### Zgłoszone braki po stronie SalesForge

Sprawy w Organizacji `advertpro-co` (dostęp wymaga konta):

- **`GET /me` dla klucza API + filtr zadań po slugu** —
  [`7664e9b9-ce5e-4aa7-b96a-29993aec5e7f`](https://sf.dpakula.pl/tickets/7664e9b9-ce5e-4aa7-b96a-29993aec5e7f)
- **Ważność klucza widoczna dla posiadacza (30 dni, rotacja, powiadomienia)** —
  [`d2e243a3-ccf0-4ab9-852e-a5858dc8bd21`](https://sf.dpakula.pl/tickets/d2e243a3-ccf0-4ab9-852e-a5858dc8bd21)

---

### 13. Słownik

Nazwy używane w interfejsie SalesForge — żeby agent mówił o rzeczach tak, jak widzi je
jego użytkownik.

| pojęcie | jednym zdaniem |
|---|---|
| **Organizacja** | przestrzeń robocza jednej firmy albo projektu; wszystko, co widzisz, należy do jednej z nich |
| **Sprawa** | wątek o jednym temacie: opis, rozmowa, załączniki, decyzje; żyje tygodniami |
| **Zadanie** | jedna rzecz do zrobienia, z tytułem, statusem i wykonawcą; zwykle wisi przy sprawie |
| **Wpis** | wiadomość dopisana do sprawy — tak zdaje się sprawozdanie i zadaje pytania |
| **Oś sprawy** | chronologiczna lista wpisów i zdarzeń na sprawie |
| **Widoczność wpisu** | kto wpis zobaczy: `public` — także klient, `internal` — tylko zespół; **wpisy agenta domyślnie `internal`** |
| **Obserwujący** | osoby powiadamiane o nowych wpisach na sprawie |
| **Wykonawca** | osoba albo agent przypisany do zadania; zadanie bez wykonawcy czeka |
| **Plan** | zestaw celów i zadań rozpisany na dłuższy okres |
| **Cel** | pozycja w planie, do której podpina się zadania |
| **Spotlight** | widok najważniejszych spraw przypiętych do szybkiego dostępu |
| **Puls** | podsumowanie tego, co zmieniło się ostatnio w Organizacji |
| **Konsola** | kanał, którym prowadzący pracę odkłada decyzje i polecenia dla agentów |
| **Slug agenta** | krótka nazwa agenta w Organizacji (np. `codex-formarketing`); po niej rozpoznawane są jego zadania |
| **Klucz API** | hasło do konta w postaci ciągu `sk_live_…`; uwierzytelnia żądania zamiast logowania |

---

**SF Agent Kit** — narzędzie do pracy z **SalesForge**, systemem prowadzenia spraw i zadań
rozwijanym przez ADVERTpro.co. Organizacja, w której pracujesz, jest osobną przestrzenią
w tym systemie — jej identyfikator podaje administrator i nie musi mieć nic wspólnego
z ADVERTpro.

Pytania i usterki: wpis na sprawie, przy której pracujesz. Gdy Kit jeszcze nie działa —
formularz pomocy: **https://sf.dpakula.pl/pomoc** (bez logowania i bez klucza).
