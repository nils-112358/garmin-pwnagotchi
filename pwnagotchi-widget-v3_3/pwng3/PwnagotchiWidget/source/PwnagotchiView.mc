import Toybox.WatchUi;
import Toybox.Graphics;
import Toybox.Lang;

class PwnagotchiView extends WatchUi.View {

    function initialize() {
        View.initialize();
    }

    function onLayout(dc) {}
    function onShow()    {}
    function onHide()    {}

    function onUpdate(dc) {
        var w  = dc.getWidth();
        var h  = dc.getHeight();
        var cx = w / 2;

        // Hintergrund
        dc.setColor(Graphics.COLOR_BLACK, Graphics.COLOR_BLACK);
        dc.clear();

        // Verbindungs-Dot (oben rechts)
        dc.setColor(gConnected ? Graphics.COLOR_GREEN : Graphics.COLOR_RED,
                    Graphics.COLOR_TRANSPARENT);
        dc.fillCircle(w - 20, 22, 7);

        // Name  (y = 5% von h)
        var yName = h * 5 / 100;
        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, yName, Graphics.FONT_XTINY,
                    gName.toUpper(), Graphics.TEXT_JUSTIFY_CENTER);

        // Gesicht (y = 12% von h)
        var yFace = h * 12 / 100;
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, yFace, Graphics.FONT_LARGE,
                    gFace, Graphics.TEXT_JUSTIFY_CENTER);

        // Status-Nachricht (y = 33% von h)
        var yMsg = h * 33 / 100;
        dc.setColor(Graphics.COLOR_YELLOW, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, yMsg, Graphics.FONT_SMALL,
                    truncate(gMessage, 22), Graphics.TEXT_JUSTIFY_CENTER);

        // Trennlinie (y = 42% von h)
        var ySep1 = h * 42 / 100;
        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawLine(20, ySep1, w - 20, ySep1);

        // Stats-Bereich: 3 Zeilen gleichmäßig auf 44%–84% verteilt
        var col1  = w / 4;
        var col2  = w * 3 / 4;
        var yRow1 = h * 44 / 100;
        var yRow2 = h * 58 / 100;
        var yRow3 = h * 72 / 100;

        drawStat(dc, col1, yRow1, "HS TOTAL", gHandshakes.toString());
        drawStat(dc, col2, yRow1, "SESSION",  gSession.toString());
        drawStat(dc, col1, yRow2, "APs",      gAps.toString());
        drawStat(dc, col2, yRow2, "CH",       gChannel.toString());
        drawStat(dc, col1, yRow3, "EPOCH",    gEpoch.toString());
        drawStat(dc, col2, yRow3, "TEMP",     gTemp + "C");

        // Trennlinie (y = 86% von h)
        var ySep2 = h * 86 / 100;
        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawLine(20, ySep2, w - 20, ySep2);

        // Uptime (y = 88% von h)
        var yUp = h * 88 / 100;
        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, yUp, Graphics.FONT_XTINY,
                    "UP " + formatUptime(gUptime), Graphics.TEXT_JUSTIFY_CENTER);
    }

    hidden function drawStat(dc, x, y, label, value) {
        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(x, y, Graphics.FONT_XTINY, label, Graphics.TEXT_JUSTIFY_CENTER);
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(x, y + 16, Graphics.FONT_SMALL, value, Graphics.TEXT_JUSTIFY_CENTER);
    }

    hidden function truncate(s, maxLen) {
        if (s == null)            { return ""; }
        if (s.length() <= maxLen) { return s;  }
        return s.substring(0, maxLen - 1) + "~";
    }

    hidden function formatUptime(seconds) {
        var hh = seconds / 3600;
        var mm = (seconds % 3600) / 60;
        var ss = seconds % 60;
        return Lang.format("$1$h $2$m $3$s",
                           [hh, mm.format("%02d"), ss.format("%02d")]);
    }
}
