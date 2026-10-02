---
name: "sf-reply"
description: "Odpowiedz w sprawie — UWAGA: domyślnie widzi to klient; --wewn = notatka zespołu"
---
<!-- wygenerowano z pakiet/komendy.json przez sf-kit 0.16.0; nie edytuj ręcznie -->

Uruchom w terminalu: `sf-kit odpowiedz …` (argumenty z prośby człowieka; składnia: `<sprawa> --opis PLIK|- [--wewn] [--blok #NUMER]`)

- Gdy człowiek nie podał wszystkiego, czego polecenie wymaga, zapytaj go jednym zdaniem — nie zgaduj numeru sprawy ani adresu.
- Gdy masz kilka Organizacji, dodaj `--org <slug>` (sprawdzisz w `sf-kit whoami`).
- Odmowę (403) przekaż człowiekowi wprost: uprawnienia ma klucz, nie obchodź jej inną drogą.
- Zamknij pracę WPISEM w sprawie według skilla `sf-wpis-czytelny` i podaj człowiekowi link do sprawy. Nie zgłaszaj sukcesu, którego nie widać w SF.
- Zasady pracy: skill `sf-wpis-czytelny`.
