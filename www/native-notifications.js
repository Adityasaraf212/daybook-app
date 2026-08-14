(function () {
  "use strict";

  function isNative() {
    return !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());
  }

  var NS = "daybook_";
  var DEFAULTS = {
    morning: { enabled: true, time: "08:00" },
    noon: { enabled: true, time: "14:00" },
    night: { enabled: true, time: "21:00" },
  };

  function getSettings() {
    try {
      var raw = localStorage.getItem(NS + "db3_notifs");
      return raw ? JSON.parse(raw) : DEFAULTS;
    } catch (e) {
      return DEFAULTS;
    }
  }

  async function scheduleAll() {
    if (!isNative()) return;
    var LocalNotifications = window.Capacitor.Plugins && window.Capacitor.Plugins.LocalNotifications;
    if (!LocalNotifications) return;

    var perm = await LocalNotifications.requestPermissions();
    if (perm.display !== "granted") return;

    // Clear and re-lay the three daily alarms every time settings might have changed.
    await LocalNotifications.cancel({ notifications: [{ id: 1 }, { id: 2 }, { id: 3 }] });

    var s = getSettings();
    var defs = [
      { id: 1, key: "morning", title: "Today's list", body: "Check what's on today in Daybook — or log it if it's empty." },
      { id: 2, key: "noon", title: "Midday check-in", body: "How's today going? Open Daybook to update your progress." },
      { id: 3, key: "night", title: "Today's report", body: "See how today wrapped up in Daybook." },
    ];

    var toSchedule = [];
    defs.forEach(function (d) {
      var conf = s[d.key];
      if (!conf || !conf.enabled) return;
      var parts = (conf.time || "08:00").split(":");
      var hh = parseInt(parts[0], 10), mm = parseInt(parts[1], 10);
      toSchedule.push({
        id: d.id,
        title: d.title,
        body: d.body,
        schedule: { on: { hour: hh, minute: mm }, allowWhileIdle: true },
      });
    });

    if (toSchedule.length) await LocalNotifications.schedule({ notifications: toSchedule });
  }

  // Reschedule on load, and again any time the app comes back to the foreground
  // (covers the case where notification times were just changed in Settings).
  scheduleAll();
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) scheduleAll();
  });
})();
