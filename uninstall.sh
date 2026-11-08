#!/bin/sh
# Remove Lowlight. Your settings in ~/.config/lowlight are kept unless you
# pass --purge.

HERE=$(cd "$(dirname "$0")" && pwd)
DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}
CONFIG_HOME=${XDG_CONFIG_HOME:-$HOME/.config}
PREFIX=$DATA_HOME/lowlight
BIN=$HOME/.local/bin/lowlight

if [ -x "$BIN" ]; then
    "$BIN" restore >/dev/null 2>&1
    "$BIN" quit >/dev/null 2>&1
    "$BIN" autostart off >/dev/null 2>&1
fi
rm -f "$CONFIG_HOME/autostart/lowlight.desktop"

if command -v xfconf-query >/dev/null 2>&1; then
    for key in '<Super><Alt>Down' '<Super><Alt>Up'; do
        value=$(xfconf-query -c xfce4-keyboard-shortcuts -p "/commands/custom/$key" 2>/dev/null)
        case $value in *lowlight*)
            xfconf-query -c xfce4-keyboard-shortcuts -p "/commands/custom/$key" -r ;;
        esac
    done
fi
if command -v gsettings >/dev/null 2>&1 && gsettings list-schemas 2>/dev/null | grep -q '^org.gnome.settings-daemon.plugins.media-keys$'; then
    script=$PREFIX/data/gnome-shortcuts.py
    [ -f "$script" ] || script=$HERE/data/gnome-shortcuts.py
    python3 "$script" remove "$BIN" 2>/dev/null
fi

rm -rf "$PREFIX"
rm -f "$BIN" "$DATA_HOME/applications/lowlight.desktop" "$DATA_HOME/icons/hicolor/scalable/apps/lowlight.svg"

if [ "$1" = "--purge" ]; then
    rm -rf "$CONFIG_HOME/lowlight"
fi

echo "Lowlight removed."
[ "$1" = "--purge" ] || echo "Settings kept in $CONFIG_HOME/lowlight (run with --purge to delete them)."
[ -f /etc/udev/rules.d/90-lowlight-backlight.rules ] && \
    echo "The udev rule is still installed; remove it with: sudo rm /etc/udev/rules.d/90-lowlight-backlight.rules"
exit 0
