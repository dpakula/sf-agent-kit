---
name: "sf-settings"
description: "Ustawienia: lokalne i w SF (poziom powiadomień), ze źródłem wartości; --czlowiek dla asystenta"
---
<!-- wygenerowano z pakiet/komendy.json przez sf-kit 0.17.1; nie edytuj ręcznie -->

Uruchom w terminalu: `sf-kit ustawienia …` (argumenty z prośby człowieka; składnia: `[klucz [wartość]] [--kanaly email,in_app,push] [--czlowiek | --osoba ID] [--historia]`)

- Gdy człowiek nie podał wszystkiego, czego polecenie wymaga, zapytaj go jednym zdaniem — nie zgaduj numeru sprawy ani adresu.
- Gdy masz kilka Organizacji, dodaj `--org <slug>` (sprawdzisz w `sf-kit whoami`).
- Odmowę (403) przekaż człowiekowi wprost: uprawnienia ma klucz, nie obchodź jej inną drogą.
- Pokaż wynik człowiekowi zwięźle; nie dopisuj niczego do SF bez jego prośby.
- Zasady pracy: skill `sf-praca-w-sf`.
