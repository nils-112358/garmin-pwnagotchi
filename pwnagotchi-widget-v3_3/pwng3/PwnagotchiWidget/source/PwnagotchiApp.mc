import Toybox.Application;
import Toybox.WatchUi;
import Toybox.BluetoothLowEnergy;
import Toybox.Lang;

// ── Globaler State ────────────────────────────────────────────
var gFace       = "(・ᴗ・)";
var gMessage    = "Suche...";
var gHandshakes = 0;
var gSession    = 0;
var gAps        = 0;
var gChannel    = 0;
var gUptime     = 0;
var gEpoch      = 0;
var gTemp       = "0.0";
var gName       = "pwnagotchi";
var gConnected  = false;

// ── UUIDs ─────────────────────────────────────────────────────
// longToUuid(highLong, lowLong) → 128-bit UUID aus 2x 64-bit
// Service:  12345678-1234-1234-1234-123456789abc
// Char:     12345678-1234-1234-1234-123456789ab0
const PWNG_SVC_UUID  = BluetoothLowEnergy.longToUuid(0x1234567812341234l, 0x1234123456789ABCl);
const PWNG_CHAR_UUID = BluetoothLowEnergy.longToUuid(0x1234567812341234l, 0x1234123456789AB0l);

class PwnagotchiApp extends Application.AppBase {

    hidden var mDelegate;

    function initialize() {
        AppBase.initialize();
    }

    function onStart(state) {
        mDelegate = new PwnagotchiBleDelegate();
        BluetoothLowEnergy.setDelegate(mDelegate);
        BluetoothLowEnergy.setScanState(BluetoothLowEnergy.SCAN_STATE_SCANNING);
    }

    function onStop(state) {
        BluetoothLowEnergy.setScanState(BluetoothLowEnergy.SCAN_STATE_OFF);
    }

    function getInitialView() {
        return [new PwnagotchiView()];
    }
}
