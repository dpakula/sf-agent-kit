# SF Agent Kit

**Dla kogo:** jesteś agentem (albo człowiekiem), który ma pracować dla kogoś przez SalesForge,
i nie znasz tego systemu. Ten dokument jest wszystkim, czego potrzebujesz, żeby zacząć.
Nie musisz czytać niczego poza nim.

**Co tu dostaniesz:** jak odbierać zadania, jak je wykonywać i jak raportować wynik —
przez zwykłe API HTTP, z jednym poleceniem `sf-kit`, które robi to za ciebie.

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

### Uprawnienia, o które musisz poprosić

To jest zbadane i zmierzone, nie zgadywane (14.09.2026, wersja SF z tego dnia):

| co robisz | endpoint | jakie uprawnienie |
|---|---|---|
| czytasz listę zadań | `GET /api/v1/tasks` | **żadne szczególne** — wystarczy działający klucz |
| czytasz szczegóły zadania | `GET /api/v1/tasks/{id}` | żadne szczególne |
| piszesz wpis na sprawie | `POST /api/v1/tickets/{id}/entries` | `tickets:comment` |
| komentujesz zadanie | `POST /api/v1/tasks/{id}/comments` | żadne szczególne |
| **bierzesz zadanie i kończysz je** | `PATCH /api/v1/tasks/{id}` | **`plans:write`** ← i to jest haczyk |

**Bez `plans:write` nie zmienisz statusu zadania.** Dostaniesz `403 Manager access required`.
Czyli: zobaczysz zadanie, wykonasz je, napiszesz wpis — ale nie oznaczysz jako zrobionego,
a ono zostanie w kolejce, jakby nikt go nie tknął.

> **Poproś administratora o klucz z uprawnieniami: `tickets:read`, `tickets:comment`
> oraz `plans:write`.**

**Uczciwe ostrzeżenie, które administrator powinien przeczytać przed nadaniem:**
`plans:write` jest dziś szersze, niż nazwa sugeruje. Poza zmianą statusu twojego zadania
pozwala też **tworzyć nowe zadania, kasować cudze i wykonywać operacje zbiorcze**.
Nie ma dziś węższego uprawnienia w rodzaju „zmień status zadania, które jest twoje".
Jeśli to za dużo zaufania jak na twoją rolę — powiedz o tym; to jest znana sprawa do zawężenia
i nie chcemy, żeby ktoś nadał ci je w ciemno.

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
2. **Nie zapisuj go w repozytorium.** Kit ma hak, który zatrzyma commit, gdy w plikach pojawi
   się `sk_live_` — ale hak działa tylko tam, gdzie go zainstalowano.
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

**Krok 1 ma haczyk, o którym musisz wiedzieć:** SalesForge nie ma dziś filtru „pokaż zadania
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
| **403** | klucz jest dobry, ale nie wolno ci tej rzeczy | brakuje uprawnienia. Przy `PATCH /tasks` to prawie zawsze brak `plans:write` (§2). Zapisz, czego próbowałeś, i poproś administratora — **nie obchodź tego innym endpointem** |
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

### Instalacja haka na wyciek klucza

```bash
./hooks/install.sh              # zainstaluj hak pre-commit w tym repozytorium
bash hooks/pre-commit --autotest   # sprawdź, że hak faktycznie łapie
```

Hak zatrzymuje commit, w którym pojawia się klucz. Autotest jest tam nie bez powodu: przy
pisaniu tego haka pomyliłem się dwa razy i **za każdym razem wyglądał na działający**.

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
