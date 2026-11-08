"""Command line. Talks to the running app if there is one, else acts directly."""

import os
import sys

from . import APP_NAME, BUS_NAME, OBJECT_PATH, VERSION, core

USAGE = f"""{APP_NAME} {VERSION} - dim a laptop backlight below the normal minimum.
Linux only, for laptops with an LCD (backlit) screen. Not for OLED screens.

usage: lowlight [command]

  (no command)     open the Lowlight window (starts the tray icon too)
  --background     start in the tray only (used at login)
  down             one step darker
  up               one step brighter
  set <0-100>      set the level (0 = darkest allowed)
  restore          go back to the brightness from before dimming
  status           show the backlight values
  calibrate        find the lowest level your screen can show
  check            test that brightness can be changed (used by the installer)
  autostart on|off start Lowlight at login, or stop doing so
  quit             close the running app
  --version        show the version
"""


def _app_bus():
    """Session bus if the Lowlight app is running on it, else None."""
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        owned = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                              "org.freedesktop.DBus", "NameHasOwner",
                              GLib.Variant("(s)", (BUS_NAME,)), None,
                              Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
        return bus if owned else None
    except Exception:
        return None


def _call(bus, method, args=None):
    from gi.repository import Gio
    return bus.call_sync(BUS_NAME, OBJECT_PATH, BUS_NAME, method, args, None,
                         Gio.DBusCallFlags.NONE, 5000, None)


def _model():
    try:
        return core.Model()
    except core.BacklightError as e:
        sys.exit(f"lowlight: {e}")


def launcher_path():
    path = os.path.abspath(sys.argv[0])
    return path if os.access(path, os.X_OK) else "lowlight"


def _forward_or(method, args, local):
    from gi.repository import GLib
    bus = _app_bus()
    if bus:
        try:
            _call(bus, method, args)
            return
        except GLib.Error:
            pass
    try:
        local()
    except core.BacklightError as e:
        sys.exit(f"lowlight: {e}")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    rest = argv[1:]

    if cmd in ("-h", "--help", "help"):
        print(USAGE)
        return
    if cmd in ("-v", "--version"):
        print(f"{APP_NAME} {VERSION}")
        return

    import gi
    gi.require_version("GLib", "2.0")
    gi.require_version("Gio", "2.0")
    from gi.repository import GLib

    if cmd in ("", "--background", "calibrate"):
        bus = _app_bus()
        if bus:
            if cmd != "--background":
                _call(bus, "Calibrate" if cmd == "calibrate" else "Show")
            return
        from .app import run
        run(show_window=cmd != "--background", calibrate=cmd == "calibrate",
            launcher=launcher_path())
        return

    if cmd in ("down", "up") and not rest:
        d = -1 if cmd == "down" else 1

        def local():
            m = _model()
            core.notify(m, core.step(m, d))
        _forward_or("Step", GLib.Variant("(ib)", (d, True)), local)
    elif cmd == "set" and len(rest) == 1:
        try:
            level = float(rest[0].rstrip("%"))
        except ValueError:
            sys.exit("lowlight: set needs a number from 0 to 100")
        _forward_or("SetLevel", GLib.Variant("(d)", (level,)),
                    lambda: core.set_level(_model(), level))
    elif cmd == "restore" and not rest:
        _forward_or("Restore", None, lambda: core.restore(_model()))
    elif cmd == "status" and not rest:
        m = _model()
        raw = m.bl.get()
        print(f"device:     {m.bl.name}")
        print(f"backlight:  {raw} of {m.max}  ({m.percent(raw):.2f}%)")
        print(f"level:      {m.level(raw):.0f} of 100  (0 = darkest allowed)")
        print(f"floor:      {m.floor}{'' if m.cfg.get('floor') else '  (default; run: lowlight calibrate)'}")
        print(f"dimmed:     {'yes' if core.is_dimmed() else 'no'}")
        print(f"app:        {'running' if _app_bus() else 'not running'}")
    elif cmd == "check" and not rest:
        m = _model()
        raw = m.bl.get()
        try:
            m.bl.set(raw)  # same value: tests permission without a visible change
        except core.BacklightError as e:
            sys.exit(f"lowlight: {e}")
        print(f"ok: {m.bl.name}, max {m.max}")
    elif cmd == "autostart" and rest in (["on"], ["off"]):
        core.set_autostart(rest[0] == "on", launcher_path())
    elif cmd == "quit" and not rest:
        bus = _app_bus()
        if bus:
            _call(bus, "Quit")
    else:
        print(USAGE)
        sys.exit(2)
