import Toybox.BluetoothLowEnergy;
import Toybox.WatchUi;
import Toybox.Timer;
import Toybox.Lang;

class PwnagotchiBleDelegate extends BluetoothLowEnergy.BleDelegate {

    hidden var mDevice = null;
    hidden var mChar   = null;
    hidden var mTimer  = null;

    function initialize() {
        BleDelegate.initialize();
        mTimer = new Timer.Timer();
        // Methode muss Void zurückgeben → korrekte Signatur
        mTimer.start(method(:onPollTimer), 5000, true);
    }

    // ── Scan ──────────────────────────────────────────────────
    function onScanResults(scanResults) {
        // ScanIterator.next() gibt ScanResult oder null zurück
        // Cast über 'as' nötig damit der Typ-Checker mitspielt
        var result = scanResults.next() as BluetoothLowEnergy.ScanResult;
        while (result != null) {
            var name = result.getDeviceName();
            if (name != null && name.equals("Pwnagotchi")) {
                BluetoothLowEnergy.setScanState(BluetoothLowEnergy.SCAN_STATE_OFF);
                gMessage = "Verbinde...";
                BluetoothLowEnergy.pairDevice(result);
                WatchUi.requestUpdate();
                return;
            }
            result = scanResults.next() as BluetoothLowEnergy.ScanResult;
        }
    }

    // ── Verbindungsstatus ─────────────────────────────────────
    function onConnectedStateChanged(device, state) {
        if (state == BluetoothLowEnergy.CONNECTION_STATE_CONNECTED) {
            mDevice    = device;
            gConnected = true;
            gMessage   = "Verbunden";

            var svc = device.getService(PWNG_SVC_UUID);
            if (svc != null) {
                mChar = svc.getCharacteristic(PWNG_CHAR_UUID);
                if (mChar != null) {
                    var cccd = mChar.getDescriptor(BluetoothLowEnergy.cccdUuid());
                    if (cccd != null) {
                        cccd.requestWrite([0x01, 0x00]b);
                    }
                    mChar.requestRead();
                }
            }
        } else {
            mDevice    = null;
            mChar      = null;
            gConnected = false;
            gMessage   = "Getrennt – suche...";
            BluetoothLowEnergy.setScanState(BluetoothLowEnergy.SCAN_STATE_SCANNING);
        }
        WatchUi.requestUpdate();
    }

    // ── Notify vom Gerät ──────────────────────────────────────
    function onCharacteristicChanged(char, value) {
        parseStatusJson(value);
        WatchUi.requestUpdate();
    }

    // ── Read-Antwort ──────────────────────────────────────────
    function onCharacteristicRead(char, status, value) {
        if (status == 0) {
            parseStatusJson(value);
            WatchUi.requestUpdate();
        }
    }

    // ── Poll alle 5s (Void-Rückgabe!) ─────────────────────────
    function onPollTimer() as Void {
        if (gConnected && mChar != null) {
            mChar.requestRead();
        }
    }

    // ── JSON parsen ───────────────────────────────────────────
    hidden function parseStatusJson(bytes) {
        var str = bytes.toString();
        if (str == null || str.length() == 0) { return; }

        var v;
        v = extractStr(str, "face");  if (v != null && v.length() > 0) { gFace       = v; }
        v = extractStr(str, "msg");   if (v != null && v.length() > 0) { gMessage    = v; }
        v = extractStr(str, "temp");  if (v != null && v.length() > 0) { gTemp       = v; }
        v = extractStr(str, "name");  if (v != null && v.length() > 0) { gName       = v; }

        var n;
        n = extractInt(str, "hs");   if (n != null) { gHandshakes = n; }
        n = extractInt(str, "shs");  if (n != null) { gSession    = n; }
        n = extractInt(str, "aps");  if (n != null) { gAps        = n; }
        n = extractInt(str, "ch");   if (n != null) { gChannel    = n; }
        n = extractInt(str, "up");   if (n != null) { gUptime     = n; }
        n = extractInt(str, "ep");   if (n != null) { gEpoch      = n; }
    }

    hidden function extractStr(json, key) {
        var pattern = "\"" + key + "\":\"";
        var idx = json.find(pattern);
        if (idx == null) { return null; }
        var start = idx + pattern.length();
        var end   = json.find("\"", start);
        if (end == null) { return null; }
        return json.substring(start, end);
    }

    hidden function extractInt(json, key) {
        var pattern = "\"" + key + "\":";
        var idx = json.find(pattern);
        if (idx == null) { return null; }
        var start = idx + pattern.length();
        var eC = json.find(",", start);
        var eB = json.find("}", start);
        var end;
        if      (eC == null) { end = eB; }
        else if (eB == null) { end = eC; }
        else                 { end = (eC < eB) ? eC : eB; }
        if (end == null) { return null; }
        var s = json.substring(start, end);
        if (s == null) { return null; }
        return s.toNumber();
    }
}
