SF Agent Kit 0.19.0: nawyki koordynatorki — `blok nowy`, `--tresc`, `nowa-sprawa` jedną komendą, kody wyjścia (SF-496)

STAN: WYDANIE LOKALNE 04/05.11.2026 (kickoff Agaty, SF-496 pkt 1–5 i 11). Gałąź `klaudiusz/kit-0190-wydanie` = 0.18.0
(`klaudiusz/kit-0180-wydanie`) + ta paczka. Tag `v0.19.0` lokalny. **Push gałęzi i tagu (klucz wdrożeniowy u seweryna)
i wydanie (`GET /kit/version` = latest w SF) czekają na GO Damiana.** Bez tego `sf-kit update` u innych widzi wersję
sprzed.

## Po co

04.11 koordynatorka zrobiła ~140 operacji SF przez curl / sf_api.sh, a przez Kita 2. Komendy w większości były już
w 0.18, ale w innym kształcie niż jej nawyki. 0.19 dopasowuje Kita do tego, jak ona pisze. Miara sukcesu: ≥ 80 %
operacji SF Agaty przez Kit w dniu po wydaniu.

## Nowe

- **`blok nowy …`** = `konsola blok …` (pkt 1). Krok domyślnie z `tracking/rozgrywka.json` → `ostatni_ticket_id`,
  tak samo jak `sf_box_sprawa` floty (`SF_KIT_ROZGRYWKA` = inna ścieżka, `--bez-kroku` = bez). `--zastepuje #N`
  zamyka stary blok, gdy nowy powstał (dubel = nic). Dedup bez zmian (ten sam algorytm co biblioteka: otwarty, ten sam
  rodzaj i kotwica, < 2 h).
- **`konsola bloki [--otwarte|--wszystkie] [--sprawa <nr|uuid|link>] [--json]`** — numer, rodzaj, prio, wysiłek, wiek,
  kotwica (pkt 2). `--sprawa` przyjmuje też numer.
- **`konsola zamknij #N… --odpowiedz "…"`** — zamknięcie, odpowiedź oznaczona jako odebrana, notka jako wpis
  WEWNĘTRZNY na sprawie kotwicy (pkt 2). `konsola odpowiedzi --odebrane #N --notka "…"` (pkt 10, przy okazji).
- **`--tresc "tekst"`** obok `--opis PLIK|-` w: `wpis`, `konsola blok`, `nowa-sprawa`/`zglos`, `krok nowy`,
  `krok zamknij` (też `--wpis`), `odpowiedz`, `zlec` (pkt 3). Plik i `-` też działają.
- **`nowa-sprawa` jedną komendą** (pkt 4): `--przypisz <e-mail>` (assignee przy założeniu), `--prio low|med|high|urgent`,
  `--obserwujacy a@x,b@y`, `--tag` powtarzalny (tag z taksonomii nadawany; nazwa spoza = kategoria jak dotąd),
  `--zalacz`, `--json`.
- **`sprawa <nr> --rodzaj document|message|lead|case`** (= `--kind`, ślad `field_change` na osi; SF-361), `--json` przy
  zmianach (pkt 5). **`sprawa <nr> --id`** → `uuid  numer  Organizacja` (pkt 10, przy okazji).
- **Kody wyjścia i `--json`** w komendach paczki (pkt 11): `0` zrobione · `1` SF odmówił / częściowo · `2` złe wejście,
  nic nie wysłane. „Błąd: …” na stderr; z `--json` jeden obiekt `{"ok": …}` na stdout.

## Zmienione zachowanie (sprawdź, jeśli używasz)

- **Zła ścieżka treści = kod 2 i „Błąd: …”** (było: kod 1 i „nie ma pliku z opisem”). `--tresc raport.md` bez pliku
  `raport.md` to błąd, a nie wpis o treści „raport.md”. Tekst ze spacją jest zawsze tekstem.
- `konsola blok` bez `--krok` bierze krok z `tracking/rozgrywka.json`, jeśli plik jest. Kotwica podstawowa (sprawa
  źródłowa) bez zmian; krok idzie jako `krok_id` (kotwica podwójna, SF-182) i na lustro.
- `nowa-sprawa --tag X`: gdy X jest tagiem w taksonomii Organizacji, zostaje NADANY (wcześniej szedł jako kategoria).
  Nazwa w kilku typach = błąd wejścia (bez zgadywania typu).
- `sprawa --status` odmowa reguły rozwiązywania → kod 2 (było 1).

## Wymaga SF

Nic nowego, kontrakt API bez zmian (OpenAPI 04.11). **Prośba do borysa (SF-496):** `BoxPatch` nie ma pola na treść
zamknięcia bloku, więc notka z `zamknij --odpowiedz` idzie wpisem na sprawę kotwicy. Pole `notka` w `BoxPatch`
(widoczne w bloku i na osi) pozwoliłoby trzymać ją przy bloku.

## Na 0.20 (SF-496 pkt 6–9)

`poczta szkic/akcept/wyslij` (SF-491), `zalacz --sprawa … --publiczny` z MIME, `krok nowy` z PATCH tytułu, obserwującymi,
tagiem Krok, dashboardem i aktualizacją `rozgrywka.json`, `os <nr> --od --autor --limit` z offsetem > 200.

## Bramka (04.11)

- Testy: 808, z czego 805 OK i 1 pominięty. 2 błędy `test_onboarding_960` są znane z 0.18 (macOS: pęk zamiast pliku;
  test pisze do PRAWDZIWEGO pęku — izolacja `MaszynaTestowa` dalej do zrobienia). Nowe: `testy/test_nawyki_sf496.py`
  17/17.
- Pakiet zgodny z manifestem (`python3 -m sf_kit.pakiet --sprawdz`), pakiety zregenerowane (`--zapisz`).
- `claude plugin validate .`: OK.
- Na żywym SF (odczyt): `sprawa SF-496 --id`, `konsola bloki --otwarte`, `wpis --tresc <zła ścieżka>` → kod 2 bez zapisu.
