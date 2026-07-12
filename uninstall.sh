#!/usr/bin/env bash
set -euo pipefail
systemctl --user disable --now zdorovo.service zdorovo-indicator.service 2>/dev/null || true
gnome-extensions disable zdorovo@jabka.github.io 2>/dev/null || true
if command -v gsettings >/dev/null 2>&1; then
python3 - <<'PY' || true
import ast
import subprocess

uuid = "zdorovo@jabka.github.io"
raw = subprocess.check_output(["gsettings", "get", "org.gnome.shell", "enabled-extensions"], text=True).strip()
enabled = [item for item in ast.literal_eval(raw) if item != uuid]
subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", repr(enabled)], check=True)
PY
fi
rm -rf "$HOME/.local/lib/zdorovo" "$HOME/.local/share/gnome-shell/extensions/zdorovo@jabka.github.io"
rm -f "$HOME/.local/bin/zdorovo" "$HOME/.local/share/applications/io.github.jabka.Zdorovo.desktop"
rm -f \
  "$HOME/.local/share/icons/hicolor/scalable/apps/io.github.jabka.Zdorovo.svg" \
  "$HOME/.local/share/icons/hicolor/scalable/apps/io.github.jabka.Zdorovo-mint-v2.svg" \
  "$HOME/.config/systemd/user/zdorovo.service" \
  "$HOME/.config/systemd/user/zdorovo-indicator.service"
gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
systemctl --user daemon-reload
echo "Приложение удалено. Статистика сохранена в ~/.local/share/zdorovo"
