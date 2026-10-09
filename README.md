# SF Agent Kit

To instrukcja dla ludzi. Instrukcja dla agenta AI jest w pliku [AGENT.md](AGENT.md).

## Dla użytkownika

**SF Agent Kit** łączy Twojego agenta AI (Claude Code, Codex, Kimi) z SalesForge. Agent przyjmuje od Ciebie zadania i pracuje na sprawach Twojej Organizacji. Każdą czynność zapisuje w sprawie, więc widzisz, co zrobił i dlaczego.

### Jak zacząć

Masz konto w SalesForge i Twój agent też. Jeśli nie, poproś administratora swojej Organizacji. Zainstaluj Kit jednym poleceniem.

Potrzebujesz tylko Pythona 3.9 lub nowszego. Git i uprawnienia administratora komputera nie są potrzebne.

### 1. Zainstaluj Kit

Wklej jedno polecenie do terminala.

- **macOS i Linux** (aplikacja Terminal):

  ```
  curl -fsSL https://raw.githubusercontent.com/dpakula/sf-agent-kit/main/install.sh | sh
  ```

- **Windows** (PowerShell: menu Start, wpisz „PowerShell”). Uruchom polecenie sam, we własnym oknie PowerShell, a nie przez agenta w aplikacji Claude.

  ```
  irm https://raw.githubusercontent.com/dpakula/sf-agent-kit/main/install.ps1 | iex
  ```

Instalator pobiera Kita z GitHuba do Twojego katalogu użytkownika i zakłada polecenie `sf-kit`. Na macOS, jeśli instalator o to prosi, otwórz nowe okno terminala albo użyj pełnej ścieżki, którą wypisał. Ponowne uruchomienie instalatora niczego nie psuje: konfiguracja i klucze zostają.

Jeśli brakuje Pythona, instalator powie, jak go doinstalować.

### 2. Skonfiguruj agenta

```
sf-kit init
```

Kit poprosi o klucz agenta od administratora, sam rozpozna resztę w SalesForge i zapyta „Zapisać?”: odpowiedz `t`. Wklejonego klucza nie widać na ekranie, to normalne.

### 3. Sprawdź, czy klucz działa

```
sf-kit whoami
```

Kit pokazuje, kim jest agent i w których Organizacjach może pracować. Jeśli widzisz „Nie mam klucza”, wróć do kroku 2.

### 4. Przygotuj folder na pracę z asystentem

```
mkdir praca-z-ai
cd praca-z-ai
sf-kit start
```

W folderze powstaje instrukcja dla asystenta z Twoją Organizacją i zgoda na polecenia Kita, więc asystent od razu wie, co robić. Nie rób tego w katalogu domowym, tam `sf-kit start` odmówi.

### 5. Uruchom agenta w tym folderze i po prostu powiedz, czego chcesz

```
claude
```

To polecenie dla Claude Code; dla Codex wpisz `codex`. Rozmawiaj z agentem normalnym językiem, na przykład:

```
Hej, pokaż mi, co dzisiaj na nas czeka.
```

```
Co jest w sprawie FM-66?
```

```
Zgłoś sprawę: formularz kontaktowy na stronie nie wysyła wiadomości.
```

```
Odpowiedz na sprawę FM-66, że poprawka jest już na stronie.
```

```
Załącz do sprawy FM-66 plik raport.pdf.
```

Przed każdym zapisem w SalesForge agent pokaże, co wyśle, i zapyta o zgodę.

> **Jeśli coś nie działa przy pierwszym uruchomieniu Claude Code**
>
> - Na dole ekranu widzisz „Not logged in · Run /login”? Wpisz `/login` i zaloguj się w przeglądarce. Bez tego Claude Code nic nie odpowiada.
> - Pytanie „Is this a project you created or one you trust?”: zejdź strzałką na „Yes, I trust this folder” i dopiero wtedy naciśnij Enter. Sam Enter zamyka Claude Code.
> - Claude Code przy każdym poleceniu Kita pyta „Do you want to proceed?”? Folder nie jest zaufany. Wybierz „1. Yes” albo uruchom `claude` jeszcze raz i zaufaj folderowi.

### Claude w aplikacji mobilnej albo w chmurze

Sesja uruchomiona z telefonu albo z claude.ai/code działa w chmurze, nie na Twoim komputerze. Nie masz tam terminala, a wszystko, co agent zainstaluje, znika razem z sesją.

Najprościej zrobić kroki 1–4 na swoim komputerze. Z telefonu pracujesz potem przez aplikację Claude Desktop albo przez `claude remote-control` uruchomione w folderze pracy, a Kit i klucz zostają na Twoim komputerze.

Jeśli chcesz pracować w samej chmurze, dodaj klucz w ustawieniach środowiska jako zmienną `SF_KIT_KEY`. Nigdy nie wklejaj klucza w czacie. Otwórz nową sesję i poproś agenta: „Zainstaluj SF Agent Kit z github.com/dpakula/sf-agent-kit i pokaż sprawy z mojej Organizacji”. Klucz w chmurze nie odnawia się sam: gdy wygaśnie (po 30 dniach), wpisz w ustawieniach nowy klucz od administratora.

### Aktualizacja

```
sf-kit aktualizuj
```

Kit raz na dobę sprawdza, czy jest nowa wersja, i mówi o tym jedną linią.

### Dobrze wiedzieć

**Klucz.** Klucz agenta widać tylko raz, gdy administrator go wystawia. Administrator przekazuje go menedżerem haseł, nigdy mailem ani czatem. Wpisujesz go sam, w terminalu, przy `sf-kit init`. Kit trzyma go w pęku kluczy na Macu i w Menedżerze poświadczeń na Windows. Jeśli na Macu wyskoczy okno pęku kluczy, kliknij „Zezwalaj zawsze”.

**Brak uprawnień.** Jeśli Kit odpowiada „Twój klucz nie ma uprawnienia …”, poproś administratora Organizacji o nadanie. Nowy klucz nie jest potrzebny.

**Kilku agentów na jednym komputerze.** `sf-kit init` pokazuje listę agentów i pozwala dodać nowego albo poprawić istniejącego. W poleceniach wybierasz agenta przez `--agent <nazwa>`, np. `sf-kit --agent claude-jkowalski whoami`.

**Agent inny niż Claude Code i Codex.** Gdy nie używasz `sf-kit start`, wklej agentowi na początku rozmowy ten tekst. Slug Organizacji znajdziesz w wyniku `sf-kit whoami`, w linii „pracuję w:”.

```
Uruchom `sf-kit readme --tresc`: wypisze instrukcję dla agenta (AGENT.md). Przeczytaj ją
i postępuj według niej.
Moja Organizacja w SalesForge to: <slug Twojej Organizacji>   (podawaj ją zawsze jako --org)
1. Uruchom sf-kit whoami i powiedz mi zwykłym językiem, co widzisz.
2. Jeśli czegoś brakuje, powiedz mi, o co poprosić administratora.
3. Gdy dam Ci link do sprawy, odpowiadaj w tej sprawie. Nową sprawę zakładaj tylko wtedy, gdy żadnej nie ma.
Nie pytaj mnie o klucz i nie wpisuj go w rozmowie.
```

**Dla programistów.** Kit można też pobrać gitem: `git clone https://github.com/dpakula/sf-agent-kit.git`, potem `cd sf-agent-kit` i `./sf-kit init`.

## Instrukcja dla agenta

Agent AI, który pracuje z Kitem, czyta osobną instrukcję: [AGENT.md](AGENT.md). Jeśli jesteś agentem i trafiłeś najpierw tutaj, przejdź tam. Na komputerze z zainstalowanym Kitem pokaże ją polecenie `sf-kit readme --tresc`.
