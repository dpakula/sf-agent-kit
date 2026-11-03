"""Konsola koordynatora: bloki Konsoli A, wiadomości ze wszystkich Organizacji, tagi spraw.

v0.1 (03.11.2026) - APro Agents / klaudiusz-general · SF-486 krok 2 (alfa Agaty jako koordynatora)

SKĄD TO SIĘ WZIĘŁO
══════════════════
Inwentarz SF-486 (wpis cdd47b1e): koordynator robił curlem 373 wywołania `/console/boxes` i 183
`/console/messages` w tydzień, plus 115 bloków przez `sf_box_sprawa` z biblioteki floty. Ten moduł
przenosi te drogi do Kita z ZACHOWANIEM bezpieczników biblioteki (1.12.0):

- **dedup kotwicy** — otwarty blok tego samego rodzaju z tą samą sprawą źródłową sprzed < 2 h
  oddajemy, zamiast zakładać drugi (#2358/#2359 z dwóch okien jednego koordynatora);
- **„Zastępuje …”** w treści zostaje tylko z numerem istniejącego bloku (`#N`); opis bez numeru
  wprowadzał człowieka w błąd („zastępuje wczorajszy” — który?);
- **etykieta opcji ≤ 80 znaków** — dłuższa = POST odrzucony w całości (25.10, dwa bloki nie powstały);
- **brak sprawy źródłowej = brak bloku** — kotwica „null” psuła PATCH statusu (SF-473);
- **lustro** — gdy kanał konsoli Organizacji sprawy jest wyłączony albo kotwica obca odpada,
  blok kotwiczy na sprawie kroku (`--krok`), a na sprawie źródłowej zostaje wpis `konsola`.

Wiadomości: dyspozycje człowieka z konsoli NIE mają adresata (tylko `session_target`), więc
`/console/messages/inbox` ich nie widzi. `inbox --wszystkie-org` czyta obie drogi w każdej
Organizacji klucza (równolegle — 13 Organizacji szeregowo to kilkanaście sekund).
"""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import asystent, flow
from .api import BladAPI, Klient

#: Okno dedupu bloków (godziny) — jak `SF_BOX_DEDUP_H` biblioteki.
DEDUP_H = 2.0
#: Sufit etykiety opcji po stronie SF (OpcjaIn) — dłuższa = 422 całego bloku.
ETYKIETA_MAX = 80
RODZAJE_BLOKU = ("action", "info", "uwaga")
#: Równoległość odczytu po Organizacjach. Więcej nie przyspiesza, a obciąża SF przy każdym /work.
WATKI = 8

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_ZASTEPUJE = re.compile(r"(^|[\s(·—])(?:[Zz]astępuje)\s+([^.;\n)]*)[.;)]?")


# ── pomocnicze ─────────────────────────────────────────────────────────────────

def _czas(wartosc) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(wartosc).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _krotko(tekst: str, ile: int = 100) -> str:
    jedna = " ".join(str(tekst or "").split())
    return jedna if len(jedna) <= ile else jedna[: ile - 1] + "…"


def numer_bloku(wskazanie: str) -> int | None:
    """`#2364` / `2364` → 2364; uuid i śmieci → None."""
    m = re.fullmatch(r"#?(\d+)", (wskazanie or "").strip())
    return int(m.group(1)) if m else None


def znajdz_blok(klient: Klient, wskazanie: str) -> dict:
    """Blok po numerze (`#2364`) albo identyfikatorze. `ValueError`, gdy go nie ma."""
    wskazanie = (wskazanie or "").strip()
    if _UUID.match(wskazanie):
        return klient.blok_konsoli(wskazanie)
    numer = numer_bloku(wskazanie)
    if numer is None:
        raise ValueError(f"nie rozumiem „{wskazanie}” — podaj numer bloku (#2364) albo jego id.")
    trafione = [b for b in klient.bloki(numer=numer, limit=5)
                if numer_bloku(str(b.get("numer") or "")) == numer]
    if not trafione:
        raise ValueError(f"nie ma bloku #{numer} w tej Organizacji (sprawdź --org).")
    return trafione[0]


def opcje_z_tresci(tresc: str) -> list[dict]:
    """„A) … · B) …” z treści → `[{klucz, etykieta, rekomendowana}]` (2–6 opcji, inaczej pusto).

    Ta sama reguła co biblioteka (22.10, Damian na #2078: „decyzyjny blok nie ma decyzji”).
    """
    out: list[dict] = []
    for segment in re.split(r"\s·\s|\n", tresc or ""):
        m = re.search(r"(?:^|[\s(—:])([A-Z]|T[0-9])\)\s*(.+)$", segment.strip())
        if not m:
            continue
        klucz, etykieta = m.group(1), m.group(2).strip(" .;")
        if len(etykieta) > 2 and klucz not in [o["klucz"] for o in out]:
            out.append({"klucz": klucz, "etykieta": etykieta[:ETYKIETA_MAX],
                        "rekomendowana": bool(re.search(r"rekomend|poleca", etykieta, re.I))})
    return out if 2 <= len(out) <= 6 else []


def opcje_z_argumentow(pary: list[str], rekomendowana: str | None) -> list[dict]:
    """`--opcja A="Tak, wdrażaj"` (powtarzalne) → opcje bloku. `ValueError` przy złym kształcie."""
    out = []
    for para in pary or []:
        klucz, _, etykieta = para.partition("=")
        klucz, etykieta = klucz.strip(), etykieta.strip()
        if not klucz or not etykieta:
            raise ValueError(f"--opcja „{para}”: oczekuję KLUCZ=etykieta")
        out.append({"klucz": klucz, "etykieta": etykieta[:ETYKIETA_MAX],
                    "rekomendowana": klucz == rekomendowana})
    if out and not 2 <= len(out) <= 6:
        raise ValueError("blok decyzyjny ma od 2 do 6 opcji")
    return out


def przytnij_zastepuje(klient: Klient, tresc: str) -> tuple[str, list[str]]:
    """„Zastępuje …” zostaje tylko z numerem ISTNIEJĄCEGO bloku. → (treść, ostrzeżenia)."""
    ostrzezenia: list[str] = []

    def tnij(m):
        numer = re.match(r"#(\d+)", m.group(2).strip())
        if numer:
            try:
                znajdz_blok(klient, numer.group(0))
                return m.group(0)
            except (ValueError, BladAPI):
                pass
        ostrzezenia.append(f"odcinam „{_krotko(m.group(0).strip(), 80)}” — nie wskazuje istniejącego bloku #N")
        return m.group(1)

    nowa = _ZASTEPUJE.sub(tnij, tresc)
    return re.sub(r"[ \t]{2,}", " ", nowa), ostrzezenia


def dubel(klient: Klient, *, rodzaj: str, sprawa_id: str, godzin: float = DEDUP_H,
          teraz: datetime | None = None) -> dict | None:
    """Otwarty blok tego rodzaju z tą samą kotwicą sprzed < `godzin` h — albo None."""
    granica = (teraz or datetime.now(timezone.utc)) - timedelta(hours=godzin)
    for b in klient.bloki(status="open", kind=rodzaj, anchor_id=sprawa_id, limit=50):
        if b.get("status") != "open" or b.get("kind") != rodzaj:
            continue
        if str((b.get("context_anchor") or {}).get("id") or "").lower() != sprawa_id.lower():
            continue
        t = _czas(b.get("created_at"))
        if t and t >= granica and b.get("numer"):
            return b
    return None


def _org_uuid(toz, wskazanie: str | None, domyslna: str) -> str:
    if not wskazanie:
        return domyslna
    if _UUID.match(wskazanie):
        return wskazanie.lower()
    org = toz.znajdz(wskazanie)
    if not org:
        raise ValueError(f"Organizacja „{wskazanie}” nie jest w zasięgu tego klucza (sprawdź `sf-kit whoami`).")
    return org.uuid


def _sprawa(klient_konsoli: Klient, toz, wskazanie: str, org_sprawy: str | None) -> tuple[str, str]:
    """(uuid sprawy, uuid jej Organizacji) z linku `?org=`, uuid albo numeru (z `--sprawa-org`)."""
    link = flow.sprawa_z_linku(wskazanie)
    if link:
        return link.lower(), _org_uuid(toz, flow.organizacja_z_linku(wskazanie) or org_sprawy,
                                       klient_konsoli.organizacja)
    org = _org_uuid(toz, org_sprawy, klient_konsoli.organizacja)
    sprawa = asystent.znajdz_sprawe(klient_konsoli.w_organizacji(org), wskazanie)
    return str(sprawa["id"]).lower(), org


# ── konsola blok ───────────────────────────────────────────────────────────────

def zaloz_blok(klient: Klient, toz, *, rodzaj: str, tresc: str, sprawa: str,
               sprawa_org: str | None = None, krok: str | None = None, priorytet: str = "med",
               effort: str | None = None, adresat_id: str | None = None, tytul: str | None = None,
               zastepuje: str | None = None, opcje: list[dict] | None = None,
               bez_dedupu: bool = False, dedup_h: float = DEDUP_H,
               log=lambda s: print(s, file=sys.stderr)) -> tuple[dict, bool]:
    """Załóż blok konsoli w Organizacji `klient`. → (blok, czy_nowy). Rzuca ValueError/BladAPI."""
    if rodzaj not in RODZAJE_BLOKU:
        raise ValueError(f"rodzaj bloku: {', '.join(RODZAJE_BLOKU)}")
    if not (tresc or "").strip():
        raise ValueError("pusta treść bloku — nic nie wysyłam")
    if not sprawa or sprawa.strip().lower() in ("null", "none", "undefined"):
        raise ValueError("brak sprawy źródłowej (--sprawa) — blok bez kotwicy nie powstaje (SF-473)")

    sprawa_id, org_sprawy = _sprawa(klient, toz, sprawa, sprawa_org)
    krok_id = None
    if krok and krok.strip().lower() not in ("null", "none", ""):
        krok_id, _ = _sprawa(klient, toz, krok, None)

    if not bez_dedupu:
        stary = dubel(klient, rodzaj=rodzaj, sprawa_id=sprawa_id, godzin=dedup_h)
        if stary:
            log(f"dubel: otwarty blok {stary.get('numer')} ({rodzaj}) z tą samą sprawą sprzed "
                f"< {dedup_h:g} h — oddaję go, nic nie wysyłam (--bez-dedupu = świadomie drugi)")
            return stary, False

    tresc, ostrzezenia = przytnij_zastepuje(klient, tresc)
    for o in ostrzezenia:
        log(o)
    if opcje is None:
        opcje = opcje_z_tresci(tresc)

    cialo: dict = {"kind": rodzaj, "priority": priorytet, "body": tresc}
    if adresat_id:
        cialo["assignee_user_id"] = adresat_id
    if opcje:
        cialo["opcje"] = opcje
    if rodzaj == "action" and effort:
        cialo["effort_tag"] = effort
    if tytul:
        cialo["tytul"] = tytul[:80]
    if zastepuje:
        stary = znajdz_blok(klient, zastepuje)
        cialo["zastepuje"] = str(stary.get("numer") or zastepuje)

    lustro = False
    if org_sprawy != klient.organizacja:
        lustro = klient.w_organizacji(org_sprawy).kanal_konsoli() is not True
        if lustro:
            log("kanał konsoli Organizacji sprawy wyłączony (albo nieznany) — kotwica na kroku + lustro")
    blok = None
    if not lustro:
        kotwica = {"type": "ticket", "id": sprawa_id, "tenant": org_sprawy}
        if krok_id:
            kotwica["krok_id"] = krok_id
        try:
            blok = klient.zaloz_blok({**cialo, "context_anchor": kotwica})
        except BladAPI as blad:
            if org_sprawy == klient.organizacja or getattr(blad, "kod", None) not in (403, 422):
                raise
            log(f"kotwica na sprawie źródłowej odrzucona ({getattr(blad, 'kod', '?')}) — kotwica na kroku + lustro")
            lustro = True
    if lustro:
        if not krok_id:
            raise ValueError("lustro potrzebuje sprawy kroku w Organizacji konsoli (--krok) — blok nie wysłany")
        blok = klient.zaloz_blok({**cialo, "context_anchor": {
            "type": "ticket", "id": krok_id, "tenant": klient.organizacja}})
        numer = blok.get("numer") or "?"
        try:
            klient.w_organizacji(org_sprawy).wpis(
                sprawa_id, f"**Blok konsoli {numer} (dla człowieka)** — odpowiedź tutaj albo w bloku.\n\n{tresc}",
                widocznosc="konsola")
        except BladAPI as blad:
            log(f"wpis-lustro na sprawie źródłowej NIE powstał: {blad}")
    if not (blok or {}).get("numer"):
        raise BladAPI("SF nie zwrócił numeru bloku")
    return blok, True


# ── wypisywanie ────────────────────────────────────────────────────────────────

def wiersz_bloku(b: dict) -> str:
    stan = b.get("status") or "?"
    if b.get("replied_at"):
        stan += ", odpowiedź" + ("" if b.get("reply_seen_at") else " NIEODEBRANA")
    tytul = b.get("tytul") or _krotko(b.get("body"), 90)
    return (f"{b.get('numer') or '?':>6}  {b.get('kind') or '?':<6} {b.get('priority') or '':<5} "
            f"[{stan}]  {tytul}")


def pokaz_blok(b: dict) -> str:
    wiersze = [wiersz_bloku(b), f"  id: {b.get('id')}   utworzony: {str(b.get('created_at'))[:16]}"
               f"   przez: {b.get('created_by') or '?'}"]
    if b.get("url"):
        wiersze.append(f"  {b['url']}")
    kotwica = b.get("context_anchor") or {}
    if kotwica:
        wiersze.append(f"  kotwica: {kotwica.get('type')} {kotwica.get('id')}"
                       f"{' · krok ' + str(kotwica['krok_id']) if kotwica.get('krok_id') else ''}")
    wiersze += ["", str(b.get("body") or "")]
    if b.get("opcje"):
        wiersze.append("\nOpcje: " + " · ".join(
            f"{o.get('klucz')}) {o.get('etykieta')}{' (rekomendowana)' if o.get('rekomendowana') else ''}"
            for o in b["opcje"] if isinstance(o, dict)))
    if b.get("replied_at"):
        wiersze += ["", f"Odpowiedź ({str(b.get('replied_at'))[:16]}, {b.get('replied_by') or '?'}"
                        f"{', opcja ' + str(b['wybrana']) if b.get('wybrana') else ''}):",
                    str(b.get("reply_body") or "(bez treści)")]
    return "\n".join(wiersze)


def _json(dane) -> str:
    return json.dumps(dane, ensure_ascii=False, indent=2, default=str)


# ── wiadomości ze wszystkich Organizacji ───────────────────────────────────────

def _kiedy(w: dict) -> str:
    """Czas wiadomości: `created_at` (console/messages) albo `utworzono` (skrzynka adresata)."""
    return str(w.get("created_at") or w.get("utworzono") or "")


def _wiadomosci_w_org(klient: Klient, org, slug: str) -> tuple[list[dict], str | None]:
    """Nieodebrane w jednej Organizacji: skrzynka adresata + dyspozycje na `session_target`."""
    k = klient.w_organizacji(org.uuid)
    znalezione: dict[str, dict] = {}
    bledy = []
    try:
        dane = k.skrzynka(tylko_nieodebrane=True, limit=50)
        for w in dane.get("wiadomosci") or []:
            mid = str(w.get("message_id") or w.get("id") or "")
            if mid and w.get("status") in ("new", "delivered", "failed"):
                znalezione[mid] = {**w, "id": mid, "_droga": "skrzynka"}
    except BladAPI as blad:
        if getattr(blad, "kod", None) not in (403, 422, 503):
            bledy.append(f"skrzynka: {blad}")
    if slug:
        try:
            for w in k.wiadomosci_konsoli(status="new", session_target=slug, limit=50):
                if w.get("session_target") == slug:
                    znalezione.setdefault(str(w.get("id")), {**w, "_droga": "dyspozycja"})
        except BladAPI as blad:
            if getattr(blad, "kod", None) != 403:
                bledy.append(f"dyspozycje: {blad}")
    lista = sorted(znalezione.values(), key=_kiedy)
    for w in lista:
        w["_org"] = org.slug
        w["_org_uuid"] = org.uuid
    return lista, ("; ".join(bledy) or None)


def wiadomosci_wszedzie(klient: Klient, toz, slug_domyslny: str) -> tuple[list[dict], list[str]]:
    """Nieodebrane wiadomości ze WSZYSTKICH Organizacji klucza. → (wiadomości, problemy)."""
    orgi = toz.z_nadaniami or toz.organizacje
    with ThreadPoolExecutor(max_workers=WATKI) as pula:
        wyniki = list(pula.map(
            lambda o: (o, _wiadomosci_w_org(klient, o, o.agent_slug or slug_domyslny)), orgi))
    wszystkie, problemy = [], []
    for org, (lista, blad) in wyniki:
        wszystkie += lista
        if blad:
            problemy.append(f"{org.slug}: {blad}")
    wszystkie.sort(key=_kiedy)
    return wszystkie, problemy


def wiersz_wiadomosci(w: dict) -> str:
    kotwica = w.get("anchor") or {}
    gdzie = kotwica.get("url") or kotwica.get("id") or ""
    return (f"[{_kiedy(w)[:16].replace('T', ' ')}] {w.get('_org', '?'):<16} "
            f"{w.get('_droga', ''):<10} {w.get('id')}\n    {_krotko(w.get('body'), 160)}"
            + (f"\n    → {gdzie}" if gdzie else ""))


def odbierz_wiadomosc(klient: Klient, toz, message_id: str, *, notka: str,
                      org_wskazana: str | None = None, slug: str = "",
                      mapa: dict | None = None) -> str:
    """Potwierdź odbiór jednej wiadomości (consumed + notka). → Organizacja, w której była.

    Organizację znajdujemy sami — koordynator ma ich kilkanaście. `mapa` (id → uuid Org) z listy
    nieodebranych (`wiadomosci_wszedzie`) wystarcza prawie zawsze; `GET /console/messages/{id}`
    adresatowi bywa niedostępny (403/404), więc jest tylko zapasem. Najpierw `/recipients/me`
    (wiadomość z adresatem), przy 404/422 `PATCH /console/messages/{id}` (dyspozycja bez adresata).
    """
    if org_wskazana:
        org = _org_uuid(toz, org_wskazana, klient.organizacja)
    else:
        if mapa is None:
            mapa = {str(w.get("id")): w["_org_uuid"] for w in wiadomosci_wszedzie(klient, toz, slug)[0]}
        org = mapa.get(message_id)
        if not org:
            def zna(o):
                try:
                    return o.uuid if klient.w_organizacji(o.uuid).wiadomosc_konsoli(message_id) else None
                except BladAPI:
                    return None
            with ThreadPoolExecutor(max_workers=WATKI) as pula:
                org = next((u for u in pula.map(zna, toz.z_nadaniami or toz.organizacje) if u), None)
        if not org:
            raise ValueError(f"wiadomości {message_id} nie ma wśród nieodebranych w Organizacjach tego klucza "
                             "(już odebrana? podaj --org)")
    k = klient.w_organizacji(org)
    try:
        k.potwierdz_odbior(message_id, status="consumed", powod=notka)
    except BladAPI as blad:
        if getattr(blad, "kod", None) not in (404, 422):
            raise
        k.zmien_wiadomosc(message_id, status="consumed", notka=notka)
    return org


# ── tagi ───────────────────────────────────────────────────────────────────────

def _bez_ogonkow(tekst: str) -> str:
    import unicodedata
    znormalizowany = unicodedata.normalize("NFKD", str(tekst or "")).replace("ł", "l").replace("Ł", "L")
    return "".join(z for z in znormalizowany if not unicodedata.combining(z)).casefold().strip()


def typy_wszystkie(klient: Klient) -> list[dict]:
    """Typy tagów z tagami: lista SF + grupy, których lista nie pokazuje (pełny odczyt, równolegle)."""
    typy = klient.typy_tagow()
    znane = {str(t.get("id")) for t in typy}
    try:
        brakujace = [tid for tid in klient.grupy_taksonomii() if tid not in znane]
    except BladAPI:
        brakujace = []

    def pelny(tid):
        try:
            return klient.typ_tagow(tid)
        except BladAPI:
            return None
    if brakujace:
        with ThreadPoolExecutor(max_workers=WATKI) as pula:
            typy += [t for t in pula.map(pelny, brakujace) if t and t.get("id")]
    return typy


def znajdz_typ(typy: list[dict], wskazanie: str) -> dict:
    klucz = _bez_ogonkow(wskazanie)
    trafione = [t for t in typy if klucz in (_bez_ogonkow(t.get("name")), _bez_ogonkow(t.get("slug")),
                                            str(t.get("id")).lower())]
    if not trafione:
        raise ValueError(f"nie ma typu tagów „{wskazanie}” (są: "
                         + ", ".join(str(t.get("name")) for t in typy) + ")")
    return trafione[0]


def znajdz_tag(typy: list[dict], wskazanie: str, *, typ: str | None = None) -> tuple[dict, dict]:
    """(tag, jego typ) po nazwie / wartości / id; `typ` zawęża. `ValueError` przy braku lub wieloznaczności."""
    zakres = [znajdz_typ(typy, typ)] if typ else typy
    klucz = _bez_ogonkow(wskazanie)
    trafione = [(g, t) for t in zakres for g in (t.get("tags") or [])
                if klucz in (_bez_ogonkow(g.get("name")), _bez_ogonkow(g.get("value")), str(g.get("id")).lower())]
    if not trafione:
        raise ValueError(f"nie ma tagu „{wskazanie}”{' w typie ' + typ if typ else ''} "
                         "(lista: `sf-kit tag lista`)")
    if len(trafione) > 1:
        raise ValueError(f"„{wskazanie}” pasuje do kilku tagów ("
                         + ", ".join(f"{t.get('name')}: {g.get('name')}" for g, t in trafione)
                         + ") — dodaj --typ")
    return trafione[0]


def nadaj_tag(klient: Klient, sprawa_id: str, tag: dict, typ: dict, *, zamien: bool = False) -> list[str]:
    """Nadaj tag sprawie. Typ jednokrotny z innym tagiem: odmowa, chyba że `zamien`. → co zrobiono."""
    # Przypisanie z SF: `{id: <id przypisania>, tag_id, tag: {id, tag_type_id, name, …}}`.
    obecne = [{**(g.get("tag") or {}), "id": str(g.get("tag_id") or (g.get("tag") or {}).get("id"))}
              for g in klient.tagi_sprawy(sprawa_id)]
    if any(g["id"] == str(tag["id"]) for g in obecne):
        return [f"sprawa ma już tag {typ.get('name')}: {tag.get('name')} — nic nie robię"]
    zrobione = []
    if not typ.get("is_multi", True):
        inne = [g for g in obecne if str(g.get("tag_type_id")) == str(typ.get("id"))]
        if inne and not zamien:
            raise ValueError(f"typ „{typ.get('name')}” przyjmuje jeden tag, a sprawa ma już: "
                             + ", ".join(str(g.get("name")) for g in inne) + " — dodaj --zamien")
        for g in inne:
            klient.zdejmij_tag(sprawa_id, g["id"])
            zrobione.append(f"zdjęty {typ.get('name')}: {g.get('name')}")
    klient.nadaj_tag(sprawa_id, str(tag["id"]))
    zrobione.append(f"nadany {typ.get('name')}: {tag.get('name')}")
    return zrobione


def sprawy_bez_tagu_typu(klient: Klient, typ: dict, *, wszystkie_statusy: bool = False,
                         limit: int = 200) -> tuple[list[dict], int | None]:
    """Sprawy bez ŻADNEGO tagu danego typu — filtr po stronie SF (`exclude_tags`), bez cache."""
    ids = [str(g["id"]) for g in (typ.get("tags") or []) if g.get("id")]
    filtry = {"sort_by": "created_at", "sort_dir": "desc"}
    if ids:
        filtry["exclude_tags"] = ",".join(ids)
    if not wszystkie_statusy:
        filtry["exclude_status"] = "resolved,closed"
    return klient.sprawy_filtrem(limit=limit, **filtry)
