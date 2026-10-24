/* NSF Restricted Entities Guide — checklist progress, stored in this browser only. */
(function () {
  "use strict";
  var boxes = document.querySelectorAll(".check-item input[type=checkbox]");
  if (!boxes.length) return;

  var KEY = "nsf-re-checklist";
  var saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { saved = {}; }

  function updateProgress() {
    document.querySelectorAll(".check-group").forEach(function (g) {
      var all = g.querySelectorAll("input[type=checkbox]");
      var done = g.querySelectorAll("input:checked");
      var p = g.querySelector(".progress");
      if (p) p.textContent = done.length + " of " + all.length + " complete";
    });
  }

  boxes.forEach(function (b) {
    if (saved[b.id]) b.checked = true;
    b.addEventListener("change", function () {
      saved[b.id] = b.checked;
      try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) {}
      updateProgress();
    });
  });

  updateProgress();
})();
