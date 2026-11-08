"""GTK windows: main window, calibration, About and error dialogs."""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import APP_NAME, VERSION, core  # noqa: E402

SUPPORT_NOTE = ("Linux only. For laptops with an LCD (backlit) screen. "
                "OLED screens and external monitors are not supported.")

PRESETS = (("Darkest", 0), ("Dim", 20), ("Low", 40))

# Colours come from the user's GTK theme (@theme_fg_color etc.), so the
# window looks right in both light and dark themes. Amber is the moon
# from the app icon.
CSS = b"""
.ll-body { padding: 18px 24px 22px 24px; }
.ll-caption { font-size: 0.72em; font-weight: bold; letter-spacing: 1px; opacity: 0.6; }
.ll-big { font-size: 46px; font-weight: 300; }
.ll-big-unit { font-size: 20px; font-weight: 300; opacity: 0.6; }
.ll-sub { opacity: 0.65; }
.ll-note { font-size: 0.85em; opacity: 0.55; }

.ll-pill {
    border-radius: 999px; padding: 3px 11px; font-size: 0.8em; font-weight: bold;
    background-color: alpha(@theme_fg_color, 0.08);
}
.ll-pill.dimmed { background-color: alpha(#f2c14e, 0.22); color: mix(#f2c14e, @theme_fg_color, 0.35); }

scale.ll-scale { padding: 8px 0; }
scale.ll-scale trough {
    min-height: 10px; border-radius: 999px; border: none;
    background-image: none; background-color: alpha(@theme_fg_color, 0.10);
}
scale.ll-scale highlight {
    border-radius: 999px; border: none;
    background-image: linear-gradient(to right, #3c5378, #f2c14e);
}
scale.ll-scale slider {
    min-width: 24px; min-height: 24px; margin: -8px; border-radius: 999px;
    background-image: none; background-color: #ffffff;
    border: 1px solid alpha(black, 0.18);
    box-shadow: 0 1px 4px alpha(black, 0.30);
}
scale.ll-scale slider:hover { background-color: #fbf3df; }
.ll-scale-icon { opacity: 0.55; }

button.ll-chip {
    border-radius: 999px; padding: 5px 14px; box-shadow: none; background-image: none;
    background-color: alpha(@theme_fg_color, 0.06);
    border: 1px solid alpha(@theme_fg_color, 0.10);
}
button.ll-chip:hover { background-color: alpha(@theme_fg_color, 0.12); }
button.ll-chip.active { background-color: alpha(#f2c14e, 0.25); border-color: alpha(#f2c14e, 0.65); }
button.ll-chip:disabled { opacity: 0.45; }

button.ll-primary {
    border-radius: 999px; padding: 6px 18px; font-weight: bold; box-shadow: none;
    background-image: none; background-color: #f2c14e; color: #1d2433; border: none;
}
button.ll-primary:hover { background-color: #f6cf6e; }
button.ll-primary label { color: #1d2433; }

.ll-card {
    border-radius: 12px;
    background-color: alpha(@theme_fg_color, 0.04);
    border: 1px solid alpha(@theme_fg_color, 0.08);
}
.ll-row { padding: 11px 14px; }
.ll-card separator { background-color: alpha(@theme_fg_color, 0.08); min-height: 1px; }

progressbar.ll-progress trough { min-height: 6px; border-radius: 999px; border: none;
    background-image: none; background-color: alpha(@theme_fg_color, 0.10); }
progressbar.ll-progress progress { min-height: 6px; border-radius: 999px; border: none;
    background-image: none; background-color: #f2c14e; }
"""

_css_loaded = False


def _load_css():
    global _css_loaded
    if _css_loaded:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _css_loaded = True


def _label(text="", markup=False, cls=(), wrap=False, xalign=0.0):
    lbl = Gtk.Label(xalign=xalign)
    if markup:
        lbl.set_markup(text)
    else:
        lbl.set_text(text)
    if wrap:
        lbl.set_line_wrap(True)
        lbl.set_max_width_chars(46)
    for c in cls:
        lbl.get_style_context().add_class(c)
    return lbl


def _classes(widget, *names):
    for n in names:
        widget.get_style_context().add_class(n)
    return widget


def _icon(app, size):
    try:
        from gi.repository import GdkPixbuf
        return Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(app.icon_path, size, size))
    except Exception:
        return Gtk.Image.new_from_icon_name("display-brightness", Gtk.IconSize.DIALOG)


def _set_window_icon(win, app):
    try:
        win.set_icon_from_file(app.icon_path)
    except GLib.Error:
        win.set_icon_name("display-brightness")


class MainWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title=APP_NAME)
        _load_css()
        self.app = app
        self.set_resizable(False)
        self.set_default_size(460, -1)
        self.set_position(Gtk.WindowPosition.CENTER)
        _set_window_icon(self, app)
        self.connect("delete-event", lambda w, e: w.hide() or True)
        self.connect("key-press-event", self._on_key)

        # Header bar with the app menu.
        header = Gtk.HeaderBar(show_close_button=True, title=APP_NAME)
        actions = Gio.SimpleActionGroup()
        for name, fn in (("calibrate", app.calibrate), ("about", app.about), ("quit", app.quit)):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", lambda a, p, f=fn: f())
            actions.add_action(act)
        self.insert_action_group("ll", actions)
        menu = Gio.Menu()
        menu.append("Calibrate…", "ll.calibrate")
        menu.append("About Lowlight", "ll.about")
        section = Gio.Menu()
        section.append("Quit Lowlight", "ll.quit")
        menu.append_section(None, section)
        menu_btn = Gtk.MenuButton(menu_model=menu, use_popover=True)
        menu_btn.set_image(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        menu_btn.set_tooltip_text("Menu")
        header.pack_end(menu_btn)
        self.set_titlebar(header)

        body = _classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16), "ll-body")
        self.add(body)

        # Big level readout.
        hero = Gtk.Box(spacing=12)
        readout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        readout.pack_start(_label("BRIGHTNESS", cls=("ll-caption",)), False, False, 0)
        number = Gtk.Box(spacing=2)
        self.big = _label("0", cls=("ll-big",))
        number.pack_start(self.big, False, False, 0)
        unit = _label("%", cls=("ll-big-unit",))
        unit.set_valign(Gtk.Align.BASELINE)
        self.big.set_valign(Gtk.Align.BASELINE)
        number.pack_start(unit, False, False, 0)
        readout.pack_start(number, False, False, 0)
        self.detail = _label(cls=("ll-sub",))
        readout.pack_start(self.detail, False, False, 0)
        hero.pack_start(readout, True, True, 0)
        self.pill = _label("Normal", cls=("ll-pill",))
        self.pill.set_valign(Gtk.Align.START)
        self.pill.set_margin_top(4)
        hero.pack_end(self.pill, False, False, 0)
        body.pack_start(hero, False, False, 0)

        # Slider.
        self.adj = Gtk.Adjustment(value=50, lower=0, upper=100, step_increment=1, page_increment=5)
        scale = _classes(Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.adj), "ll-scale")
        scale.set_draw_value(False)
        scale.set_hexpand(True)
        row = Gtk.Box(spacing=10)
        row.pack_start(_classes(Gtk.Image.new_from_icon_name("weather-clear-night-symbolic",
                                                             Gtk.IconSize.BUTTON), "ll-scale-icon"), False, False, 0)
        row.pack_start(scale, True, True, 0)
        row.pack_start(_classes(Gtk.Image.new_from_icon_name("weather-clear-symbolic",
                                                             Gtk.IconSize.BUTTON), "ll-scale-icon"), False, False, 0)
        body.pack_start(row, False, False, 0)
        self._pending = None
        self.adj.connect("value-changed", self._on_slider)

        # Quick presets.
        chips = Gtk.Box(spacing=8, homogeneous=True)
        self.chips = []
        for name, level in PRESETS:
            b = _classes(Gtk.Button(label=name), "ll-chip")
            b.connect("clicked", lambda _b, lv=level: self._preset(lv))
            chips.pack_start(b, True, True, 0)
            self.chips.append((b, level))
        self.restore_btn = _classes(Gtk.Button(label="Normal"), "ll-chip")
        self.restore_btn.set_tooltip_text("Back to the brightness from before dimming")
        self.restore_btn.connect("clicked", lambda b: self.app.restore())
        chips.pack_start(self.restore_btn, True, True, 0)
        body.pack_start(chips, False, False, 0)

        # Settings card.
        card = _classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "ll-card")
        self.popups = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.popups.connect("notify::active", lambda s, p: self._set_if_changed("notify", s.get_active()))
        card.pack_start(self._row("Brightness popups", "When using shortcuts or scrolling on the icon",
                                  self.popups), False, False, 0)
        card.pack_start(Gtk.Separator(), False, False, 0)
        self.login = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.login.connect("notify::active", self._on_login)
        card.pack_start(self._row("Start at login", "Keeps your level after restarts", self.login),
                        False, False, 0)
        card.pack_start(Gtk.Separator(), False, False, 0)
        calib = Gtk.Button(label="Calibrate…", valign=Gtk.Align.CENTER)
        calib.connect("clicked", lambda b: self.app.calibrate())
        self.floor_label = _label(cls=("ll-sub",))
        card.pack_start(self._row("Lowest level", None, calib, sub_widget=self.floor_label), False, False, 0)
        body.pack_start(card, False, False, 0)

        self.tray_hint = _label(
            "No panel tray was found, so there's no tray icon. Open Lowlight from your app "
            "menu instead. On GNOME, install the “AppIndicator and KStatusNotifierItem Support” "
            "extension to get the icon.", cls=("ll-note",), wrap=True)
        body.pack_start(self.tray_hint, False, False, 0)
        note = _label(SUPPORT_NOTE, cls=("ll-note",), wrap=True, xalign=0.5)
        note.set_justify(Gtk.Justification.CENTER)
        body.pack_start(note, False, False, 0)

        header.show_all()
        body.show_all()
        self.tray_hint.set_visible(False)

    def _row(self, title, subtitle, widget, sub_widget=None):
        row = _classes(Gtk.Box(spacing=12), "ll-row")
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        text.pack_start(_label(title), False, False, 0)
        if subtitle:
            text.pack_start(_label(f"<small>{subtitle}</small>", markup=True, cls=("ll-sub",)), False, False, 0)
        if sub_widget:
            text.pack_start(sub_widget, False, False, 0)
        row.pack_start(text, True, True, 0)
        row.pack_end(widget, False, False, 0)
        return row

    def sync(self):
        m = self.app.model
        raw = m.bl.get()
        self.adj.handler_block_by_func(self._on_slider)
        self.adj.set_value(m.level(raw))
        self.adj.handler_unblock_by_func(self._on_slider)
        self._show_level(raw)
        self.popups.set_active(bool(m.cfg.get("notify", True)))
        self.login.set_active(core.autostart_enabled())
        floor = f"{m.percent(m.floor):.2f}% backlight"
        self.floor_label.set_markup(f"<small>{floor}" +
                                    ("" if m.cfg.get("floor") else " · not calibrated yet") + "</small>")
        self.tray_hint.set_visible(not self.app.tray_visible)

    def _show_level(self, raw):
        m = self.app.model
        level = round(m.level(raw))
        self.big.set_text(str(level))
        self.detail.set_text(f"Backlight {m.percent(raw):.2f}%  ·  {raw} of {m.max}")
        dimmed = core.is_dimmed()
        self.pill.set_text("Dimmed" if dimmed else "Normal")
        ctx = self.pill.get_style_context()
        (ctx.add_class if dimmed else ctx.remove_class)("dimmed")
        self.restore_btn.set_sensitive(dimmed)
        for b, lv in self.chips:
            c = b.get_style_context()
            (c.add_class if abs(level - lv) < 1 else c.remove_class)("active")

    def _on_slider(self, adj):
        self._show_level(self.app.model.raw_for_level(adj.get_value()))
        if self._pending is None:
            self._pending = GLib.timeout_add(40, self._commit)

    def _commit(self):
        self._pending = None
        self.app.set_level(self.adj.get_value())
        self._show_level(self.app.model.bl.get())
        return False

    def _preset(self, level):
        self.app.set_level(level)
        self.sync()

    def _set_if_changed(self, key, value):
        if bool(self.app.model.cfg.get(key, True)) != value:
            self.app.set_option(key, value)

    def _on_login(self, switch, _pspec):
        if core.autostart_enabled() != switch.get_active():
            self.app.set_autostart(switch.get_active())

    def _on_key(self, win, event):
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False


class Calibration(Gtk.Window):
    """Steps the backlight down until the user says it stopped working.

    If a step makes the screen black, the user can't answer; each step
    times out and the last good value is kept.
    """

    TIMEOUT = 8

    def __init__(self, app, parent):
        super().__init__(title="Calibrate")
        _load_css()
        self.app = app
        app.calibrating = True
        m = app.model
        self.model = m
        self.start_raw = m.bl.get()
        self.good = None
        self.index = -1
        self.timer = None
        self.remaining = 0
        self.values = self._candidates(m.max)

        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_resizable(False)
        self.set_default_size(420, -1)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        self.set_keep_above(True)
        _set_window_icon(self, app)
        self.connect("delete-event", lambda w, e: self._finish(cancelled=True) or True)
        self.set_titlebar(Gtk.HeaderBar(show_close_button=True, title="Calibrate Lowlight"))

        box = _classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14), "ll-body")
        self.add(box)
        self.caption = _label("FIND YOUR SCREEN'S LOWEST LEVEL", cls=("ll-caption",))
        self.progress = _classes(Gtk.ProgressBar(), "ll-progress")
        self.heading = _label("<span size='large' weight='bold'>Let's find how dark your screen can go</span>",
                              markup=True, wrap=True)
        self.text = _label(
            "The backlight goes down one step at a time. At each step, say whether the screen "
            "got darker and still looks fine.\n\n"
            "Many screens stop getting darker at some point: answer No there. If the screen "
            f"goes black, just wait {self.TIMEOUT} seconds and it comes back on its own.",
            cls=("ll-sub",), wrap=True)
        self.countdown = _label(cls=("ll-note",))
        for w in (self.caption, self.progress, self.heading, self.text, self.countdown):
            box.pack_start(w, False, False, 0)

        buttons = Gtk.Box(spacing=8)
        buttons.set_margin_top(6)
        self.cancel = _classes(Gtk.Button(label="Cancel"), "ll-chip")
        self.cancel.connect("clicked", lambda b: self._finish(cancelled=True))
        self.no = _classes(Gtk.Button(label="No"), "ll-chip")
        self.no.connect("clicked", lambda b: self._finish())
        self.yes = _classes(Gtk.Button(label="Start"), "ll-primary")
        self.yes.set_can_default(True)
        self.yes.connect("clicked", lambda b: self._answer_yes())
        buttons.pack_start(self.cancel, False, False, 0)
        buttons.pack_end(self.yes, False, False, 0)
        buttons.pack_end(self.no, False, False, 0)
        box.pack_start(buttons, False, False, 0)

        self.show_all()
        self.progress.hide()
        self.no.hide()
        self.yes.grab_default()
        self.yes.grab_focus()

    @staticmethod
    def _candidates(max_raw):
        v = max(round(max_raw * 0.05), min(3, max_raw))
        out = []
        while v >= 1:
            if not out or v < out[-1]:
                out.append(int(v))
            if v == 1:
                break
            v = max(1, int(v * 0.7))
        return out

    def _answer_yes(self):
        if self.index >= 0:
            self.good = self.values[self.index]
        self._next()

    def _next(self):
        self.index += 1
        if self.index >= len(self.values):
            self._finish()
            return
        raw = self.values[self.index]
        try:
            self.model.bl.set(raw)
        except core.BacklightError as e:
            self._finish(cancelled=True)
            show_error(self, str(e))
            return
        first = self.index == 0
        self.caption.set_text(f"STEP {self.index + 1} OF {len(self.values)}  ·  "
                              f"BACKLIGHT {self.model.percent(raw):.2f}%")
        self.progress.set_fraction((self.index + 1) / len(self.values))
        self.progress.show()
        self.heading.set_markup("<span size='large' weight='bold'>" +
                                ("Is the screen readable, with no flicker?" if first else
                                 "Did it get darker, and does it still look fine?") + "</span>")
        self.text.set_text("Readable and steady → Yes.  Flickers or looks bad → No." if first else
                           "Darker and steady → Yes.  No change, flicker or too dark → No.")
        self.yes.set_label("Yes")
        self.no.show()
        self.yes.grab_focus()
        self._start_timer()

    def _start_timer(self):
        if self.timer:
            GLib.source_remove(self.timer)
        self.remaining = self.TIMEOUT
        self._tick_label()
        self.timer = GLib.timeout_add_seconds(1, self._tick)

    def _tick(self):
        self.remaining -= 1
        if self.remaining <= 0:
            self.timer = None
            self._finish()
            return False
        self._tick_label()
        return True

    def _tick_label(self):
        self.countdown.set_text(f"No answer in {self.remaining} s counts as No.")

    def _finish(self, cancelled=False):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None
        try:
            self.model.bl.set(self.start_raw)
        except core.BacklightError:
            pass
        self.app.calibrating = False
        self.destroy()
        if cancelled:
            self.app.changed()
            return
        if self.good is None:
            show_info(self.app.window, "Calibration finished",
                      "No step was accepted, so the lowest level was left unchanged.")
            self.app.changed()
            return
        cfg = core.load_config()
        cfg["floor"] = self.good
        core.save_config(cfg)
        self.app.reload_model()
        show_info(self.app.window, "Calibration saved",
                  f"Your lowest level is now {self.model.percent(self.good):.2f}% backlight "
                  f"(raw value {self.good}). The slider's 0 now means this level.")


def show_about(app, parent):
    dlg = Gtk.AboutDialog(transient_for=parent, modal=False)
    dlg.set_program_name(APP_NAME)
    dlg.set_version(VERSION)
    m = app.model
    dlg.set_comments("Dims your laptop screen below the normal minimum brightness by lowering "
                     "the real backlight, which also saves battery.\n\n" + SUPPORT_NOTE +
                     f"\n\nBacklight device: {m.bl.name} (max {m.max}, lowest used {m.floor})")
    dlg.set_website("https://github.com/ThanosZappas/lowlight")
    dlg.set_website_label("Project page")
    dlg.set_license_type(Gtk.License.MIT_X11)
    dlg.set_copyright("© 2026 Thanos Zappas")
    try:
        from gi.repository import GdkPixbuf
        dlg.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_size(app.icon_path, 96, 96))
    except Exception:
        dlg.set_logo_icon_name("display-brightness")
    dlg.connect("response", lambda d, r: d.destroy())
    dlg.show()


def show_info(parent, title, text):
    dlg = Gtk.MessageDialog(transient_for=parent, modal=False, message_type=Gtk.MessageType.INFO,
                            buttons=Gtk.ButtonsType.OK, text=title)
    dlg.format_secondary_text(text)
    dlg.connect("response", lambda d, r: d.destroy())
    dlg.show()


def show_error(parent, message, blocking=False):
    dlg = Gtk.MessageDialog(transient_for=parent, modal=blocking, message_type=Gtk.MessageType.ERROR,
                            buttons=Gtk.ButtonsType.OK, text=f"{APP_NAME} can't change the brightness")
    dlg.format_secondary_text(message)
    if blocking:
        dlg.run()
        dlg.destroy()
    else:
        dlg.connect("response", lambda d, r: d.destroy())
        dlg.show()
