---
name: "sf-zglos"
description: "Zgłoś gotową pracę jako nową sprawę (tytuł, opis, załączniki) — to samo co $sf-report-work"
---
<!-- wygenerowano z pakiet/komendy.json przez sf-kit 0.17.1; nie edytuj ręcznie -->

Uruchom w terminalu: `sf-kit zglos …` (argumenty z prośby człowieka; składnia: `--tytul "…" [--opis PLIK] [--zalacz PLIK…] [--obserwujacy ADRES…] [--priorytet P] [--termin DATA]`)

- Gdy człowiek nie podał wszystkiego, czego polecenie wymaga, zapytaj go jednym zdaniem — nie zgaduj numeru sprawy ani adresu.
- Gdy masz kilka Organizacji, dodaj `--org <slug>` (sprawdzisz w `sf-kit whoami`).
- Odmowę (403) przekaż człowiekowi wprost: uprawnienia ma klucz, nie obchodź jej inną drogą.
- Zamknij pracę WPISEM w sprawie według skilla `sf-wpis-czytelny` i podaj człowiekowi link do sprawy. Nie zgłaszaj sukcesu, którego nie widać w SF.
- Zasady pracy: skille `sf-oddawanie-pracy`, `sf-wpis-czytelny`.
