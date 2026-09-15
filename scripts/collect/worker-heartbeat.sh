#!/usr/bin/env bash
# Czujka tętna workera SF Agent Kit (ADVERTPR-807 C6c).
#
# v0.1 (16.09.2026) - APro Agents / borys-sf
#
# CO ROBI
#   Czyta plik tętna agenta, a gdy tętno jest przeterminowane — restartuje usługę i woła Iris.
#   Przeznaczone do wpięcia w tic (wpięcie dopisze Agata/k-general).
#
# DLACZEGO PLIK, A NIE ZAPYTANIE DO SF
#   Worker bez łączności z SF nadal zapisuje plik. Tętno wysyłane do SF milczałoby dokładnie
#   wtedy, gdy zawodzi sieć — czyli nie dałoby się odróżnić „worker padł" od „worker żyje,
#   ale nie ma jak tego powiedzieć". To są dwie różne awarie i wymagają czego innego.
#
# DLACZEGO PRÓG JEST W PLIKU TĘTNA, A NIE TUTAJ
#   Worker sam deklaruje, jak długo bieżący stan może trwać (`wazne_do`). Zadanie z limitem
#   trzydziestu minut nie odświeża tętna w trakcie wykonania; stały próg w czujce restartowałby
#   workera w połowie pracy modelu — czyli robił dokładnie tę szkodę, przed którą ma chronić.
#
# UŻYCIE
#   worker-heartbeat.sh <slug-agenta> [--restartuj]
#   Bez `--restartuj` tylko raportuje (kod wyjścia 1 = brak tętna) — tak się to testuje
#   na żywej maszynie, zanim wpuści się czujkę z prawem do restartu.
set -euo pipefail

SLUG="${1:-}"
RESTARTUJ="${2:-}"
[[ -n "$SLUG" ]] || { echo "użycie: worker-heartbeat.sh <slug-agenta> [--restartuj]" >&2; exit 2; }

PLIK="$HOME/.sf-kit/heartbeat"
USLUGA="sf-kit-worker@${SLUG}.service"

if [[ ! -f "$PLIK" ]]; then
    echo "BRAK TĘTNA: nie ma $PLIK — worker $SLUG nigdy nie wystartował albo padł przy starcie"
    zywy=1
else
    # Próg czytamy z pliku; `wazne_do` dokłada worker. Starsze tętno (bez tego pola) dostaje
    # 120 s, żeby aktualizacja Kitu nie ogłosiła wszystkich workerów martwymi.
    zywy=$(python3 - "$PLIK" <<'PY'
import json, sys, time
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as e:
    print(f"tętno nieczytelne: {e}", file=sys.stderr)
    sys.exit(1)
kiedy = float(d.get("kiedy", 0))
granica = float(d.get("wazne_do") or (kiedy + 120))
ile = int(time.time() - kiedy)
if time.time() > granica:
    print(f"BRAK TĘTNA: ostatnie {ile} s temu, stan „{d.get('stan','?')}” już nieważny", file=sys.stderr)
    sys.exit(1)
print(f"OK: worker „{d.get('slug','?')}” żyje ({ile} s temu, stan: {d.get('stan','?')})")
PY
    ) && zywy=0 || zywy=1
    [[ $zywy -eq 0 ]] && echo "$zywy" >/dev/null
fi

if [[ $zywy -eq 0 ]]; then
    exit 0
fi

if [[ "$RESTARTUJ" == "--restartuj" ]]; then
    echo "restartuję $USLUGA"
    systemctl --user restart "$USLUGA" || systemctl restart "$USLUGA" || true
    if command -v iris-notify >/dev/null 2>&1; then
        iris-notify "Worker $SLUG bez tętna — zrestartowałem $USLUGA" || true
    fi
fi
exit 1
