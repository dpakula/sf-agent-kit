"""Ramka promptu — co wykonawca dostaje POZA treścią zadania.

v0.2 (14.09.2026) - APro Agents / borys-sf

PO CO RAMKA, SKORO ZADANIE MA TREŚĆ
═══════════════════════════════════
Bo treść zadania pisał człowiek do człowieka. Model, który dostaje samo `body_md`, nie wie
trzech rzeczy, bez których pracuje po omacku:

  · KIM jest w tym układzie (agentem o konkretnym slugu, pracującym w SalesForge),
  · GDZIE wolno mu pracować (jeden katalog, nic poza nim, żadnych sekretów),
  · CO ma oddać na końcu (sprawozdanie dla człowieka, nie dziennik pracy).

Trzecia rzecz jest tu najważniejsza. Wpis na sprawie czyta CZŁOWIEK — najczęściej ktoś, kto
nie siedział przy tej pracy i nie zna narzędzi. Model, którego się o to nie poprosi, oddaje
surowe wyjście: listę poleceń, ścieżki, znaczniki. Worker umie to opakować (`wpis_sukces`),
ale opakowany dziennik pracy dalej jest dziennikiem pracy.

CZEGO W RAMCE NIE MA
**Klucza API i niczego, co przyszło z SF poza treścią zadania i jego identyfikatorami.**
Model rozmawia z plikami; z SalesForge rozmawia worker. To jest granica, przez którą nic nie
przechodzi — także „dla wygody".
"""
from __future__ import annotations

#: Układ sprawozdania. Ten sam, którego SalesForge używa we wpisach — więc sprawozdanie agenta
#: czyta się tak samo jak sprawozdanie człowieka, a nie jak wydruk z maszyny.
UKLAD_SPRAWOZDANIA = ("**Sedno**", "**Co zrobiono**", "**Szczegóły techniczne**")


def zbuduj(zadanie: dict, *, slug: str, katalog: str) -> str:
    """Prompt dla wykonawcy: nagłówek (kim jesteś, gdzie) + treść zadania + stopka (co oddać).

    Treść zadania idzie w ŚRODKU i bez zmian — nie parafrazujemy jej, nie skracamy i nie
    tłumaczymy. Zmieniona treść to zmienione zadanie, a człowiek, który je pisał, zobaczy
    wynik pracy nad czymś, czego nie zlecił.
    """
    nazwa = zadanie.get("external_id") or zadanie.get("id") or "?"
    tytul = zadanie.get("title") or "(bez tytułu)"
    sprawa = zadanie.get("ticket_ref") or zadanie.get("ticket_id")
    skad_sprawa = f"Sprawa, przy której to zadanie stoi: {sprawa}.\n" if sprawa else ""

    return f"""Pracujesz jako agent „{slug}" w systemie SalesForge.

Dostałeś zadanie {nazwa}: {tytul}.
{skad_sprawa}Katalog roboczy: {katalog}. Pracuj WYŁĄCZNIE w nim.

Czego nie wolno:
- nie wychodź poza katalog roboczy — ani do odczytu, ani do zapisu,
- nie otwieraj i nie wypisuj plików z sekretami (.env, klucze, hasła, tokeny). Jeśli zadanie
  wydaje się tego wymagać, nie zgaduj: napisz o tym w sprawozdaniu i przerwij,
- nie zgaduj kontekstu, którego nie dostałeś. Brakujące polecenie opisz zamiast domyślać się.

--- TREŚĆ ZADANIA ---

{(zadanie.get("body_md") or "").strip()}

--- KONIEC TREŚCI ZADANIA ---

Na koniec napisz SPRAWOZDANIE dla człowieka. To ono trafi do systemu jako wpis na sprawie,
więc nie jest to dziennik twojej pracy — to wiadomość do kogoś, kto nie widział, co robiłeś,
i często nie zna narzędzi, których użyłeś.

Po polsku, w tym układzie i z tymi nagłówkami:

**Sedno** — jedno zdanie: co udało się osiągnąć (albo czego nie i dlaczego).

**Co zrobiono** — dwa do pięciu zdań zwykłym językiem. Bez ścieżek, bez nazw poleceń,
bez znaczników. Tak, jakbyś tłumaczył to osobie, która zleciła pracę.

**Szczegóły techniczne** — dopiero tutaj konkrety: zmienione pliki, uruchomione polecenia,
wyniki testów, napotkane błędy. Ta część jest dla kogoś, kto będzie to sprawdzał.

Jeśli zadania NIE udało się wykonać, napisz to w **Sedno** wprost i wyjaśnij, na czym
stanęło. Sprawozdanie z nieudanej pracy jest warte więcej niż sprawozdanie zmyślone.
"""
