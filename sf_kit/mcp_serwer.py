"""`sf-kit mcp` — serwer MCP (stdio) nad tym samym kodem co CLI (SF-203, Agata 14:36).

v1.0.0 (02.10.2026) - APro Agents / borys-sf

PO CO
═════
Asystent ma mieć SalesForge „w swoich narzędziach”, nie w README (Damian, SF-201). Claude Code, Codex
i Kimi Code obsługują MCP natywnie — jeden serwer, cztery konsumenty.

JAK
═══
- Transport stdio: JSON-RPC 2.0, jedna wiadomość na linię (stdin → stdout); logi WYŁĄCZNIE na stderr.
- Narzędzia = komendy kanoniczne z `pakiet/komendy.json` z `mcp: true` (bez aliasów — to te same
  operacje). `tylko_odczyt` → adnotacja `readOnlyHint`. `sf-kit update` NIE jest narzędziem (strażnik).
- Wywołanie narzędzia = ta sama podkomenda `sf-kit` w podprocesie: argumenty jako LISTA (bez powłoki),
  stdin zamknięty (nic nie zawiśnie na pytaniu), limit czasu. Kod jest dokładnie ten sam co w terminalu,
  więc MCP nie ma własnych reguł, które mogłyby się rozjechać z CLI.
- Klucz: z magazynu Kita (to, co ustawił `sf-kit init`) — serwer sam nie zna i nie przyjmuje klucza.

Bez bibliotek zewnętrznych (Kit = biblioteka standardowa Pythona 3.9+).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, TextIO

from . import WERSJA, pakiet

PROTOKOL = "2025-06-18"
LIMIT_S = 120
SKRYPT = Path(__file__).resolve().parents[1] / "sf-kit"

INSTRUKCJE = (
    "SalesForge (SF) przez SF Kit. Każde narzędzie to podkomenda `sf-kit` z argumentami podanymi jak w "
    "terminalu (lista `argumenty`). `reply` domyślnie pisze DO KLIENTA (`--wewn` = notatka zespołu). "
    "Wzmianka tylko pełnym adresem (@anna@firma.pl). Odmowę (403) przekaż człowiekowi — uprawnienia ma klucz.")


def narzedzia(manifest: dict) -> list[dict]:
    wynik = []
    for k in manifest["komendy"]:
        if not k.get("mcp") or k.get("rola") != "wszyscy":
            continue
        opis = k["opis"]["pl"] + (f" Składnia argumentów: {k['argumenty']}" if k.get("argumenty") else "")
        wynik.append({
            "name": k["id"].replace("-", "_"),
            "title": k["opis"]["pl"],
            "description": f"{opis} (w terminalu: `sf-kit {k['cli']}`; aliasy PL: "
                           f"{', '.join(k.get('aliasy', [])) or '—'})",
            "inputSchema": {
                "type": "object",
                "properties": {"argumenty": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Argumenty podkomendy, każdy osobno, np. [\"ADVERTPR-12\", \"--opis\", \"-\"]"}},
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": bool(k.get("tylko_odczyt")),
                            "destructiveHint": False, "openWorldHint": True},
        })
    return wynik


def _cli_dla(manifest: dict) -> dict[str, str]:
    return {k["id"].replace("-", "_"): k["cli"] for k in manifest["komendy"]
            if k.get("mcp") and k.get("rola") == "wszyscy"}


def wywolaj(cli: str, argumenty: list[str], uruchom=subprocess.run) -> dict:
    """Uruchom `sf-kit <cli> <argumenty…>` jak w terminalu; wynik jako treść MCP."""
    try:
        w = uruchom([sys.executable, str(SKRYPT), cli, *argumenty], capture_output=True, text=True,
                    encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=LIMIT_S)
    except subprocess.TimeoutExpired:
        return {"content": [{"type": "text", "text": f"`sf-kit {cli}` nie skończyło się w {LIMIT_S} s."}],
                "isError": True}
    tekst = (w.stdout or "").strip()
    if w.stderr and w.stderr.strip():
        tekst = (tekst + "\n\n" if tekst else "") + w.stderr.strip()
    return {"content": [{"type": "text", "text": tekst or "(bez wyniku)"}], "isError": w.returncode != 0}


def obsluz(wiadomosc: dict, manifest: dict, uruchom=subprocess.run) -> dict | None:
    """Jedna wiadomość JSON-RPC → odpowiedź (albo `None` dla powiadomień)."""
    metoda, ident = wiadomosc.get("method"), wiadomosc.get("id")
    if ident is None:                      # powiadomienie (np. notifications/initialized) — bez odpowiedzi
        return None

    def ok(wynik: dict) -> dict:
        return {"jsonrpc": "2.0", "id": ident, "result": wynik}

    def blad(kod: int, tekst: str) -> dict:
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": kod, "message": tekst}}

    if metoda == "initialize":
        klient = (wiadomosc.get("params") or {}).get("protocolVersion") or PROTOKOL
        return ok({"protocolVersion": klient if isinstance(klient, str) else PROTOKOL,
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": "sf-kit", "version": WERSJA},
                   "instructions": INSTRUKCJE})
    if metoda == "ping":
        return ok({})
    if metoda == "tools/list":
        return ok({"tools": narzedzia(manifest)})
    if metoda == "tools/call":
        params = wiadomosc.get("params") or {}
        cli = _cli_dla(manifest).get(params.get("name"))
        if not cli:
            return blad(-32602, f"Nieznane narzędzie: {params.get('name')}")
        argumenty = (params.get("arguments") or {}).get("argumenty") or []
        if not isinstance(argumenty, list) or not all(isinstance(a, str) for a in argumenty):
            return blad(-32602, "`argumenty` musi być listą napisów")
        return ok(wywolaj(cli, argumenty, uruchom))
    return blad(-32601, f"Nieobsługiwana metoda: {metoda}")


def petla(wejscie: TextIO = sys.stdin, wyjscie: TextIO = sys.stdout, *,
          manifest: dict | None = None, uruchom: Callable = subprocess.run) -> int:
    manifest = manifest or pakiet.wczytaj()
    for linia in wejscie:
        linia = linia.strip()
        if not linia:
            continue
        try:
            wiadomosc = json.loads(linia)
        except json.JSONDecodeError:
            odp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Niepoprawny JSON"}}
        else:
            odp = obsluz(wiadomosc, manifest, uruchom) if isinstance(wiadomosc, dict) else \
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Oczekiwano obiektu"}}
        if odp is not None:
            wyjscie.write(json.dumps(odp, ensure_ascii=False) + "\n")
            wyjscie.flush()
    return 0
