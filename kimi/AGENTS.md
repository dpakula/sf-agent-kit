<!-- sf-kit:kimi:start — sekcję zapisuje `sf-kit init --kimi`; zmiany w niej nadpisze -->
<!-- wygenerowano z pakiet/komendy.json przez sf-kit 0.17.0; nie edytuj ręcznie -->

## SalesForge przez SF Kit
Pracujesz w SalesForge (SF) WYŁĄCZNIE poleceniami `sf-kit` w terminalu — nigdy surowym `curl` z kluczem. Uprawnienia ma klucz; odmowę (403) przekaż człowiekowi, nie obchodź jej.

- `sf-kit odpowiedz` domyślnie pisze DO KLIENTA; notatka zespołu: `--wewn`. `sf-kit wpis` domyślnie wewnętrzny.
- Wzmianka działa tylko pełnym adresem: `@anna@firma.pl`.
- Praca jest oddana, gdy jest w SF (wpis/sprawa) — nie zgłaszaj sukcesu, którego nie widać w SF.
- Zasady pracy: skille `/skill:sf-praca-w-sf`, `/skill:sf-wpis-czytelny`, `/skill:sf-oddawanie-pracy`.

| skill (Kimi Code) | po polsku | w terminalu | co robi |
|---|---|---|---|
| `/skill:sf-cases` | `/skill:sf-sprawy` | `sf-kit sprawy` | Sprawy w Organizacji (u asystenta: co czeka na mnie i mojego człowieka) |
| `/skill:sf-case` | `/skill:sf-sprawa` | `sf-kit sprawa` | Karta sprawy: opis, wpisy, załączniki, „Do Ciebie” |
| `/skill:sf-report-work` | `/skill:sf-zglos` | `sf-kit zglos` | Zgłoś gotową pracę jako nową sprawę (tytuł, opis, załączniki) |
| `/skill:sf-note` | `/skill:sf-wpis` | `sf-kit wpis` | Dopisz postęp do sprawy (domyślnie wewnętrznie, dla zespołu) |
| `/skill:sf-reply` | `/skill:sf-odpowiedz` | `sf-kit odpowiedz` | Odpowiedz w sprawie — UWAGA: domyślnie widzi to klient; --wewn = notatka zespołu |
| `/skill:sf-attach` | `/skill:sf-zalacz` | `sf-kit zalacz` | Załącz pliki do sprawy |
| `/skill:sf-publish` | `/skill:sf-publikuj` | `sf-kit publikuj` | Opublikuj szkic sprawy (wymaga wpisu ze zgodą ownera/admina) |
| `/skill:sf-inbox` | — | `sf-kit inbox` | Moje wiadomości — pokaż i potwierdź odbiór |
| `/skill:sf-tasks` | `/skill:sf-zadania` | `sf-kit tasks` | Moje zadania |
| `/skill:sf-block` | `/skill:sf-blok` | `sf-kit blok` | Pokaż blok (decyzja, dyspozycja, raport) albo katalog rodzajów: typy |
| `/skill:sf-timeline` | `/skill:sf-os` | `sf-kit os` | Oś czasu sprawy |
| `/skill:sf-status` | — | `sf-kit whoami` | Kim jestem w SF: konto, klucz, Organizacje, uprawnienia |
| `/skill:sf-settings` | `/skill:sf-ustawienia` | `sf-kit ustawienia` | Ustawienia: lokalne i w SF (poziom powiadomień), ze źródłem wartości; --czlowiek dla asystenta |
| `/skill:sf-update` | `/skill:sf-aktualizuj` | `sf-kit update` | Zaktualizuj Kita do wydania wskazanego przez SF |

<!-- sf-kit:kimi:end -->
