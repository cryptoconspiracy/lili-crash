# Lili Crash 0.4.0: install

Pick your Linux and paste its block into a terminal. Each one downloads the package
from this folder and installs it with the missing pieces from your distribution.

These packages don't update themselves. To get new versions with your system updates,
add the repository instead: see [Install](../README.md#install) in the README.

## Fedora 44

```sh
sudo dnf install https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.4.0/lili-crash-0.4.0-fedora44.noarch.rpm
```

## Fedora 43

```sh
sudo dnf install https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.4.0/lili-crash-0.4.0-fedora43.noarch.rpm
```

## openSUSE Tumbleweed and Slowroll

```sh
sudo zypper --no-gpg-checks install https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.4.0/lili-crash-0.4.0-opensuse-tumbleweed.noarch.rpm
```

## Debian 13 (trixie)

```sh
cd /tmp && curl -fLO https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.4.0/lili-crash-0.4.0-debian13.all.deb
sudo apt install ./lili-crash-0.4.0-debian13.all.deb
```

## Ubuntu 26.04, Kubuntu 26.04 and their flavours

```sh
cd /tmp && curl -fLO https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.4.0/lili-crash-0.4.0-ubuntu26.04.all.deb
sudo apt install ./lili-crash-0.4.0-ubuntu26.04.all.deb
```

## Ubuntu 25.10, Kubuntu 25.10 and their flavours

```sh
cd /tmp && curl -fLO https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.4.0/lili-crash-0.4.0-ubuntu25.10.all.deb
sudo apt install ./lili-crash-0.4.0-ubuntu25.10.all.deb
```

## Arch Linux, Garuda, Manjaro, EndeavourOS, CachyOS

```sh
sudo pacman -U https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.4.0/lili-crash-0.4.0-arch.any.pkg.tar.zst
```

## Then

```sh
lili-crash setup
```

## Checking the files

`SHA256SUMS` lists every file's checksum: `sha256sum -c SHA256SUMS` in this folder.
