---
description: "Opublikuj szkic sprawy (wymaga wpisu ze zgodą ownera/admina)"
argument-hint: "<sprawa> --zgoda WPIS"
allowed-tools: "Bash(sf-kit:*), PowerShell(sf-kit *)"
disable-model-invocation: true
---
<!-- wygenerowano z pakiet/komendy.json przez sf-kit 0.16.0; nie edytuj ręcznie -->

Uruchom w terminalu: `sf-kit publikuj $ARGUMENTS`

- Gdy człowiek nie podał wszystkiego, czego polecenie wymaga, zapytaj go jednym zdaniem — nie zgaduj numeru sprawy ani adresu.
- Gdy masz kilka Organizacji, dodaj `--org <slug>` (sprawdzisz w `sf-kit whoami`).
- Odmowę (403) przekaż człowiekowi wprost: uprawnienia ma klucz, nie obchodź jej inną drogą.
- Zamknij pracę WPISEM w sprawie według skilla `wpis-czytelny` i podaj człowiekowi link do sprawy. Nie zgłaszaj sukcesu, którego nie widać w SF.
- Zasady pracy: skill `oddawanie-pracy`.
