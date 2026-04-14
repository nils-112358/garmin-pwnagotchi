"""
Pwnagotchi Plugin: ble_hrm.py
Tarnt den Pwnagotchi als BLE Heart Rate Monitor.
Garmin verbindet sich nativ — Pwnagotchi-Daten werden in HRM-Felder gemappt:
  - Heart Rate (uint8)  = Handshakes (session)
  - Energy Expended     = Handshakes (total)
  - RR-Interval         = APs in Reichweite

Installation:
  1. Nach /usr/local/share/pwnagotchi/custom-plugins/ble_hrm.py kopieren
  2. config.toml: main.plugins.ble_hrm.enabled = true
  3. sudo pip3 install dbus-python --break-system-packages
  4. sudo apt-get install python3-gi
  5. Neustart
"""

import pwnagotchi.plugins as plugins
import logging
import threading
import struct
import time

try:
    import dbus
    import dbus.service
    import dbus.mainloop.glib
    from gi.repository import GLib
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False
    logging.error("[ble_hrm] dbus-python / gi fehlt!")

# ─── BLE HRM UUIDs (offizielle Bluetooth SIG) ─────────────────
HRM_SERVICE_UUID   = "0000180d-0000-1000-8000-00805f9b34fb"
HRM_CHAR_UUID      = "00002a37-0000-1000-8000-00805f9b34fb"
BODY_SENSOR_UUID   = "00002a38-0000-1000-8000-00805f9b34fb"

BLUEZ_SERVICE        = "org.bluez"
GATT_MANAGER_IFACE   = "org.bluez.GattManager1"
DBUS_OM_IFACE        = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE      = "org.freedesktop.DBus.Properties"
GATT_SERVICE_IFACE   = "org.bluez.GattService1"
GATT_CHRC_IFACE      = "org.bluez.GattCharacteristic1"
LE_ADV_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
LE_ADV_IFACE         = "org.bluez.LEAdvertisement1"


def find_adapter(bus):
    om = dbus.Interface(bus.get_object(BLUEZ_SERVICE, "/"), DBUS_OM_IFACE)
    for path, props in om.GetManagedObjects().items():
        if LE_ADV_MANAGER_IFACE in props:
            return path
    return None


# ─── Advertisement ────────────────────────────────────────────
class HrmAdvert(dbus.service.Object):
    def __init__(self, bus, index):
        self.path = f"/org/bluez/pwnagotchi/adv{index}"
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        return {
            "Type":         dbus.String("peripheral"),
            "ServiceUUIDs": dbus.Array([HRM_SERVICE_UUID], signature="s"),
            "LocalName":    dbus.String("PWN-HRM"),  # erscheint als HR-Sensor
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
class HrmService(dbus.service.Object):
    def __init__(self, bus, index):
        self.path = f"/org/bluez/pwnagotchi/service{index}"
        self.uuid = HRM_SERVICE_UUID
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


# ─── Heart Rate Measurement Characteristic ────────────────────
# Flags Byte:
#   Bit 0: HR Format (0=uint8, 1=uint16)
#   Bit 3: Energy Expended present
#   Bit 4: RR-Interval present
# Format: [flags, hr_uint8, energy_lo, energy_hi, rr_lo, rr_hi]
class HrmCharacteristic(dbus.service.Object):
    def __init__(self, bus, index, service):
        self.path = service.path + f"/char{index}"
        self.uuid = HRM_CHAR_UUID
        self.notifying = False
        self._value = self._encode(0, 0, 0)
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {GATT_CHRC_IFACE: {
            "UUID":    self.uuid,
            "Service": dbus.ObjectPath(self.path.rsplit("/", 1)[0]),
            "Flags":   dbus.Array(["read", "notify"], signature="s"),
            "Descriptors": dbus.Array([], signature="o"),
        }}

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE, out_signature="ay")
    def ReadValue(self, options):
        return self._value

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        self.notifying = True
        logging.info("[ble_hrm] Garmin connected & notifying")

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        self.notifying = False
        logging.info("[ble_hrm] Garmin disconnected")

    @dbus.service.signal(DBUS_PROP_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    @staticmethod
    def _encode(session_hs, total_hs, aps):
        """
        session_hs → Heart Rate (uint8, max 255)
        total_hs   → Energy Expended (uint16, max 65535)
        aps        → RR-Interval (uint16, in 1/1024s Einheiten — wir zweckentfremden das)
        """
        flags = 0b00011000  # Energy Expended + RR-Interval present, HR=uint8
        hr    = min(session_hs, 255)
        ee    = min(total_hs, 65535)
        rr    = min(aps * 100, 65535)  # skaliert damit Wert sichtbar ist
        raw   = struct.pack("<BBHh", flags, hr, ee, rr)
        return dbus.Array([dbus.Byte(b) for b in raw], signature="y")

    def update(self, session_hs, total_hs, aps):
        self._value = self._encode(session_hs, total_hs, aps)
        if self.notifying:
            self.PropertiesChanged(
                GATT_CHRC_IFACE,
                {"Value": self._value},
                []
            )


# ─── Body Sensor Location Characteristic (optional, aber korrekt) ─
class BodySensorCharacteristic(dbus.service.Object):
    def __init__(self, bus, index, service):
        self.path = service.path + f"/char{index}"
        self.uuid = BODY_SENSOR_UUID
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {GATT_CHRC_IFACE: {
            "UUID":    self.uuid,
            "Service": dbus.ObjectPath(self.path.rsplit("/", 1)[0]),
            "Flags":   dbus.Array(["read"], signature="s"),
            "Descriptors": dbus.Array([], signature="o"),
        }}

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE, out_signature="ay")
    def ReadValue(self, options):
        # 0=Other, 1=Chest, 2=Wrist, 3=Finger, 4=Hand, 5=Ear, 6=Foot
        return dbus.Array([dbus.Byte(0)], signature="y")


# ─── Plugin ───────────────────────────────────────────────────
class BleHrm(plugins.Plugin):
    __author__      = "cypherfrog"
    __version__     = "1.0.0"
    __license__     = "GPL3"
    __description__ = "Pwnagotchi → Garmin Fenix 8 via BLE HRM-Profil"

    def __init__(self):
        self._thread  = None
        self._loop    = None
        self._char    = None
        self._state   = {"session_hs": 0, "total_hs": 0, "aps": 0}

    def on_loaded(self):
        if not DBUS_AVAILABLE:
            logging.error("[ble_hrm] Abhängigkeiten fehlen!")
            return
        self._thread = threading.Thread(target=self._ble_main, daemon=True)
        self._thread.start()
        logging.info("[ble_hrm] BLE HRM Thread gestartet")

    def _ble_main(self):
        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            bus = dbus.SystemBus()
            adapter = find_adapter(bus)
            if not adapter:
                logging.error("[ble_hrm] Kein BLE-Adapter!"); return

            a_obj   = bus.get_object(BLUEZ_SERVICE, adapter)
            a_props = dbus.Interface(a_obj, DBUS_PROP_IFACE)
            for k, v in [("Powered", True), ("Discoverable", True), ("Pairable", True)]:
                a_props.Set("org.bluez.Adapter1", k, dbus.Boolean(v))

            app  = Application(bus)
            svc  = HrmService(bus, 0)
            char = HrmCharacteristic(bus, 0, svc)
            body = BodySensorCharacteristic(bus, 1, svc)
            svc.add_characteristic(char)
            svc.add_characteristic(body)
            app.add_service(svc)
            self._char = char

            gatt_mgr = dbus.Interface(a_obj, GATT_MANAGER_IFACE)
            gatt_mgr.RegisterApplication(
                app.get_path(), {},
                reply_handler=lambda: logging.info("[ble_hrm] GATT registriert"),
                error_handler=lambda e: logging.error(f"[ble_hrm] GATT Fehler: {e}"),
            )

            adv     = HrmAdvert(bus, 0)
            adv_mgr = dbus.Interface(a_obj, LE_ADV_MANAGER_IFACE)
            adv_mgr.RegisterAdvertisement(
                adv.get_path(), {},
                reply_handler=lambda: logging.info("[ble_hrm] Advertisement aktiv"),
                error_handler=lambda e: logging.error(f"[ble_hrm] Adv Fehler: {e}"),
            )

            GLib.timeout_add_seconds(5, self._push)
            self._loop = GLib.MainLoop()
            self._loop.run()
        except Exception as e:
            logging.exception(f"[ble_hrm] {e}")

    def _push(self):
        if self._char is None:
            return True
        s = self._state
        try:
            self._char.update(s["session_hs"], s["total_hs"], s["aps"])
        except Exception as e:
            logging.error(f"[ble_hrm] push: {e}")
        return True

    # ── Event Hooks ───────────────────────────────────────────
    def on_handshake(self, agent, filename, access_point, client_station):
        self._state["session_hs"] = self._state.get("session_hs", 0) + 1
        self._state["total_hs"]   = self._state.get("total_hs",   0) + 1

    def on_epoch(self, agent, epoch, stats):
        self._state["total_hs"] = int(stats.get("total_handshakes", 0))

    def on_wifi_update(self, agent, access_points):
        self._state["aps"] = len(access_points)

    def on_unloaded(self):
        if self._loop:
            self._loop.quit()
