#!/bin/bash

# Installs Lili Crash for the current user. The command and the skill are
# symlinked to this checkout, so a git pull updates them. Plasma only loads widgets
# installed through kpackagetool6, so the widget is copied again on every run.
# The only step that may need your password is installing missing system packages,
# and it asks first.
#
#   ./install.sh          ask before installing packages
#   ./install.sh --yes    don't ask

set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
bin=${XDG_BIN_HOME:-$HOME/.local/bin}

assume_yes=false
[[ ${1:-} == --yes ]] && assume_yes=true

# Every crash Lili shows comes from systemd-coredump.
if [[ ! -d /run/systemd/system ]]; then
  echo "Lili Crash needs systemd, and this system doesn't run it, so there are no crash records to read." >&2
  exit 1
fi

family=
for word in $(. /etc/os-release && echo "${ID:-} ${ID_LIKE:-}"); do
  case $word in
    arch) family=arch ;;
    debian | ubuntu) family=debian ;;
    fedora) family=fedora ;;
    opensuse* | suse) family=suse ;;
  esac
  [[ -n $family ]] && break
done
[[ $family == fedora && -e /run/ostree-booted ]] && family=fedora-atomic

package_for() {
  case $family:$1 in
    arch:python3) echo python ;;
    arch:coredumpctl | fedora*:coredumpctl) echo systemd ;;
    debian:notify-send) echo libnotify-bin ;;
    debian:coredumpctl | suse:coredumpctl) echo systemd-coredump ;;
    suse:msgfmt) echo gettext-tools ;;
    suse:notify-send) echo libnotify-tools ;;
    *:python3) echo python3 ;;
    *:msgfmt) echo gettext ;;
    *:notify-send) echo libnotify ;;
    *:xdg-open) echo xdg-utils ;;
  esac
}

sudo=()
((EUID)) && sudo=(sudo)

confirm() {
  $assume_yes && return 0
  [[ -t 0 ]] || return 1
  read -rp "$1 [Y/n] " answer
  [[ ${answer,,} != n* ]]
}

packages=()
for cmd in coredumpctl python3 msgfmt notify-send xdg-open; do
  command -v "$cmd" >/dev/null || packages+=("$(package_for "$cmd")")
done

if ((${#packages[@]})); then
  case $family in
    arch) install=("${sudo[@]}" pacman -S --needed --noconfirm) ;;
    debian) install=("${sudo[@]}" apt-get install -y) ;;
    fedora) install=("${sudo[@]}" dnf install -y) ;;
    suse) install=("${sudo[@]}" zypper --non-interactive install) ;;
    fedora-atomic)
      echo "Lili Crash needs: ${packages[*]}" >&2
      echo "This system updates as a whole image. Layer them and reboot:" >&2
      echo "  rpm-ostree install ${packages[*]}" >&2
      exit 1
      ;;
    *)
      echo "Lili Crash needs these commands: coredumpctl python3 msgfmt notify-send xdg-open" >&2
      echo "Install the packages that provide them with your package manager and run this again." >&2
      exit 1
      ;;
  esac
  echo "Lili Crash needs: ${packages[*]}"
  echo "  ${install[*]} ${packages[*]}"
  if ! confirm "Install them now?"; then
    echo "Run that command and then ./install.sh again." >&2
    exit 1
  fi
  [[ $family == debian ]] && "${sudo[@]}" apt-get update -q
  if ! "${install[@]}" "${packages[@]}"; then
    # Refreshing the package list alone (pacman -Sy) is a partial upgrade, which Arch
    # forbids, and a full -Syu is not the installer's call to make.
    if [[ $family == arch ]]; then
      echo "pacman couldn't find those packages, so its package list is out of date." >&2
      echo "Update the system first (sudo pacman -Syu, or garuda-update on Garuda) and run ./install.sh again." >&2
    fi
    exit 1
  fi
fi

# Ubuntu hands crashes to Apport by default. Installing systemd-coredump normally
# takes them over (the two coexist since Ubuntu 24.04), but only from the next boot.
if [[ $(</proc/sys/kernel/core_pattern) != *systemd-coredump* ]]; then
  sysctl_file=$(ls /usr/lib/sysctl.d/50-coredump.conf /lib/sysctl.d/50-coredump.conf 2>/dev/null | head -1)
  if [[ -n $sysctl_file ]] && confirm "Crashes still go to $(cut -d' ' -f1 </proc/sys/kernel/core_pattern). Hand them to systemd-coredump now?"; then
    "${sudo[@]}" sysctl -q -p "$sysctl_file"
  fi
  if [[ $(</proc/sys/kernel/core_pattern) != *systemd-coredump* ]]; then
    echo "Warning: crashes are handed to $(cut -d' ' -f1 </proc/sys/kernel/core_pattern), not to systemd-coredump," >&2
    echo "so Lili won't see new ones. On Ubuntu 22.04 and older, Apport has to be turned off first:" >&2
    echo "  sudo systemctl disable --now apport && sudo sysctl -p $sysctl_file" >&2
  fi
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
sed "s|^Exec=lili-crash|Exec=$bin/lili-crash|" "$repo/share/lili-crash.desktop" >"$data/applications/lili-crash.desktop"
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

mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
cp "$repo/share/lili-crash.service" "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/"
if systemctl --user daemon-reload 2>/dev/null; then
  systemctl --user enable lili-crash.service >/dev/null 2>&1
  systemctl --user restart lili-crash.service
else
  service_note="
The notification service starts with your next login (no user session to start it now)."
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
Lili Crash installed. Try it on a past crash: lili-crash list${service_note:-}${widget_note:-}
EOF
