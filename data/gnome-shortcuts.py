"""Add or remove Lowlight's GNOME custom keyboard shortcuts.

usage: python3 gnome-shortcuts.py add|remove /path/to/lowlight
Works on GNOME, Ubuntu, Pop!_OS and Budgie (all use gnome-settings-daemon).
"""

import ast
import subprocess
import sys

SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
SHORTCUTS = (("Lowlight darker", "<Super><Alt>Down", "down"),
             ("Lowlight brighter", "<Super><Alt>Up", "up"))


def gsettings(*args):
    return subprocess.run(["gsettings", *args], capture_output=True, text=True, check=True).stdout.strip()


def main(action, launcher):
    current = gsettings("get", SCHEMA, "custom-keybindings")
    paths = [] if current.startswith("@as") else ast.literal_eval(current)

    def is_ours(path):
        return "lowlight" in gsettings("get", f"{SCHEMA}.custom-keybinding:{path}", "command")

    ours = [p for p in paths if is_ours(p)]
    paths = [p for p in paths if p not in ours]
    for p in ours:
        for key in ("name", "command", "binding"):
            gsettings("reset", f"{SCHEMA}.custom-keybinding:{p}", key)

    if action == "add":
        n = 0
        for name, binding, cmd in SHORTCUTS:
            while f"{BASE}custom{n}/" in paths:
                n += 1
            path = f"{BASE}custom{n}/"
            paths.append(path)
            for key, value in (("name", name), ("command", f"{launcher} {cmd}"), ("binding", binding)):
                gsettings("set", f"{SCHEMA}.custom-keybinding:{path}", key, value)

    gsettings("set", SCHEMA, "custom-keybindings", str(paths))


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("add", "remove"):
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
