#!/bin/sh
# Lowlight installer. Installs for the current user only; root is needed
# only for the optional steps it asks about (missing packages, udev rule).
#
#   ./install.sh            interactive
#   ./install.sh --yes      accept every question
#   ./install.sh --no-shortcuts

set -e

HERE=$(cd "$(dirname "$0")" && pwd)
DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}
PREFIX=$DATA_HOME/lowlight
BIN_DIR=$HOME/.local/bin
BIN=$BIN_DIR/lowlight
APPS_DIR=$DATA_HOME/applications
ICON_DIR=$DATA_HOME/icons/hicolor/scalable/apps

YES=0
SHORTCUTS=1
for arg in "$@"; do
    case $arg in
        -y|--yes) YES=1 ;;
        --no-shortcuts) SHORTCUTS=0 ;;
        -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg"; exit 2 ;;
    esac
done

say() { printf '%s\n' "$*"; }
step() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ask() {
    [ "$YES" = 1 ] && return 0
    printf '%s [Y/n] ' "$1"
    read -r answer || answer=n
    case $answer in [nN]*) return 1 ;; esac
    return 0
}
as_root() {
    if [ "$(id -u)" = 0 ]; then "$@"
    elif command -v sudo >/dev/null 2>&1; then sudo "$@"
    elif command -v doas >/dev/null 2>&1; then doas "$@"
    else say "Please run as root: $*"; return 1
    fi
}

# ------------------------------------------------------------------ checks
step "Checking this computer"

if [ "$(uname -s)" != Linux ]; then
    say "Lowlight only runs on Linux."
    exit 1
fi

if [ -z "$(ls /sys/class/backlight 2>/dev/null)" ]; then
    say "No backlight device was found."
    say "Lowlight works on laptops with an LCD (backlit) screen. OLED screens and"
    say "desktop monitors have no backlight it can control, so it can't help here."
    exit 1
fi
say "Backlight: $(ls /sys/class/backlight | tr '\n' ' ')"

# ------------------------------------------------------------------ dependencies
deps_command() {
    [ -r /etc/os-release ] && . /etc/os-release
    for id in ${ID:-} ${ID_LIKE:-}; do
        case $id in
            debian|ubuntu|linuxmint|mx|pop|elementary|zorin|kali|raspbian|neon)
                echo "apt install python3 python3-gi gir1.2-gtk-3.0"; return ;;
            fedora|rhel|centos|rocky|almalinux|nobara)
                echo "dnf install python3 python3-gobject gtk3"; return ;;
            arch|manjaro|endeavouros|garuda|artix|cachyos)
                echo "pacman -S --needed python python-gobject gtk3"; return ;;
            opensuse*|suse|sles)
                echo "zypper install python3 python3-gobject python3-gobject-Gdk typelib-1_0-Gtk-3_0"; return ;;
            void)
                echo "xbps-install -S python3 python3-gobject gtk+3"; return ;;
            gentoo)
                echo "emerge --ask dev-python/pygobject x11-libs/gtk+:3"; return ;;
            alpine|postmarketos)
                echo "apk add python3 py3-gobject3 gtk+3.0"; return ;;
        esac
    done
}

has_deps() {
    python3 -c 'import gi; gi.require_version("Gtk", "3.0"); gi.require_version("Gio", "2.0")' 2>/dev/null
}

step "Checking dependencies (Python 3, PyGObject, GTK 3)"
if has_deps; then
    say "All present."
else
    cmd=$(deps_command)
    if [ -z "$cmd" ]; then
        say "Missing. Install Python 3, PyGObject and GTK 3 with your package manager,"
        say "then run this installer again."
        exit 1
    fi
    say "Missing. This command installs them:"
    say "    $cmd"
    if ask "Run it now?"; then
        # shellcheck disable=SC2086
        as_root $cmd
    fi
    has_deps || { say "Dependencies are still missing. Install them and run this again."; exit 1; }
fi

# ------------------------------------------------------------------ files
step "Installing to $PREFIX"
"$BIN" quit >/dev/null 2>&1 || true
rm -rf "$PREFIX"
mkdir -p "$PREFIX" "$BIN_DIR" "$APPS_DIR" "$ICON_DIR"
cp -r "$HERE/bin" "$HERE/lowlight" "$HERE/data" "$HERE/LICENSE" "$HERE/README.md" "$PREFIX/"
find "$PREFIX" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
chmod +x "$PREFIX/bin/lowlight"
ln -sf "$PREFIX/bin/lowlight" "$BIN"
cp "$HERE/data/icons/hicolor/scalable/apps/lowlight.svg" "$ICON_DIR/"
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$DATA_HOME/icons/hicolor" 2>/dev/null || true

cat > "$APPS_DIR/lowlight.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Lowlight
GenericName=Screen Dimmer
Comment=Dim your laptop screen below the normal minimum brightness
Exec=$BIN
Icon=lowlight
Terminal=false
Categories=Utility;Settings;HardwareSettings;
Keywords=brightness;backlight;dim;dark;night;screen;
StartupNotify=false
EOF
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$APPS_DIR" 2>/dev/null || true
say "Done."

# ------------------------------------------------------------------ permission
step "Checking permission to change brightness"
if "$BIN" check; then
    :
else
    say ""
    say "Your system has no logind/elogind brightness service, so Lowlight needs a"
    say "udev rule that lets the 'video' group change the backlight."
    if ask "Install the udev rule now (needs root)?"; then
        as_root install -m 644 "$HERE/data/90-lowlight-backlight.rules" /etc/udev/rules.d/
        as_root udevadm control --reload
        as_root udevadm trigger --subsystem-match=backlight --action=add
        if ! id -nG | grep -qw video; then
            if command -v usermod >/dev/null 2>&1; then
                as_root usermod -aG video "$USER"
            else
                as_root addgroup "$USER" video
            fi
            say "You were added to the 'video' group. Log out and back in before using Lowlight."
        fi
    fi
fi

# ------------------------------------------------------------------ autostart
step "Start at login"
if ask "Start Lowlight automatically when you log in?"; then
    "$BIN" autostart on
    say "Enabled (change it any time in the Lowlight window)."
else
    "$BIN" autostart off
fi

# ------------------------------------------------------------------ shortcuts
desktop=$(printf '%s' "${XDG_CURRENT_DESKTOP:-}" | tr '[:upper:]' '[:lower:]')
if [ "$SHORTCUTS" = 1 ]; then
    step "Keyboard shortcuts"
    case $desktop in
        *xfce*)
            if ask "Add Super+Alt+Down (darker) and Super+Alt+Up (brighter)?"; then
                xfconf-query -c xfce4-keyboard-shortcuts -p '/commands/custom/<Super><Alt>Down' -n -t string -s "$BIN down"
                xfconf-query -c xfce4-keyboard-shortcuts -p '/commands/custom/<Super><Alt>Up' -n -t string -s "$BIN up"
                say "Added."
            fi ;;
        *gnome*|*ubuntu*|*budgie*|*pop*|*unity*)
            if ask "Add Super+Alt+Down (darker) and Super+Alt+Up (brighter)?"; then
                python3 "$HERE/data/gnome-shortcuts.py" add "$BIN" && say "Added."
            fi ;;
        *)
            say "Add these yourself in your desktop's keyboard shortcut settings"
            say "(the README has steps for KDE, Cinnamon, MATE, Sway, Hyprland and i3):"
            say "    darker:   $BIN down"
            say "    brighter: $BIN up" ;;
    esac
fi

# ------------------------------------------------------------------ finish
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) say ""
       say "Note: $BIN_DIR is not in your PATH, so typing 'lowlight' in a terminal"
       say "won't work until you log out and back in (or add it to PATH)." ;;
esac

if command -v setsid >/dev/null 2>&1; then
    setsid "$BIN" --background >/dev/null 2>&1 &
else
    nohup "$BIN" --background >/dev/null 2>&1 &
fi

step "Lowlight is installed"
say "Look for the moon icon in your panel's tray:"
say "  left click   open the window"
say "  right click  menu (About, Quit, ...)"
say "  scroll       darker / brighter"
say ""
say "First, open the window and click 'Calibrate…' to find your screen's lowest level."
case $desktop in
    *gnome*|*ubuntu*)
        say ""
        say "GNOME only shows tray icons with the 'AppIndicator and KStatusNotifierItem"
        say "Support' extension (Ubuntu has it already). Without it, open Lowlight from"
        say "the app menu." ;;
esac
