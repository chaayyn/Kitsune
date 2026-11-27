"""Faux services d'énergie pour les tests du module « Rester éveillé ».

Lancé en sous-processus sur un bus de test (qui sert aussi de bus système) :
gestionnaire de session GNOME (sauf ``--no-gnome``), org.freedesktop.ScreenSaver,
systemd-logind et UPower. ``org.saturn.Test1.State`` renvoie, en JSON, les
inhibitions en cours ; ``SetBattery`` simule la batterie.
"""

from __future__ import annotations

import json
import os
import sys

from gi.repository import Gio, GLib

XML = """
<node>
  <interface name="org.gnome.SessionManager">
    <method name="Inhibit">
      <arg type="s" direction="in"/><arg type="u" direction="in"/>
      <arg type="s" direction="in"/><arg type="u" direction="in"/>
      <arg type="u" direction="out"/>
    </method>
    <method name="Uninhibit"><arg type="u" direction="in"/></method>
  </interface>
  <interface name="org.freedesktop.ScreenSaver">
    <method name="Inhibit">
      <arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="u" direction="out"/>
    </method>
    <method name="UnInhibit"><arg type="u" direction="in"/></method>
  </interface>
  <interface name="org.freedesktop.login1.Manager">
    <method name="Inhibit">
      <arg type="s" direction="in"/><arg type="s" direction="in"/>
      <arg type="s" direction="in"/><arg type="s" direction="in"/>
      <arg type="h" direction="out"/>
    </method>
  </interface>
  <interface name="org.freedesktop.UPower">
    <property name="OnBattery" type="b" access="read"/>
  </interface>
  <interface name="org.freedesktop.UPower.Device">
    <property name="Percentage" type="d" access="read"/>
  </interface>
  <interface name="org.freedesktop.portal.Inhibit">
    <method name="Inhibit">
      <arg type="s" direction="in"/><arg type="u" direction="in"/>
      <arg type="a{sv}" direction="in"/><arg type="o" direction="out"/>
    </method>
  </interface>
  <interface name="org.freedesktop.portal.Request">
    <method name="Close"/>
    <signal name="Response"><arg type="u"/><arg type="a{sv}"/></signal>
  </interface>
  <interface name="org.saturn.Test1">
    <method name="State"><arg type="s" direction="out"/></method>
    <method name="SetBattery">
      <arg type="b" direction="in"/><arg type="d" direction="in"/>
    </method>
  </interface>
</node>
"""

NODE = Gio.DBusNodeInfo.new_for_xml(XML)
state: dict[str, dict[str, object]] = {"gnome": {}, "screensaver": {}, "logind": {}, "portal": {}}
#: --portal ok : inhibitions acceptées ; --portal fail : le service du portail échoue.
PORTAL = sys.argv[sys.argv.index("--portal") + 1] if "--portal" in sys.argv else ""
battery = {"on_battery": False, "percentage": 80.0}
counter = iter(range(1, 1_000_000))


def iface(name: str) -> Gio.DBusInterfaceInfo:
    return NODE.lookup_interface(name)


def on_call(conn, _sender, path, interface, method, params, invocation) -> None:
    args = params.unpack()
    if interface == "org.gnome.SessionManager" and method == "Inhibit":
        cookie = next(counter)
        state["gnome"][str(cookie)] = args[3]
        invocation.return_value(GLib.Variant("(u)", (cookie,)))
    elif interface == "org.gnome.SessionManager" and method == "Uninhibit":
        state["gnome"].pop(str(args[0]), None)
        invocation.return_value(None)
    elif interface == "org.freedesktop.ScreenSaver" and method == "Inhibit":
        cookie = next(counter)
        state["screensaver"][str(cookie)] = args[1]
        invocation.return_value(GLib.Variant("(u)", (cookie,)))
    elif interface == "org.freedesktop.ScreenSaver" and method == "UnInhibit":
        state["screensaver"].pop(str(args[0]), None)
        invocation.return_value(None)
    elif interface == "org.freedesktop.login1.Manager":
        what, _who, _why, mode = args
        if "handle-lid-switch" in what and os.environ.get("FAKE_LOGIND_REFUSE_LID"):
            invocation.return_dbus_error("org.freedesktop.DBus.Error.AccessDenied", "refusé")
            return
        read_end, write_end = os.pipe()
        key = str(next(counter))
        state["logind"][key] = f"{what}/{mode}"

        def closed(fd, _condition) -> bool:
            # Tous les exemplaires du descripteur sont fermés : inhibition levée.
            state["logind"].pop(key, None)
            os.close(fd)
            return GLib.SOURCE_REMOVE

        GLib.unix_fd_add_full(GLib.PRIORITY_DEFAULT, read_end, GLib.IOCondition.HUP, closed)
        fds = Gio.UnixFDList.new_from_array([write_end])
        invocation.return_value_with_unix_fd_list(GLib.Variant("(h)", (0,)), fds)
    elif interface == "org.freedesktop.portal.Inhibit":
        _window, flags, options = args
        sender = invocation.get_sender().lstrip(":").replace(".", "_")
        handle = f"/org/freedesktop/portal/desktop/request/{sender}/{options['handle_token']}"
        invocation.return_value(GLib.Variant("(o)", (handle,)))
        if PORTAL == "fail":
            # Comme xdg-desktop-portal : Response non nul, et la requête n'est pas gardée.
            conn.emit_signal(None, handle, "org.freedesktop.portal.Request", "Response",
                             GLib.Variant("(ua{sv})", (2, {})))
            return
        state["portal"][handle] = flags
        ids: list[int] = []

        def on_request(conn, _sender, path, _iface, _method, _params, inv) -> None:
            state["portal"].pop(path, None)
            conn.unregister_object(ids[0])
            inv.return_value(None)

        ids.append(conn.register_object(handle, iface("org.freedesktop.portal.Request"), on_request, None, None))
    elif interface == "org.saturn.Test1" and method == "State":
        invocation.return_value(GLib.Variant("(s)", (json.dumps(state),)))
    elif interface == "org.saturn.Test1" and method == "SetBattery":
        battery["on_battery"], battery["percentage"] = args
        for obj, prop_iface, name, value in (
            ("/org/freedesktop/UPower", "org.freedesktop.UPower", "OnBattery", GLib.Variant("b", args[0])),
            ("/org/freedesktop/UPower/devices/DisplayDevice", "org.freedesktop.UPower.Device",
             "Percentage", GLib.Variant("d", args[1])),
        ):
            conn.emit_signal(None, obj, "org.freedesktop.DBus.Properties", "PropertiesChanged",
                             GLib.Variant("(sa{sv}as)", (prop_iface, {name: value}, [])))
        invocation.return_value(None)
    else:
        invocation.return_dbus_error("org.freedesktop.DBus.Error.UnknownMethod", method)


def on_get(_conn, _sender, _path, _interface, prop):
    if prop == "OnBattery":
        return GLib.Variant("b", battery["on_battery"])
    return GLib.Variant("d", battery["percentage"])


def main() -> None:
    gnome = "--no-gnome" not in sys.argv
    conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    objects = [
        ("/org/freedesktop/ScreenSaver", "org.freedesktop.ScreenSaver"),
        ("/org/freedesktop/login1", "org.freedesktop.login1.Manager"),
        ("/org/freedesktop/UPower", "org.freedesktop.UPower"),
        ("/org/freedesktop/UPower/devices/DisplayDevice", "org.freedesktop.UPower.Device"),
        ("/org/saturn/Test", "org.saturn.Test1"),
    ]
    if gnome:
        objects.append(("/org/gnome/SessionManager", "org.gnome.SessionManager"))
    if PORTAL:
        objects.append(("/org/freedesktop/portal/desktop", "org.freedesktop.portal.Inhibit"))
    for path, name in objects:
        conn.register_object(path, iface(name), on_call, on_get, None)
    names = ["org.freedesktop.ScreenSaver", "org.freedesktop.login1", "org.freedesktop.UPower"]
    if gnome:
        names.append("org.gnome.SessionManager")
    if PORTAL:
        names.append("org.freedesktop.portal.Desktop")
    for name in names:
        conn.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                       "RequestName", GLib.Variant("(su)", (name, 4)), None, Gio.DBusCallFlags.NONE, -1, None)
    # Signal de disponibilité : le test attend ce nom.
    conn.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                   "RequestName", GLib.Variant("(su)", ("org.saturn.Test", 4)), None,
                   Gio.DBusCallFlags.NONE, -1, None)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
