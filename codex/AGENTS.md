<!-- sf-kit:codex:start — sekcję zapisuje `sf-kit init --codex`; zmiany w niej nadpisze -->
<!-- wygenerowano z pakiet/komendy.json przez sf-kit 0.16.0; nie edytuj ręcznie -->

## SalesForge przez SF Kit
Pracujesz w SalesForge (SF) WYŁĄCZNIE poleceniami `sf-kit` w terminalu — nigdy surowym `curl` z kluczem. Uprawnienia ma klucz; odmowę (403) przekaż człowiekowi, nie obchodź jej.

- `sf-kit odpowiedz` domyślnie pisze DO KLIENTA; notatka zespołu: `--wewn`. `sf-kit wpis` domyślnie wewnętrzny.
- Wzmianka działa tylko pełnym adresem: `@anna@firma.pl`.
- Praca jest oddana, gdy jest w SF (wpis/sprawa) — nie zgłaszaj sukcesu, którego nie widać w SF.
- Zasady pracy: skille `$sf-praca-w-sf`, `$sf-wpis-czytelny`, `$sf-oddawanie-pracy`.

| skill (Codex) | po polsku | w terminalu | co robi |
|---|---|---|---|
| `$sf-cases` | `$sf-sprawy` | `sf-kit sprawy` | Sprawy w Organizacji (u asystenta: co czeka na mnie i mojego człowieka) |
| `$sf-case` | `$sf-sprawa` | `sf-kit sprawa` | Karta sprawy: opis, wpisy, załączniki, „Do Ciebie” |
| `$sf-report-work` | `$sf-zglos` | `sf-kit zglos` | Zgłoś gotową pracę jako nową sprawę (tytuł, opis, załączniki) |
| `$sf-note` | `$sf-wpis` | `sf-kit wpis` | Dopisz postęp do sprawy (domyślnie wewnętrznie, dla zespołu) |
| `$sf-reply` | `$sf-odpowiedz` | `sf-kit odpowiedz` | Odpowiedz w sprawie — UWAGA: domyślnie widzi to klient; --wewn = notatka zespołu |
| `$sf-attach` | `$sf-zalacz` | `sf-kit zalacz` | Załącz pliki do sprawy |
| `$sf-publish` | `$sf-publikuj` | `sf-kit publikuj` | Opublikuj szkic sprawy (wymaga wpisu ze zgodą ownera/admina) |
| `$sf-inbox` | — | `sf-kit inbox` | Moje wiadomości — pokaż i potwierdź odbiór |
| `$sf-tasks` | `$sf-zadania` | `sf-kit tasks` | Moje zadania |
| `$sf-block` | `$sf-blok` | `sf-kit blok` | Pokaż blok (decyzja, dyspozycja, raport) albo katalog rodzajów: typy |
| `$sf-timeline` | `$sf-os` | `sf-kit os` | Oś czasu sprawy |
| `$sf-status` | — | `sf-kit whoami` | Kim jestem w SF: konto, klucz, Organizacje, uprawnienia |
| `$sf-settings` | `$sf-ustawienia` | `sf-kit ustawienia` | Ustawienia: lokalne i w SF (poziom powiadomień), ze źródłem wartości; --czlowiek dla asystenta |
| `$sf-update` | `$sf-aktualizuj` | `sf-kit update` | Zaktualizuj Kita do wydania wskazanego przez SF |

<!-- sf-kit:codex:end -->
