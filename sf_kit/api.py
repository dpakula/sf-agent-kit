"""Rozmowa z SalesForge. Wyłącznie biblioteka standardowa — zero `pip install`.

v0.1 (14.09.2026) - APro Agents / borys-sf

DLACZEGO `urllib`, A NIE `requests`
═══════════════════════════════════
Bo Kit ma się uruchomić u kogoś, kto nie zna ani nas, ani Pythona — u Codexa Damiana, u
pracownika Krzyśka, u Wójta Michała. Każda zależność to jedno miejsce, w którym uruchomienie
kończy się na `ModuleNotFoundError` zamiast na pracy. `urllib` jest brzydsze w użyciu i ta
brzydota siedzi w tym jednym pliku, żeby reszta Kitu jej nie widziała.

CO TEN MODUŁ ROBI Z BŁĘDAMI
Zamienia kody HTTP na wyjątki, które **mówią człowiekowi, co zrobić** — nie na `HTTPError:
403`. Worker chodzi bez nadzoru; komunikat „403" w logu o trzeciej w nocy nie pomoże nikomu,
a „brakuje uprawnienia tasks:own, poproś administratora" pomoże.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from . import WERSJA

#: Ile czekamy na odpowiedź. Minuta: `codex exec` bywa wolny, ale SAMO API nie ma prawa.
LIMIT_CZASU_S = 60

#: Osobny, dłuższy limit na wysyłkę załączników. Makieta HTML ze zrzutami to megabajty,
#: a zerwanie wysyłki w połowie zostawia sprawę z częścią plików.
LIMIT_CZASU_WYSYLKI_S = 300

#: Ile zadań bierzemy jednym pytaniem. 200 to sufit strony po stronie SalesForge — większa
#: liczba nie da większej strony, da 422.
NA_STRONE = 200

#: Bezpiecznik przeglądania, nie limit projektowy. Dwadzieścia stron to 4000 zadań; kolejka,
#: która tego nie mieści, potrzebuje filtru po stronie serwera, a nie kolejnej pętli u klienta.
STRON_NAJWYZEJ = 20


@dataclass
class WynikSzukania:
    """Zadania znalezione + ILE kolejki przy tym przejrzano.

    Dwie liczby obok listy, bo „nie masz zadań" i „przejrzałem 4000 z 6200 i nie znalazłem"
    to dwie różne wiadomości dla człowieka — a wyglądają identycznie, gdy oddaje się samą
    pustą listę. Obcięcie ma być widoczne.
    """

    zadania: list[dict] = field(default_factory=list)
    przejrzano: int = 0
    wszystkich: int = 0

    @property
    def urwane(self) -> bool:
        """Czy skończyliśmy na bezpieczniku, nie na końcu kolejki."""
        return self.przejrzano < self.wszystkich

    def __iter__(self):
        """Żeby `for z in wynik` i `list(wynik)` dawały zadania — wołający pyta o nie najczęściej."""
        return iter(self.zadania)

    def __len__(self) -> int:
        return len(self.zadania)

    def __bool__(self) -> bool:
        return bool(self.zadania)


class BladAPI(RuntimeError):
    """Błąd rozmowy z SF, z komunikatem pisanym do człowieka."""

    def __init__(self, wiadomosc: str, *, kod: int | None = None, szczegoly: str = ""):
        super().__init__(wiadomosc)
        self.kod = kod
        self.szczegoly = szczegoly


class BrakUprawnienia(BladAPI):
    """403 — klucz działa, ale nie wolno mu tej rzeczy. Ponawianie nic nie da."""


class ZlyKlucz(BladAPI):
    """401 — klucz nieznany, wygasły albo niewysłany. Ponawianie nic nie da."""


class Konflikt(BladAPI):
    """409 — ktoś zmienił obiekt przed nami. Pobierz od nowa i spróbuj raz jeszcze."""


class Klient:
    """Cienka warstwa nad `urllib`. Trzyma klucz i Organizację; nic nie zapisuje na dysk."""

    def __init__(self, *, baza: str, klucz: str, organizacja: str = ""):
        self.baza = baza.rstrip("/")
        self._klucz = klucz                  # podkreślenie: nie jest częścią interfejsu
        self.organizacja = organizacja

    def _naglowki(self) -> dict[str, str]:
        naglowki = {
            "Authorization": f"Bearer {self._klucz}",
            "Accept": "application/json",
            "User-Agent": f"sf-agent-kit/{WERSJA}",
        }
        # Nagłówek POMIJAMY, gdy Organizacji jeszcze nie znamy — a nie wysyłamy pustego.
        # `GET /me` działa bez niego od 15.09 (ADVERTPR-796) i to jest jedyny moment, w którym
        # Kit czyta cokolwiek przed wyborem Organizacji: pusty nagłówek znaczyłby dla serwera
        # „podaję Organizację i jest nią pustka", czyli 403 zamiast odpowiedzi.
        if self.organizacja:
            naglowki["X-Tenant-Id"] = self.organizacja
        return naglowki

    def _wywolaj(self, metoda: str, sciezka: str, *, cialo: dict | None = None) -> dict | list:
        adres = f"{self.baza}/api/v1/{sciezka.lstrip('/')}"
        dane = None
        naglowki = self._naglowki()
        if cialo is not None:
            dane = json.dumps(cialo, ensure_ascii=False).encode("utf-8")
            naglowki["Content-Type"] = "application/json"

        zadanie = urllib.request.Request(adres, data=dane, headers=naglowki, method=metoda)
        try:
            with urllib.request.urlopen(zadanie, timeout=LIMIT_CZASU_S) as odp:
                tresc = odp.read().decode("utf-8")
                return json.loads(tresc) if tresc else {}
        except urllib.error.HTTPError as blad:
            tresc = ""
            try:
                tresc = blad.read().decode("utf-8", errors="replace")[:500]
            except Exception:                      # noqa: BLE001 — treść błędu jest dodatkiem
                pass
            raise self._na_wyjatek(blad.code, metoda, sciezka, tresc) from None
        except urllib.error.URLError as blad:
            raise BladAPI(
                f"nie mogę połączyć się z {self.baza} ({blad.reason}). "
                f"Sprawdź adres i sieć — to nie jest problem z kluczem.") from None

    @staticmethod
    def _na_wyjatek(kod: int, metoda: str, sciezka: str, tresc: str) -> BladAPI:
        """Kod HTTP → wyjątek z instrukcją. Treść odpowiedzi dokładamy, ale nie liczymy na nią.

        Uwaga: `tresc` pochodzi z serwera i MOŻE zawierać wartość pola, które odrzucił walidator
        (422 potrafi wydrukować to, co przysłaliśmy). Dlatego wołający nie powinien wrzucać jej
        do wpisu na sprawie bez zastanowienia — jest tu dla człowieka przy terminalu.
        """
        gdzie = f"{metoda} /{sciezka.lstrip('/')}"
        if kod == 401:
            return ZlyKlucz(
                "klucz nie został przyjęty (401). Uruchom `sf-kit init` i wpisz go jeszcze raz; "
                "jeśli dalej nie działa, poproś administratora o nowy — ten mógł zostać odwołany.",
                kod=kod, szczegoly=tresc)
        if kod == 403:
            podpowiedz = ""
            if "/tasks/" in gdzie and metoda == "PATCH":
                # Dwie możliwe przyczyny i obie warto wymienić: „brak uprawnienia" i „to nie
                # twoje zadanie" wyglądają tak samo w kodzie odpowiedzi, a naprawia się je
                # zupełnie inaczej — jedną prosi się administratora, drugą sprawdza u siebie.
                podpowiedz = (" Przy zmianie statusu zadania znaczy to jedno z dwojga: brak "
                              "uprawnienia `tasks:own` (nadawanego na członkostwie — README §2) "
                              "albo to zadanie nie jest przypisane do ciebie.")
            return BrakUprawnienia(
                f"nie wolno ci tej operacji ({gdzie}, 403).{podpowiedz}", kod=kod, szczegoly=tresc)
        if kod == 404:
            return BladAPI(
                f"nie ma takiego obiektu albo nie masz do niego dostępu ({gdzie}, 404). "
                f"Te dwie rzeczy wyglądają tak samo celowo.", kod=kod, szczegoly=tresc)
        if kod == 409:
            return Konflikt(
                f"ktoś zmienił ten obiekt przed tobą ({gdzie}, 409). Pobierz go od nowa.",
                kod=kod, szczegoly=tresc)
        if kod == 422:
            return BladAPI(
                f"wysłałem coś w złym kształcie ({gdzie}, 422). Odpowiedź mówi, którego pola "
                f"brakuje: {tresc}", kod=kod, szczegoly=tresc)
        if kod == 429 or kod >= 500:
            return BladAPI(
                f"serwer nie dał rady ({gdzie}, {kod}). To nie jest twoja wina — odczekaj "
                f"i spróbuj później.", kod=kod, szczegoly=tresc)
        return BladAPI(f"nieoczekiwana odpowiedź ({gdzie}, {kod}): {tresc}",
                       kod=kod, szczegoly=tresc)

    # ── zadania ──────────────────────────────────────────────────────────────

    def zadania(self, *, status: str = "queued", limit: int = 50,
                offset: int = 0) -> dict:
        """Jedna STRONA zadań agentów o danym statusie. Bez zawężenia do mnie.

        Oddaje całą odpowiedź serwera (`items`, `total`, `offset`), a nie samą listę: bez
        `total` wołający nie ma jak odróżnić „to wszystko" od „tyle zmieściło się na stronie".
        """
        zapytanie = urllib.parse.urlencode(
            {"assignee_kind": "agent", "status": status, "limit": limit, "offset": offset})
        odp = self._wywolaj("GET", f"tasks?{zapytanie}")
        return odp if isinstance(odp, dict) else {"items": [], "total": 0}

    def moje_zadania(self, *, slug: str, status: str = "queued",
                     ile_najwyzej: int | None = None) -> WynikSzukania:
        """Moje zadania — odsiane PO STRONIE KLIENTA, ale przez CAŁĄ kolejkę.

        SalesForge nie ma dziś filtru „zadania agenta o slugu X": parametr `assignee` przyjmuje
        wewnętrzny numer konta, którego posiadacz klucza nie zna. To jest OBEJŚCIE i tak jest
        opisane w README — nie funkcja. Filtr po stronie serwera jest zgłoszony jako osobna
        potrzeba (README, „Ograniczenia wersji 0.2").

        DLACZEGO STRONICOWANIE, A NIE WIĘKSZY `limit`
        ══════════════════════════════════════════════
        Wersja 0.1 pytała o pierwsze 50 zadań i odsiewała je u siebie. Przy 518 zadaniach
        w kolejce oznaczało to, że agent, którego zadanie stoi na pozycji 51 albo dalszej,
        **nigdy go nie zobaczy** — a worker wygląda wtedy na bezczynnego, nie na zepsutego.
        To jest najgorszy rodzaj usterki: cisza, którą łatwo wziąć za spokój.

        Sufit strony po stronie SF to 200, więc bierzemy po 200 i idziemy `offset`-em aż do
        `total` albo do znalezienia tego, po co przyszliśmy (`ile_najwyzej`). Worker potrzebuje
        JEDNEGO zadania, więc zwykle kończy na pierwszej stronie.

        `STRON_NAJWYZEJ` jest bezpiecznikiem na wypadek kolejki, która rośnie szybciej, niż ją
        czytamy — a nie limitem projektowym. Gdy się o niego obijemy, wynik mówi o tym wprost
        (`urwane`), bo przeszukanie części kolejki i przeszukanie całej dają ten sam wygląd:
        „brak zadań".
        """
        zebrane: list[dict] = []
        przejrzano = 0
        wszystkich = 0

        for _ in range(STRON_NAJWYZEJ):
            strona = self.zadania(status=status, limit=NA_STRONE, offset=przejrzano)
            pozycje = strona.get("items") or []
            wszystkich = int(strona.get("total") or 0)
            przejrzano += len(pozycje)

            zebrane.extend(z for z in pozycje
                           if (z.get("assigned_agent_slug") or "") == slug)

            if ile_najwyzej is not None and len(zebrane) >= ile_najwyzej:
                return WynikSzukania(zebrane[:ile_najwyzej], przejrzano, wszystkich)
            # Pusta strona kończy przeglądanie także wtedy, gdy `total` kłamie — inaczej
            # jedno przekłamanie licznika po stronie serwera dałoby dwadzieścia pustych pytań.
            if not pozycje or przejrzano >= wszystkich:
                break

        return WynikSzukania(zebrane, przejrzano, wszystkich)

    def zadanie(self, task_id: str) -> dict:
        return self._wywolaj("GET", f"tasks/{task_id}")

    def ustaw_status(self, task_id: str, status: str, *, wersja: int | None = None) -> dict:
        """Zmiana statusu zadania. **Wymaga `tasks:own`** (ADVERTPR-778) — bez niego 403.

        `tasks:own` działa wyłącznie na zadaniu, którego jesteś wykonawcą, i wyłącznie na
        statusie. Prowadzący pracę ma szersze `plans:write`; worker go nie potrzebuje i nie
        powinien dostać, bo niesie kasowanie cudzych zadań.

        `wersja` (OCC) podawana, gdy ją znamy: serwer odrzuci zmianę, jeśli ktoś ruszył zadanie
        w międzyczasie. Lepszy konflikt niż ciche nadpisanie cudzej decyzji.
        """
        cialo: dict = {"status": status}
        if wersja is not None:
            cialo["version"] = wersja
        return self._wywolaj("PATCH", f"tasks/{task_id}", cialo=cialo)

    # ── sprawy: profil AUTOR (v0.3) ──────────────────────────────────────────

    def zaloz_sprawe(self, *, tytul: str, opis: str, priorytet: str = "medium",
                     kategoria: str | None = None,
                     obserwatorzy: list[str] | None = None) -> dict:
        """Nowa sprawa w Organizacji klucza. Wymaga `tickets:write`.

        `obserwatorzy` to identyfikatory KONT (nie adresy) — SalesForge sprawdza przy tym
        członkostwo w tej Organizacji. Podajemy ich jawnie, bo backend przy kluczu API
        **nie dopisuje nikogo poza samym autorem** (`create_ticket`: „skip for API key").
        Sprawa założona przez agenta spoza floty bez obserwujących nie powiadomiłaby nikogo —
        czyli leżałaby, wyglądając na zgłoszoną.
        """
        cialo: dict = {"title": tytul, "description": opis, "priority": priorytet}
        if kategoria:
            cialo["category"] = kategoria
        if obserwatorzy:
            cialo["watcher_user_ids"] = list(obserwatorzy)
        return self._wywolaj("POST", "tickets", cialo=cialo)

    def sprawy(self, *, limit: int = 50) -> list[dict]:
        """Sprawy widoczne dla tego klucza w jego Organizacji."""
        zapytanie = urllib.parse.urlencode({"limit": limit})
        odp = self._wywolaj("GET", f"tickets?{zapytanie}")
        if isinstance(odp, dict):
            return odp.get("items") or odp.get("pozycje") or []
        return odp if isinstance(odp, list) else []

    def wpis_z_plikami(self, ticket_id: str, tresc: str | None, pliki: list,
                       *, widocznosc: str = "internal") -> dict:
        """JEDEN wpis z N plikami — i jedno powiadomienie dla obserwujących.

        Trasa `/entries/with-attachments` istnieje dokładnie po to: wgranie dwunastu plików
        po jednym dało kiedyś dwanaście wpisów i dwanaście maili w piętnaście sekund. Kit ma
        z tej lekcji korzystać, a nie powtarzać ją po swojej stronie.

        Pliki sprawdzamy PRZED wysłaniem (`multipart.sprawdz_pliki`): paczka odrzucona w połowie
        zostawiłaby sprawę z częścią załączników.
        """
        from . import multipart

        gotowe = multipart.sprawdz_pliki([str(p) for p in pliki])
        cialo, typ = multipart.zloz(
            {"content": tresc or "", "entry_type": "note",
             "is_internal": "true" if widocznosc == "internal" else "false"},
            gotowe,
        )
        return self._wywolaj_surowo(
            "POST", f"tickets/{ticket_id}/entries/with-attachments",
            dane=cialo, typ_tresci=typ)

    def _wywolaj_surowo(self, metoda: str, sciezka: str, *, dane: bytes,
                        typ_tresci: str) -> dict:
        """Żądanie z gotowym ciałem (multipart). Osobne od `_wywolaj`, które składa JSON.

        Limit czasu jest tu WIĘKSZY: paczka plików idzie dłużej niż zapytanie o listę,
        a zerwanie wysyłki w połowie jest gorsze niż czekanie.
        """
        adres = f"{self.baza}/api/v1/{sciezka.lstrip('/')}"
        naglowki = self._naglowki()
        naglowki["Content-Type"] = typ_tresci
        zadanie = urllib.request.Request(adres, data=dane, headers=naglowki, method=metoda)
        try:
            with urllib.request.urlopen(zadanie, timeout=LIMIT_CZASU_WYSYLKI_S) as odp:
                tresc = odp.read().decode("utf-8")
                return json.loads(tresc) if tresc else {}
        except urllib.error.HTTPError as blad:
            tresc = ""
            try:
                tresc = blad.read().decode("utf-8", errors="replace")[:500]
            except Exception:                      # noqa: BLE001
                pass
            raise self._na_wyjatek(blad.code, metoda, sciezka, tresc) from None
        except urllib.error.URLError as blad:
            raise BladAPI(
                f"nie mogę połączyć się z {self.baza} ({blad.reason}). "
                f"Sprawdź adres i sieć — to nie jest problem z kluczem.") from None

    # ── sprawy ───────────────────────────────────────────────────────────────

    def wpis(self, ticket_id: str, tresc: str, *, widocznosc: str = "internal") -> dict:
        """Wpis na sprawie — tak zdajesz sprawozdanie.

        `internal` domyślnie i celowo: treści, której klient nie miał zobaczyć, nie da się
        odzobaczyć. `public` zostaje świadomą decyzją wołającego.
        """
        return self._wywolaj(
            "POST", f"tickets/{ticket_id}/entries",
            cialo={"entry_type": "note", "content": tresc, "visibility": widocznosc})

    # ── sonda ────────────────────────────────────────────────────────────────

    def komentarz_zadania(self, task_id: str, tresc: str, *, wewnetrzny: bool = True) -> dict:
        """Komentarz pod ZADANIEM (nie pod sprawą). Ostatnia deska ratunku dla wyniku.

        Zadanie bez sprawy nie ma osi, na której dałoby się zdać sprawozdanie — a praca bywa
        już zrobiona. Komentarz jest wtedy jedynym miejscem, gdzie wynik zostaje; worker mówi
        wprost, że to NIE jest ślad na żadnej sprawie, żeby nikt nie szukał go później na osi.
        """
        return self._wywolaj(
            "POST", f"tasks/{task_id}/comments",
            cialo={"content": tresc, "is_internal": wewnetrzny})

    def kim_jestem(self) -> dict:
        """`GET /me` — konto, klucz i WSZYSTKIE Organizacje z efektywnymi uprawnieniami.

        Działa BEZ nagłówka Organizacji (ADVERTPR-796) i to jest cała wartość tej trasy dla
        Kitu: agent czyta ją, **zanim** wie, co miałby w tym nagłówku wpisać. Do 15.09 jedyną
        odpowiedzią na „kim jestem" była próba odczytu zadań — czyli zgadywanie po skutku.

        Uprawnienia liczy po tamtej stronie ta sama funkcja, co bramka żądań, więc to, co tu
        widać, jest tym, co naprawdę przejdzie. Kit ma prawo na tym polegać przy ukrywaniu
        poleceń; nie ma prawa polegać na tym przy decyzjach o bezpieczeństwie — te zapadają
        po stronie serwera i tak.
        """
        return self._wywolaj("GET", "me")

    def sprawdz_klucz(self) -> dict:
        """Czy klucz żyje i co nim wolno. Namiastka „kim jestem", którego SF nie ma.

        Sprawdzamy PRÓBUJĄC, a nie pytając o metadane — bo pytać nie ma gdzie, a poza tym
        próba mówi prawdę także wtedy, gdy metadane by kłamały (uprawnienie może istnieć
        na kluczu i nie działać, jeśli bramka patrzy na coś innego).

        Zmiany statusu NIE próbujemy naprawdę — sondowanie uprawnienia przez zepsucie cudzego
        zadania byłoby gorsze niż niewiedza. Mówimy wprost, że tego nie sprawdziliśmy.
        """
        wynik: dict = {"adres": self.baza, "organizacja": self.organizacja}
        try:
            strona = self.zadania(limit=1)
            wynik["odczyt_zadan"] = "działa"
            wynik["zadan_widocznych"] = str(strona.get("total") or 0)
        except BladAPI as blad:
            wynik["odczyt_zadan"] = f"NIE DZIAŁA — {blad}"
        return wynik
