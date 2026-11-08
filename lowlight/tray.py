"""Panel/tray icon.

Uses the StatusNotifierItem protocol (KDE, XFCE, Cinnamon, MATE, LXQt,
Budgie, Waybar, GNOME with the AppIndicator extension), implemented
directly over D-Bus so no extra library is needed. On X11 panels that
only know the old XEmbed tray, it falls back to Gtk.StatusIcon.

Left click opens the window, right click shows the menu, and scrolling
over the icon changes brightness.
"""

import os

from gi.repository import Gio, GLib

WATCHER = "org.kde.StatusNotifierWatcher"
ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"

SNI_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="AttentionIconName" type="s" access="read"/>
    <property name="OverlayIconName" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <method name="ContextMenu"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="Activate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="SecondaryActivate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="Scroll"><arg name="delta" type="i" direction="in"/><arg name="orientation" type="s" direction="in"/></method>
    <signal name="NewTitle"/>
    <signal name="NewIcon"/>
    <signal name="NewToolTip"/>
    <signal name="NewStatus"><arg name="status" type="s"/></signal>
  </interface>
</node>"""

MENU_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <method name="GetLayout">
      <arg type="i" name="parentId" direction="in"/>
      <arg type="i" name="recursionDepth" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="u" name="revision" direction="out"/>
      <arg type="(ia{sv}av)" name="layout" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="a(ia{sv})" name="properties" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="name" direction="in"/>
      <arg type="v" name="value" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="eventId" direction="in"/>
      <arg type="v" name="data" direction="in"/>
      <arg type="u" name="timestamp" direction="in"/>
    </method>
    <method name="EventGroup">
      <arg type="a(isvu)" name="events" direction="in"/>
      <arg type="ai" name="idErrors" direction="out"/>
    </method>
    <method name="AboutToShow">
      <arg type="i" name="id" direction="in"/>
      <arg type="b" name="needUpdate" direction="out"/>
    </method>
    <method name="AboutToShowGroup">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="ai" name="updatesNeeded" direction="out"/>
      <arg type="ai" name="idErrors" direction="out"/>
    </method>
    <signal name="ItemsPropertiesUpdated">
      <arg type="a(ia{sv})" name="updatedProps"/>
      <arg type="a(ias)" name="removedProps"/>
    </signal>
    <signal name="LayoutUpdated">
      <arg type="u" name="revision"/>
      <arg type="i" name="parent"/>
    </signal>
    <signal name="ItemActivationRequested">
      <arg type="i" name="id"/>
      <arg type="u" name="timestamp"/>
    </signal>
  </interface>
</node>"""


def _icon_pixmaps(path):
    """ARGB32 pixmaps for hosts that ignore IconThemePath."""
    try:
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
    except (ImportError, ValueError):
        return []
    out = []
    for size in (16, 22, 24, 32, 48):
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size).add_alpha(False, 0, 0, 0)
        except GLib.Error:
            return []
        w, h, stride = pb.get_width(), pb.get_height(), pb.get_rowstride()
        src = pb.get_pixels()
        argb = bytearray(w * h * 4)
        for y in range(h):
            row = y * stride
            for x in range(w):
                r, g, b, a = src[row + x * 4: row + x * 4 + 4]
                i = (y * w + x) * 4
                argb[i:i + 4] = bytes((a, r, g, b))
        out.append((w, h, bytes(argb)))
    return out


class Tray:
    """Shows the icon. `app` supplies menu_items(), tooltip() and actions."""

    def __init__(self, app, icon_path):
        self.app = app
        self.icon_path = icon_path
        self.icon_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(icon_path))))
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.revision = 1
        self.pixmaps = None
        self.registered = False
        self.status_icon = None
        self.items = {}

        self.name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        sni = Gio.DBusNodeInfo.new_for_xml(SNI_XML).interfaces[0]
        menu = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
        self.bus.register_object(ITEM_PATH, sni, self._sni_call, self._sni_prop, None)
        self.bus.register_object(MENU_PATH, menu, self._menu_call, self._menu_prop, None)
        Gio.bus_own_name_on_connection(self.bus, self.name, Gio.BusNameOwnerFlags.NONE, None, None)

        # The panel may start after us (at login) or restart later.
        Gio.bus_watch_name_on_connection(self.bus, WATCHER, Gio.BusNameWatcherFlags.NONE,
                                         self._watcher_appeared, self._watcher_vanished)
        GLib.timeout_add_seconds(4, self._fallback_if_needed)

    # -------------------------------------------------- availability

    @property
    def visible(self):
        return self.registered or self.status_icon is not None

    def _watcher_appeared(self, conn, name, owner):
        try:
            self.bus.call_sync(WATCHER, "/StatusNotifierWatcher", WATCHER, "RegisterStatusNotifierItem",
                               GLib.Variant("(s)", (self.name,)), None, Gio.DBusCallFlags.NONE, 3000, None)
            self.registered = True
            if self.status_icon is not None:
                self.status_icon.set_visible(False)
                self.status_icon = None
        except GLib.Error:
            self.registered = False

    def _watcher_vanished(self, conn, name):
        self.registered = False

    def _fallback_if_needed(self):
        if not self.registered and self.status_icon is None and _is_x11():
            self._make_status_icon()
        self.app.tray_ready(self.visible)
        return False

    # -------------------------------------------------- updates from the app

    def refresh(self):
        """Brightness changed: refresh tooltip and menu labels."""
        self.revision += 1
        try:
            self.bus.emit_signal(None, ITEM_PATH, "org.kde.StatusNotifierItem", "NewToolTip", None)
            self.bus.emit_signal(None, MENU_PATH, "com.canonical.dbusmenu", "LayoutUpdated",
                                 GLib.Variant("(ui)", (self.revision, 0)))
        except GLib.Error:
            pass
        if self.status_icon is not None:
            self.status_icon.set_tooltip_text(self._tooltip_text())

    def _tooltip_text(self):
        title, body = self.app.tooltip()
        return f"{title}\n{body}"

    # -------------------------------------------------- StatusNotifierItem

    def _sni_prop(self, conn, sender, path, iface, prop):
        if prop == "IconPixmap":
            if self.pixmaps is None:
                self.pixmaps = _icon_pixmaps(self.icon_path)
            return GLib.Variant("a(iiay)", self.pixmaps)
        if prop == "ToolTip":
            title, body = self.app.tooltip()
            return GLib.Variant("(sa(iiay)ss)", ("lowlight", [], title, body))
        values = {
            "Category": ("s", "Hardware"),
            "Id": ("s", "lowlight"),
            "Title": ("s", "Lowlight"),
            "Status": ("s", "Active"),
            "WindowId": ("i", 0),
            "IconName": ("s", "lowlight"),
            "IconThemePath": ("s", self.icon_dir),
            "AttentionIconName": ("s", ""),
            "OverlayIconName": ("s", ""),
            "ItemIsMenu": ("b", False),
            "Menu": ("o", MENU_PATH),
        }
        if prop in values:
            return GLib.Variant(*values[prop])
        return None

    def _sni_call(self, conn, sender, path, iface, method, params, invocation):
        if method in ("Activate", "SecondaryActivate"):
            _once(self.app.toggle_window)
        elif method == "Scroll":
            delta, orientation = params.unpack()
            if delta and orientation.lower() == "vertical":
                # XFCE sends a negative delta for scrolling up (screen
                # coordinates), so up = brighter needs the sign flipped.
                _once(self.app.scroll, 1 if delta < 0 else -1)
        elif method == "ContextMenu":
            pass  # hosts draw the menu themselves from com.canonical.dbusmenu
        invocation.return_value(None)

    # -------------------------------------------------- com.canonical.dbusmenu

    def _menu_prop(self, conn, sender, path, iface, prop):
        return {
            "Version": GLib.Variant("u", 3),
            "TextDirection": GLib.Variant("s", "ltr"),
            "Status": GLib.Variant("s", "normal"),
            "IconThemePath": GLib.Variant("as", [self.icon_dir]),
        }.get(prop)

    @staticmethod
    def _props(item):
        if item.get("separator"):
            return {"type": GLib.Variant("s", "separator")}
        p = {"label": GLib.Variant("s", item["label"]),
             "enabled": GLib.Variant("b", item.get("enabled", True))}
        if "checked" in item:
            p["toggle-type"] = GLib.Variant("s", "checkmark")
            p["toggle-state"] = GLib.Variant("i", 1 if item["checked"] else 0)
        return p

    def _layout(self):
        items = self.app.menu_items()
        self.items = {i + 1: item for i, item in enumerate(items)}
        children = [GLib.Variant("(ia{sv}av)", (iid, self._props(item), []))
                    for iid, item in self.items.items()]
        return (0, {"children-display": GLib.Variant("s", "submenu")}, children)

    def _menu_call(self, conn, sender, path, iface, method, params, invocation):
        if method == "GetLayout":
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (self.revision, self._layout())))
        elif method == "GetGroupProperties":
            ids, _names = params.unpack()
            if not self.items:
                self._layout()
            out = [(i, self._props(self.items[i])) for i in ids if i in self.items]
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (out,)))
        elif method == "GetProperty":
            iid, name = params.unpack()
            value = self._props(self.items.get(iid, {"label": ""})).get(name, GLib.Variant("s", ""))
            invocation.return_value(GLib.Variant("(v)", (value,)))
        elif method == "Event":
            iid, event = params.unpack()[:2]
            if event == "clicked":
                self._activate(iid)
            invocation.return_value(None)
        elif method == "EventGroup":
            for iid, event, _data, _ts in params.unpack()[0]:
                if event == "clicked":
                    self._activate(iid)
            invocation.return_value(GLib.Variant("(ai)", ([],)))
        elif method == "AboutToShow":
            self.revision += 1
            self._layout()
            invocation.return_value(GLib.Variant("(b)", (True,)))
        elif method == "AboutToShowGroup":
            self._layout()
            invocation.return_value(GLib.Variant("(aiai)", ([0], [])))
        else:
            invocation.return_value(None)

    def _activate(self, iid):
        item = self.items.get(iid)
        if item and item.get("action") and item.get("enabled", True):
            _once(item["action"])

    # -------------------------------------------------- XEmbed fallback

    def _make_status_icon(self):
        import warnings
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            icon = Gtk.StatusIcon.new_from_file(self.icon_path)
        icon.set_title("Lowlight")
        icon.set_tooltip_text(self._tooltip_text())
        icon.connect("activate", lambda i: self.app.toggle_window())
        icon.connect("popup-menu", self._popup_gtk_menu)
        icon.connect("scroll-event", self._gtk_scroll)
        self.status_icon = icon

    def _gtk_scroll(self, icon, event):
        from gi.repository import Gdk
        if event.direction == Gdk.ScrollDirection.UP:
            self.app.scroll(1)
        elif event.direction == Gdk.ScrollDirection.DOWN:
            self.app.scroll(-1)
        return True

    def _popup_gtk_menu(self, icon, button, time):
        from gi.repository import Gtk
        menu = Gtk.Menu()
        for item in self.app.menu_items():
            if item.get("separator"):
                w = Gtk.SeparatorMenuItem()
            elif "checked" in item:
                w = Gtk.CheckMenuItem(label=item["label"])
                w.set_active(item["checked"])
            else:
                w = Gtk.MenuItem(label=item["label"])
            w.set_sensitive(item.get("enabled", True))
            if item.get("action"):
                w.connect("activate", lambda _w, a=item["action"]: a())
            menu.append(w)
        menu.show_all()
        menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, time)
        self._menu = menu  # keep a reference while it is open


def _once(fn, *args):
    """Run fn on the main loop exactly once, whatever it returns."""
    def run():
        fn(*args)
        return False
    GLib.idle_add(run)


def _is_x11():
    return not os.environ.get("WAYLAND_DISPLAY") and os.environ.get("XDG_SESSION_TYPE", "x11") != "wayland"
