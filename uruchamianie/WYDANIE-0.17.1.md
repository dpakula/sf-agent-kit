SF Agent Kit 0.17.1: wklejanie klucza w `sf-kit init` na Windows PowerShell 5.1 (GRA-1)

STAN: WYDANE 06.10.2026 (dyspozycja Agaty po GRA-1). Gałąź: borys/kit-0171-klucz-windows (main 0.17.0 + jedna poprawka).

## Poprawka

**`sf-kit init` na Windows przyjmuje wklejony klucz.**
- Dotąd w Windows PowerShell 5.1 skrót Ctrl+V w ukrytym polu wysyłał niewidoczny znak sterujący zamiast tekstu. Kit odpowiadał wtedy „to nie wygląda na klucz SalesForge”, choć klucz był dobry (zgłoszenie z GRA-1).
- Teraz Ctrl+V wkleja zawartość schowka.
- Zamiast znaków pojawiają się gwiazdki, więc widać, że wklejenie doszło.
- Działają Backspace i Ctrl+C.
- Jeśli wklejony tekst nadal nie zaczyna się od `sk_live_`, Kit **raz** proponuje widoczną drugą próbę (wklejenie prawym przyciskiem myszy). Nie odmawia od razu.

## Nowe

**`sf-kit init` bierze klucz ze zmiennej `SF_KIT_KEY`**, gdy jest ustawiona, i wtedy o klucz nie pyta. Droga bez ukrytego pola:
```
$env:SF_KIT_KEY = Get-Clipboard; sf-kit init
```
Klucz nie trafia ani do argumentów, ani na ekran (pokazywany jest tylko skrót `sk_live_…1a2b`). Zapis jak dotąd idzie do Menedżera poświadczeń Windows albo do pęku kluczy macOS.

## Bez zmian

- macOS i Linux pytają o klucz jak dotąd (`getpass`).
- Pozostałe polecenia, plugin Claude, Codex, Kimi i Gemini: zmieniła się tylko wersja w pakietach.

## Wymaga SF

Nic nowego (zmiana tylko po stronie Kita).

## Bramka (06.10)

- 722 testy OK (1 pominięty: TOML Gemini bez tomllib). Wśród nich 9 nowych (`testy/test_klucz_windows_gra1.py`) z atrapą konsoli Windows; 4 mutacje, każda zapala test.
- Pakiet zgodny z manifestem; `claude plugin validate` OK (marketplace + plugin).
- **Nie sprawdzone na prawdziwym Windows.** Testy podmieniają `msvcrt` atrapą, bo maszyna wydania to Linux. Pierwszy prawdziwy test to test generalny Damiana.
