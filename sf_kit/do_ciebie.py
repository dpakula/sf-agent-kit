"""Sekcja „Do Ciebie” w `sf-kit sprawa` — otwarte bloki konsoli przy sprawie (SF-182).

v1.0.0 (01.10.2026) - APro Agents / borys-sf

Źródło: `GET /tickets/{id}/bloki-konsoli` (SF-182) — bloki przy sprawie, także z Konsoli A INNEJ
Organizacji (pytania koordynatora do człowieka, które do 01.10 nie było widać na samej sprawie).
Nie `GET /console/boxes`: tamta trasa wymaga `console:read` i widzi wyłącznie Organizację klucza.

„Do Ciebie” = zaadresowane do konta, którym pracuje ten Kit (serwer porównuje adresata z wołającym).
Gdy asystent pozna swojego człowieka (`pracuje_dla`, SF-170), dojdą bloki do człowieka.

Czysta funkcja formatująca — bez sieci; pobieranie i obsługę błędów robi `cli.polecenie_sprawa`.
"""
from __future__ import annotations

#: Ile bloków pokazujemy w sekcji; reszta jako liczba (sprawa bywa kotwicą dziesiątek boxów).
POKAZ = 10
DLUGOSC_TRESCI = 160

_RODZAJE = {"action": "decyzja", "info": "info", "uwaga": "uwaga", "dispatch": "dyspozycja"}


def _krotko(tekst: str | None, n: int = DLUGOSC_TRESCI) -> str:
    jednolinijkowo = " ".join((tekst or "").split())
    return jednolinijkowo if len(jednolinijkowo) <= n else jednolinijkowo[: n - 1].rstrip() + "…"


def _adres(link: str | None, *, baza: str, org: str | None) -> str:
    if not link:
        return ""
    adres = f"{baza.rstrip('/')}{link}" if link.startswith("/") else link
    if org and "org=" not in adres:
        adres += ("&" if "?" in adres else "?") + f"org={org}"
    return adres


def sekcja(do_mnie: dict | None, wszystkie_otwarte: dict | None, *, baza: str,
           org: str | None) -> str | None:
    """Tekst sekcji albo `None`, gdy nie ma czego pokazać (i nie ma czego zgłosić).

    `do_mnie is None` = serwer nie zna trasy (SF sprzed SF-182) — jedna linia wyjaśnienia zamiast
    „nic do Ciebie”, które byłoby twierdzeniem o stanie, którego nie znamy.
    """
    if do_mnie is None:
        return ("\nDo Ciebie: ta wersja SalesForge nie pokazuje jeszcze bloków konsoli przy sprawie "
                "(SF-182) — sprawdź Konsolę A.")
    moje = do_mnie.get("pozycje") or []
    razem_otwartych = (wszystkie_otwarte or {}).get("razem")
    inne = (razem_otwartych - len(moje)) if isinstance(razem_otwartych, int) else None
    if not moje and not inne:
        return None
    linie = [f"\nDo Ciebie — otwarte bloki konsoli: {len(moje)}"]
    for b in moje[:POKAZ]:
        rodzaj = _RODZAJE.get(b.get("rodzaj") or "", b.get("rodzaj") or "blok")
        skad = " · z Konsoli A innej Organizacji" if b.get("z_innej_organizacji") else ""
        ref = f"{b['ref']} " if b.get("ref") else ""
        linie.append(f"  • [{rodzaj}] {ref}{_krotko(b.get('tresc'))}{skad}")
        adres = _adres(b.get("link"), baza=baza, org=org)
        if adres:
            linie.append(f"    odpowiedz na osi tej sprawy: {adres}")
    if len(moje) > POKAZ:
        linie.append(f"  … i {len(moje) - POKAZ} kolejnych")
    if moje:
        linie.append("  odpowiedź z Kita: `sf-kit odpowiedz <sprawa> --blok <#numer> --opis -` (SF-185)")
    if inne:
        linie.append(f"  (otwartych bloków do innych osób przy tej sprawie: {inne})")
    return "\n".join(linie)
