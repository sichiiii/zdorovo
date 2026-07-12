#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m unittest discover -s tests -v
dpkg-buildpackage --build=binary --no-sign

find "$ROOT/.." -maxdepth 1 -type f -name 'zdorovo_*.deb' -print

