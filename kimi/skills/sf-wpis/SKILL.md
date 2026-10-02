---
name: "sf-wpis"
description: "Dopisz postęp do sprawy (domyślnie wewnętrznie, dla zespołu) — to samo co /skill:sf-note"
disable-model-invocation: true
---
<!-- wygenerowano z pakiet/komendy.json przez sf-kit 0.16.0; nie edytuj ręcznie -->

Uruchom w terminalu: `sf-kit wpis $ARGUMENTS`

- Gdy człowiek nie podał wszystkiego, czego polecenie wymaga, zapytaj go jednym zdaniem — nie zgaduj numeru sprawy ani adresu.
- Gdy masz kilka Organizacji, dodaj `--org <slug>` (sprawdzisz w `sf-kit whoami`).
- Odmowę (403) przekaż człowiekowi wprost: uprawnienia ma klucz, nie obchodź jej inną drogą.
- Zamknij pracę WPISEM w sprawie według skilla `sf-wpis-czytelny` i podaj człowiekowi link do sprawy. Nie zgłaszaj sukcesu, którego nie widać w SF.
- Zasady pracy: skill `sf-wpis-czytelny`.
