#!/bin/sh
# SF Agent Kit — instalacja jednym poleceniem na macOS i Linuksie (ADVERTPR-987).
#
#   curl -fsSL https://raw.githubusercontent.com/dpakula/sf-agent-kit/main/install.sh | sh
#
# v0.2 (01.10.2026) - APro Agents / borys-sf — SF-175: zapas `git clone`, gdy codeload odmawia (proxy chmury: 403)
# v0.1 (29.09.2026) - APro Agents / borys-sf
#
# Robi TYLKO to, czego Python nie zrobi, zanim go znajdziemy: sprawdza Pythona 3.9+, pobiera
# ZIP wydania z GitHuba i rozpakowuje go. Resztę (katalog, polecenie `sf-kit`, PATH) robi
# `sf-kit instaluj` — jeden kod na trzy systemy (sf_kit/instalacja.py).
# Git NIE jest potrzebny. Uprawnienia administratora (sudo) NIE są potrzebne.
#
# SF_KIT_REF — inne wydanie niż domyślne: tag, gałąź albo SHA (codeload rozwiązuje każde); przy wydaniu podbijamy niżej.
set -eu

REF="${SF_KIT_REF:-v0.17.1}"
ADRES="https://codeload.github.com/dpakula/sf-agent-kit/zip/${REF}"
REPO="https://github.com/dpakula/sf-agent-kit.git"

blad() { printf '\n%s\n' "$*" >&2; exit 1; }

PY=""
for kandydat in python3 python; do
    if command -v "$kandydat" >/dev/null 2>&1 &&
       "$kandydat" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
        PY="$(command -v "$kandydat")"
        break
    fi
done
if [ -z "$PY" ]; then
    case "$(uname -s)" in
        Darwin) rada="Jeśli macOS pokazał okno instalacji „narzędzi wiersza poleceń” — kliknij Zainstaluj (to też daje Pythona) i po zakończeniu uruchom to polecenie jeszcze raz.
Albo zainstaluj Pythona ze strony https://www.python.org/downloads/ (przycisk „Download Python”)." ;;
        *)      rada="Zainstaluj Pythona 3.9 lub nowszego, np. Ubuntu/Debian: sudo apt install python3 — potem uruchom to polecenie jeszcze raz." ;;
    esac
    blad "Kit potrzebuje Pythona 3.9 lub nowszego, a nie znalazłem go na tym komputerze.
$rada"
fi

TMP="$(mktemp -d 2>/dev/null || mktemp -d -t sf-kit)"
trap 'rm -rf "$TMP"' EXIT INT TERM

echo "Pobieram SF Agent Kit ${REF}…"
POBRANE=""
if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$ADRES" -o "$TMP/kit.zip" && POBRANE=1 || true
else
    "$PY" -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' "$ADRES" "$TMP/kit.zip" \
        && POBRANE=1 || true
fi

if [ -n "$POBRANE" ]; then
    # Rozpakowanie Pythonem (zipfile), nie `unzip` — tego na świeżym Linuksie bywa brak.
    # Komentarz archiwum GitHuba = pełny SHA commita; idzie do znacznika instalacji.
    COMMIT="$("$PY" - "$TMP/kit.zip" "$TMP/src" <<'PYEOF'
import sys, zipfile
from pathlib import Path
arch, cel = sys.argv[1], Path(sys.argv[2]).resolve()
with zipfile.ZipFile(arch) as z:
    for n in z.namelist():
        d = (cel / n).resolve()
        if d != cel and cel not in d.parents:
            sys.exit("archiwum zawiera ścieżkę spoza katalogu: " + n)
    z.extractall(cel)
    print(z.comment.decode("ascii", "replace").strip())
PYEOF
)" || blad "Nie udało się rozpakować Kita."
    SRC="$(find "$TMP/src" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
elif command -v git >/dev/null 2>&1; then
    # SF-175: proxy sesji Claude Code w chmurze blokuje codeload.github.com (403), a github.com
    # przepuszcza. To samo wydanie gitem — i ten sam krok `sf-kit instaluj` niżej.
    echo "Archiwum niedostępne ($ADRES) — pobieram to samo wydanie gitem…"
    git clone --quiet --depth 1 --branch "$REF" "$REPO" "$TMP/src-git" >/dev/null 2>&1 \
        || blad "Nie udało się pobrać Kita ani archiwum ($ADRES), ani gitem ($REPO, $REF). Sprawdź połączenie z internetem."
    SRC="$TMP/src-git"
    COMMIT="$(git -C "$SRC" rev-parse HEAD 2>/dev/null || true)"
else
    blad "Nie udało się pobrać Kita ($ADRES). Sprawdź połączenie z internetem.
Jeśli pracujesz w sesji w chmurze, która blokuje codeload.github.com, zainstaluj git — instalator pobierze Kita nim."
fi

[ -f "$SRC/sf-kit" ] || blad "Pobrane archiwum nie wygląda na Kita."

"$PY" "$SRC/sf-kit" instaluj --ref "$REF" --commit "$COMMIT"
