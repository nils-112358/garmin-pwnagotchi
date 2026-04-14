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
logging.error(”[ble_power] dbus-python / gi fehlt!”)

# ── Cycling Power Service & Characteristics (Bluetooth SIG Standard) ──

POWER_SERVICE_UUID   = “00001818-0000-1000-8000-00805f9b34fb”
POWER_CHAR_UUID      = “00002a63-0000-1000-8000-00805f9b34fb”  # Cycling Power Measurement
SENSOR_LOC_UUID      = “00002a5d-0000-1000-8000-00805f9b34fb”  # Sensor Location (Pflicht)
POWER_FEAT_UUID      = “00002a65-0000-1000-8000-00805f9b34fb”  # Cycling Power Feature (Pflicht)

# Appearance: 0x0480 = 1152 = “Cycling Power Sensor”

# Pflicht damit Garmin den Sensor in der BLE-Suche erkennt!

APPEARANCE_CYCLING_POWER = 0x0480

BLUEZ_SERVICE        = “org.bluez”
GATT_MANAGER_IFACE   = “org.bluez.GattManager1”
DBUS_OM_IFACE        = “org.freedesktop.DBus.ObjectManager”
DBUS_PROP_IFACE      = “org.freedesktop.DBus.Properties”
GATT_SERVICE_IFACE   = “org.bluez.GattService1”
GATT_CHRC_IFACE      = “org.bluez.GattCharacteristic1”
LE_ADV_MANAGER_IFACE = “org.bluez.LEAdvertisingManager1”
LE_ADV_IFACE         = “org.bluez.LEAdvertisement1”

def find_adapter(bus):
om = dbus.Interface(bus.get_object(BLUEZ_SERVICE, “/”), DBUS_OM_IFACE)
for path, props in om.GetManagedObjects().items():
if LE_ADV_MANAGER_IFACE in props:
return path
return None

# ── Advertisement ──────────────────────────────────────────────────────────────

class PowerAdvert(dbus.service.Object):
def **init**(self, bus, index):
self.path = f”/org/bluez/pwnagotchi/adv{index}”
dbus.service.Object.**init**(self, bus, self.path)

```
def get_path(self):
    return dbus.ObjectPath(self.path)

@dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
def GetAll(self, iface):
    return {
        "Type":         dbus.String("peripheral"),
        "ServiceUUIDs": dbus.Array([POWER_SERVICE_UUID], signature="s"),
        "LocalName":    dbus.String("PWN-POWER"),
        # Appearance 0x0480 als Little-Endian 2-Byte im ManufacturerData
        # Garmin wertet das Appearance-Flag aus um den Sensor-Typ zu bestimmen
        "Appearance":   dbus.UInt16(APPEARANCE_CYCLING_POWER),
        "Discoverable": dbus.Boolean(True),
        "IncludeTxPower": dbus.Boolean(True),
    }

@dbus.service.method(LE_ADV_IFACE)
def Release(self):
    pass
```

# ── GATT Application (Object Manager) ─────────────────────────────────────────

class Application(dbus.service.Object):
def **init**(self, bus):
self.path = “/”
self.services = []
dbus.service.Object.**init**(self, bus, self.path)

```
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
```

# ── Cycling Power Service ──────────────────────────────────────────────────────

class PowerService(dbus.service.Object):
def **init**(self, bus, index):
self.path = f”/org/bluez/pwnagotchi/service{index}”
self.uuid = POWER_SERVICE_UUID
self.chars = []
dbus.service.Object.**init**(self, bus, self.path)

```
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
```

# ── Cycling Power Measurement Characteristic (0x2A63) ─────────────────────────

class PowerMeasurementCharacteristic(dbus.service.Object):
“””
Format laut Bluetooth SIG Spec (Cycling Power Measurement, 0x2A63):
Bytes 0-1 : Flags        (uint16, LE) – 0x0000 = nur Instantaneous Power
Bytes 2-3 : Inst. Power  (sint16, LE) – Watt, hier = session_hs

```
Das ist das Minimum das Garmin akzeptiert.
"""

def __init__(self, bus, index, service):
    self.path = service.path + f"/char{index}"
    self.uuid = POWER_CHAR_UUID
    self.notifying = False
    self._value = self._encode(0)
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

@dbus.service.method(GATT_CHRC_IFACE)
def StopNotify(self):
    self.notifying = False

@dbus.service.signal(DBUS_PROP_IFACE, signature="sa{sv}as")
def PropertiesChanged(self, interface, changed, invalidated):
    pass

@staticmethod
def _encode(session_hs):
    # Flags = 0x0000: nur Instantaneous Power vorhanden, kein Kurbel-/Rad-Daten
    # Power = session_hs als sint16, geclampt auf 0–32767 (Garmin zeigt keine neg. Watt)
    flags = 0x0000
    power = max(0, min(session_hs, 32767))
    raw = struct.pack("<Hh", flags, power)
    return dbus.Array([dbus.Byte(b) for b in raw], signature="y")

def update(self, session_hs):
    self._value = self._encode(session_hs)
    if self.notifying:
        self.PropertiesChanged(
            GATT_CHRC_IFACE,
            {"Value": self._value},
            []
        )
```

# ── Sensor Location Characteristic (0x2A5D) ───────────────────────────────────

class SensorLocationCharacteristic(dbus.service.Object):
“””
Pflicht-Characteristic im Cycling Power Service.
Wert 0 = “Other” – ausreichend damit Garmin den Service akzeptiert.
“””

```
def __init__(self, bus, index, service):
    self.path = service.path + f"/char{index}"
    self.uuid = SENSOR_LOC_UUID
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
    return dbus.Array([dbus.Byte(0)], signature="y")  # 0 = "Other"
```

# ── Cycling Power Feature Characteristic (0x2A65) ─────────────────────────────

class PowerFeatureCharacteristic(dbus.service.Object):
“””
Pflicht-Characteristic. uint32 Bitfeld – 0x00000000 = keine Extras.
“””

```
def __init__(self, bus, index, service):
    self.path = service.path + f"/char{index}"
    self.uuid = POWER_FEAT_UUID
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
    # uint32 LE: 0x00000000 = keine optionalen Features
    raw = struct.pack("<I", 0x00000000)
    return dbus.Array([dbus.Byte(b) for b in raw], signature="y")
```

# ── Haupt-Plugin ───────────────────────────────────────────────────────────────

class BlePower(plugins.Plugin):
**author**      = “pwnagotchi-community”
**version**     = “1.0.0”
**license**     = “GPL3”
**description** = “Gibt sich als BLE Cycling Power Meter aus; session_hs → Watt”

```
def __init__(self):
    self._thread = None
    self._loop   = None
    self._char   = None   # PowerMeasurementCharacteristic
    self._state  = {"session_hs": 0, "total_hs": 0, "aps": 0}

def on_loaded(self):
    if not DBUS_AVAILABLE:
        logging.error("[ble_power] Abhängigkeiten fehlen – Plugin deaktiviert")
        return
    logging.info("[ble_power] Starte BLE Cycling Power Server...")
    self._thread = threading.Thread(target=self._ble_main, daemon=True)
    self._thread.start()

def _ble_main(self):
    try:
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus     = dbus.SystemBus()
        adapter = find_adapter(bus)
        if not adapter:
            logging.error("[ble_power] Kein BLE-Adapter gefunden!")
            return

        a_obj   = bus.get_object(BLUEZ_SERVICE, adapter)
        a_props = dbus.Interface(a_obj, DBUS_PROP_IFACE)
        for k, v in [("Powered", True), ("Discoverable", True), ("Pairable", True)]:
            a_props.Set("org.bluez.Adapter1", k, dbus.Boolean(v))

        # Service + Characteristics aufbauen
        app  = Application(bus)
        svc  = PowerService(bus, 0)

        # Reihenfolge wichtig: Measurement zuerst (Index 0)
        char = PowerMeasurementCharacteristic(bus, 0, svc)
        loc  = SensorLocationCharacteristic(bus, 1, svc)
        feat = PowerFeatureCharacteristic(bus, 2, svc)

        svc.add_characteristic(char)
        svc.add_characteristic(loc)
        svc.add_characteristic(feat)
        app.add_service(svc)

        self._char = char  # Referenz für _push

        # GATT Application registrieren
        gatt_mgr = dbus.Interface(a_obj, GATT_MANAGER_IFACE)
        gatt_mgr.RegisterApplication(
            app.get_path(), {},
            reply_handler=lambda: logging.info("[ble_power] GATT App registriert"),
            error_handler=lambda e: logging.error(f"[ble_power] GATT Fehler: {e}")
        )

        # Advertisement mit Appearance 0x0480 registrieren
        adv     = PowerAdvert(bus, 0)
        adv_mgr = dbus.Interface(a_obj, LE_ADV_MANAGER_IFACE)
        adv_mgr.RegisterAdvertisement(
            adv.get_path(), {},
            reply_handler=lambda: logging.info("[ble_power] Advertisement aktiv (Appearance=0x0480)"),
            error_handler=lambda e: logging.error(f"[ble_power] Advertisement Fehler: {e}")
        )

        GLib.timeout_add_seconds(5, self._push)
        self._loop = GLib.MainLoop()
        self._loop.run()

    except Exception as e:
        logging.exception(f"[ble_power] {e}")

def _push(self):
    if self._char is None:
        return True
    try:
        self._char.update(self._state["session_hs"])
    except Exception as e:
        logging.warning(f"[ble_power] Push-Fehler: {e}")
    return True  # GLib Timer wiederholen

# ── Pwnagotchi Hooks ──────────────────────────────────────────────────────

def on_handshake(self, agent, filename, access_point, client_station):
    self._state["session_hs"] += 1
    self._state["total_hs"]   += 1
    # Sofort pushen statt auf den 5s-Timer warten
    if self._char:
        try:
            self._char.update(self._state["session_hs"])
        except Exception:
            pass

def on_wifi_update(self, agent, access_points):
    self._state["aps"] = len(access_points)

def on_epoch(self, agent, epoch, stats):
    # total_hs aus Stats synchronisieren (nach Neustart korrekt)
    try:
        self._state["total_hs"] = int(stats.get("total_handshakes", 0))
    except Exception:
        pass

def on_unloaded(self):
    if self._loop:
        self._loop.quit()
    logging.info("[ble_power] Plugin entladen")
```
