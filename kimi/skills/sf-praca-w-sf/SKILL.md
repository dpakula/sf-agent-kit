---
name: "sf-praca-w-sf"
description: "Jak pracować w SalesForge przez SF Kit: Organizacja, sprawa vs zadanie, poziomy widoczności, Kit zamiast curl. Użyj, gdy praca dotyczy spraw, zadań albo wpisów w SalesForge."
---
<!-- wygenerowano z pakiet/komendy.json przez sf-kit 0.17.1; nie edytuj ręcznie -->

# Praca w SalesForge przez SF Kit

SalesForge (SF) to system spraw i zadań. Pracujesz w nim **wyłącznie przez polecenia `sf-kit`** — nigdy surowym `curl` z kluczem w wierszu poleceń (klucz byłby widoczny dla innych procesów na maszynie).

## Pojęcia
- **Organizacja** — przestrzeń firmy w SF (nie „tenant”). Masz w niej konto i uprawnienia. Gdy masz kilka Organizacji, wskaż właściwą: `sf-kit --org <slug> …`.
- **Sprawa** — wątek z historią wpisów (zgłoszenie, temat, projekt do załatwienia). Numer w postaci `SKROT-123`.
- **Zadanie** — konkretna praca do wykonania, zwykle przy sprawie. Lista: `sf-kit tasks`.
- **Wpis** — każda wiadomość lub notatka na sprawie. Wpis ma **poziom widoczności**:
  - `internal` (domyślnie) — tylko zespół Organizacji;
  - zewnętrzny (`external` w `wpis`, domyślny w `odpowiedz`) — widzi go też klient. Treści, którą klient zobaczył, nie da się „odzobaczyć”, więc wybieraj świadomie.
- **Blok** — wpis o określonym rodzaju (decyzja, dyspozycja, raport), z adresatem. Podgląd: `sf-kit blok <id>`; rodzaje: `sf-kit blok typy`.

## Zasady
1. **Uprawnienia ma Twój klucz, nie Ty jako osoba.** Odmowa (403) znaczy, że kluczowi czegoś brakuje — powiedz o tym człowiekowi, nie obchodź jej inną drogą.
2. **Pracuj na oryginalnych słowach zgłaszającego** (sekcja „Oryginalne słowa” w sprawie). Twoje streszczenie jest pomocnicze.
3. **Najpierw przeczytaj sprawę** (`sf-kit sprawa <numer>`), potem pisz — wpisy innych często odpowiadają już na pytanie.
4. **Odpowiedź przychodzi wpisem w sprawie**, nie w rozmowie poza SF. To, czego nie ma w sprawie, dla zespołu nie istnieje.
5. Linki do spraw i wpisów podawaj pełne (z `?org=`), żeby otwierały się we właściwej Organizacji.

## Gdy coś nie działa
- `sf-kit status` (whoami) — czy klucz działa, w jakiej jesteś Organizacji, jakie masz uprawnienia.
- `sf-kit update --check` — czy Kit nie jest za stary względem SF.
