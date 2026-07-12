#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_EXEC="$ROOT/healthbreak.py"

systemctl --user start zdorovo.service zdorovo-indicator.service

# The systemd process must own the Gtk.Application bus name. Starting another
# binary here creates a race where the visible window outlives the service.
for _attempt in 1 2 3 4 5 6 7 8 9 10; do
  if gdbus call --session \
      --dest io.github.jabka.Zdorovo \
      --object-path /io/github/jabka/Zdorovo \
      --method org.gtk.Application.Activate '{}' >/dev/null 2>&1; then
    exit 0
  fi
  sleep 0.1
done

# A direct launch is retained only as a last-resort fallback if systemd or the
# session bus is temporarily unavailable.
exec "$APP_EXEC"
