SF Agent Kit 0.17.0 — ustawienia (SF-173), asystent związany z człowiekiem (SF-170), decyzje w sesji (SF-188)

STAN: PRZYGOTOWANE, NIEOPUBLIKOWANE — wydanie po słowie Damiana (Agata 04.10 01:3x).
Gałąź: borys/kit-0170-wydanie (main 0.16.0 + borys/sf170-asystent-czlowieka + borys/sf188-kit).

Nowe:
- `sf-kit ustawienia [klucz [wartość]]` — ustawienia lokalne i w SF ze źródłem wartości;
  `powiadomienia.poziom cisza|wazne|wszystko` (+ `--kanaly email,in_app,push`), `--czlowiek` /
  `--osoba ID` (cudze, za zgodą), `--historia` (kto, kiedy, z czego na co). SF-173.
  W pluginie Claude, Codexie, Kimi i Gemini jako `settings` / `ustawienia` (bez MCP — zapis).
- Asystent związany z człowiekiem: `sf-kit ustawienia pracuje_dla <e-mail|id>` (sprawdzane w SF),
  „co czeka na mnie i mojego człowieka”, podpis wpisów „dla …” (`na_rzecz`). SF-170.
- `sf-kit odpowiedz <sprawa> --blok #N --opcja B [--opis komentarz]` — wybór opcji z bloku
  `decyzja` raportu sesji; Kit pokazuje zapisany wybór (kto, kiedy). SF-188.
- `sf-kit raport <sprawa> plik.md --styl sesja` — sesja zamknięcia z blokami ```decyzja. SF-188.

Poprawka:
- `--blok #1094` dopasowuje po polu `numer` bloku (dotąd porównywał z `ref` = `BOX-…`, więc numer
  praktycznie nie trafiał; działał tylko UUID / jego początek).

Wymaga SF:
- `ustawienia` (poziom, historia) i `pracuje_dla`/`na_rzecz` — SF z SF-173 i SF-170 (paczka 16).
- `--opcja`, `--styl sesja` — SF z SF-188 (paczka 16). Na starszym SF Kit mówi wprost, co nie działa.
  → Wydanie Kita PO wdrożeniu paczki 16.

Bez zmian w narzędziach: Claude sprawdzony na żywo (0.16.0), Kimi sprawdzony na żywo (0.16.0),
Codex / Gemini: nieprzetestowane w narzędziu.

Bramka (04.10, ~01:45 PL): 668 testów OK (1 pominięty: TOML Gemini bez tomllib), pakiet zgodny
z manifestem, `claude plugin validate` OK (marketplace + plugin).

Do wykonania przy wydaniu (po słowie Damiana i po wdrożeniu paczki 16):
1. main ← borys/kit-0170-wydanie (ff), tag v0.17.0 z tym opisem (bez linii STAN), push main + tag.
2. Superadmin: PUT /api/v1/super-admin/kit/version
   {"latest": "0.17.0", "min": "0.13.0", "tag": "v0.17.0", "commit": "<sha tagu>",
    "released_at": "<czas tagu UTC>", "notes_url": "https://github.com/dpakula/sf-agent-kit/releases/tag/v0.17.0",
    "breaking": false}
