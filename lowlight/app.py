"""The resident app: tray icon, D-Bus service for the CLI, resume handling.

While idle it only waits for D-Bus events (clicks, key shortcuts,
suspend/resume). There is no polling, so it costs no CPU or battery.
"""

import os
import signal
import sys

import gi

gi.require_version("GLib", "2.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from . import APP_NAME, BUS_NAME, OBJECT_PATH, core  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_PATH = os.path.join(ROOT, "data", "icons", "hicolor", "scalable", "apps", "lowlight.svg")

SERVICE_XML = f"""
<node>
  <interface name="{BUS_NAME}">
    <method name="Step">
      <arg type="i" name="direction" direction="in"/>
      <arg type="b" name="popup" direction="in"/>
      <arg type="u" name="raw" direction="out"/>
    </method>
    <method name="SetLevel">
      <arg type="d" name="level" direction="in"/>
      <arg type="u" name="raw" direction="out"/>
    </method>
    <method name="Restore"><arg type="u" name="raw" direction="out"/></method>
    <method name="Show"/>
    <method name="Calibrate"/>
    <method name="Quit"/>
  </interface>
</node>"""


class App:
    def __init__(self, launcher):
        self.launcher = launcher
        self.icon_path = ICON_PATH
        self.loop = GLib.MainLoop()
        self.window = None
        self.calibrating = False
        self.tray = None
        self.tray_visible = True
        self.model = core.Model()  # raises BacklightError on unsupported machines

    # -------------------------------------------------- startup

    def start(self, show_window, calibrate):
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        iface = Gio.DBusNodeInfo.new_for_xml(SERVICE_XML).interfaces[0]
        bus.register_object(OBJECT_PATH, iface, self._service_call, None, None)
        Gio.bus_own_name_on_connection(bus, BUS_NAME, Gio.BusNameOwnerFlags.DO_NOT_QUEUE,
                                       None, lambda *a: self.quit())

        from .tray import Tray
        self.tray = Tray(self, ICON_PATH)

        # Suspend/resume: firmware or the desktop may reset the backlight.
        try:
            system = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            system.signal_subscribe("org.freedesktop.login1", "org.freedesktop.login1.Manager",
                                    "PrepareForSleep", "/org/freedesktop/login1", None,
                                    Gio.DBusSignalFlags.NONE, self._on_sleep)
        except GLib.Error:
            pass

        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self._on_exit_signal)

        if self.model.cfg.get("restore_on_login", True):
            # Let the desktop finish restoring its own brightness first.
            GLib.timeout_add_seconds(3, self._reapply)

        if show_window or calibrate:
            GLib.idle_add(self._show_initial, calibrate)
        self.loop.run()

    def _show_initial(self, calibrate):
        self.show_window()
        if calibrate:
            self.calibrate()
        return False

    # -------------------------------------------------- D-Bus service (CLI, shortcuts)

    def _service_call(self, conn, sender, path, iface, method, params, invocation):
        try:
            if method == "Step":
                direction, popup = params.unpack()
                raw = self.change(direction, popup)
                invocation.return_value(GLib.Variant("(u)", (raw,)))
            elif method == "SetLevel":
                raw = self.set_level(params.unpack()[0])
                invocation.return_value(GLib.Variant("(u)", (raw,)))
            elif method == "Restore":
                invocation.return_value(GLib.Variant("(u)", (self.restore(),)))
            else:
                invocation.return_value(None)
                {"Show": self.show_window, "Calibrate": self.calibrate, "Quit": self.quit}[method]()
        except core.BacklightError as e:
            invocation.return_dbus_error(f"{BUS_NAME}.Error", str(e))

    # -------------------------------------------------- brightness actions

    def _guard(self, fn, *args):
        try:
            return fn(*args)
        except core.BacklightError as e:
            self.error(str(e))
            return self.model.bl.get()

    def change(self, direction, popup=False):
        if self.calibrating:
            return self.model.bl.get()
        raw = self._guard(core.step, self.model, direction)
        if popup:
            core.notify(self.model, raw)
        self.changed()
        return raw

    def scroll(self, direction):
        self.change(direction, popup=True)

    def set_level(self, level):
        raw = self._guard(core.set_level, self.model, level)
        self.changed(from_window=True)
        return raw

    def restore(self):
        raw = self._guard(core.restore, self.model)
        self.changed()
        return raw

    def changed(self, from_window=False):
        if self.tray:
            self.tray.refresh()
        if self.window and not from_window:
            self.window.sync()

    def reload_model(self):
        self.model = core.Model()
        self.changed()

    def _reapply(self):
        if not self.calibrating:
            self._guard(core.reapply, self.model)
            self.changed()
        return False

    def _on_sleep(self, conn, sender, path, iface, sig, params):
        going_to_sleep = params.unpack()[0]
        if going_to_sleep:
            core.remember_current(self.model)
        else:
            # Some power managers restore brightness a little after resume.
            GLib.timeout_add(1500, self._reapply)
            GLib.timeout_add(4000, self._reapply)

    def _on_exit_signal(self):
        core.remember_current(self.model)
        self.loop.quit()
        return False

    # -------------------------------------------------- tray support

    def tooltip(self):
        raw = self.model.bl.get()
        return APP_NAME, f"Brightness {self.model.level(raw):.0f}%  ·  backlight {self.model.percent(raw):.2f}%"

    def menu_items(self):
        raw = self.model.bl.get()
        sep = {"separator": True}
        return [
            {"label": "Open Lowlight", "action": self.show_window},
            {"label": f"Brightness: {self.model.level(raw):.0f}%", "enabled": False},
            sep,
            {"label": "Darker", "action": lambda: self.change(-1)},
            {"label": "Brighter", "action": lambda: self.change(1)},
            {"label": "Restore normal brightness", "enabled": core.is_dimmed(), "action": self.restore},
            sep,
            {"label": "Calibrate…", "action": self.calibrate},
            {"label": "Show popups", "checked": bool(self.model.cfg.get("notify", True)),
             "action": lambda: self.set_option("notify", not self.model.cfg.get("notify", True))},
            {"label": "Start at login", "checked": core.autostart_enabled(),
             "action": lambda: self.set_autostart(not core.autostart_enabled())},
            sep,
            {"label": "About Lowlight", "action": self.about},
            {"label": "Quit", "action": self.quit},
        ]

    def tray_ready(self, visible):
        self.tray_visible = visible
        if self.window:
            self.window.sync()
        if visible:
            return
        state = core.load_state()
        if not state.get("tray_hint_shown"):
            state["tray_hint_shown"] = True
            core.save_state(state)
            self.show_window()

    # -------------------------------------------------- options

    def set_option(self, key, value):
        cfg = core.load_config()
        cfg[key] = value
        core.save_config(cfg)
        self.model.cfg[key] = value
        self.changed()

    def set_autostart(self, enabled):
        core.set_autostart(enabled, self.launcher)
        self.changed()

    # -------------------------------------------------- windows

    def _gtk(self):
        gi.require_version("Gtk", "3.0")
        from . import window
        return window

    def show_window(self):
        if self.window is None:
            self.window = self._gtk().MainWindow(self)
        self.window.sync()
        self.window.present()

    def toggle_window(self):
        if self.window is not None and self.window.is_visible() and self.window.is_active():
            self.window.hide()
        else:
            self.show_window()

    def calibrate(self):
        if not self.calibrating:
            self.show_window()
            self._gtk().Calibration(self, self.window)

    def about(self):
        self._gtk().show_about(self, self.window)

    def error(self, message):
        self._gtk().show_error(self.window, message)

    def quit(self):
        core.remember_current(self.model)
        self.loop.quit()


def run(show_window=True, calibrate=False, launcher="lowlight"):
    try:
        app = App(launcher)
    except core.BacklightError as e:
        _fatal(str(e))
        return
    app.start(show_window, calibrate)


def _fatal(message):
    """Explain why Lowlight can't run, in a dialog if possible."""
    print(f"lowlight: {message}", file=sys.stderr)
    try:
        gi.require_version("Gtk", "3.0")
        from .window import show_error
        show_error(None, message, blocking=True)
    except Exception:
        pass
    sys.exit(1)
