# Lili Crash 0.5.0: install

Pick your Linux. Download its package and open it: your software center (GNOME Software,
KDE Discover, the Ubuntu App Center, Mint's Software Manager) installs it with the missing
pieces from your distribution. Or paste the block below it into a terminal, which does the
same.

These packages don't update themselves. To get new versions with your system updates,
add the repository instead: see [Install](../../README.md#install) in the README.

## Fedora 44

[Download lili-crash-0.5.0-fedora44.noarch.rpm](https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-fedora44.noarch.rpm)

```sh
sudo dnf install https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-fedora44.noarch.rpm
```

## Fedora 43

[Download lili-crash-0.5.0-fedora43.noarch.rpm](https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-fedora43.noarch.rpm)

```sh
sudo dnf install https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-fedora43.noarch.rpm
```

## openSUSE Tumbleweed and Slowroll

[Download lili-crash-0.5.0-opensuse-tumbleweed.noarch.rpm](https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-opensuse-tumbleweed.noarch.rpm)

```sh
sudo zypper --no-gpg-checks install https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-opensuse-tumbleweed.noarch.rpm
```

## openSUSE Leap 16.0

[Download lili-crash-0.5.0-opensuse-leap16.0.noarch.rpm](https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-opensuse-leap16.0.noarch.rpm)

```sh
sudo zypper --no-gpg-checks install https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-opensuse-leap16.0.noarch.rpm
```

## Debian 13 (trixie)

[Download lili-crash-0.5.0-debian13.all.deb](https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-debian13.all.deb)

```sh
cd /tmp && curl -fLO https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-debian13.all.deb
sudo apt install ./lili-crash-0.5.0-debian13.all.deb
```

## Debian 12 (bookworm)

[Download lili-crash-0.5.0-debian12.all.deb](https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-debian12.all.deb)

```sh
cd /tmp && curl -fLO https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-debian12.all.deb
sudo apt install ./lili-crash-0.5.0-debian12.all.deb
```

## Ubuntu 26.04, Kubuntu 26.04 and their flavours

[Download lili-crash-0.5.0-ubuntu26.04.all.deb](https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-ubuntu26.04.all.deb)

```sh
cd /tmp && curl -fLO https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-ubuntu26.04.all.deb
sudo apt install ./lili-crash-0.5.0-ubuntu26.04.all.deb
```

## Ubuntu 25.10, Kubuntu 25.10 and their flavours

[Download lili-crash-0.5.0-ubuntu25.10.all.deb](https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-ubuntu25.10.all.deb)

```sh
cd /tmp && curl -fLO https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-ubuntu25.10.all.deb
sudo apt install ./lili-crash-0.5.0-ubuntu25.10.all.deb
```

## Ubuntu 24.04 LTS, Linux Mint 22, Pop!_OS 24.04, Zorin OS 18 and other flavours

[Download lili-crash-0.5.0-ubuntu24.04.all.deb](https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-ubuntu24.04.all.deb)

```sh
cd /tmp && curl -fLO https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-ubuntu24.04.all.deb
sudo apt install ./lili-crash-0.5.0-ubuntu24.04.all.deb
```

## Ubuntu 22.04 LTS, Linux Mint 21, Pop!_OS 22.04, Zorin OS 17 and other flavours

[Download lili-crash-0.5.0-ubuntu22.04.all.deb](https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-ubuntu22.04.all.deb)

```sh
cd /tmp && curl -fLO https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-ubuntu22.04.all.deb
sudo apt install ./lili-crash-0.5.0-ubuntu22.04.all.deb
```

## Arch Linux, Garuda, Manjaro, EndeavourOS, CachyOS

```sh
cd /tmp && curl -fLO https://github.com/cryptoconspiracy/lili-crash/raw/main/packages/0.5.0/lili-crash-0.5.0-arch.any.pkg.tar.zst
sudo pacman -U ./lili-crash-0.5.0-arch.any.pkg.tar.zst
```

## Then

Log out and back in, or open **Lili Crash** from the application menu: Lili sets herself up for your user the first time.

## Checking the files

`SHA256SUMS` lists every file's checksum: `sha256sum -c SHA256SUMS` in this folder.
