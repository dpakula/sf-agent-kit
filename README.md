# SF Agent Kit

**Dla kogo:** jesteś agentem (albo człowiekiem), który ma pracować dla kogoś przez SalesForge,
i nie znasz tego systemu. Ten dokument jest wszystkim, czego potrzebujesz, żeby zacząć.
Nie musisz czytać niczego poza nim.

**Co tu dostaniesz:** jak odbierać zadania, jak je wykonywać i jak raportować wynik —
przez zwykłe API HTTP, z jednym poleceniem `sf-kit`, które robi to za ciebie.

---

## 0. Zacznij tutaj

```bash
git clone git@github.com:dpakula/sf-agent-kit.git
cd sf-agent-kit
./sf-kit --help
```

**Nie ma nic do zainstalowania.** Potrzebujesz Pythona 3.9 lub nowszego — i to wszystko.
Kit korzysta wyłącznie z biblioteki standardowej, więc `pip install` nie jest do niczego
potrzebny. Jeśli `./sf-kit --help` wypisało listę poleceń, jesteś gotowy.

Chcesz mieć `sf-kit` pod ręką z dowolnego katalogu:

```bash
ln -s "$PWD/sf-kit" ~/.local/bin/sf-kit     # o ile ~/.local/bin jest w twoim PATH
```

### Aktualizacja do najnowszej wersji

```bash
cd sf-agent-kit
git pull
```

Twoja konfiguracja i klucz leżą **poza** katalogiem Kitu (`~/.config/sf-kit/`), więc `git pull`
ich nie dotyka — nie musisz nic ustawiać od nowa.

Wydania są oznaczane tagami, licząc od **`v0.1.0`**. Listę zmian znajdziesz na stronie repozytorium
w zakładce **Releases**; jeśli chcesz stanąć na konkretnym wydaniu zamiast na najnowszym kodzie:

```bash
git fetch --tags
git checkout v0.1.0
```

Dalej: §2 (klucz) → §7 (polecenia) → `sf-kit init`. Reszta dokumentu tłumaczy, co się dzieje
pod spodem, i przyda się, gdy coś pójdzie nie tak.

---

## 1. Czym jest SalesForge z twojej strony

Trzy pojęcia. Nic więcej nie musisz rozumieć, żeby pracować.

| pojęcie | czym jest | z czym to porównać |
|---|---|---|
| **Organizacja** | firma albo projekt, w którego ramach pracujesz. Wszystko, co widzisz, należy do jednej Organizacji. | „przestrzeń robocza" |
| **Sprawa** | kontener na temat: opis problemu, historia rozmowy, załączniki, decyzje. Żyje długo. | wątek / zgłoszenie |
| **Zadanie** | jednostka pracy do wykonania. Ma tytuł, opis, status i wykonawcę. Zwykle wisi przy sprawie. | pozycja na tablicy kanban |
| **Wpis** | wiadomość dopisana do sprawy. Tak rozmawiasz z ludźmi: piszesz, co zrobiłeś, o co pytasz. | komentarz w wątku |

Twoja praca wygląda tak: **dostajesz zadanie → wykonujesz je → piszesz wpis na sprawie →
oznaczasz zadanie jako zrobione.** Reszta dokumentu to szczegóły tych czterech kroków.

### Statusy zadania

Są cztery i tylko te cztery:

- `queued` — czeka, nikt się nim nie zajmuje. **To są twoje nowe zadania.**
- `in_progress` — ktoś (ty) właśnie nad nim pracuje.
- `on_hold` — wstrzymane, czeka na coś z zewnątrz.
- `completed` — zrobione.

---

## 2. Klucz — jak go dostać i jak go trzymać

Klucz API dostajesz **raz**, od administratora SalesForge. Wygląda tak: `sk_live_` i dalej
ciąg znaków. Jest to **hasło do konta** — kto go ma, ten jest tobą.

### Twój klucz ma być OSOBISTY (`scope=user`)

To nie jest szczegół techniczny, tylko warunek, żeby cokolwiek zadziałało.

W SalesForge klucz może mieć jeden z kilku zasięgów. **Klucz agenta ma być osobisty,
czyli `scope=user`** — przypisany do twojego konta. Wtedy:

- twoje uprawnienia **liczą się w locie z konta**, a nie z listy zapisanej na kluczu;
- klucz niesie twoją rolę, więc przechodzisz przez bramki, które pytają o rolę, a nie
  o pojedyncze uprawnienie;
- wszystko, co robisz, jest podpisane twoim kontem — widać, kto co zrobił.

**Klucz `member` albo `tenant` u agenta to błąd konfiguracji.** Taki klucz albo nie ma
właściciela wcale (`tenant` — to klucz integracji, nie osoby), albo nosi zamrożoną listę
uprawnień, która nie nadąża za zmianami na koncie. Jeśli dostałeś taki klucz — **powiedz
o tym, zamiast obchodzić problem**; poproś o klucz osobisty.

### Uprawnienia nadaje się na CZŁONKOSTWIE, nie na kluczu

Drugi punkt, który myli wszystkich na początku (mnie też):

> **Uprawnienia nie mieszkają na kluczu. Mieszkają na twoim członkostwie w Organizacji.**

Twoje prawa to suma trzech rzeczy: **rola systemowa** + **tagi roli** + **nadania wpisane
wprost na członkostwie**. Klucz osobisty czyta to wszystko w chwili każdego żądania.

Lista uprawnień **na kluczu** ma inne znaczenie, niż się wydaje: to **zawężenie**, czyli sufit.
Uprawnienia efektywne = *prawa właściciela* ∩ *lista na kluczu*. Dopisanie czegoś do klucza
**nie doda ci uprawnienia**, którego nie masz na członkostwie — doda pozycję, która nic nie
zmieni. Działa to tylko w jedną stronę: żeby ograniczyć klucz poniżej własnych praw.

Praktyczny wniosek dla administratora: **uprawnienia agenta nadaj na jego członkostwie**
w tej Organizacji. Jeśli dodatkowo zawężasz klucz listą — każde potrzebne uprawnienie musi być
**w obu miejscach naraz**, inaczej przecięcie je wytnie.

### Uprawnienia, o które musisz poprosić

To jest zbadane i zmierzone, nie zgadywane (14.09.2026).

**Podstawowy odczyt daje sam działający klucz** — żeby zobaczyć swoje zadania i przeczytać ich
treść, nie potrzebujesz niczego ponad to. Dodatkowych uprawnień wymagają dopiero czynności,
które coś zmieniają:

| co robisz | endpoint | dodatkowe uprawnienie |
|---|---|---|
| czytasz listę zadań | `GET /api/v1/tasks` | – |
| czytasz szczegóły zadania | `GET /api/v1/tasks/{id}` | – |
| komentujesz zadanie | `POST /api/v1/tasks/{id}/comments` | – |
| piszesz wpis na sprawie | `POST /api/v1/tickets/{id}/entries` | `tickets:comment` |
| **bierzesz zadanie i kończysz je** | `PATCH /api/v1/tasks/{id}` | `tasks:own` |

`tasks:own` znaczy dokładnie to, co mówi: wolno ci zmienić **status zadania, którego jesteś
wykonawcą**. Nie cudzego, nie nieprzypisanego, i tylko status — nie tytuł ani termin. Tworzenie
i kasowanie zadań to osobna sprawa i tego uprawnienia **nie dostaniesz ani nie potrzebujesz**.

> **Poproś administratora o:** klucz **osobisty (`scope=user`)** oraz o nadanie ci na
> **członkostwie** w tej Organizacji uprawnień `tickets:read`, `tickets:comment` i `tasks:own`.

Nowe konto agenta zakładane z panelu dostaje ten zestaw **automatycznie** — jeśli twój klucz
jest świeży, najprawdopodobniej masz już wszystko i nie musisz o nic prosić.

### Jak zapisać klucz

**Nigdy nie wklejaj klucza do polecenia.** Argumenty procesu widzi każdy użytkownik maszyny
(`ps aux`), a historia powłoki zapisuje je na dysk.

```bash
sf-kit init
```

Polecenie zapyta o klucz, **nie pokazując go na ekranie**, i zapisze go:

- **macOS** → do pęku kluczy (`security add-generic-password`),
- **Linux** → do `~/.config/sf-kit/credentials` z prawami `600` (czyta tylko twoje konto).

Sprawdzenie, czy klucz działa:

```bash
sf-kit whoami
```

### Czego z kluczem nie wolno — trzy rzeczy

1. **Nie podawaj go modelowi.** Jeśli jesteś agentem AI: klucz należy do programu, który cię
   uruchamia, nie do ciebie. Model, który zna klucz, może go powtórzyć w dowolnej odpowiedzi.
2. **Nie zapisuj go w repozytorium.** Kit potrafi cię przed tym obronić: po uruchomieniu
   `./sf-kit init` **sprawdza pliki przy każdym `git commit` i zatrzymuje zapis, jeśli znajdzie
   w nich klucz** (ciąg zaczynający się od `sk_live_`). Działa to **tylko w tym katalogu** —
   w innych twoich projektach nic nie pilnuje, więc tam uważaj sam.
3. **Nie wklejaj go do logów ani zgłoszeń.** Jeśli klucz gdziekolwiek wyciekł: powiedz
   administratorowi **od razu**. Wyciek plus milczenie jest gorszy niż sam wyciek.

---

## 3. Pętla pracy

To jest cały twój cykl. `sf-kit worker` robi go za ciebie, ale warto wiedzieć, co się dzieje.

```
  1. Weź moje zadania    GET  /api/v1/tasks?assignee_kind=agent&status=queued
                         → odfiltruj po swoim slugu (pole `assigned_agent_slug`)
  2. Przyjmij zadanie    PATCH /api/v1/tasks/{id}   {"status": "in_progress"}
  3. Zrób robotę         (twoja sprawa — Kit uruchamia tu twój model albo skrypt)
  4. Zdaj sprawozdanie   POST /api/v1/tickets/{ticket_id}/entries
  5. Zamknij zadanie     PATCH /api/v1/tasks/{id}   {"status": "completed"}
```

**Krok 1 wymaga wyjaśnienia:** SalesForge nie ma dziś filtru „pokaż zadania
agenta o slugu X". Filtr `assignee` przyjmuje wewnętrzny numer konta, którego ty nie znasz.
Dlatego Kit pobiera zadania agentów i **odsiewa je po swojej stronie** po polu
`assigned_agent_slug`. Działa; jest to obejście i tak jest opisane.

**Krok 4 — wpis idzie na SPRAWĘ, nie na zadanie.** Zadanie ma pole `ticket_id`; to jego
używasz. Jeśli zadanie nie ma sprawy, nie masz gdzie napisać sprawozdania — patrz §6.

---

## 4. Endpointy, z przykładami

Wszystkie wywołania potrzebują dwóch nagłówków:

```
Authorization: Bearer sk_live_...
X-Tenant-Id: <identyfikator Organizacji>
```

`X-Tenant-Id` jest wymagany, gdy twój klucz ma zasięg `member` (czyli prawie zawsze).
Identyfikator Organizacji dostajesz razem z kluczem.

> W przykładach klucz jest w zmiennej `$SF_KEY`, a nie wpisany wprost — patrz §2.

### Moje zadania do wzięcia

```bash
curl -sS "$SF_URL/api/v1/tasks?assignee_kind=agent&status=queued&limit=50" \
  -H "Authorization: Bearer $SF_KEY" \
  -H "X-Tenant-Id: $SF_TENANT"
```

Odpowiedź: `{"items": [...], "total": 518, "limit": 50, "offset": 0}`.
Każda pozycja ma m.in. `id`, `title`, `body_md` (treść zadania — **to jest twój prompt**),
`status`, `assigned_agent_slug`, `ticket_id`, `ticket_ref`, `version`.

### Przyjęcie zadania

```bash
curl -sS -X PATCH "$SF_URL/api/v1/tasks/$TASK_ID" \
  -H "Authorization: Bearer $SF_KEY" -H "X-Tenant-Id: $SF_TENANT" \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress"}'
```

### Wpis na sprawie (twoje sprawozdanie)

```bash
curl -sS -X POST "$SF_URL/api/v1/tickets/$TICKET_ID/entries" \
  -H "Authorization: Bearer $SF_KEY" -H "X-Tenant-Id: $SF_TENANT" \
  -H "Content-Type: application/json" \
  -d '{"entry_type": "note", "content": "Sedno...", "visibility": "internal"}'
```

`visibility`: `internal` (widzi zespół) albo `public` (widzi też klient). **W razie wątpliwości
zawsze `internal`** — treści, której klient nie miał zobaczyć, nie da się odzobaczyć.

### Zamknięcie zadania

```bash
curl -sS -X PATCH "$SF_URL/api/v1/tasks/$TASK_ID" \
  -H "Authorization: Bearer $SF_KEY" -H "X-Tenant-Id: $SF_TENANT" \
  -H "Content-Type: application/json" \
  -d '{"status": "completed"}'
```

### Komentarz do samego zadania (rzadziej potrzebny)

```bash
curl -sS -X POST "$SF_URL/api/v1/tasks/$TASK_ID/comments" \
  -H "Authorization: Bearer $SF_KEY" -H "X-Tenant-Id: $SF_TENANT" \
  -H "Content-Type: application/json" \
  -d '{"content": "treść", "is_internal": true}'
```

Uwaga: pole nazywa się `content`, nie `body`. Pomyłka daje `422`.

---

## 5. Kody odpowiedzi — co znaczą i co z tym zrobić

| kod | co znaczy | co zrobić |
|---|---|---|
| **200 / 201** | udało się | nic |
| **401** | klucz nieznany, wygasł albo go nie wysłałeś | sprawdź `sf-kit whoami`. Jeśli nie działa — klucz jest zły albo odwołany. **Nie próbuj w pętli**, poproś o nowy |
| **403** | klucz jest dobry, ale nie wolno ci tej rzeczy | brakuje uprawnienia **na twoim członkostwie** (nie na kluczu — §2). Przy `PATCH /tasks` to albo brak `tasks:own`, albo zadanie **nie jest twoje** — odpowiedź mówi które. Zapisz, czego próbowałeś, i poproś administratora — **nie obchodź tego innym endpointem** |
| **404** | nie ma takiego obiektu **albo nie masz do niego dostępu** | te dwie rzeczy wyglądają tak samo celowo. Sprawdź identyfikator; jeśli jest dobry, to znaczy, że ten obiekt nie jest twój |
| **409** | konflikt — ktoś zmienił obiekt przed tobą | pobierz zadanie od nowa i spróbuj jeszcze raz. Nie nadpisuj na siłę |
| **422** | wysłałeś coś w złym kształcie | odpowiedź mówi, którego pola brakuje. Najczęstsza pomyłka: `body` zamiast `content` |
| **429 / 5xx** | przeciążenie albo awaria po naszej stronie | odczekaj i ponów, zwiększając odstęp (30 s, 60 s, 120 s). Nie waliuj w pętli co sekundę |

---

## 6. Zasady, które nie są opcjonalne

**Nie zgaduj kontekstu.** Jeśli zadanie ma pustą treść, nie mówi, w którym katalogu pracować,
albo nie ma przypiętej sprawy — **nie domyślaj się**. Napisz wpis „nie mam czego wykonać,
bo…" i zostaw zadanie w kolejce. Zgadnięty kontekst to praca wykonana na cudzych plikach.

**Nie kończ zadania, którego nie zrobiłeś.** `completed` znaczy „zrobione i sprawdzone".
Gdy utknąłeś — wpis z opisem, status z powrotem na `queued` albo `on_hold`. Zadanie
oznaczone jako zrobione znika ludziom z widoku.

**Pisz po polsku i po ludzku.** Twoje wpisy czytają ludzie, nie maszyny. Trzyczęściowy układ,
którego używamy:

```
**Sedno** — jedno zdanie: co się stało.

**Co zrobiono** — 2-5 zdań: konkretnie, co zrobiłeś.

**Szczegóły techniczne** — pliki, polecenia, liczby. Dla tego, kto będzie to sprawdzał.
```

**Nie wysyłaj sekretów.** Nie wklejaj do wpisów haseł, kluczy ani zawartości plików
`.env`. Jeśli musisz powiedzieć, że coś jest źle skonfigurowane — napisz **nazwę** zmiennej,
nigdy jej wartość.

---

## 7. `sf-kit` — polecenia

```bash
sf-kit init                  # zapisz klucz (bez echa) i podstawową konfigurację
sf-kit whoami                # sprawdź, czy klucz działa i co nim wolno
sf-kit tasks                 # pokaż moje zadania w kolejce
sf-kit worker                # pętla: bierz zadania, wykonuj, raportuj
sf-kit worker --runtime codex   # wykonuj przez `codex exec` (domyślne)
sf-kit worker --runtime shell   # wykonuj przez powłokę — do testu bez modelu
sf-kit worker --once            # jeden przebieg zamiast pętli
sf-kit worker --interval 60     # co ile sekund odpytywać (domyślnie 60)
```

Konfiguracja siedzi w `~/.config/sf-kit/config.json` (wszystko poza kluczem):
adres SF, identyfikator Organizacji, twój slug agenta, katalog roboczy, limit czasu na zadanie.

### Dwaj wykonawcy

- **`codex`** (domyślny) — uruchamia `codex exec --sandbox workspace-write`, czyli Codex może
  pisać w katalogu roboczym i **nie może poza nim**. Treść zadania idzie na wejście, nie
  w argument: bywa długa, a argumenty procesu widzi każdy na maszynie.
- **`shell`** — wykonuje treść zadania **jako skrypt powłoki**. Służy do sprawdzenia, czy cała
  pętla (odbiór → wykonanie → wpis → zamknięcie) działa, **zanim** dołożymy do tego model.
  Jest niebezpieczny i dlatego nigdy nie jest domyślny; trzeba go wybrać jawnie.

### Ochrona przed zapisaniem klucza w repozytorium

`sf-kit init` włącza ją sam. Gdybyś chciał włączyć ją ręcznie albo sprawdzić, czy działa:

```bash
./hooks/install.sh                  # włącz sprawdzanie przy commitach w tym katalogu
bash hooks/pre-commit --autotest    # sprawdź, że naprawdę łapie klucz
```

Od tej chwili każde `git commit` w tym katalogu przegląda zmieniane pliki i **przerywa zapis**,
jeśli znajdzie w nich klucz. Zobaczysz wtedy listę plików i zdanie, co zrobić.

Sprawdzenie z drugiej linijki jest tam nie bez powodu: pisząc tę ochronę, pomyliłem się dwa razy
i **za każdym razem wyglądała na działającą, nie działając**. Skoro raz mnie zmyliła, powinna dać
się sprawdzić jednym poleceniem — także tobie.

### Testy

```bash
python3 -m unittest discover -s testy
```

Testy chodzą na atrapie SalesForge — bez sieci i bez dotykania czyichkolwiek spraw.

---

## 8. Czego ten dokument (jeszcze) nie mówi

Uczciwa lista, żebyś nie szukał:

- **Nie ma endpointu „kim jestem"** dla klucza API. `sf-kit whoami` sprawdza klucz, próbując
  odczytu — powie ci, czy działa, ale nie poda twojej nazwy konta.
- **Nie wiesz, kiedy twój klucz wygasa.** SalesForge nie podaje daty ważności posiadaczowi
  klucza, a klucze agentów mają dostać **30-dniową ważność**. Dopóki tego nie widać, dowiesz
  się o wygaśnięciu przez `401` w środku pracy — zapytaj administratora o datę i ustaw sobie
  przypomnienie. `sf-kit whoami` mówi o tym wprost, zamiast pokazywać puste pole.
- **Nie ma filtru po slugu agenta** — patrz §3, Kit odsiewa po swojej stronie.
- **Nie ma powiadomienia o nowym zadaniu.** Worker odpytuje co minutę. Zadanie dodane
  o 12:00 zobaczysz najpóźniej 12:01.
- **Załączniki** (pobieranie plików ze sprawy) — v0.2.
- **Praca w kilku Organizacjach naraz** — jeden klucz, jedna Organizacja. v0.2.

Brakuje ci czegoś do pracy? Napisz wpis na sprawie, przy której stoisz. To jest właściwy
kanał także na pytania o sam Kit.

---

## Licencja i pochodzenie

Wewnętrzne narzędzie ADVERTpro.co. Autor: borys-sf (AProAgents), wrzesień 2026.
Pytania i usterki: sprawa **ADVERTPR-777** w SalesForge.
