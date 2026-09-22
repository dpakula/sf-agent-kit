"""Bramka: kod woła na kliencie TYLKO to, co klient naprawdę ma (i atrapy tego nie zasłonią).

v1.0.0 (22.09.2026) - APro Agents / borys-sf

DLACZEGO TA BRAMKA ISTNIEJE — INCYDENT, NIE OSTROŻNOŚĆ
═══════════════════════════════════════════════════════
19.09 worker wołał metodę, której `Klient` NIE MIAŁ. Testy były zielone, bo atrapa w teście tę
metodę miała, a w produkcji `AttributeError` połykał fail-soft — czyli ostrzeżenie o wygasającym
kluczu po prostu nigdy nie wychodziło. Opisane w README, §„Ograniczenia".

To jest ogólniejszy wzorzec i arek zgłosił dziś jego nawrót po swojej stronie (rozszerzenie
`Protocol` → atrapa implementująca go nie dostaje nowej metody, testy dalej zielone). **Atrapa
z definicji nie zapali tego rodzaju rozjazdu** — bo atrapa JEST tym, co się rozjeżdża. Dlatego
bramka nie pyta atrap, tylko czyta kod produkcyjny statycznie i porównuje go z prawdziwą klasą.

CO DOKŁADNIE PILNUJE
════════════════════
1. każde `klient.cokolwiek(...)` w `sf_kit/` ma odpowiednik w `api.Klient`;
2. atrapa dziedzicząca po `Klient` nie nadpisuje metody, której w `Klient` nie ma — taki
   „override" jest martwy (literówka w nazwie) i cicho testuje nie to, co się wydaje.

Run: pytest testy/test_bramka_klienta.py -v
"""
import ast
import inspect
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sf_kit.api import Klient  # noqa: E402

KORZEN = pathlib.Path(__file__).resolve().parents[1]

#: Nazwy zmiennych, pod którymi w kodzie mieszka klient SF.
NAZWY_KLIENTA = {"klient", "_klient"}

#: Metody wołane na obiekcie, który NIE jest klientem SF, mimo pasującej nazwy zmiennej.
#: Pusto — i dobrze; ten zbiór ma rosnąć wyłącznie z udokumentowanym powodem.
WYJATKI: set[str] = set()


def _metody_klienta() -> set[str]:
    return {n for n, _ in inspect.getmembers(Klient, predicate=inspect.isfunction)}


def _wywolania_na_kliencie() -> list[tuple[str, str, int]]:
    """`[(metoda, plik, linia)]` — wszystkie `klient.x(...)` i `self.klient.x(...)` w `sf_kit/`."""
    znalezione = []
    for plik in sorted((KORZEN / "sf_kit").rglob("*.py")):
        drzewo = ast.parse(plik.read_text(encoding="utf-8"), filename=str(plik))
        for w in ast.walk(drzewo):
            if not (isinstance(w, ast.Call) and isinstance(w.func, ast.Attribute)):
                continue
            cel = w.func.value
            nazwa_celu = None
            if isinstance(cel, ast.Name):
                nazwa_celu = cel.id
            elif isinstance(cel, ast.Attribute):
                nazwa_celu = cel.attr
            if nazwa_celu in NAZWY_KLIENTA:
                znalezione.append((w.func.attr, plik.name, w.lineno))
    return znalezione


def test_kod_wola_tylko_istniejace_metody_klienta():
    """SEDNO: to jest ten test, którego brak kosztował ciche wygaszenie ostrzeżeń 19.09.

    MUTACJA: dopisz w `cli.py` wywołanie `klient.metoda_ktorej_nie_ma()` — bramka czerwienieje,
    choćby wszystkie atrapy tę metodę miały.
    """
    istnieje = _metody_klienta()
    braki = [(m, p, l) for m, p, l in _wywolania_na_kliencie()
             if m not in istnieje and m not in WYJATKI and not m.startswith("_")]

    assert not braki, (
        "kod woła metody, których `api.Klient` nie ma — atrapa w teście tego NIE zapali:\n"
        + "\n".join(f"  {p}:{l} → klient.{m}()" for m, p, l in braki))


def test_wywolan_jest_ile_trzeba_czyli_bramka_naprawde_patrzy():
    """Bramka, która niczego nie znajduje, przechodzi także wtedy, gdy przestała szukać.

    Liczba jest luźnym progiem, nie dokładną wartością: ma złapać sytuację „parser przestał
    rozpoznawać wywołania", a nie zmuszać do jej podnoszenia przy każdym nowym poleceniu.
    """
    wywolania = _wywolania_na_kliencie()

    assert len(wywolania) >= 30, (
        f"bramka widzi tylko {len(wywolania)} wywołań na kliencie — wcześniej było ponad 50. "
        "Sprawdź, czy kod nie zmienił nazwy zmiennej albo czy parser nie przestał rozpoznawać "
        "wzorca; bramka, która nic nie znajduje, przechodzi zawsze.")


def test_atrapy_nie_nadpisuja_nieistniejacych_metod():
    """Martwy override = literówka, która cicho testuje nie to, co się wydaje.

    Atrapa dziedzicząca po `Klient` z metodą `wpisy_spray` (zamiast `wpisy_sprawy`) przechodzi
    wszystkie testy — bo prawdziwa metoda leci do prawdziwej implementacji, a ta w teście
    nie ma sieci. Objawem jest zwykle timeout, nigdy nazwa literówki.
    """
    istnieje = _metody_klienta()
    martwe = []
    for plik in sorted((KORZEN / "testy").rglob("*.py")):
        drzewo = ast.parse(plik.read_text(encoding="utf-8"), filename=str(plik))
        for w in ast.walk(drzewo):
            if not isinstance(w, ast.ClassDef):
                continue
            dziedziczy_po_kliencie = any(
                (isinstance(b, ast.Name) and b.id == "Klient")
                or (isinstance(b, ast.Attribute) and b.attr == "Klient")
                for b in w.bases)
            if not dziedziczy_po_kliencie:
                continue
            for element in w.body:
                if isinstance(element, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not element.name.startswith("_") and element.name not in istnieje:
                        martwe.append((w.name, element.name, plik.name, element.lineno))

    assert not martwe, (
        "atrapy nadpisują metody, których `Klient` nie ma (martwy override — pewnie literówka):\n"
        + "\n".join(f"  {p}:{l} → {klasa}.{metoda}()" for klasa, metoda, p, l in martwe))
