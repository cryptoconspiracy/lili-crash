#!/bin/bash
# Publishes a new version everywhere, from this computer:
#
#   make release VERSION=1.2.1            bump, tag, GitHub release, AUR hash, OBS, packages/VERSION
#   make release VERSION=1.2.1 DRY_RUN=1  the same in a throwaway clone, nothing leaves the machine
#
# It uses the gh and osc logins of this machine; no password is stored anywhere else.
# The changelog is the list of commit subjects since the last tag.

set -euo pipefail

version=${1:?usage: packaging/release.sh VERSION}
dry=${DRY_RUN:-0}
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
gh_repo=cryptoconspiracy/lili-crash
obs_prj=home:cryptoconspiracy
obs_pkg=lili-crash
osc=(osc -A https://api.opensuse.org)

step() { echo; echo ">> $*"; }
fail() { echo "release: $*" >&2; exit 1; }

[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "VERSION must look like 1.2.3"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

if [[ $dry == 1 ]]; then
  step "dry run: working in a throwaway clone"
  git clone -q "$repo" "$work/src"
  cd "$work/src"
else
  cd "$repo"
  [[ -z $(git status --porcelain) ]] || fail "uncommitted changes; commit or stash them first"
  [[ $(git branch --show-current) == main ]] || fail "not on main"
  git fetch -q origin
  [[ $(git rev-parse HEAD) == $(git rev-parse origin/main) ]] || fail "main differs from origin/main; pull or push first"
fi
git rev-parse -q --verify "refs/tags/v$version" >/dev/null && fail "tag v$version already exists"

step "tests"
make -s check

last=$(git describe --tags --abbrev=0 2>/dev/null || true)
mapfile -t changes < <(git log --no-merges --format=%s ${last:+"$last"..HEAD} | grep -vE '^(AUR package|Packages:|README|[0-9]+\.[0-9]+\.[0-9]+)' || true)
((${#changes[@]})) || changes=("Maintenance release")
today_rpm=$(LC_ALL=C date '+%a %b %d %Y')
today_deb=$(LC_ALL=C date -R)
author="Dan B <unknown@cryptoconspiracy.io>"

step "version $version in the app, the widget and the packages"
sed -i "s/\"Version\": \"[^\"]*\"/\"Version\": \"$version\"/" plasma/lili/metadata.json
sed -i "s/^Version:        .*/Version:        $version/" packaging/rpm/lili-crash.spec
{
  printf '* %s %s - %s-1\n' "$today_rpm" "$author" "$version"
  printf -- '- %s\n' "${changes[@]}"
  echo
} > "$work/rpmlog"
sed -i "/^%changelog$/r $work/rpmlog" packaging/rpm/lili-crash.spec
{
  printf 'lili-crash (%s-1) unstable; urgency=medium\n\n' "$version"
  printf '  * %s\n' "${changes[@]}"
  printf '\n -- %s  %s\n\n' "$author" "$today_deb"
  cat packaging/debian/changelog
} > "$work/deblog"
cp "$work/deblog" packaging/debian/changelog
sed -i "s/^pkgver=.*/pkgver=$version/; s/^pkgrel=.*/pkgrel=1/" packaging/aur/PKGBUILD
# GNOME Software and Discover show the latest <release> as the version and its notes.
metainfo=share/io.github.cryptoconspiracy.LiliCrash.metainfo.xml
{
  printf '    <release version="%s" date="%s">\n      <description>\n        <ul>\n' "$version" "$(date +%F)"
  for c in "${changes[@]}"; do
    c=${c//&/&amp;}; c=${c//</&lt;}; c=${c//>/&gt;}
    printf '          <li>%s</li>\n' "$c"
  done
  printf '        </ul>\n      </description>\n    </release>\n'
} > "$work/release.xml"
sed -i "/<releases>/r $work/release.xml" "$metainfo"
appstreamcli validate --no-net "$metainfo" >/dev/null || fail "the AppStream file doesn't validate after adding the release"
git add -A
git commit -q -m "$version"
git tag -a "v$version" -m "Lili Crash $version"

step "panel widget for the release and the KDE Store"
make -s locales
(cd plasma/lili && zip -qr "$work/lili-crash-$version.plasmoid" .)
notes="$(printf -- '- %s\n' "${changes[@]}")

\`lili-crash-$version.plasmoid\` is the panel widget alone, for the KDE Store; it needs the app installed."

if [[ $dry == 1 ]]; then
  git archive --prefix="lili-crash-$version/" "v$version" | gzip -n > "$work/lili-crash-$version.tar.gz"
  echo "   would push main and v$version, and publish a GitHub release with:"
  echo "$notes" | sed 's/^/     /'
else
  step "push and GitHub release"
  git push -q origin main "v$version"
  gh release create "v$version" "$work/lili-crash-$version.plasmoid" --repo "$gh_repo" \
    --title "Lili Crash $version" --notes "$notes" >/dev/null
  curl -fsSL -o "$work/lili-crash-$version.tar.gz" \
    "https://github.com/$gh_repo/archive/refs/tags/v$version.tar.gz"
fi
sum=$(sha256sum "$work/lili-crash-$version.tar.gz" | cut -d' ' -f1)

step "AUR recipe: checksum $sum"
sed -i "s/^sha256sums=('.*')/sha256sums=('$sum')/" packaging/aur/PKGBUILD
(cd packaging/aur && makepkg --printsrcinfo > .SRCINFO)
git add packaging/aur
git commit -q -m "AUR package: $version"
[[ $dry == 1 ]] || git push -q origin main

step "openSUSE Build Service ($obs_prj/$obs_pkg)"
(cd "$work" && "${osc[@]}" co "$obs_prj" "$obs_pkg" -o obs >/dev/null)
obs=$work/obs
for f in "$obs"/lili-crash-*.tar.gz; do [[ -e $f ]] && (cd "$obs" && "${osc[@]}" rm "$(basename "$f")" >/dev/null); done
cp "$work/lili-crash-$version.tar.gz" packaging/rpm/lili-crash.spec packaging/aur/lili-crash.install "$obs/"
# OBS builds offline from the files it holds, so the recipe points at the uploaded tarball.
sed 's|^source=(.*)|source=("$pkgname-$pkgver.tar.gz")|' packaging/aur/PKGBUILD > "$obs/PKGBUILD"
mkdir -p "$work/deb" && cp -r packaging/debian "$work/deb/debian" && rm -rf "$work/deb/debian/source"
tar -C "$work/deb" -czf "$obs/debian.tar.gz" debian
# OBS turns debian.tar.gz and the tarball into a Debian source package through this file.
[[ -e $obs/lili-crash.dsc ]] || cat > "$obs/lili-crash.dsc" <<'DSC'
Format: 1.0
Source: lili-crash
Binary: lili-crash
Architecture: all
Version: 0
Maintainer: Dan B <unknown@cryptoconspiracy.io>
Homepage: https://github.com/cryptoconspiracy/lili-crash
Standards-Version: 4.7.2
Build-Depends: debhelper-compat (= 13), gettext, python3
DEBTRANSFORM-TAR: none
DSC
sed -i "s/^Version: .*/Version: $version-1/; s/^DEBTRANSFORM-TAR: .*/DEBTRANSFORM-TAR: lili-crash-$version.tar.gz/" "$obs/lili-crash.dsc"
(cd "$obs" && "${osc[@]}" addremove >/dev/null && "${osc[@]}" status)
if [[ $dry == 1 ]]; then
  echo "   would commit the above to OBS"
else
  (cd "$obs" && "${osc[@]}" commit -m "lili-crash $version" >/dev/null)
  step "waiting for the OBS builds"
  for _ in $(seq 1 120); do
    results=$("${osc[@]}" results "$obs_prj" "$obs_pkg")
    grep -qE 'building|scheduled|dispatching|finished|signing|blocked|\*|unknown' <<<"$results" || break
    sleep 20
  done
  echo "$results"
  grep -qE 'failed|unresolvable|broken' <<<"$results" && fail "an OBS build failed: ${osc[*]} buildlog $obs_prj $obs_pkg <repo> x86_64"

  step "packages/$version: the built packages, one per distribution, for people who'd rather download a file"
  packaging/packages.sh "$version"
  git add packages
  git commit -q -m "Packages: $version"
  git push -q origin main
fi

step "AUR"
if ssh -o BatchMode=yes -o ConnectTimeout=10 aur@aur.archlinux.org help >/dev/null 2>&1; then
  git clone -q ssh://aur@aur.archlinux.org/lili-crash.git "$work/aur"
  cp packaging/aur/{PKGBUILD,.SRCINFO,lili-crash.install} "$work/aur/"
  (cd "$work/aur" && git add -A && git commit -q -m "$version" && { [[ $dry == 1 ]] && echo "   would push to the AUR" || git push -q; })
else
  echo "   skipped: no AUR login on this machine yet"
fi

step "done"
echo "KDE Store: upload $work/lili-crash-$version.plasmoid by hand at https://store.kde.org/product/add"
if [[ $dry != 1 ]]; then
  mkdir -p "$HOME/Downloads/lili-crash-kde-store"
  cp "$work/lili-crash-$version.plasmoid" "$HOME/Downloads/lili-crash-kde-store/"
  echo "  (a copy is in ~/Downloads/lili-crash-kde-store)"
fi
