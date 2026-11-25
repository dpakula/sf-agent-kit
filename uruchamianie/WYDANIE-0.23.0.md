# SF Agent Kit 0.23.0 — przyznania bloków stron Organizacji (SF-517 R5)

STAN: DO BRAMKI 25.11.2026 (arek-sf, kickoff Agaty). Gałąź `arek/sf517-kit-blok-przyznaj` = `origin/main` (v0.22.0,
`2982d36`) + ta paczka. Push `main` i tagu, a potem ogłoszenie w SF (`PUT /super-admin/kit/version`) robi seweryn albo Damian.
Zmiana niełamiąca, `min` bez zmian. Działa po wydaniu R5 SF-517 na serwerze (paczka B3 `arek/sf517-r3a-r4`); wcześniej
polecenia mówią „serwer nie zna tras przyznań” i kończą się kodem 1.

## Dlaczego

R5 dało trasy superadmina do przyznawania Organizacji bloków stron `granted` (np. `lib/vehicle_list` dla FixForum).
Bez Kita przyznanie wymaga panelu albo ręcznego `curl` z uuid Organizacji w ścieżce.

## Nowe

- **`sf-kit blok-przyznane --dla <slug|uuid> [--json]`**: bloki przyznawane i które z nich Organizacja ma.
- **`sf-kit blok-przyznaj <rodzina/nazwa> --dla <slug|uuid> [--json]`** i **`blok-odbierz`**: zapis superadmina.
  Kit odczytuje stan przed zapisem (ten sam stan = nic nie wysyła), sprawdza stan po zapisie (200 bez zmiany = kod 1),
  zdejmuje `@N` z referencji. Odebranie nie zdejmuje sekcji już stojących na stronach.
- Kody wyjścia: `0` gotowe albo bez zmian, `1` odmowa lub awaria serwera, `2` błąd wywołania (brak `--dla`, nieznany slug,
  zły kształt referencji, blok nieprzyznawany). Przy kodzie 2 nic nie zostało zapisane.
- `kontrakt blok-przyznane` i `kontrakt blok-przyznaj`: trasy, pola, pułapki.

## Decyzje

- **Osobne polecenia, nie `blok przyznaj`.** `sf-kit blok` jest w pakiecie narzędziem MCP `block` z `readOnlyHint`.
  Zapis pod nim dostałby tę adnotację. `sf-kit blok przyznaj` odsyła do `blok-przyznaj` (kod 2).
- **`--dla`, nie `--org`.** `--org` to Organizacja robocza wołającego (członkostwo + nadania). Superadmin przyznaje blok
  Organizacji, w której zwykle nie jest członkiem. Slug tłumaczy `GET /tenants` (superadmin widzi wszystkie).
- Poza manifestem pakietu (`komendy.json`), jak reszta warstwy administracyjnej.

## Testy

`python3 -m unittest discover -s testy`: 984, OK (1 pominięty). Nowe: `test_przyznania_blokow_sf517.py` (19), mutacje 10/10
zabite. `python3 -m sf_kit.pakiet --sprawdz`: zgodny. Przegląd koordynatora: 80 linii (nowe polecenia w linii `kontrakt`).
Żywy SF 25.11 (PROD bez R5, sam odczyt): `blok-przyznane --dla fixforum` → kod 1 „serwer nie zna tras przyznań”.
Zapis przetestowany tylko z atrapą; pierwszy prawdziwy przebieg po wydaniu B3, kluczem superadmina.
Jeden przebieg pakietu przy obciążonej maszynie: 10 F + 1 E (onboarding/slug, 41 s), dwa kolejne czyste — ten sam flake co 24.11.
