"""Klucz w Menedżerze poświadczeń Windows — odpowiednik pęku kluczy macOS (ADVERTPR-987).

v0.1 (29.09.2026) - APro Agents / borys-sf

DLACZEGO `ctypes`, A NIE `cmdkey`
═════════════════════════════════
`cmdkey /generic:… /pass:<klucz>` wkłada klucz do ARGUMENTÓW procesu — widać go na liście
procesów każdemu programowi tego konta, a to jest dokładnie pierwszy z trzech wycieków,
przed którymi broni `klucz.py`. Interfejs systemu (`advapi32`: `CredWriteW`/`CredReadW`)
przyjmuje wartość w pamięci procesu i nic nie wypisuje. `ctypes` jest w bibliotece
standardowej, więc Kit dalej nie wymaga `pip install`.

Wpis jest typu „ogólne poświadczenie" (widać go w Panelu sterowania → Menedżer poświadczeń →
Poświadczenia systemu Windows), szyfrowany przez system dla tego konta Windows. Trwałość
`LOCAL_MACHINE`: zostaje na tym komputerze, nie wędruje z profilem na inne maszyny.

Wszystkie wywołania `ctypes.WinDLL` są WEWNĄTRZ funkcji: moduł importuje się także na
macOS/Linux (testy), a błąd „nie ma advapi32" pojawiłby się dopiero przy próbie użycia.
"""
from __future__ import annotations

import ctypes

#: Typ poświadczenia „ogólne" (nie hasło domenowe).
CRED_TYPE_GENERIC = 1
#: Zostaje na tym komputerze (nie `ENTERPRISE`, które wędruje z profilem).
CRED_PERSIST_LOCAL_MACHINE = 2
#: `GetLastError()`, gdy wpisu nie ma.
ERROR_NOT_FOUND = 1168


class BladMenedzera(RuntimeError):
    """Menedżer poświadczeń odmówił — komunikat zawiera kod błędu systemu, nie klucz."""


def _typy():
    from ctypes import wintypes

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
    advapi32.CredWriteW.restype = wintypes.BOOL
    advapi32.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]
    advapi32.CredReadW.restype = wintypes.BOOL
    advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    advapi32.CredDeleteW.restype = wintypes.BOOL
    advapi32.CredFree.argtypes = [ctypes.c_void_p]
    advapi32.CredFree.restype = None
    return CREDENTIALW, advapi32


def zapisz(cel: str, konto: str, klucz: str) -> None:
    """Zapisz (albo nadpisz) wpis `cel`. Wartość jako UTF-16LE — tak zapisuje ją sam Windows."""
    CREDENTIALW, advapi32 = _typy()
    dane = klucz.encode("utf-16-le")
    bufor = ctypes.create_string_buffer(dane, len(dane))
    wpis = CREDENTIALW()
    wpis.Type = CRED_TYPE_GENERIC
    wpis.TargetName = cel
    wpis.UserName = konto
    wpis.Comment = "SF Agent Kit — klucz API SalesForge"
    wpis.CredentialBlobSize = len(dane)
    wpis.CredentialBlob = ctypes.cast(bufor, ctypes.POINTER(ctypes.c_char))
    wpis.Persist = CRED_PERSIST_LOCAL_MACHINE
    try:
        if not advapi32.CredWriteW(ctypes.byref(wpis), 0):
            raise BladMenedzera(f"CredWriteW odmówił (kod systemu {ctypes.get_last_error()})")
    finally:
        # Kopia klucza w naszym buforze — wyzeruj, zanim oddamy pamięć.
        ctypes.memset(bufor, 0, len(dane))


def wczytaj(cel: str) -> str | None:
    """Klucz albo `None`, gdy wpisu nie ma. Inny błąd systemu → `BladMenedzera`."""
    CREDENTIALW, advapi32 = _typy()
    wskaznik = ctypes.POINTER(CREDENTIALW)()
    if not advapi32.CredReadW(cel, CRED_TYPE_GENERIC, 0, ctypes.byref(wskaznik)):
        kod = ctypes.get_last_error()
        if kod == ERROR_NOT_FOUND:
            return None
        raise BladMenedzera(f"CredReadW odmówił (kod systemu {kod})")
    try:
        wpis = wskaznik.contents
        surowe = ctypes.string_at(wpis.CredentialBlob, wpis.CredentialBlobSize)
    finally:
        advapi32.CredFree(wskaznik)
    return surowe.decode("utf-16-le").strip() or None


def usun(cel: str) -> bool:
    """Skasuj wpis. `False` = nie było czego kasować albo system odmówił."""
    _, advapi32 = _typy()
    return bool(advapi32.CredDeleteW(cel, CRED_TYPE_GENERIC, 0))
