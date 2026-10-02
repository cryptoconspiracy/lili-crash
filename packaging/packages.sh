#!/bin/bash
# Copies the packages OBS built for VERSION into packages/VERSION/, one file per
# distribution with the distribution in its name, and writes the install page.
#
#   packaging/packages.sh 0.4.0
#
# release.sh runs it once the OBS builds are done; run it by hand to fill in an older
# version. The files are the same ones the OBS repositories serve, signed by OBS.

set -euo pipefail

version=${1:?usage: packaging/packages.sh VERSION}
pkg=lili-crash
name="Lili Crash"
gh_repo=cryptoconspiracy/lili-crash
obs_prj=home:cryptoconspiracy
osc=(osc -A https://api.opensuse.org)
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
out=$repo/packages/$version
raw=https://github.com/$gh_repo/raw/main/packages/$version

# What to do after installing, shown at the end of the page
then="Log out and back in, or open **$name** from the application menu: Lili sets herself up for your user the first time."

# OBS repository, the label in file names, the name people know, the package format
distros=(
  "Fedora_44|fedora44|Fedora 44|rpm"
  "Fedora_43|fedora43|Fedora 43|rpm"
  "openSUSE_Tumbleweed|opensuse-tumbleweed|openSUSE Tumbleweed and Slowroll|rpm"
  "openSUSE_Leap_16.0|opensuse-leap16.0|openSUSE Leap 16.0|rpm"
  "Debian_13|debian13|Debian 13 (trixie)|deb"
  "Debian_12|debian12|Debian 12 (bookworm)|deb"
  "xUbuntu_26.04|ubuntu26.04|Ubuntu 26.04, Kubuntu 26.04 and their flavours|deb"
  "xUbuntu_25.10|ubuntu25.10|Ubuntu 25.10, Kubuntu 25.10 and their flavours|deb"
  "xUbuntu_24.04|ubuntu24.04|Ubuntu 24.04 LTS, Linux Mint 22, Pop!_OS 24.04, Zorin OS 18 and other flavours|deb"
  "xUbuntu_22.04|ubuntu22.04|Ubuntu 22.04 LTS, Linux Mint 21, Pop!_OS 22.04, Zorin OS 17 and other flavours|deb"
  "Arch|arch|Arch Linux, Garuda, Manjaro, EndeavourOS, CachyOS|pkg.tar.zst"
)

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
rm -rf "$out"
mkdir -p "$out"

built=()
for d in "${distros[@]}"; do
  IFS='|' read -r obs label _ fmt <<<"$d"
  # A distribution the package doesn't build for (too old, a library it lacks) is left out.
  "${osc[@]}" getbinaries -q -d "$work/$obs" "$obs_prj" "$pkg" "$obs" x86_64 >/dev/null 2>&1 || true
  case $fmt in
    rpm) src=$(ls "$work/$obs"/$pkg-"$version"-*.rpm 2>/dev/null | grep -v '\.src\.rpm$' || true) ;;
    deb) src=$(ls "$work/$obs"/${pkg}_"$version"-*_*.deb 2>/dev/null || true) ;;
    *) src=$(ls "$work/$obs"/$pkg-"$version"-*.pkg.tar.zst 2>/dev/null || true) ;;
  esac
  if [[ -z $src ]]; then echo "packages: no $version build for $obs, left out" >&2; continue; fi
  [[ $(wc -l <<<"$src") == 1 && -f $src ]] || { echo "packages: more than one $version build for $obs" >&2; exit 1; }
  built+=("$d")
  arch=$(basename "$src" | grep -oE '(noarch|all|any|x86_64|amd64)' | tail -1)
  cp "$src" "$out/$pkg-$version-$label.$arch.$fmt"
done
(cd "$out" && sha256sum -- * > SHA256SUMS)

file_for() { (cd "$out" && ls -- "$pkg-$version-$1".*); }

{
  cat <<EOF
# $name $version: install

Pick your Linux. Download its package and open it: your software center (GNOME Software,
KDE Discover, the Ubuntu App Center, Mint's Software Manager) installs it with the missing
pieces from your distribution. Or paste the block below it into a terminal, which does the
same.

These packages don't update themselves. To get new versions with your system updates,
add the repository instead: see [Install](../../README.md#install) in the README.

EOF
  for d in "${built[@]}"; do
    IFS='|' read -r _ label title fmt <<<"$d"
    f=$(file_for "$label")
    echo "## $title"
    echo
    [[ $fmt == pkg.tar.zst ]] || { echo "[Download $f]($raw/$f)"; echo; }
    echo '```sh'
    case $fmt in
      rpm) [[ $label == fedora* ]] && echo "sudo dnf install $raw/$f" || echo "sudo zypper --no-gpg-checks install $raw/$f" ;;
      deb) printf 'cd /tmp && curl -fLO %s/%s\nsudo apt install ./%s\n' "$raw" "$f" "$f" ;;
      # From a URL pacman insists on a signature from a trusted key; a local file doesn't.
      *) printf 'cd /tmp && curl -fLO %s/%s\nsudo pacman -U ./%s\n' "$raw" "$f" "$f" ;;
    esac
    echo '```'
    echo
  done
  echo "## Then"
  echo
  echo "$then"
  echo
  echo "## Checking the files"
  echo
  echo "\`SHA256SUMS\` lists every file's checksum: \`sha256sum -c SHA256SUMS\` in this folder."
} > "$out/README.md"

# packages/README.md always shows the newest version
latest=$(ls "$repo/packages" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1)
sed "s|(../../README.md#install)|(../README.md#install)|; s|^# $name .*: install|# $name $latest: install|" \
  "$repo/packages/$latest/README.md" > "$repo/packages/README.md"
echo "packages/$version:"
ls "$out"
