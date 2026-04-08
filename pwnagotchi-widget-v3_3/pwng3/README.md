# Pwnagotchi → Garmin Fenix 8 Widget

## Ordnerstruktur

```
pwnagotchi-widget/
├── PwnagotchiWidget/          ← Garmin Connect IQ Projekt (in VSC öffnen)
│   ├── monkey.jungle
│   ├── manifest.xml
│   ├── source/
│   │   ├── PwnagotchiApp.mc   ← BLE + Logik
│   │   └── PwnagotchiView.mc  ← Anzeige auf der Uhr
│   └── resources/
│       ├── drawables/
│       │   ├── launcher_icon.png
│       │   └── drawables.xml
│       └── strings/
│           └── strings.xml
└── pwnagotchi_plugin/
    └── ble_garmin.py          ← auf den Pwnagotchi kopieren
```

---

## 1. Garmin Widget installieren

### Voraussetzungen
- [VS Code](https://code.visualstudio.com/)
- [Monkey C Extension](https://marketplace.visualstudio.com/items?itemName=garmin.monkey-c) installieren
- [Connect IQ SDK](https://developer.garmin.com/connect-iq/sdk/) herunterladen

### Schritte
1. VSC öffnen → `File > Open Folder` → `PwnagotchiWidget` Ordner wählen
2. Beim ersten Öffnen fragt VSC nach dem SDK-Pfad → auf deinen SDK-Ordner zeigen
3. Fenix 8 per USB verbinden
4. `Ctrl+Shift+P` → `Monkey C: Build and Install` wählen
5. Gerät auswählen: `fenix847mm` oder `fenix851mm`

---

## 2. Pwnagotchi Plugin installieren

```bash
# Datei auf den Pwnagotchi kopieren (per SSH oder direkt auf SD-Karte)
scp pwnagotchi_plugin/ble_garmin.py pi@pwnagotchi.local:/etc/pwnagotchi/custom-plugins/

# Abhängigkeiten installieren
ssh pi@pwnagotchi.local
sudo pip3 install dbus-python --break-system-packages
sudo apt-get install python3-gi -y

# In /etc/pwnagotchi/config.toml eintragen:
#   main.plugins.ble_garmin.enabled = true

# Pwnagotchi neu starten
sudo systemctl restart pwnagotchi
```

---

## 3. Verbindung herstellen

1. Pwnagotchi läuft → advertised sich als `"Pwnagotchi"` per BLE
2. Widget auf der Fenix 8 starten (Widget-Menü)
3. Uhr sucht automatisch → verbindet sich → grüner Punkt erscheint
4. Daten werden alle 5 Sekunden aktualisiert

---

## Was die Uhr anzeigt

| Feld | Beschreibung |
|------|-------------|
| 😐 Gesicht | Aktueller Pwnagotchi-Ausdruck |
| Status | Aktuelle Nachricht |
| HS TOTAL | Alle Handshakes gesamt |
| SESSION | Handshakes dieser Session |
| APs | WLAN-Netze in Reichweite |
| CH | Aktueller Channel |
| EPOCH | Aktuelle Epoch |
| TEMP | CPU-Temperatur in °C |
| UP | Uptime (h/m/s) |
| 🟢/🔴 | BLE Verbindungsstatus |
