---
name: "oddawanie-pracy"
description: "Jak oddać gotową pracę do SalesForge: zglos, zalacz, publikuj, sprawdzenie, że doszło. Użyj, gdy praca jest gotowa do przekazania."
---
<!-- wygenerowano z pakiet/komendy.json przez sf-kit 0.17.1; nie edytuj ręcznie -->

# Oddawanie pracy do SalesForge

Praca jest oddana dopiero wtedy, gdy jest w SF — w sprawie, z plikami, widoczna dla tych, którzy mają ją odebrać.

## Nowa praca → nowa sprawa
```
sf-kit zglos --tytul "Konspekt kursu: moduł 3" --opis opis.md --zalacz konspekt.pdf --obserwujacy anna@firma.pl
```
- Tytuł mówi, CO oddajesz. Opis według szablonu czytelnego wpisu (skill `wpis-czytelny`).
- Obserwujących dodajesz **po adresie e-mail**. Gdy któryś nie wejdzie (brak uprawnienia), Kit powie to wprost — dołóż go potem: `sf-kit obserwujacy <sprawa> --dodaj adres`.
- Priorytet i termin: `--priorytet`, `--termin` (nie tylko słowami w opisie).

## Praca do istniejącej sprawy
- Postęp / wynik dla zespołu: `sf-kit wpis <sprawa> --opis plik.md` (albo `--opis -` i treść na wejściu).
- Odpowiedź w sprawie: `sf-kit odpowiedz <sprawa> --opis plik.md` — **domyślnie widzi ją klient**; notatka tylko dla zespołu: `--wewn`. Odpowiedź na blok „Do Ciebie”: `--blok #NUMER`.
- Pliki: `sf-kit zalacz <sprawa> plik1 plik2` (opcjonalnie `--notka "…"`). Odmowę SF (rozmiar, rodzaj pliku) Kit pokaże wprost — wtedy powiedz o tym człowiekowi, nie zmieniaj rozszerzenia „na siłę”.
- Szkic sprawy publikuje się tylko ze zgodą ownera/admina: `sf-kit publikuj <sprawa> --zgoda <id wpisu ze zgodą>`.

## Czy doszło?
- `sf-kit sprawa <numer>` — zobacz swój wpis i załączniki w sprawie.
- `sf-kit outbox` — czy to, co wysłałeś do innych, zostało odebrane.

**Nie zgłaszaj sukcesu, którego nie widać w SF.** Zapowiedź („wrzucę za chwilę”) to nie oddanie.
