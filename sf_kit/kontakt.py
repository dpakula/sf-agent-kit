"""Profil komunikacji kontaktu — `sf-kit kontakt` i migracja profili z LUDZIE.md / contacts.md (ADVERTPR-612).

v1.0.0 (04.11.2026) - APro Agents / borys-sf · kontrakt backend/docs/API-PROFIL-KOMUNIKACJI-KONTRAKT.md v0.2 (repo salesforge)

PO CO
═════
Damian 03.11: zasady komunikacji z każdą osobą (forma zwrotu, ton L1–L3, relacja, kanały, reguły szczególne) żyją
w SF na kontakcie, a nie w plikach floty. Agent czyta profil PRZED każdym mailem, wpisem publicznym, WhatsAppem
(`sf-kit kontakt pokaz ADRES`), a człowiek albo koordynator go zmienia (`sf-kit kontakt ustaw …`).

CO TU SIEDZI
Czyste funkcje bez sieci: zmiany z poleceń → ciało PATCH/POST, różnice „było → będzie”, parser plików Markdown
z profilami i plan migracji. Rozmowę z SF prowadzi `api.Klient`, polecenia — `cli`.

SŁOWNIKI
Lustro `app/modules/profile_komunikacji/slowniki.py` v1.1.0. Serwer i tak waliduje (422 z listą dozwolonych) —
kopia służy temu, żeby parser rozpoznał „na ty” albo „WhatsApp” i żeby `--sucho` złapał literówkę przed siecią.
Dopisanie wartości na serwerze bez dopisania tutaj = `--sucho` odmówi, a zapis wprost i tak przejdzie przez 422.

TON = poziom SZCZEROŚCI (L1 soft / L2 balanced / L3 frank), NIE formalności — ta żyje w `forma_zwrotu`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

RELACJE = ("zespol", "wspolnik", "klient", "dostawca", "partner", "inna")
FORMY_ZWROTU = ("ty", "pan", "pani", "panstwo")
TONY = ("L1", "L2", "L3")
KANALY = ("email", "sf", "telefon", "sms", "whatsapp", "signal", "teams")

#: Pola profilu, które Kit porównuje i zapisuje (kolejność = kolejność w raporcie). `reguly` osobno.
POLA = ("nazwa", "relacja", "relacja_opis", "forma_zwrotu", "zwrot", "ton", "jezyk", "kanal_preferowany",
        "kanaly_dozwolone", "notatki", "zrodlo", "ustalono_dnia", "party_id")

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_STRZALKA = re.compile(r"\s*(?:→|->|=>|⇒)\s*")


class BladProfilu(ValueError):
    """Zła wartość w poleceniu — komunikat dla człowieka, przed siecią."""


def to_uuid(wskazanie: str) -> bool:
    return bool(_UUID.match((wskazanie or "").strip()))


def normalizuj_email(adres: str) -> str:
    adres = (adres or "").strip().lower()
    if not _EMAIL.fullmatch(adres):
        raise BladProfilu(f"to nie jest adres e-mail: {adres!r}")
    return adres


# ── polecenie `ustaw`: zmiany → ciało ─────────────────────────────────────────────────────────────

def _ze_slownika(wartosc: str, slownik: tuple, pole: str) -> str | None:
    """Pusty napis = wyczyść pole (serwer zamienia go na null)."""
    wartosc = wartosc.strip()
    if pole == "ton":
        wartosc = wartosc.upper()
    if wartosc and wartosc not in slownik:
        raise BladProfilu(f"{pole}: dozwolone {', '.join(slownik)} (pusty napis czyści pole)")
    return wartosc or None


def regula_z_napisu(napis: str, *, zrodlo: str | None = None) -> dict:
    """„warunek => działanie” (albo →, ->). Bez strzałki — odmowa: reguła bez warunku to nie reguła."""
    czesci = _STRZALKA.split(napis.strip(), maxsplit=1)
    if len(czesci) != 2 or not czesci[0].strip() or not czesci[1].strip():
        raise BladProfilu(f"reguła musi mieć postać „warunek => działanie”: {napis!r}")
    regula = {"warunek": czesci[0].strip(), "dzialanie": czesci[1].strip(), "aktywna": True}
    if zrodlo:
        regula["zrodlo"] = zrodlo
    return regula


def _klucz_reguly(r: dict) -> tuple[str, str]:
    return (" ".join(str(r.get("warunek", "")).lower().split()), " ".join(str(r.get("dzialanie", "")).lower().split()))


def zmiany_z_polecenia(args, obecny: dict | None) -> dict:
    """Argumenty `kontakt ustaw` → słownik zmian (tylko pola, które człowiek podał).

    `obecny` = profil z serwera albo None (nowy). Reguły: `--regula` DOKŁADA do listy (bez dubli), `--zastap-reguly`
    zastępuje całą, `--usun-regule N` usuwa N-tą AKTYWNĄ — w numeracji, którą agent widzi w `kontakt pokaz`.
    """
    zmiany: dict = {}
    for pole, atrybut in (("nazwa", "nazwa"), ("relacja_opis", "relacja_opis"), ("zwrot", "zwrot"),
                          ("notatki", "notatki"), ("zrodlo", "zrodlo")):
        wartosc = getattr(args, atrybut, None)
        if wartosc is not None:
            zmiany[pole] = wartosc.strip() or None
    for pole, atrybut, slownik in (("relacja", "relacja", RELACJE), ("forma_zwrotu", "forma", FORMY_ZWROTU),
                                   ("ton", "ton", TONY), ("kanal_preferowany", "kanal", KANALY)):
        wartosc = getattr(args, atrybut, None)
        if wartosc is not None:
            zmiany[pole] = _ze_slownika(wartosc, slownik, pole)
    if getattr(args, "kanaly", None) is not None:
        lista = [k.strip().lower() for k in args.kanaly.split(",") if k.strip()]
        for k in lista:
            _ze_slownika(k, KANALY, "kanaly")
        zmiany["kanaly_dozwolone"] = list(dict.fromkeys(lista))
    if getattr(args, "jezyk", None) is not None:
        jezyk = args.jezyk.strip().lower()
        if not re.fullmatch(r"[a-z]{2}", jezyk):
            raise BladProfilu("jezyk: dwuliterowy kod, np. pl, en")
        zmiany["jezyk"] = jezyk
    if getattr(args, "ustalono", None) is not None:
        if args.ustalono.strip():
            try:
                zmiany["ustalono_dnia"] = date.fromisoformat(args.ustalono.strip()).isoformat()
            except ValueError:
                raise BladProfilu("ustalono: data RRRR-MM-DD") from None
        else:
            zmiany["ustalono_dnia"] = None
    if getattr(args, "party", None) is not None:
        party = args.party.strip()
        if party and not to_uuid(party):
            raise BladProfilu("party: uuid klienta z kartoteki SF (pusty napis odpina)")
        zmiany["party_id"] = party or None

    nowe = [regula_z_napisu(r) for r in (getattr(args, "regula", None) or [])]
    usun = getattr(args, "usun_regule", None) or []
    if nowe or usun or getattr(args, "zastap_reguly", False):
        reguly = [] if getattr(args, "zastap_reguly", False) else [dict(r) for r in (obecny or {}).get("reguly") or []]
        if usun:
            aktywne = [r for r in reguly if r.get("aktywna", True)]
            do_usuniecia = []
            for numer in usun:
                if not 1 <= numer <= len(aktywne):
                    raise BladProfilu(f"--usun-regule {numer}: profil ma {len(aktywne)} aktywnych reguł")
                do_usuniecia.append(id(aktywne[numer - 1]))
            reguly = [r for r in reguly if id(r) not in do_usuniecia]
        znane = {_klucz_reguly(r) for r in reguly}
        for r in nowe:
            if _klucz_reguly(r) not in znane:
                reguly.append(r)
                znane.add(_klucz_reguly(r))
        zmiany["reguly"] = reguly
    return zmiany


def sprawdz_kanaly(stan: dict) -> str | None:
    """To samo, co serwer sprawdza po scaleniu: preferowany musi być wśród dozwolonych (pusta lista = wszystkie)."""
    dozwolone = list(stan.get("kanaly_dozwolone") or [])
    pref = stan.get("kanal_preferowany")
    if dozwolone and pref and pref not in dozwolone:
        return f"kanał preferowany „{pref}” nie jest na liście dozwolonych ({', '.join(dozwolone)}) — serwer odmówi"
    return None


# ── różnice „było → będzie” ───────────────────────────────────────────────────────────────────────

def _pokaz_wartosc(wartosc) -> str:
    if wartosc is None or wartosc == "" or wartosc == []:
        return "—"
    if isinstance(wartosc, list):
        return ", ".join(str(w) for w in wartosc)
    tekst = str(wartosc).replace("\n", " ⏎ ")
    return tekst if len(tekst) <= 120 else tekst[:117] + "…"


def roznice(obecny: dict | None, zmiany: dict) -> list[str]:
    """Linie „pole: było → będzie” — tylko pola, które naprawdę się zmieniają."""
    obecny = obecny or {}
    linie = []
    for pole in POLA:
        if pole in zmiany and _pusty_na_none(obecny.get(pole)) != _pusty_na_none(zmiany[pole]):
            linie.append(f"{pole}: {_pokaz_wartosc(obecny.get(pole))} → {_pokaz_wartosc(zmiany[pole])}")
    if "reguly" in zmiany:
        przed = {_klucz_reguly(r): r for r in obecny.get("reguly") or []}
        po = {_klucz_reguly(r): r for r in zmiany["reguly"]}
        for k, r in po.items():
            if k not in przed:
                linie.append(f"reguła +: Gdy: {r['warunek']} → {r['dzialanie']}")
        for k, r in przed.items():
            if k not in po:
                linie.append(f"reguła −: Gdy: {r['warunek']} → {r['dzialanie']}")
    return linie


def _pusty_na_none(w):
    return None if w in ("", [], None) else w


def tylko_zmienione(obecny: dict | None, zmiany: dict) -> dict:
    """Zmiany bez pól, które już mają tę wartość — PATCH nie podbija wersji dla niczego."""
    obecny = obecny or {}
    wynik = {}
    for pole, wartosc in zmiany.items():
        if pole == "reguly":
            if [_klucz_reguly(r) for r in wartosc] != [_klucz_reguly(r) for r in obecny.get("reguly") or []] \
                    or [r.get("aktywna", True) for r in wartosc] != [r.get("aktywna", True)
                                                                    for r in obecny.get("reguly") or []]:
                wynik[pole] = wartosc
        elif _pusty_na_none(obecny.get(pole)) != _pusty_na_none(wartosc):
            wynik[pole] = wartosc
    return wynik


# ── parser plików z profilami (LUDZIE.md → PROFILE, contacts.md) ─────────────────────────────────

#: Etykieta z pliku (małe litery, bez ogonków) → pole profilu. Pliki pisali ludzie i agenci, więc synonimów sporo.
_ETYKIETY = {
    "email": "email", "e-mail": "email", "mail": "email", "adres": "email", "adres e-mail": "email",
    "imie": "nazwa", "imie i nazwisko": "nazwa", "nazwa": "nazwa", "osoba": "nazwa", "kto": "nazwa",
    "forma": "forma_zwrotu", "forma zwrotu": "forma_zwrotu", "zwracanie sie": "forma_zwrotu", "per": "forma_zwrotu",
    "zwrot": "zwrot", "wolacz": "zwrot", "jak sie zwracac": "zwrot", "powitanie": "zwrot",
    "ton": "ton", "poziom": "ton", "poziom szczerosci": "ton", "szczerosc": "ton",
    "relacja": "relacja", "kim jest": "relacja", "kim jest dla nas": "relacja", "rola": "relacja",
    "kanaly": "kanaly_dozwolone", "kanal": "kanaly_dozwolone", "kanaly dozwolone": "kanaly_dozwolone",
    "kontakt przez": "kanaly_dozwolone",
    "kanal preferowany": "kanal_preferowany", "preferowany kanal": "kanal_preferowany",
    "preferowany": "kanal_preferowany",
    "jezyk": "jezyk",
    "regula": "reguly", "reguly": "reguly", "reguly szczegolne": "reguly", "zasada": "reguly", "zasady": "reguly",
    "uwagi": "notatki", "notatki": "notatki", "notatka": "notatki", "inne": "notatki",
    "ustalono": "ustalono_dnia", "data": "ustalono_dnia", "ustalono dnia": "ustalono_dnia",
    "zrodlo": "zrodlo_ustalenia",
    "organizacja": "organizacja", "org": "organizacja",
}

_OGONKI = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def _bez_ogonkow(s: str) -> str:
    return s.translate(_OGONKI)


def _etykieta(s: str) -> str:
    s = re.sub(r"[*_`]", "", s).strip().rstrip(":").strip()
    return " ".join(_bez_ogonkow(s).lower().split())


_RELACJE_SLOWA = (("wspolni", "wspolnik"), ("zespol", "zespol"), ("pracowni", "zespol"), ("klient", "klient"),
                  ("dostawc", "dostawca"), ("partner", "partner"))
_KANALY_SLOWA = (("whatsapp", "whatsapp"), ("wa", "whatsapp"), ("e-mail", "email"), ("email", "email"),
                 ("mail", "email"), ("salesforge", "sf"), ("sf", "sf"), ("telefon", "telefon"), ("tel", "telefon"),
                 ("sms", "sms"), ("signal", "signal"), ("teams", "teams"))
_JEZYKI = {"polski": "pl", "angielski": "en", "niemiecki": "de", "ukrainski": "uk", "english": "en"}


@dataclass
class Osoba:
    """Profil wyczytany z pliku: pola gotowe do POST/PATCH + to, czego parser nie zrozumiał (do raportu)."""

    email: str
    zrodlo_pliku: str
    pola: dict = field(default_factory=dict)
    reguly: list = field(default_factory=list)
    nierozpoznane: list = field(default_factory=list)
    niejasne: list = field(default_factory=list)
    organizacja: str | None = None


def _forma(wartosc: str) -> tuple[str | None, str | None]:
    """„na ty („Michale”)” → ("ty", "Michale"); „per Pan” → ("pan", None)."""
    zwrot = None
    cytat = re.search(r"[„\"“']([^”\"“']+)[”\"“']", wartosc)
    if cytat:
        zwrot = cytat.group(1).strip()
    m = _bez_ogonkow(wartosc).lower()
    if re.search(r"\bna ty\b|\bty\b", m):
        return "ty", zwrot
    if "panstw" in m:
        return "panstwo", zwrot
    if re.search(r"\bpani\b", m):
        return "pani", zwrot
    if re.search(r"\bpan\b", m):
        return "pan", zwrot
    return None, zwrot


def _ton(wartosc: str) -> str | None:
    m = re.search(r"\bL\s?([123])\b", wartosc, re.I)
    if m:
        return f"L{m.group(1)}"
    w = _bez_ogonkow(wartosc).lower()
    for slowa, kod in ((("soft", "lagodn"), "L1"), (("balanced", "wywaz"), "L2"), (("frank", "wprost"), "L3")):
        if any(s in w for s in slowa):
            return kod
    return None


def _kanaly(wartosc: str) -> tuple[list[str], str | None]:
    """Lista kanałów + preferowany, gdy przy którymś stoi „preferowany”/„najlepiej”/„(pref)”."""
    wynik, pref = [], None
    for kawalek in re.split(r"[,;/+]|\bi\b|\boraz\b", wartosc):
        k = _bez_ogonkow(kawalek).lower().strip()
        if not k:
            continue
        for slowo, kod in _KANALY_SLOWA:
            if re.search(rf"(?<![a-z]){re.escape(slowo)}(?![a-z])", k):
                if kod not in wynik:
                    wynik.append(kod)
                if re.search(r"prefer|najlepiej|\bpref\b|glown", k):
                    pref = kod
                break
    return wynik, pref


def _data(wartosc: str) -> str | None:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", wartosc)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", wartosc)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return None


def _przypisz(osoba: Osoba, pole: str, wartosc: str, *, zrodlo_reguly: str) -> None:
    """Jedna para „etykieta: wartość” → pole profilu. Wartość, której nie umiemy przełożyć, trafia do `niejasne`."""
    wartosc = wartosc.strip()
    if not wartosc:
        return
    if pole == "nazwa":
        osoba.pola.setdefault("nazwa", wartosc[:200])
    elif pole == "forma_zwrotu":
        forma, zwrot = _forma(wartosc)
        if forma:
            osoba.pola["forma_zwrotu"] = forma
        else:
            osoba.niejasne.append(f"forma zwrotu: {wartosc}")
        if zwrot:
            osoba.pola.setdefault("zwrot", zwrot[:80])
    elif pole == "zwrot":
        forma, _ = _forma(wartosc)
        if forma and "forma_zwrotu" not in osoba.pola:
            osoba.pola["forma_zwrotu"] = forma
        cytat = re.search(r"[„\"“']([^”\"“']+)[”\"“']", wartosc)
        osoba.pola["zwrot"] = (cytat.group(1) if cytat else wartosc)[:80]
    elif pole == "ton":
        ton = _ton(wartosc)
        if ton:
            osoba.pola["ton"] = ton
        else:
            osoba.niejasne.append(f"ton: {wartosc}")
    elif pole == "relacja":
        w = _bez_ogonkow(wartosc).lower()
        kod = next((k for slowo, k in _RELACJE_SLOWA if slowo in w), None)
        osoba.pola["relacja"] = kod or "inna"
        opis = wartosc if (kod is None or len(wartosc.split()) > 1) else None
        if opis:
            osoba.pola["relacja_opis"] = opis[:300]
    elif pole == "kanaly_dozwolone":
        lista, pref = _kanaly(wartosc)
        if lista:
            osoba.pola["kanaly_dozwolone"] = lista
        else:
            osoba.niejasne.append(f"kanały: {wartosc}")
        if pref:
            osoba.pola.setdefault("kanal_preferowany", pref)
    elif pole == "kanal_preferowany":
        lista, _ = _kanaly(wartosc)
        if lista:
            osoba.pola["kanal_preferowany"] = lista[0]
        else:
            osoba.niejasne.append(f"kanał preferowany: {wartosc}")
    elif pole == "jezyk":
        w = _bez_ogonkow(wartosc).lower().strip()
        kod = _JEZYKI.get(w) or (w if re.fullmatch(r"[a-z]{2}", w) else None)
        if kod:
            osoba.pola["jezyk"] = kod
        else:
            osoba.niejasne.append(f"język: {wartosc}")
    elif pole == "reguly":
        try:
            osoba.reguly.append(regula_z_napisu(wartosc, zrodlo=zrodlo_reguly))
        except BladProfilu:
            osoba.niejasne.append(f"reguła bez „warunek → działanie”: {wartosc}")
    elif pole == "notatki":
        _dopisz_notatke(osoba, wartosc)
    elif pole == "ustalono_dnia":
        d = _data(wartosc)
        if d:
            osoba.pola["ustalono_dnia"] = d
        else:
            osoba.niejasne.append(f"data ustalenia: {wartosc}")
    elif pole == "zrodlo_ustalenia":
        osoba.pola["zrodlo_ustalenia"] = wartosc[:200]
    elif pole == "organizacja":
        osoba.organizacja = wartosc.strip().lower()


def _dopisz_notatke(osoba: Osoba, tekst: str) -> None:
    obecne = osoba.pola.get("notatki")
    osoba.pola["notatki"] = (f"{obecne}\n{tekst}" if obecne else tekst)[:5000]


def _sekcja_profile(tekst: str) -> tuple[str, bool]:
    """Fragment pod nagłówkiem zawierającym słowo PROFILE aż do nagłówka tego samego lub wyższego poziomu.
    Brak takiego nagłówka → cały plik (drugi element = False, raport to odnotuje)."""
    linie = tekst.splitlines()
    for i, linia in enumerate(linie):
        m = re.match(r"^(#{1,6})\s+(.*)$", linia)
        if m and re.search(r"\bPROFIL(E|E?S)?\b", m.group(2), re.I):
            poziom = len(m.group(1))
            koniec = len(linie)
            for j in range(i + 1, len(linie)):
                n = re.match(r"^(#{1,6})\s+", linie[j])
                if n and len(n.group(1)) <= poziom:
                    koniec = j
                    break
            return "\n".join(linie[i + 1:koniec]), True
    return tekst, False


def _tabela(linie: list[str], zrodlo: str, nazwa_pliku: str) -> list[Osoba]:
    """Tabela Markdown z nagłówkiem (kolumna z adresem obowiązkowa)."""
    naglowek = [_etykieta(k) for k in linie[0].strip().strip("|").split("|")]
    pola = [_ETYKIETY.get(k) for k in naglowek]
    if "email" not in pola:
        return []
    osoby = []
    for wiersz in linie[2:]:
        komorki = [k.strip() for k in wiersz.strip().strip("|").split("|")]
        email_k = komorki[pola.index("email")] if len(komorki) > pola.index("email") else ""
        m = _EMAIL.search(email_k)
        if not m:
            continue
        osoba = Osoba(email=m.group(0).lower(), zrodlo_pliku=nazwa_pliku)
        for pole, naz, wartosc in zip(pola, naglowek, komorki):
            if pole and pole != "email":
                if pole == "reguly":
                    for r in re.split(r"\s*(?:<br\s*/?>|;)\s*", wartosc):
                        _przypisz(osoba, pole, r, zrodlo_reguly=zrodlo)
                else:
                    _przypisz(osoba, pole, wartosc, zrodlo_reguly=zrodlo)
            elif not pole and wartosc:
                osoba.nierozpoznane.append(f"{naz}: {wartosc}")
        osoby.append(osoba)
    return osoby


def parsuj_profile(tekst: str, nazwa_pliku: str, *, tylko_sekcja_profile: bool) -> tuple[list[Osoba], list[str]]:
    """Plik Markdown → lista osób + uwagi dla raportu.

    Rozpoznaje dwa układy, bo formatu nikt nie spisał:
    1. blok osoby = nagłówek (### Imię Nazwisko <adres>) albo punkt pierwszego poziomu z adresem, pod nim linie
       `- Etykieta: wartość` (wcięte punkty pod „Reguły:” to kolejne reguły);
    2. tabela Markdown z kolumną adresu.
    Osoba bez adresu e-mail jest pomijana z uwagą — adres to klucz profilu w SF.
    """
    uwagi = []
    if tylko_sekcja_profile:
        tekst, znaleziona = _sekcja_profile(tekst)
        if not znaleziona:
            uwagi.append(f"{nazwa_pliku}: brak nagłówka z „PROFILE” — czytam cały plik")
    zrodlo = f"{nazwa_pliku} (migracja ADVERTPR-612)"
    osoby: list[Osoba] = []
    linie = tekst.splitlines()

    # Tabele najpierw — wycinamy je, żeby wiersze nie wróciły jako „nierozpoznane”.
    zostaja: list[str] = []
    i = 0
    while i < len(linie):
        if linie[i].lstrip().startswith("|") and i + 1 < len(linie) and re.match(r"^\s*\|?\s*:?-{3,}", linie[i + 1]):
            j = i
            while j < len(linie) and linie[j].lstrip().startswith("|"):
                j += 1
            osoby.extend(_tabela(linie[i:j], zrodlo, nazwa_pliku))
            i = j
            continue
        zostaja.append(linie[i])
        i += 1

    biezaca: Osoba | None = None
    w_regulach = False
    bez_adresu = 0
    for linia in zostaja:
        if not linia.strip():
            continue
        naglowek = re.match(r"^#{1,6}\s+(.*)$", linia)
        punkt = re.match(r"^(\s*)[-*+]\s+(.*)$", linia)
        wciecie = len(punkt.group(1)) if punkt else 0
        tresc = naglowek.group(1) if naglowek else (punkt.group(2) if punkt else linia.strip())
        adres = _EMAIL.search(tresc)
        etykieta_m = re.match(r"^\**([^:*]{1,40}?)\**\s*:\s*(.*)$", tresc)
        pole = _ETYKIETY.get(_etykieta(etykieta_m.group(1))) if etykieta_m else None

        # Nowa osoba: nagłówek albo punkt pierwszego poziomu z adresem, który NIE jest linią „E-mail: …”.
        if (naglowek or (punkt and wciecie == 0 and pole is None)) and adres:
            biezaca = Osoba(email=adres.group(0).lower(), zrodlo_pliku=nazwa_pliku)
            nazwa = re.sub(r"[<(\[]?" + re.escape(adres.group(0)) + r"[>)\]]?", "", tresc)
            nazwa = re.sub(r"[*_`]", "", nazwa).strip(" -—–:·,")
            if nazwa:
                biezaca.pola["nazwa"] = nazwa[:200]
            osoby.append(biezaca)
            w_regulach = False
            continue
        if naglowek:
            # Nagłówek bez adresu: nowa osoba, której adres może przyjść w linii „E-mail:”.
            biezaca = Osoba(email="", zrodlo_pliku=nazwa_pliku)
            biezaca.pola["nazwa"] = re.sub(r"[*_`]", "", naglowek.group(1)).strip()[:200]
            osoby.append(biezaca)
            w_regulach = False
            continue
        if biezaca is None:
            continue
        if pole == "email" and adres:
            biezaca.email = adres.group(0).lower()
            continue
        if pole == "reguly":
            w_regulach = True
            if etykieta_m.group(2).strip():
                _przypisz(biezaca, "reguly", etykieta_m.group(2), zrodlo_reguly=zrodlo)
            continue
        if w_regulach and punkt and wciecie > 0 and pole is None:
            _przypisz(biezaca, "reguly", tresc, zrodlo_reguly=zrodlo)
            continue
        w_regulach = False
        if pole:
            _przypisz(biezaca, pole, etykieta_m.group(2), zrodlo_reguly=zrodlo)
        else:
            biezaca.nierozpoznane.append(tresc.strip())

    wynik = []
    for o in osoby:
        if not o.email:
            bez_adresu += 1
            continue
        wynik.append(o)
    if bez_adresu:
        uwagi.append(f"{nazwa_pliku}: {bez_adresu} blok(ów) osób bez adresu e-mail — pominięte (adres = klucz profilu)")
    return wynik, uwagi


def scal_zrodla(glowne: list[Osoba], dodatkowe: list[Osoba]) -> tuple[dict[str, Osoba], list[str]]:
    """LUDZIE.md (główne) wygrywa z contacts.md; różna wartość tego samego pola = konflikt źródeł w raporcie.

    Ta sama osoba dwa razy w JEDNYM pliku też jest scalana (drugie wystąpienie dokłada brakujące pola)."""
    konflikty = []
    osoby: dict[str, Osoba] = {}
    for lista, wazniejsze in ((glowne, True), (dodatkowe, False)):
        for o in lista:
            if o.email not in osoby:
                osoby[o.email] = Osoba(email=o.email, zrodlo_pliku=o.zrodlo_pliku, pola=dict(o.pola),
                                       reguly=list(o.reguly), nierozpoznane=list(o.nierozpoznane),
                                       niejasne=list(o.niejasne), organizacja=o.organizacja)
                continue
            cel = osoby[o.email]
            if o.zrodlo_pliku not in cel.zrodlo_pliku:
                cel.zrodlo_pliku += f" + {o.zrodlo_pliku}"
            for pole, wartosc in o.pola.items():
                if pole not in cel.pola:
                    cel.pola[pole] = wartosc
                elif pole == "notatki" and wartosc not in cel.pola[pole]:
                    cel.pola[pole] = (cel.pola[pole] + "\n" + wartosc)[:5000]
                elif cel.pola[pole] != wartosc:
                    konflikty.append(f"{o.email} · {pole}: zostaje {_pokaz_wartosc(cel.pola[pole])!s} "
                                     f"({cel.zrodlo_pliku.split(' + ')[0]}), pomijam {_pokaz_wartosc(wartosc)} "
                                     f"({o.zrodlo_pliku})")
            znane = {_klucz_reguly(r) for r in cel.reguly}
            cel.reguly.extend(r for r in o.reguly if _klucz_reguly(r) not in znane)
            cel.nierozpoznane.extend(o.nierozpoznane)
            cel.niejasne.extend(o.niejasne)
            cel.organizacja = cel.organizacja or o.organizacja
    return osoby, konflikty


# ── plan migracji ────────────────────────────────────────────────────────────────────────────────

@dataclass
class Pozycja:
    """Jedna osoba w planie: co zrobić w SF i dlaczego."""

    email: str
    akcja: str                    # utworz | uzupelnij | bez_zmian | pomin
    zmiany: dict = field(default_factory=dict)
    roznice: list = field(default_factory=list)
    konflikty_z_sf: list = field(default_factory=list)
    uwagi: list = field(default_factory=list)
    profil_id: str | None = None
    wersja: int | None = None
    kontakt_w_sf: str = "nie sprawdzono"   # klient | członek | klient + członek | brak | nie sprawdzono


def _zmiany_z_osoby(osoba: Osoba) -> dict:
    zmiany = {k: v for k, v in osoba.pola.items() if k in POLA}
    if osoba.nierozpoznane:
        dopisek = "Z pliku (nierozpoznane przy migracji):\n" + "\n".join(f"- {n}" for n in osoba.nierozpoznane)
        zmiany["notatki"] = ((zmiany.get("notatki") + "\n\n") if zmiany.get("notatki") else "") + dopisek
        zmiany["notatki"] = zmiany["notatki"][:5000]
    zrodlo = osoba.zrodlo_pliku
    if osoba.pola.get("zrodlo_ustalenia"):
        zrodlo = f"{osoba.pola['zrodlo_ustalenia']} · {zrodlo}"
    zmiany["zrodlo"] = f"{zrodlo} (migracja ADVERTPR-612)"[:300]
    if osoba.reguly:
        zmiany["reguly"] = osoba.reguly
    return zmiany


def zaplanuj(osoba: Osoba, obecny: dict | None, *, nadpisz: bool = False) -> Pozycja:
    """Osoba z pliku + profil z SF (albo None) → pozycja planu.

    Zasada: SF jest źródłem prawdy od wdrożenia (03.11), więc wartość w SF, która różni się od pliku, NIE jest
    nadpisywana bez `--nadpisz` — trafia do konfliktów. Puste pole w SF = uzupełnij z pliku. Reguły dokładamy
    (bez dubli), nigdy nie usuwamy. `zrodlo` w istniejącym profilu zostaje.
    """
    zmiany = _zmiany_z_osoby(osoba)
    poz = Pozycja(email=osoba.email, akcja="utworz")
    poz.uwagi.extend(f"niejasne w pliku: {n}" for n in osoba.niejasne)
    if obecny is None:
        zmiany.setdefault("jezyk", "pl")
        poz.zmiany = zmiany
        poz.roznice = roznice(None, zmiany)
    else:
        poz.profil_id, poz.wersja = str(obecny.get("id")), obecny.get("wersja")
        do_zapisu: dict = {}
        for pole, wartosc in zmiany.items():
            if pole == "zrodlo":
                continue
            if pole == "reguly":
                znane = {_klucz_reguly(r) for r in obecny.get("reguly") or []}
                nowe = [r for r in wartosc if _klucz_reguly(r) not in znane]
                if nowe:
                    do_zapisu["reguly"] = list(obecny.get("reguly") or []) + nowe
                continue
            w_sf = _pusty_na_none(obecny.get(pole))
            if w_sf is None:
                do_zapisu[pole] = wartosc
            elif w_sf != _pusty_na_none(wartosc):
                poz.konflikty_z_sf.append(f"{pole}: w SF {_pokaz_wartosc(w_sf)} · w pliku {_pokaz_wartosc(wartosc)}")
                if nadpisz:
                    do_zapisu[pole] = wartosc
        poz.zmiany = do_zapisu
        poz.roznice = roznice(obecny, do_zapisu)
        poz.akcja = "uzupelnij" if do_zapisu else "bez_zmian"
    stan = {**(obecny or {}), **poz.zmiany}
    blad = sprawdz_kanaly(stan)
    if blad:
        poz.uwagi.append(blad)
    return poz


def odpowiada_organizacji(osoba: Osoba, slug: str, uuid: str) -> bool:
    """Osoba z jawnym „Organizacja: X” w pliku idzie tylko do tej Organizacji; bez wpisu — do wskazanej `--org`."""
    if not osoba.organizacja:
        return True
    return osoba.organizacja in {(slug or "").lower(), (uuid or "").lower()}


def wczytaj_plik(sciezka: str) -> str:
    return Path(sciezka).expanduser().read_text(encoding="utf-8")


def maskuj_email(adres: str) -> str:
    """m.hanajczyk@advertpro.co → m***@a***.co — do wpisu w SF (dane osobowe nie wychodzą z raportu)."""
    lokal, _, domena = adres.partition("@")
    czesci = domena.split(".")
    return f"{lokal[:1]}***@{czesci[0][:1]}***.{czesci[-1]}" if len(czesci) > 1 else f"{lokal[:1]}***@***"
