#!/bin/bash

# Installs Lili Crash for the current user, no sudo needed. The command and the
# skill are symlinked to this checkout, so a git pull updates them. Plasma only
# loads widgets installed through kpackagetool6, so the widget is copied again on
# every run.

set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
bin=${XDG_BIN_HOME:-$HOME/.local/bin}

missing=()
for cmd in journalctl coredumpctl python3 notify-send msgfmt xdg-open; do
  command -v "$cmd" >/dev/null || missing+=("$cmd")
done
if ((${#missing[@]})); then
  echo "Missing: ${missing[*]}" >&2
  exit 1
fi

for po in "$repo"/po/*/lili.po; do
  lang=$(basename "$(dirname "$po")")
  mkdir -p "$repo/locale/$lang/LC_MESSAGES"
  msgfmt -o "$repo/locale/$lang/LC_MESSAGES/lili.mo" "$po"
done

mkdir -p "$bin"
ln -sfn "$repo/bin/lili-crash" "$bin/lili-crash"

data=${XDG_DATA_HOME:-$HOME/.local/share}
icons=$data/icons/hicolor/128x128/apps
mkdir -p "$icons" "$data/applications"
for img in "$repo"/plasma/lili/contents/images/lili*.png; do
  cp "$img" "$icons/lili-crash-$(basename "$img")"
done
cp "$repo/share/lili-crash.desktop" "$data/applications/"
# Points the lili-crash icon at the avatar picked in the settings.
"$bin/lili-crash" config set avatar "$("$bin/lili-crash" config | python3 -c 'import json,sys; print(json.load(sys.stdin)["avatar"])')"

for agent_dir in "$HOME/.claude" "$HOME/.codex"; do
  [[ -d $agent_dir ]] || continue
  mkdir -p "$agent_dir/skills"
  target=$agent_dir/skills/lili-diagnose-crash
  # A real directory at that path would get the link created inside it.
  if [[ -d $target && ! -L $target ]]; then
    mv "$target" "$target.bak-$(date +%Y%m%d%H%M%S)"
  fi
  ln -sfn "$repo/skill/lili-diagnose-crash" "$target"
done

if command -v systemctl >/dev/null; then
  mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  cp "$repo/share/lili-crash.service" "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/"
  systemctl --user daemon-reload
  systemctl --user enable --now lili-crash.service >/dev/null 2>&1
  systemctl --user restart lili-crash.service
fi

if command -v kpackagetool6 >/dev/null; then
  widget=$repo/plasma/lili
  for po in "$repo"/po/*/plasma_applet_lili.po; do
    lang=$(basename "$(dirname "$po")")
    mkdir -p "$widget/contents/locale/$lang/LC_MESSAGES"
    msgfmt -o "$widget/contents/locale/$lang/LC_MESSAGES/plasma_applet_lili.mo" "$po"
  done
  installed=$data/plasma/plasmoids/lili
  if [[ -d $installed ]]; then
    # kpackagetool6 --upgrade removes the widget before reinstalling it, and the
    # system tray drops anything that disappears, even for a moment.
    cp -rT "$widget" "$installed"
  else
    kpackagetool6 --type Plasma/Applet --install "$widget"
  fi
  # Wayland taskbars pick a window's icon from its owner's .desktop file, and Lili's
  # windows belong to plasmashell or plasmawindowed. This KWin rule claims them.
  if command -v kwriteconfig6 >/dev/null; then
    rule=(kwriteconfig6 --file kwinrulesrc --group lili-crash)
    "${rule[@]}" --key Description "Lili Crash windows"
    "${rule[@]}" --key title "Lili Crash"
    "${rule[@]}" --key titlematch 2
    "${rule[@]}" --key desktopfile lili-crash
    "${rule[@]}" --key desktopfilerule 2
    rules=$(kreadconfig6 --file kwinrulesrc --group General --key rules)
    if [[ ,$rules, != *,lili-crash,* ]]; then
      rules=${rules:+$rules,}lili-crash
      kwriteconfig6 --file kwinrulesrc --group General --key rules "$rules"
      kwriteconfig6 --file kwinrulesrc --group General --key count "$(tr ',' '\n' <<<"$rules" | grep -c .)"
    fi
    dbus-send --session --type=method_call --dest=org.kde.KWin /KWin org.kde.KWin.reconfigure 2>/dev/null || true
  fi
  widget_note="
To see Lili in the tray: right-click the system tray, Configure System Tray >
Entries, and set Lili Crash to Always shown. If Plasma was already running an
older version, restart it: systemctl --user restart plasma-plasmashell"
fi

cat <<EOF
Lili Crash installed. Try it on a past crash: lili-crash list${widget_note:-}
EOF
