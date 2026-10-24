/* NSF Restricted Entities Guide — search engine, no dependencies.
 *
 * Two data files back this page. assets/lists.js is small and loads with the
 * page: it carries the list metadata, the per-list counts and the totals, so
 * the filters and the result counts work immediately. assets/entities.js holds
 * the search index and is fetched only when a search actually starts, which
 * keeps the first paint of this page in the tens of kilobytes rather than the
 * megabytes the index weighs. Injecting a script element rather than fetching
 * JSON keeps the page working when it is opened straight from the file system.
 */
(function () {
  "use strict";

  var LISTS = window.NSF_LISTS;
  var $q = document.getElementById("q");
  if (!LISTS || !$q) return; // not the search page, or metadata failed to load

  var $results = document.getElementById("results");
  var $meta = document.getElementById("results-meta");
  var $filters = document.getElementById("agency-filters");
  var $statusFilters = document.getElementById("status-filters");
  var $go = document.getElementById("go");

  var PAGE = 40;
  var shown = PAGE;
  var entities = null;        // filled once the index has loaded
  var loading = false;
  var loadFailed = false;

  var AGENCIES = [
    ["all", "All agencies"],
    ["DoW", "Dept. of War"],
    ["Commerce/BIS", "Commerce (BIS)"],
    ["Treasury/OFAC", "Treasury (OFAC)"],
    ["State", "State"],
    ["FCC", "FCC"],
    ["DHS", "DHS"],
    ["CBP", "CBP"]
  ];
  var activeAgency = "all";
  var activeList = null;   // restrict to one list id
  var activeStatus = "all"; // all | active | historical

  var BADGE_CLASS = {
    "DoW": "dow", "Commerce/BIS": "bis", "Treasury/OFAC": "ofac",
    "State/DDTC": "state", "State/ISN": "state", "FCC": "fcc",
    "DHS": "dhs", "CBP": "cbp"
  };

  /* ---- helpers ---- */

  function agencyFamily(short) {
    return short.indexOf("State") === 0 ? "State" : short;
  }

  function norm(s) {
    if (!s) return "";
    s = s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
    s = s.replace(/[^a-z0-9\s]/g, " ");
    return s.replace(/\s+/g, " ").trim();
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function num(n) { return n.toLocaleString(); }

  function isActive(rec) { return rec.s === "Active"; }
  function isHistorical(rec) { return !!rec.s && rec.s !== "Active"; }

  /* ---- loading the index on demand ---- */

  // The asset version is carried on this script's own URL, so the index is
  // requested with the same cache-busting string the build stamped on it.
  var VERSION = (function () {
    var src = (document.currentScript && document.currentScript.src) || "";
    var m = src.match(/[?&]v=([^&]+)/);
    return m ? m[1] : "";
  })();

  function ensureIndex(then) {
    if (entities) { then(); return; }
    if (loadFailed) { then(); return; }
    if (loading) return;
    loading = true;
    renderLoading();
    var s = document.createElement("script");
    s.src = "assets/entities.js" + (VERSION ? "?v=" + encodeURIComponent(VERSION) : "");
    s.onload = function () {
      loading = false;
      entities = window.NSF_ENTITIES || null;
      if (!entities) { loadFailed = true; } else { prepare(); }
      then();
    };
    s.onerror = function () {
      loading = false;
      loadFailed = true;
      then();
    };
    document.head.appendChild(s);
  }

  function renderLoading() {
    $meta.textContent = "Loading the search index…";
    $results.innerHTML = '<p class="loading-note">Fetching ' +
      num(LISTS.totals.entries) + " entries. This happens once per visit.</p>";
  }

  function renderLoadFailure() {
    $meta.textContent = "";
    $results.innerHTML = '<div class="empty"><p class="big">The search index could not be loaded.</p>' +
      "<p>Reload the page to try again. In the meantime the " +
      '<a href="lists.html">per-list explainers</a> link every official source directly, and the ' +
      '<a href="https://www.trade.gov/consolidated-screening-list" target="_blank" rel="noopener">Consolidated Screening List</a>' +
      " searches several of these lists officially.</p></div>";
  }

  /* ---- scoring ---- */

  function score(rec, tokens, joined) {
    var k = rec.k;
    var nameNorm = norm(rec.n);
    if (nameNorm === joined) return 100;
    if (nameNorm.indexOf(joined) === 0) return 85;
    var all = true, i;
    for (i = 0; i < tokens.length; i++) {
      if (k.indexOf(tokens[i]) === -1) { all = false; break; }
    }
    if (all) {
      var inName = true;
      for (i = 0; i < tokens.length; i++) {
        if (nameNorm.indexOf(tokens[i]) === -1) { inName = false; break; }
      }
      return inName ? 70 : 55;
    }
    // country / address / notes fallback: require every token to appear somewhere
    var extra = norm((rec.c || "") + " " + (rec.ad || "") + " " + (rec.no || ""));
    for (i = 0; i < tokens.length; i++) {
      if (k.indexOf(tokens[i]) === -1 && extra.indexOf(tokens[i]) === -1) return 0;
    }
    return 25;
  }

  // The search key is built here rather than shipped in the index: it is
  // derivable from the name and aliases, and leaving it out of the file saves
  // about 360 KB over the wire.
  function prepare() {
    for (var i = 0; i < entities.length; i++) {
      var rec = entities[i];
      rec.k = norm([rec.n].concat(rec.a || []).join(" | "));
    }
  }

  function isBrowse(qRaw) {
    return !!activeList && norm(qRaw).length < 2;
  }

  function search(qRaw) {
    var joined = norm(qRaw);
    var browse = isBrowse(qRaw);
    if (!browse && joined.length < 2) return null;
    var tokens = browse ? [] : joined.split(" ");
    var groups = {};
    for (var i = 0; i < entities.length; i++) {
      var rec = entities[i];
      var list = LISTS.lists[rec.l];
      if (activeList) {
        if (rec.l !== activeList) continue;
      } else if (activeAgency !== "all" && agencyFamily(list.agency_short) !== activeAgency) {
        continue;
      }
      if (activeStatus === "active" && !isActive(rec)) continue;
      if (activeStatus === "historical" && !isHistorical(rec)) continue;
      var sc = browse ? 50 : score(rec, tokens, joined);
      if (sc <= 0) continue;
      var gk = norm(rec.n);
      var g = groups[gk];
      if (!g) { g = groups[gk] = { name: rec.n, score: 0, recs: [] }; }
      g.recs.push(rec);
      if (sc > g.score) g.score = sc;
    }
    var out = [];
    for (var k in groups) out.push(groups[k]);
    out.sort(function (a, b) {
      if (b.score !== a.score) return b.score - a.score;
      if (b.recs.length !== a.recs.length) return b.recs.length - a.recs.length;
      return a.name.localeCompare(b.name);
    });
    return out;
  }

  /* ---- rendering ---- */

  function badge(list) {
    var cls = BADGE_CLASS[list.agency_short] || "";
    return '<span class="badge ' + cls + '">' + esc(list.agency_short) + " — " + esc(list.short_name) + "</span>";
  }

  function statusBadge(rec) {
    if (!rec.s) return "";
    var cls = isActive(rec) ? "status-active" : "status-revoked";
    return ' <span class="badge ' + cls + '">' + esc(rec.s) + "</span>";
  }

  function renderGroup(g) {
    var h = '<article class="result">';
    h += "<h3>" + esc(g.name) + "</h3>";
    var countries = {}, aliases = {};
    g.recs.forEach(function (r) {
      if (r.c) countries[r.c] = 1;
      (r.a || []).forEach(function (a) { aliases[a] = 1; });
    });
    var cList = Object.keys(countries);
    var listCount = {};
    g.recs.forEach(function (r) { listCount[r.l] = 1; });
    var nLists = Object.keys(listCount).length;
    h += '<p class="sub">' + (cList.length ? esc(cList.join(", ")) + " · " : "") +
      "Appears on <strong>" + nLists + (nLists === 1 ? " list" : " lists") + "</strong></p>";
    var aList = Object.keys(aliases);
    if (aList.length) {
      h += '<p class="aliases"><em>Also known as:</em> ' + esc(aList.slice(0, 8).join("; ")) +
        (aList.length > 8 ? " …" : "") + "</p>";
    }
    h += '<div class="listings">';
    g.recs.forEach(function (r) {
      var list = LISTS.lists[r.l];
      h += '<div class="listing">' + badge(list) + statusBadge(r);
      if (r.d) h += "<span>Effective " + esc(r.d) + "</span>";
      if (r.fr) h += "<span>" + esc(r.fr) + "</span>";
      h += '<a class="src" href="' + esc(list.official_url) + '" target="_blank" rel="noopener">Verify at official source ↗</a>';
      var det = [];
      if (r.sd) det.push("Measures: " + esc(r.sd));
      if (r.ad) det.push(esc(r.ad));
      if (r.no) det.push(esc(r.no));
      if (det.length) h += '<span class="det">' + det.join(" · ") + "</span>";
      h += "</div>";
    });
    h += "</div></article>";
    return h;
  }

  function idleMessage() {
    return "Search " + num(LISTS.totals.entries) + " entries across all " +
      LISTS.totals.lists + " lists. Results are grouped by entity name.";
  }

  function render() {
    updateFilterUI();
    var q = $q.value;

    if (!entities) {
      if (loadFailed) { renderLoadFailure(); return; }
      if (q.trim().length >= 2 || activeList) { ensureIndex(render); return; }
      $results.innerHTML = "";
      $meta.textContent = q.trim().length ? "Keep typing — at least 2 characters." : idleMessage();
      return;
    }

    var browse = isBrowse(q);
    var res = search(q);
    if (res === null) {
      $results.innerHTML = "";
      $meta.textContent = q.trim().length ? "Keep typing — at least 2 characters." : idleMessage();
      return;
    }
    var listName = activeList ? LISTS.lists[activeList].short_name : null;
    if (!res.length) {
      $meta.textContent = "";
      $results.innerHTML = '<div class="empty"><p class="big">No matches for “' + esc(q) + '”' +
        (listName ? " in " + esc(listName) : " in this snapshot") + '.</p>' +
        '<p>That is <strong>not</strong> a clearance. Names vary (translations, abbreviations, subsidiaries) and lists change often. ' +
        (activeList ? 'Try <a href="index.html">searching all lists</a>, the ' : 'Check the ') +
        '<a href="https://www.trade.gov/consolidated-screening-list" target="_blank" rel="noopener">Consolidated Screening List</a>' +
        (activeList ? ',' : '') + ' and the <a href="lists.html">official sources</a>, and consult your institution’s research security office.</p></div>';
      return;
    }
    var total = res.length;
    var slice = res.slice(0, shown);
    var statusNote = activeStatus === "active" ? " with an active designation"
      : (activeStatus === "historical" ? " whose designations were lifted, expired, terminated or waived" : "");
    if (browse) {
      $meta.innerHTML = "Showing all <strong>" + num(total) + "</strong> " +
        (total === 1 ? "entry" : "entries") + " in " + esc(listName) + statusNote +
        ". Type above to search within this list. Always verify against the official source before acting.";
    } else {
      $meta.innerHTML = "<strong>" + num(total) + "</strong> " + (total === 1 ? "entity matches" : "entities match") +
        " “" + esc(q) + "”" + (listName ? " in " + esc(listName) : (activeAgency !== "all" ? " (filtered)" : "")) +
        statusNote + ". Always verify against the official source before acting.";
    }
    var h = slice.map(renderGroup).join("");
    if (total > shown) {
      h += '<p class="more-wrap"><button class="btn ghost" type="button" id="more">Show more (' +
        num(total - shown) + " remaining)</button></p>";
    }
    $results.innerHTML = h;
    var more = document.getElementById("more");
    if (more) {
      more.addEventListener("click", function () {
        shown += PAGE;
        render();
        var first = $results.querySelectorAll(".result")[Math.max(0, shown - PAGE)];
        if (first) { first.setAttribute("tabindex", "-1"); first.focus(); }
      });
    }
  }

  /* ---- filters ---- */

  var $banner = null;
  if ($filters && $filters.parentNode) {
    $banner = document.createElement("div");
    $banner.className = "list-banner";
    $banner.style.display = "none";
    $filters.parentNode.insertBefore($banner, $filters);
    $banner.addEventListener("click", function (ev) {
      if (!ev.target.closest("#clear-list")) return;
      setActiveList(null);
      $q.focus();
    });
  }

  function updateFilterUI() {
    if (!$filters) return;
    if (activeList) {
      var l = LISTS.lists[activeList];
      $filters.style.display = "none";
      if ($banner) {
        $banner.style.display = "";
        $banner.innerHTML = '<span class="label">Showing only:</span> ' +
          '<span class="badge ' + (BADGE_CLASS[l.agency_short] || "") + '">' +
          esc(l.agency_short) + " — " + esc(l.short_name) + "</span> " +
          '<button class="chip" type="button" id="clear-list">✕ Clear filter — search all lists</button>';
      }
    } else {
      $filters.style.display = "";
      if ($banner) $banner.style.display = "none";
    }
  }

  function syncUrl() {
    var u = new URL(location.href);
    if ($q.value.trim()) u.searchParams.set("q", $q.value.trim());
    else u.searchParams.delete("q");
    if (activeList) u.searchParams.set("list", activeList);
    else u.searchParams.delete("list");
    if (activeStatus !== "all") u.searchParams.set("status", activeStatus);
    else u.searchParams.delete("status");
    history.replaceState(null, "", u);
  }

  function setActiveList(id) {
    activeList = id && LISTS.lists[id] ? id : null;
    activeAgency = "all";
    shown = PAGE;
    $q.placeholder = activeList
      ? "Search within " + LISTS.lists[activeList].short_name + "…"
      : "Try an organization, university, company, or person…";
    syncUrl();
    if (activeList) ensureIndex(render); else render();
  }

  if ($filters) {
    $filters.innerHTML = '<span class="label">Agency:</span>' + AGENCIES.map(function (a) {
      return '<button class="chip" type="button" data-a="' + a[0] + '" aria-pressed="' +
        (a[0] === "all") + '">' + a[1] + "</button>";
    }).join("");
    $filters.addEventListener("click", function (ev) {
      var b = ev.target.closest(".chip");
      if (!b) return;
      activeAgency = b.getAttribute("data-a");
      $filters.querySelectorAll(".chip").forEach(function (c) {
        c.setAttribute("aria-pressed", String(c === b));
      });
      shown = PAGE;
      render();
    });
  }

  // Designation status. Most entries carry no status at all, because their
  // source publication does not record one, so the two narrowing options say
  // exactly how many entries they can reach.
  var statusTotals = (function () {
    var active = 0, historical = 0;
    var sc = LISTS.status_counts || {};
    Object.keys(sc).forEach(function (k) {
      if (k === "Active") active += sc[k]; else historical += sc[k];
    });
    return { active: active, historical: historical };
  })();

  if ($statusFilters && (statusTotals.active || statusTotals.historical)) {
    var STATUSES = [
      ["all", "All entries", LISTS.totals.entries],
      ["active", "Active designation", statusTotals.active],
      ["historical", "Lifted or expired", statusTotals.historical]
    ];
    $statusFilters.innerHTML = '<span class="label">Designation status:</span>' +
      STATUSES.map(function (s) {
        return '<button class="chip" type="button" data-s="' + s[0] + '" aria-pressed="' +
          (s[0] === "all") + '">' + s[1] + ' <span class="chip-n">' + num(s[2]) + "</span></button>";
      }).join("") +
      '<span class="filter-note">Only the State nonproliferation and CBP lists record a status; ' +
      "entries from the other lists appear under “All entries” only.</span>";
    $statusFilters.addEventListener("click", function (ev) {
      var b = ev.target.closest(".chip");
      if (!b) return;
      activeStatus = b.getAttribute("data-s");
      $statusFilters.querySelectorAll(".chip").forEach(function (c) {
        c.setAttribute("aria-pressed", String(c === b));
      });
      shown = PAGE;
      syncUrl();
      render();
    });
  }

  /* ---- wiring ---- */

  var t;
  $q.addEventListener("input", function () {
    clearTimeout(t);
    shown = PAGE;
    t = setTimeout(function () {
      render();
      syncUrl();
    }, 130);
  });

  // Start fetching the index as soon as the box is focused, so the first
  // keystroke usually lands on an index that is already there.
  $q.addEventListener("focus", function () { ensureIndex(render); }, { once: true });

  if ($go) {
    $go.addEventListener("click", function () {
      shown = PAGE;
      ensureIndex(render);
      $q.focus();
    });
  }

  document.querySelectorAll("[data-try]").forEach(function (b) {
    b.addEventListener("click", function () {
      $q.value = b.getAttribute("data-try");
      shown = PAGE;
      ensureIndex(render);
      syncUrl();
      $q.focus();
    });
  });

  var params = new URL(location.href).searchParams;
  var initialList = params.get("list");
  if (initialList && LISTS.lists[initialList]) {
    activeList = initialList;
    $q.placeholder = "Search within " + LISTS.lists[initialList].short_name + "…";
  }
  var initialStatus = params.get("status");
  if (initialStatus === "active" || initialStatus === "historical") {
    activeStatus = initialStatus;
  }
  var initialQ = params.get("q");
  if (initialQ) $q.value = initialQ;

  // Reflect any status taken from the URL onto the chips.
  if ($statusFilters) {
    $statusFilters.querySelectorAll(".chip").forEach(function (c) {
      c.setAttribute("aria-pressed", String(c.getAttribute("data-s") === activeStatus));
    });
  }

  if (initialQ || activeList) ensureIndex(render); else render();

})();
