# System-wide install, for distribution packages:  make && make DESTDIR=... install
# For a per-user install from this checkout, use ./install.sh instead.

PREFIX ?= /usr
SYSCONFDIR ?= /etc
DESTDIR ?=
SHARE = $(DESTDIR)$(PREFIX)/share
WIDGET = plasma/lili
METAINFO = share/io.github.cryptoconspiracy.LiliCrash.metainfo.xml

LANGS = $(patsubst po/%/,%,$(wildcard po/*/))

all: locales

locales:
	for lang in $(LANGS); do \
	  mkdir -p locale/$$lang/LC_MESSAGES $(WIDGET)/contents/locale/$$lang/LC_MESSAGES; \
	  msgfmt -o locale/$$lang/LC_MESSAGES/lili.mo po/$$lang/lili.po; \
	  msgfmt -o $(WIDGET)/contents/locale/$$lang/LC_MESSAGES/plasma_applet_lili.mo po/$$lang/plasma_applet_lili.po; \
	done

check:
	python3 -m py_compile bin/lili-crash
	for po in po/*/*.po; do msgfmt --check -o /dev/null $$po || exit 1; done
	if command -v appstreamcli >/dev/null; then appstreamcli validate --no-net $(METAINFO); fi
	if command -v desktop-file-validate >/dev/null; then desktop-file-validate share/lili-crash.desktop share/lili-crash-setup.desktop; fi

install: locales
	install -Dm755 bin/lili-crash $(DESTDIR)$(PREFIX)/bin/lili-crash
	install -d $(SHARE)/lili-crash
	cp -r skill $(SHARE)/lili-crash/
	for lang in $(LANGS); do \
	  install -Dm644 locale/$$lang/LC_MESSAGES/lili.mo $(SHARE)/locale/$$lang/LC_MESSAGES/lili.mo; \
	done
	sed 's|%h/.local/bin/lili-crash|$(PREFIX)/bin/lili-crash|' share/lili-crash.service \
	  | install -Dm644 /dev/stdin $(DESTDIR)$(PREFIX)/lib/systemd/user/lili-crash.service
	install -Dm644 share/lili-crash.desktop $(SHARE)/applications/lili-crash.desktop
	install -Dm644 share/lili-crash-setup.desktop $(DESTDIR)$(SYSCONFDIR)/xdg/autostart/lili-crash-setup.desktop
	install -Dm644 $(METAINFO) $(SHARE)/metainfo/io.github.cryptoconspiracy.LiliCrash.metainfo.xml
	for avatar in logo lili1 lili2 lili3; do \
	  install -Dm644 $(WIDGET)/contents/images/$$avatar.png $(SHARE)/icons/hicolor/128x128/apps/lili-crash-$$avatar.png; \
	done
	# the default avatar; each user's choice is a link in their own icon theme
	install -Dm644 $(WIDGET)/contents/images/logo.png $(SHARE)/icons/hicolor/128x128/apps/lili-crash.png
	# the tray icon outside Plasma; the panel paints it in the theme's text colour
	install -Dm644 $(WIDGET)/contents/images/logo-symbolic.svg $(SHARE)/icons/hicolor/scalable/apps/lili-crash-symbolic.svg
	install -d $(SHARE)/plasma/plasmoids
	cp -r $(WIDGET) $(SHARE)/plasma/plasmoids/
	install -Dm644 share/lili-crash.1 $(SHARE)/man/man1/lili-crash.1
	install -Dm644 LICENSE $(SHARE)/licenses/lili-crash/LICENSE

# Publishes VERSION to GitHub, the OBS repositories and (once there's an account) the AUR.
release:
	@test -n "$(VERSION)" || { echo "usage: make release VERSION=1.2.3 [DRY_RUN=1]"; exit 1; }
	DRY_RUN=$(DRY_RUN) packaging/release.sh $(VERSION)

.PHONY: all locales check install release
