#!/usr/bin/env bash
# Zainstaluj haki Kitu w tym repozytorium.
set -euo pipefail
KATALOG="$(cd "$(dirname "$0")" && pwd)"
CEL="$(git rev-parse --git-dir)/hooks"
install -m 755 "$KATALOG/pre-commit" "$CEL/pre-commit"
echo "Hak pre-commit zainstalowany: $CEL/pre-commit"
echo "Od teraz commit z kluczem sk_live_ zostanie zatrzymany."
