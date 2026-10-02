Name:           lili-crash
Version:        0.4.0
Release:        1%{?dist}
Summary:        Find out why a program closed by itself, with a one-click AI diagnosis
License:        MIT
URL:            https://github.com/cryptoconspiracy/lili-crash
Source0:        %{url}/archive/refs/tags/v%{version}.tar.gz#/%{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  make
BuildRequires:  gettext
BuildRequires:  python3
BuildRequires:  systemd-rpm-macros
%if 0%{?suse_version}
BuildRequires:  hicolor-icon-theme
Requires:       systemd-coredump
Requires:       libnotify-tools
Requires:       hicolor-icon-theme
%else
Requires:       systemd
Requires:       libnotify
%endif
Requires:       python3
Requires:       xdg-utils
# the tray icon outside Plasma
%if 0%{?suse_version}
Recommends:     %{primary_python}-gobject-Gdk
Recommends:     typelib-1_0-AyatanaAppIndicator3-0_1
%else
Recommends:     python3-gobject
Recommends:     libayatana-appindicator-gtk3
%endif
Suggests:       plasma-workspace

%description
When a program crashes, Lili lets you know, and with one click she asks an AI
assistant such as Claude Code or Codex to investigate and explain what happened.
She also notices a computer that froze, a Steam game that closes right after
starting and an app that won't open. It sets itself up at each user's
first login.

%prep
%autosetup -n %{name}-%{version}

%build
make locales

%check
python3 -m py_compile bin/lili-crash

%install
make PREFIX=%{_prefix} DESTDIR=%{buildroot} install
rm -f %{buildroot}%{_datadir}/licenses/%{name}/LICENSE
%find_lang lili

%files -f lili.lang
%license LICENSE
%doc README.md
%{_bindir}/lili-crash
%{_mandir}/man1/lili-crash.1*
%{_datadir}/lili-crash/
%{_userunitdir}/lili-crash.service
%{_datadir}/applications/lili-crash.desktop
%config(noreplace) %{_sysconfdir}/xdg/autostart/lili-crash-setup.desktop
%{_datadir}/metainfo/io.github.cryptoconspiracy.LiliCrash.metainfo.xml
%{_datadir}/icons/hicolor/128x128/apps/lili-crash*.png
%{_datadir}/icons/hicolor/scalable/apps/lili-crash-symbolic.svg
%dir %{_datadir}/plasma
%dir %{_datadir}/plasma/plasmoids
%{_datadir}/plasma/plasmoids/lili/

%changelog
* Mon Sep 28 2026 Dan B <unknown@cryptoconspiracy.io> - 0.4.0-1
- The first Debian package is the next release, not 0.3
- Packages for Fedora, openSUSE, Debian, Ubuntu and Arch, and lili-crash setup
- Lili notices an app that won't open
- EVM donation address next to Bitcoin, in the settings and the README
- Support page in the settings and the README: Bitcoin QR code and a copy button
- Lili notices a Steam game that closes by itself

