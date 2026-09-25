"""Składanie `multipart/form-data` ręcznie — bo Kit nie ma `requests` (v0.3, profil ASYSTENT).

v0.3 (15.09.2026) - APro Agents / borys-sf

DLACZEGO RĘCZNIE
════════════════
Załączniki to jedyne miejsce, w którym `urllib` naprawdę boli: nie umie `multipart/form-data`
i trzeba złożyć ciało żądania bajt po bajcie. Kuszące byłoby dołożyć `requests` właśnie tutaj —
i to byłby koniec zasady, na której stoi cały Kit: **żadnych zależności**, bo uruchamia go ktoś,
kto nie zna Pythona, i każde `pip install` to jedno miejsce, w którym praca kończy się na
`ModuleNotFoundError`. Sto linii brzydoty w jednym pliku jest tańsze niż jedna zależność
u kogoś, kto nie wie, co z nią zrobić.

CO TU SIEDZI, A CZEGO NIE MA
Składanie ciała i rozpoznanie typu pliku po rozszerzeniu. Wysyłką zajmuje się `api.Klient` —
ten moduł nie zna ani adresu, ani klucza i nie ma jak niczego wysłać sam.
"""
from __future__ import annotations

import mimetypes
import secrets
from pathlib import Path

#: Domyślny typ dla pliku, którego nie rozpoznajemy. „Strumień bajtów" jest uczciwy —
#: zgadnięty `text/html` przy pliku, który nim nie jest, myliłby odbiorcę po drugiej stronie.
TYP_NIEZNANY = "application/octet-stream"

#: Typy, których `mimetypes` nie zna albo zna źle na części systemów. Lista jest krótka
#: z rozmysłem: dopisujemy tylko to, co realnie wysyłają ludzie robiący makiety.
TYPY_UZUPELNIENIE = {
    ".md": "text/markdown",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
}


def typ_pliku(sciezka: Path | str) -> str:
    """MIME po rozszerzeniu. Nie zaglądamy do środka pliku — serwer i tak sprawdza sam."""
    p = Path(sciezka)
    uzupelnienie = TYPY_UZUPELNIENIE.get(p.suffix.lower())
    if uzupelnienie:
        return uzupelnienie
    zgadniety, _ = mimetypes.guess_type(p.name)
    return zgadniety or TYP_NIEZNANY


def bezpieczna_nazwa(nazwa: str) -> str:
    """Nazwa pliku nadająca się do nagłówka `Content-Disposition`.

    Cudzysłów i znaki nowej linii w nazwie pliku rozbijają nagłówek — pierwszy kończy pole
    w połowie, drugi pozwala dopisać własne nagłówki do żądania. To jest ta sama klasa błędu
    co wstrzyknięcie do zapytania, tylko w innym protokole, i dlatego nie „poprawiamy" tego
    ucieczką, lecz wycinamy znak.

    Spacje ZOSTAJĄ. Wcześniejsze narzędzie do załączników wymagało nazw bez spacji i to była
    jego wada, nie wymóg formatu: człowiek nie ma zmieniać nazw swoich plików, żeby dało się
    je wysłać.
    """
    czysta = nazwa.replace('"', "").replace("\\", "").replace("\r", "").replace("\n", "")
    czysta = czysta.strip()
    return czysta or "plik"


def zloz(pola: dict[str, str], pliki: list[Path | str],
         *, nazwa_pola_plikow: str = "files") -> tuple[bytes, str]:
    """`(ciało, nagłówek Content-Type)` dla `multipart/form-data`.

    `pola` idą jako zwykłe pola formularza, `pliki` — wszystkie pod TYM SAMYM nazwiskiem pola
    (`files`), bo tego oczekuje trasa „wpis z paczką plików". To nie jest szczegół: wysłanie
    plików osobnymi żądaniami dałoby osobny wpis na każdy z nich, a obserwujący sprawę —
    osobnego maila na każdy. Dokładnie tak powstało kiedyś dwanaście maili w piętnaście sekund.

    Granicę losujemy kryptograficznie, nie ze znacznika czasu: granica, która trafi się
    wewnątrz treści pliku, rozcina żądanie w przypadkowym miejscu, a błąd jest wtedy nie
    do odtworzenia.
    """
    granica = "----sfkit" + secrets.token_hex(16)
    czesci: list[bytes] = []

    for nazwa, wartosc in pola.items():
        if wartosc is None:
            continue
        czesci.append(
            f"--{granica}\r\n"
            f'Content-Disposition: form-data; name="{nazwa}"\r\n\r\n'
            f"{wartosc}\r\n".encode("utf-8")
        )

    for sciezka in pliki:
        p = Path(sciezka)
        zawartosc = p.read_bytes()
        czesci.append(
            f"--{granica}\r\n"
            f'Content-Disposition: form-data; name="{nazwa_pola_plikow}"; '
            f'filename="{bezpieczna_nazwa(p.name)}"\r\n'
            f"Content-Type: {typ_pliku(p)}\r\n\r\n".encode("utf-8")
        )
        czesci.append(zawartosc)
        czesci.append(b"\r\n")

    czesci.append(f"--{granica}--\r\n".encode("utf-8"))
    return b"".join(czesci), f"multipart/form-data; boundary={granica}"


#: Typy, które SalesForge przyjmuje jako załącznik (stan na 15.09.2026, `ALLOWED_MIME_TYPES`).
#: Lista jest po stronie serwera i to on rozstrzyga — tu jest po to, żeby POWIEDZIEĆ CZŁOWIEKOWI
#: PRZED wysyłką, zamiast pozwolić mu czekać na odmowę.
TYPY_PRZYJMOWANE = {
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain", "text/csv", "text/markdown",
    "application/zip", "application/x-zip-compressed",
}

#: Czego najczęściej próbuje ktoś robiący makiety — i co z tym zrobić. HTML jest tu pierwszy
#: nie przypadkiem: to jest DOKŁADNIE to, co osoba z ForMarketing ma wysyłać, a serwer tego
#: nie przyjmuje. Spakowana makieta przechodzi i jest przy okazji lepsza, bo makieta to
#: zwykle kilka plików (HTML + CSS + obrazy), a nie jeden.
PODPOWIEDZI = {
    "text/html": "spakuj makietę do `.zip` — wtedy przejdzie w całości, razem z CSS i obrazami",
    "text/javascript": "spakuj do `.zip`",
    "application/javascript": "spakuj do `.zip`",
    "text/css": "spakuj do `.zip`",
    "application/json": "zmień rozszerzenie na `.txt` albo spakuj do `.zip`",
}


def sprawdz_typy(pliki: list[Path]) -> None:
    """Rzuca, gdy któryś plik ma typ, którego SalesForge nie przyjmie.

    Sprawdzamy U SIEBIE, mimo że serwer i tak sprawdzi. Powód jest praktyczny: odmowa po
    stronie serwera przychodzi jako `403`, a `403` w każdym innym miejscu znaczy „nie masz
    uprawnień" — czyli człowiek zaczyna szukać winy w kluczu zamiast w pliku. Sam się na to
    nabrałem przy pierwszym teście odbiorczym.

    Drugi powód: przy `zglos` sprawa powstaje PRZED wysyłką plików. Odmowa dopiero na
    serwerze zostawia sprawę bez załączników i człowieka z pytaniem, co teraz.
    """
    zle = []
    for p in pliki:
        typ = typ_pliku(p)
        if typ in TYPY_PRZYJMOWANE:
            continue
        rada = PODPOWIEDZI.get(typ, "dozwolone są: obrazy, PDF, dokumenty Office, "
                                     "`.txt`, `.csv`, `.md` oraz `.zip`")
        zle.append(f"{p.name} ({typ}) — {rada}")
    if zle:
        raise ValueError(
            "SalesForge nie przyjmie tych plików:\n  " + "\n  ".join(zle))


def sprawdz_pliki(sciezki: list[str]) -> list[Path]:
    """Ścieżki → `Path`, z głośnym błędem PRZED wysłaniem czegokolwiek.

    Sprawdzamy wszystkie naraz i dopiero potem wysyłamy: paczka odrzucona w połowie zostawiłaby
    sprawę z częścią plików i człowieka z pytaniem, których brakuje. Lepiej nie zacząć.
    """
    gotowe = []
    braki = []
    for s in sciezki:
        p = Path(s).expanduser()
        if not p.is_file():
            braki.append(str(p))
            continue
        if p.stat().st_size == 0:
            braki.append(f"{p} (pusty)")
            continue
        gotowe.append(p)
    if braki:
        raise FileNotFoundError(
            "nie mogę wysłać — tych plików nie ma albo są puste:\n  " + "\n  ".join(braki))
    sprawdz_typy(gotowe)
    return gotowe
