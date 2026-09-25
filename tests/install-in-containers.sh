#!/bin/bash

# Runs install.sh from the committed tree inside clean containers of each supported
# family and checks that it installs what Lili needs and detects the right notes.
# Containers don't boot systemd, so the test fakes /run/systemd/system to get past
# that check. Needs podman.
#
#   tests/install-in-containers.sh [image...]

set -uo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
images=("$@")
((${#images[@]})) || images=(ubuntu:24.04 debian:12 fedora:42 opensuse/tumbleweed archlinux:latest)

check='
mkdir -p /run/systemd/system
cd /lili && ./install.sh --yes >/tmp/install.log 2>&1 || { echo "install.sh failed:"; tail -15 /tmp/install.log; exit 1; }
for cmd in coredumpctl python3 msgfmt notify-send xdg-open; do
  command -v "$cmd" >/dev/null || { echo "still missing: $cmd"; exit 1; }
done
echo "notes: $(basename "$(/root/.local/bin/lili-crash skill path)")"
/root/.local/bin/lili-crash list >/dev/null || { echo "lili-crash list failed"; exit 1; }
'

failed=0
for image in "${images[@]}"; do
  tree=$(mktemp -d)
  git -C "$repo" archive HEAD | tar -x -C "$tree"
  if out=$(podman run --rm -v "$tree:/lili:Z" "docker.io/$image" bash -c "$check" 2>&1); then
    printf 'PASS  %-22s %s\n' "$image" "$(grep '^notes:' <<<"$out")"
  else
    printf 'FAIL  %-22s\n%s\n' "$image" "$(sed 's/^/      /' <<<"$out" | tail -15)"
    failed=1
  fi
  rm -rf "$tree"
done
exit $failed
