#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.local/lib/zdorovo"
BIN_DIR="$HOME/.local/bin"
APPLICATIONS_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/zdorovo@jabka.github.io"
SYSTEMD_DIR="$HOME/.config/systemd/user"

for command in python3 systemctl; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Required command not found: $command" >&2
    exit 1
  fi
done

python3 - <<'PY'
import gi

for namespace, version in (
    ("Gtk", "4.0"),
    ("Adw", "1"),
    ("Atspi", "2.0"),
    ("GioUnix", "2.0"),
    ("Graphene", "1.0"),
    ("AyatanaAppIndicator3", "0.1"),
):
    gi.require_version(namespace, version)
PY

mkdir -p "$APP_DIR/assets/icons" "$BIN_DIR" "$APPLICATIONS_DIR" "$ICON_DIR" "$EXT_DIR" "$SYSTEMD_DIR"
if [[ ! -f "$HOME/.local/share/icons/hicolor/index.theme" && -f /usr/share/icons/hicolor/index.theme ]]; then
  install -m 0644 /usr/share/icons/hicolor/index.theme "$HOME/.local/share/icons/hicolor/index.theme"
fi
install -m 0755 "$ROOT/healthbreak.py" "$APP_DIR/healthbreak.py"
install -m 0644 "$ROOT/localization.py" "$APP_DIR/localization.py"
install -m 0755 "$ROOT/indicator.py" "$APP_DIR/indicator.py"
install -m 0755 "$ROOT/launch.sh" "$APP_DIR/launch.sh"
install -m 0644 "$ROOT/assets/style.css" "$APP_DIR/assets/style.css"
install -m 0644 "$ROOT"/assets/icons/*.svg "$APP_DIR/assets/icons/"
install -m 0644 "$ROOT/assets/io.github.jabka.Zdorovo.svg" "$ICON_DIR/io.github.jabka.Zdorovo.svg"
install -m 0644 "$ROOT/assets/io.github.jabka.Zdorovo.svg" "$ICON_DIR/io.github.jabka.Zdorovo-mint-v2.svg"
rm -f "$ICON_DIR/io.github.jabka.Zdorovo-teal.svg"
install -m 0644 "$ROOT/extension/metadata.json" "$ROOT/extension/extension.js" "$EXT_DIR/"
rm -rf "$EXT_DIR/assets"
rm -f "$EXT_DIR/stylesheet.css"
for guide in "$ROOT"/assets/*-guide.png; do
  if [[ -f "$guide" ]]; then
    install -m 0644 "$guide" "$APP_DIR/assets/"
  fi
done

ln -sfn "$APP_DIR/healthbreak.py" "$BIN_DIR/zdorovo"

cat > "$APPLICATIONS_DIR/io.github.jabka.Zdorovo.desktop" <<EOF
[Desktop Entry]
Name=Zdorovo
Name[ru]=Здорово
Comment=Health breaks, guided movement and screen time
Comment[ru]=Перерывы, упражнения и экранное время
Exec=$APP_DIR/launch.sh
Icon=io.github.jabka.Zdorovo-mint-v2
Terminal=false
Type=Application
Categories=Utility;GTK;
Keywords=health;break;eyes;neck;screen time;здоровье;перерыв;
StartupNotify=true
DBusActivatable=false
EOF

cat > "$SYSTEMD_DIR/zdorovo.service" <<EOF
[Unit]
Description=Здорово — напоминания и экранное время
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=$BIN_DIR/zdorovo --background
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
EOF

cat > "$SYSTEMD_DIR/zdorovo-indicator.service" <<EOF
[Unit]
Description=Здорово — значок в панели Ubuntu
After=graphical-session.target zdorovo.service
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $APP_DIR/indicator.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
EOF

update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
systemctl --user daemon-reload
systemctl --user enable zdorovo.service zdorovo-indicator.service
systemctl --user restart zdorovo.service zdorovo-indicator.service
if command -v gnome-extensions >/dev/null 2>&1; then
  gnome-extensions enable zdorovo@jabka.github.io >/dev/null 2>&1 || true
fi
if command -v gsettings >/dev/null 2>&1; then
python3 - <<'PY' || true
import ast
import subprocess

uuid = "zdorovo@jabka.github.io"
raw = subprocess.check_output(["gsettings", "get", "org.gnome.shell", "enabled-extensions"], text=True).strip()
enabled = list(ast.literal_eval(raw))
if uuid not in enabled:
    enabled.append(uuid)
    subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", repr(enabled)], check=True)
PY
fi

echo "Здорово установлено. Если расширение GNOME не включилось сразу, выйдите из системы и войдите снова."
