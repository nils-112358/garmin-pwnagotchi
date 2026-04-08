"""
Pwnagotchi Plugin: ble_garmin.py
Überträgt Pwnagotchi-Status per BLE GATT an Garmin Fenix 8.

Installation:
  1. Nach /etc/pwnagotchi/custom-plugins/ble_garmin.py kopieren
  2. config.toml:  main.plugins.ble_garmin.enabled = true
  3. Neustart

Abhängigkeiten:
  sudo pip3 install dbus-python --break-system-packages
  sudo apt-get install python3-gi
"""

import pwnagotchi.plugins as plugins
import logging
import threading
import json
import time

try:
    import dbus
    import dbus.service
    import dbus.mainloop.glib
    from gi.repository import GLib
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False
    logging.error("[ble_garmin] dbus-python / gi fehlt!")

# ─── UUIDs ────────────────────────────────────────────────────
PWNG_SERVICE_UUID = "12345678-1234-1234-1234-123456789abc"
CHAR_JSON_UUID    = "12345678-1234-1234-1234-123456789ab0"

BLUEZ_SERVICE          = "org.bluez"
GATT_MANAGER_IFACE     = "org.bluez.GattManager1"
DBUS_OM_IFACE          = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE        = "org.freedesktop.DBus.Properties"
GATT_SERVICE_IFACE     = "org.bluez.GattService1"
GATT_CHRC_IFACE        = "org.bluez.GattCharacteristic1"
LE_ADV_MANAGER_IFACE   = "org.bluez.LEAdvertisingManager1"
LE_ADV_IFACE           = "org.bluez.LEAdvertisement1"


def find_adapter(bus):
    om = dbus.Interface(bus.get_object(BLUEZ_SERVICE, "/"), DBUS_OM_IFACE)
    for path, props in om.GetManagedObjects().items():
        if LE_ADV_MANAGER_IFACE in props:
            return path
    return None


# ─── Advertisement ────────────────────────────────────────────
class PwngAdvert(dbus.service.Object):
    def __init__(self, bus, index):
        self.path = f"/org/bluez/pwnagotchi/adv{index}"
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        return {
            "Type":         dbus.String("peripheral"),
            "ServiceUUIDs": dbus.Array([PWNG_SERVICE_UUID], signature="s"),
            "LocalName":    dbus.String("Pwnagotchi"),
            "Discoverable": dbus.Boolean(True),
            "IncludeTxPower": dbus.Boolean(True),
        }

    @dbus.service.method(LE_ADV_IFACE)
    def Release(self):
        pass


# ─── GATT Application ─────────────────────────────────────────
class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = "/"
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, svc):
        self.services.append(svc)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        res = {}
        for svc in self.services:
            res[svc.get_path()] = svc.get_properties()
            for c in svc.get_characteristics():
                res[c.get_path()] = c.get_properties()
        return res


# ─── GATT Service ─────────────────────────────────────────────
class PwngService(dbus.service.Object):
    def __init__(self, bus, index):
        self.path = f"/org/bluez/pwnagotchi/service{index}"
        self.uuid = PWNG_SERVICE_UUID
        self.chars = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {GATT_SERVICE_IFACE: {
            "UUID":    self.uuid,
            "Primary": dbus.Boolean(True),
            "Characteristics": dbus.Array(
                [c.get_path() for c in self.chars], signature="o"),
        }}

    def add_characteristic(self, c):
        self.chars.append(c)

    def get_characteristics(self):
        return self.chars

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        return self.get_properties()[GATT_SERVICE_IFACE]


# ─── JSON Characteristic (read + notify) ─────────────────────
class JsonCharacteristic(dbus.service.Object):
    def __init__(self, bus, index, service):
        self.path = service.path + f"/char{index}"
        self.uuid = CHAR_JSON_UUID
        self.value = dbus.Array([], signature="y")
        self.notifying = False
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {GATT_CHRC_IFACE: {
            "UUID":    self.uuid,
            "Service": self.path.rsplit("/", 1)[0],
            "Flags":   dbus.Array(["read", "notify"], signature="s"),
            "Descriptors": dbus.Array([], signature="o"),
        }}

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE, out_signature="ay")
    def ReadValue(self, options):
        return self.value

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        self.notifying = True

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        self.notifying = False

    @dbus.service.signal(DBUS_PROP_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    def update(self, json_str):
        encoded = [dbus.Byte(b) for b in json_str.encode("utf-8")]
        self.value = dbus.Array(encoded, signature="y")
        if self.notifying:
            self.PropertiesChanged(
                GATT_CHRC_IFACE,
                {"Value": self.value},
                []
            )


# ─── Plugin ───────────────────────────────────────────────────
class BleGarmin(plugins.Plugin):
    __author__      = "cypherfrog"
    __version__     = "1.1.0"
    __license__     = "GPL3"
    __description__ = "Pwnagotchi → Garmin Fenix 8 via BLE"

    def __init__(self):
        self._thread    = None
        self._loop      = None
        self._char      = None
        self._start     = time.time()
        self._state     = {
            "face": "(・ᴗ・)", "msg": "boot", "hs": 0, "shs": 0,
            "aps": 0, "ch": 1, "up": 0, "ep": 0, "temp": 0.0, "name": "cyphergotchi",
        }

    def on_loaded(self):
        if not DBUS_AVAILABLE:
            logging.error("[ble_garmin] Abhängigkeiten fehlen!")
            return
        self._thread = threading.Thread(target=self._ble_main, daemon=True)
        self._thread.start()
        logging.info("[ble_garmin] BLE Thread gestartet")

    def _ble_main(self):
        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            bus = dbus.SystemBus()
            adapter = find_adapter(bus)
            if not adapter:
                logging.error("[ble_garmin] Kein BLE-Adapter!"); return

            # Adapter konfigurieren
            a_obj   = bus.get_object(BLUEZ_SERVICE, adapter)
            a_props = dbus.Interface(a_obj, DBUS_PROP_IFACE)
            for k, v in [("Powered", True), ("Discoverable", True), ("Pairable", True)]:
                a_props.Set("org.bluez.Adapter1", k, dbus.Boolean(v))

            # GATT aufbauen
            app  = Application(bus)
            svc  = PwngService(bus, 0)
            char = JsonCharacteristic(bus, 0, svc)
            svc.add_characteristic(char)
            app.add_service(svc)
            self._char = char

            # Registrieren
            gatt_mgr = dbus.Interface(a_obj, GATT_MANAGER_IFACE)
            gatt_mgr.RegisterApplication(
                app.get_path(), {},
                reply_handler=lambda: logging.info("[ble_garmin] GATT registriert"),
                error_handler=lambda e: logging.error(f"[ble_garmin] GATT Fehler: {e}"),
            )

            adv     = PwngAdvert(bus, 0)
            adv_mgr = dbus.Interface(a_obj, LE_ADV_MANAGER_IFACE)
            adv_mgr.RegisterAdvertisement(
                adv.get_path(), {},
                reply_handler=lambda: logging.info("[ble_garmin] Advertisement aktiv"),
                error_handler=lambda e: logging.error(f"[ble_garmin] Adv Fehler: {e}"),
            )

            GLib.timeout_add_seconds(5, self._push)
            self._loop = GLib.MainLoop()
            self._loop.run()
        except Exception as e:
            logging.exception(f"[ble_garmin] {e}")

    def _push(self):
        if self._char is None:
            return True
        self._state["up"]   = int(time.time() - self._start)
        self._state["temp"] = self._cpu_temp()
        try:
            self._char.update(json.dumps(self._state, ensure_ascii=False))
        except Exception as e:
            logging.error(f"[ble_garmin] push: {e}")
        return True  # GLib wiederholen

    @staticmethod
    def _cpu_temp():
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return round(int(f.read()) / 1000.0, 1)
        except Exception:
            return 0.0

    # ── Event Hooks ───────────────────────────────────────────
    def on_ready(self, agent):
        self._state["name"] = agent.config()["main"].get("name", "pwnagotchi")
        self._state["msg"]  = "bereit"

    def on_ui_update(self, ui):
        self._state["face"] = str(ui.get("face") or "")
        self._state["msg"]  = str(ui.get("status") or ui.get("label") or "")

    def on_epoch(self, agent, epoch, stats):
        self._state["ep"] = int(epoch)
        self._state["hs"] = int(stats.get("total_handshakes", 0))

    def on_handshake(self, agent, filename, access_point, client_station):
        self._state["shs"] = self._state.get("shs", 0) + 1
        self._state["hs"]  = self._state.get("hs",  0) + 1

    def on_wifi_update(self, agent, access_points):
        self._state["aps"] = len(access_points)

    def on_channel_hop(self, agent, frequency):
        self._state["ch"] = frequency

    def on_sleep(self, agent):   self._state["msg"] = "schläft"
    def on_bored(self, agent):   self._state["msg"] = "gelangweilt"
    def on_sad(self, agent):     self._state["msg"] = "traurig"
    def on_excited(self, agent): self._state["msg"] = "aufgeregt!"

    def on_unloaded(self):
        if self._loop:
            self._loop.quit()
