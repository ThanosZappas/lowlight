"""Backlight access, the brightness scale and saved state.

Shared by the tray app and the command line. Nothing here needs GTK.
"""

import fcntl
import json
import math
import os

from . import APP_NAME

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "lowlight")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")
RUNTIME_DIR = os.environ.get("XDG_RUNTIME_DIR") or CONFIG_DIR
SYSFS = "/sys/class/backlight"

DEFAULT_CONFIG = {
    "device": None,           # backlight device name; None = pick automatically
    "floor": None,            # lowest raw value to use; None = 1% of max (set by calibration)
    "step": 0.8,              # brightness is multiplied/divided by this per step
    "notify": True,           # on-screen popup for keyboard/scroll changes
    "restore_on_login": True, # re-apply your dim level when you log in
}

DEFAULT_STATE = {
    "normal": None,     # backlight before Lowlight dimmed it; None = not dimmed
    "raw": None,        # last value Lowlight set
    "notify_id": 0,
    "tray_hint_shown": False,
}


class BacklightError(Exception):
    pass


# ---------------------------------------------------------------- files

def _load(path, defaults):
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {**defaults, **data}
    except (OSError, ValueError):
        pass
    return dict(defaults)


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def load_config():
    return _load(CONFIG_FILE, DEFAULT_CONFIG)


def save_config(cfg):
    _save(CONFIG_FILE, {k: v for k, v in cfg.items() if k in DEFAULT_CONFIG})


def load_state():
    return _load(STATE_FILE, DEFAULT_STATE)


def save_state(state):
    _save(STATE_FILE, state)


class Lock:
    """Serialises state changes between the app and command-line calls."""

    def __enter__(self):
        os.makedirs(RUNTIME_DIR, exist_ok=True)
        self.fd = os.open(os.path.join(RUNTIME_DIR, "lowlight.lock"), os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        os.close(self.fd)


# ---------------------------------------------------------------- backlight

def list_devices():
    try:
        return sorted(os.listdir(SYSFS))
    except OSError:
        return []


class Backlight:
    """A /sys/class/backlight device, written through logind or sysfs."""

    # "raw" devices (intel_backlight, amdgpu_bl0, ...) have the finest steps,
    # which is what dimming below the desktop's minimum needs.
    PREFERENCE = {"raw": 0, "platform": 1, "firmware": 2}

    def __init__(self, name=None):
        names = list_devices()
        if not names:
            raise BacklightError(
                "No backlight device was found.\n\n"
                f"{APP_NAME} works on laptops with an LCD (backlit) screen. "
                "OLED screens and desktop monitors have no backlight it can control.")
        if name not in names:
            names.sort(key=lambda n: self.PREFERENCE.get(self._attr(n, "type"), 9))
            name = names[0]
        self.name = name
        self.max = int(self._attr(name, "max_brightness"))
        self._bus = None
        self._session = "/org/freedesktop/login1/session/auto"

    @staticmethod
    def _attr(name, attr):
        try:
            with open(os.path.join(SYSFS, name, attr)) as f:
                return f.read().strip()
        except OSError:
            return ""

    def get(self):
        return int(self._attr(self.name, "brightness") or 0)

    def set(self, value):
        value = max(0, min(self.max, int(value)))
        path = os.path.join(SYSFS, self.name, "brightness")
        if os.access(path, os.W_OK):
            with open(path, "w") as f:
                f.write(str(value))
            return
        try:
            self._logind_set(value)
        except Exception as e:
            raise BacklightError(
                "Lowlight is not allowed to change the backlight.\n\n"
                "Your system has no systemd-logind/elogind brightness service. "
                "Install the udev rule described in the README "
                "(section \"No permission to change brightness\").\n\n"
                f"Details: {e}") from e

    def _logind_set(self, value):
        from gi.repository import Gio, GLib
        if self._bus is None:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        args = GLib.Variant("(ssu)", ("backlight", self.name, value))
        try:
            self._call(self._session, args)
        except GLib.Error:
            # Not started inside the login session (e.g. a systemd user
            # service): use the user's graphical session instead.
            display = self._bus.call_sync(
                "org.freedesktop.login1", "/org/freedesktop/login1/user/self",
                "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant("(ss)", ("org.freedesktop.login1.User", "Display")),
                None, Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
            self._session = display[1]
            self._call(self._session, args)

    def _call(self, path, args):
        from gi.repository import Gio
        self._bus.call_sync("org.freedesktop.login1", path, "org.freedesktop.login1.Session",
                            "SetBrightness", args, None, Gio.DBusCallFlags.NONE, 2000, None)


# ---------------------------------------------------------------- brightness scale

class Model:
    """Maps the raw backlight to a 0-100 scale that looks even to the eye.

    0 is the calibrated floor (darkest), 100 is full brightness. The scale
    is logarithmic because eyes judge brightness by ratios.
    """

    def __init__(self):
        self.cfg = load_config()
        self.bl = Backlight(self.cfg.get("device"))
        self.max = self.bl.max
        floor = self.cfg.get("floor")
        default = max(1, round(self.max * 0.01))
        self.floor = max(1, min(self.max, int(floor))) if floor else default

    def level(self, raw):
        if self.max <= self.floor:
            return 100.0
        raw = max(self.floor, min(self.max, raw))
        return 100.0 * math.log(raw / self.floor) / math.log(self.max / self.floor)

    def raw_for_level(self, level):
        level = max(0.0, min(100.0, level))
        return int(round(self.floor * (self.max / self.floor) ** (level / 100.0)))

    def stepped(self, raw, direction):
        factor = float(self.cfg.get("step") or 0.8)
        target = raw * factor if direction < 0 else raw / factor
        target = int(round(target))
        if target == raw:  # small ranges (e.g. max 15) still move one unit
            target = raw + (1 if direction > 0 else -1)
        return max(self.floor, min(self.max, target))

    def percent(self, raw):
        return 100.0 * raw / self.max


# ---------------------------------------------------------------- actions

def _apply(model, state, raw):
    current = model.bl.get()
    if state["normal"] is None and raw < current:
        state["normal"] = current
    model.bl.set(raw)
    state["raw"] = raw
    if state["normal"] is not None and raw >= state["normal"]:
        state["normal"] = None  # back at (or above) normal: no longer dimmed
    return raw


def step(model, direction):
    with Lock():
        state = load_state()
        raw = _apply(model, state, model.stepped(model.bl.get(), direction))
        save_state(state)
    return raw


def set_level(model, level):
    with Lock():
        state = load_state()
        raw = _apply(model, state, model.raw_for_level(level))
        save_state(state)
    return raw


def restore(model):
    """Return to the brightness from before Lowlight dimmed the screen."""
    with Lock():
        state = load_state()
        raw = model.bl.get()
        if state["normal"] is not None:
            raw = state["normal"]
            model.bl.set(raw)
        state["normal"] = None
        state["raw"] = None
        save_state(state)
    return raw


def is_dimmed():
    return load_state()["normal"] is not None


def remember_current(model):
    """Record the live value (it may have been changed with the Fn keys)."""
    with Lock():
        state = load_state()
        if state["normal"] is not None:
            raw = model.bl.get()
            if raw >= state["normal"]:
                state["normal"] = state["raw"] = None
            else:
                state["raw"] = raw
            save_state(state)


def reapply(model):
    """Put the dim level back after resume or login. Returns True if applied."""
    with Lock():
        state = load_state()
        if state["normal"] is None or state["raw"] is None:
            return False
        if model.bl.get() != state["raw"]:
            model.bl.set(state["raw"])
        return True


# ---------------------------------------------------------------- popup

def notify(model, raw, title=None):
    """Brightness popup through the freedesktop notification service."""
    if not model.cfg.get("notify", True):
        return
    try:
        from gi.repository import Gio, GLib
        level = model.level(raw)
        with Lock():
            state = load_state()
            hints = {
                "value": GLib.Variant("i", int(round(level))),
                "x-canonical-private-synchronous": GLib.Variant("s", "lowlight"),
                "transient": GLib.Variant("b", True),
                "urgency": GLib.Variant("y", 0),
            }
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            reply = bus.call_sync(
                "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications", "Notify",
                GLib.Variant("(susssasa{sv}i)", (
                    APP_NAME, int(state.get("notify_id") or 0), "lowlight",
                    title or f"Brightness {level:.0f}%",
                    f"Backlight {model.percent(raw):.2f}%", [], hints, 1500)),
                GLib.VariantType("(u)"), Gio.DBusCallFlags.NONE, 1000, None)
            state["notify_id"] = reply.unpack()[0]
            save_state(state)
    except Exception:
        pass


# ---------------------------------------------------------------- autostart

AUTOSTART_FILE = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
                              "autostart", "lowlight.desktop")


def autostart_enabled():
    return os.path.exists(AUTOSTART_FILE)


def set_autostart(enabled, launcher):
    if not enabled:
        try:
            os.remove(AUTOSTART_FILE)
        except FileNotFoundError:
            pass
        return
    os.makedirs(os.path.dirname(AUTOSTART_FILE), exist_ok=True)
    with open(AUTOSTART_FILE, "w") as f:
        f.write("[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={APP_NAME}\n"
                "Comment=Dim the laptop backlight below the normal minimum\n"
                f"Exec={launcher} --background\n"
                "Icon=lowlight\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n")
