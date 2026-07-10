/* NSF Restricted Entities Guide — search engine (no dependencies). */
(function () {
  "use strict";
  var DATA = window.NSF_DATA;
  if (!DATA) return;

  var $q = document.getElementById("q");
  if (!$q) return; // not on the search page

  var $results = document.getElementById("results");
  var $meta = document.getElementById("results-meta");
  var $filters = document.getElementById("agency-filters");
  var PAGE = 40;
  var shown = PAGE;

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
  var activeList = null; // when set, results are restricted to this single list id

  var BADGE_CLASS = {
    "DoW": "dow", "Commerce/BIS": "bis", "Treasury/OFAC": "ofac",
    "State/DDTC": "state", "State/ISN": "state", "FCC": "fcc",
    "DHS": "dhs", "CBP": "cbp"
  };

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
      // all tokens somewhere in name/aliases
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

  // browse mode = a single list is selected and there is no real query yet,
  // so we list every entry in that list instead of requiring a search term
  function isBrowse(qRaw) {
    return !!activeList && norm(qRaw).length < 2;
  }

  function search(qRaw) {
    var joined = norm(qRaw);
    var browse = isBrowse(qRaw);
    if (!browse && joined.length < 2) return null;
    var tokens = browse ? [] : joined.split(" ");
    var groups = {}; // normalized name -> group
    var ents = DATA.entities;
    for (var i = 0; i < ents.length; i++) {
      var rec = ents[i];
      var list = DATA.lists[rec.l];
      if (activeList) {
        if (rec.l !== activeList) continue;
      } else if (activeAgency !== "all" && agencyFamily(list.agency_short) !== activeAgency) {
        continue;
      }
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

  function statusBadge(s) {
    if (!s) return "";
    var cls = /active/i.test(s) ? "status-active" : "status-revoked";
    return ' <span class="badge ' + cls + '">' + esc(s) + "</span>";
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
      var list = DATA.lists[r.l];
      h += '<div class="listing">' + badge(list) + statusBadge(r.s);
      if (r.d) h += "<span>Effective " + esc(r.d) + "</span>";
      if (r.fr) h += "<span>" + esc(r.fr) + "</span>";
      h += '<a class="src" href="' + esc(list.official_url) + '" target="_blank" rel="noopener">Verify at official source ↗</a>';
      var det = [];
      if (r.ad) det.push(esc(r.ad));
      if (r.no) det.push(esc(r.no));
      if (det.length) h += '<span class="det">' + det.join(" · ") + "</span>";
      h += "</div>";
    });
    h += "</div></article>";
    return h;
  }

  function render() {
    updateFilterUI();
    var q = $q.value;
    var browse = isBrowse(q);
    var res = search(q);
    if (res === null) {
      $results.innerHTML = "";
      $meta.innerHTML = q.trim().length ? "Keep typing — at least 2 characters." :
        "Search " + DATA.entities.length.toLocaleString() + " entries across all 13 lists. Results are grouped by entity name.";
      return;
    }
    var listName = activeList ? DATA.lists[activeList].short_name : null;
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
    if (browse) {
      $meta.innerHTML = "Showing all <strong>" + total.toLocaleString() + "</strong> " +
        (total === 1 ? "entry" : "entries") + " in " + esc(listName) +
        ". Type above to search within this list. Always verify against the official source before acting.";
    } else {
      $meta.innerHTML = "<strong>" + total.toLocaleString() + "</strong> " + (total === 1 ? "entity matches" : "entities match") +
        " “" + esc(q) + "”" + (listName ? " in " + esc(listName) : (activeAgency !== "all" ? " (filtered)" : "")) +
        ". Always verify against the official source before acting.";
    }
    var html = slice.map(renderGroup).join("");
    if (total > shown) {
      html += '<p style="text-align:center"><button class="btn ghost" id="more">Show more (' + (total - shown) + " remaining)</button></p>";
    }
    $results.innerHTML = html;
    var more = document.getElementById("more");
    if (more) more.addEventListener("click", function () { shown += PAGE; render(); });
  }

  /* ---- filters ---- */
  // single-list banner (shown when arriving from a "Search this snapshot" link)
  var $banner = null;
  if ($filters && $filters.parentNode) {
    $banner = document.createElement("div");
    $banner.className = "list-banner";
    $banner.style.display = "none";
    $filters.parentNode.insertBefore($banner, $filters);
    $banner.addEventListener("click", function (e) {
      if (!e.target.closest("#clear-list")) return;
      setActiveList(null);
      $q.focus();
    });
  }

  function updateFilterUI() {
    if (!$filters) return;
    if (activeList) {
      var l = DATA.lists[activeList];
      $filters.style.display = "none";
      if ($banner) {
        $banner.style.display = "";
        $banner.innerHTML = '<span class="label">Showing only:</span> ' +
          '<span class="badge ' + (BADGE_CLASS[l.agency_short] || "") + '">' +
          esc(l.agency_short) + " — " + esc(l.short_name) + "</span> " +
          '<button class="chip" id="clear-list">✕ Clear filter — search all lists</button>';
      }
    } else {
      $filters.style.display = "";
      if ($banner) $banner.style.display = "none";
    }
  }

  function setActiveList(id) {
    activeList = id && DATA.lists[id] ? id : null;
    activeAgency = "all";
    shown = PAGE;
    $q.placeholder = activeList
      ? "Search within " + DATA.lists[activeList].short_name + "…"
      : "Try an organization, university, company, or person…";
    var u = new URL(location.href);
    if (activeList) u.searchParams.set("list", activeList);
    else u.searchParams.delete("list");
    history.replaceState(null, "", u);
    render();
  }

  if ($filters) {
    $filters.innerHTML = '<span class="label">Agency:</span>' + AGENCIES.map(function (a) {
      return '<button class="chip" data-a="' + a[0] + '" aria-pressed="' + (a[0] === "all") + '">' + a[1] + "</button>";
    }).join("");
    $filters.addEventListener("click", function (e) {
      var b = e.target.closest(".chip");
      if (!b) return;
      activeAgency = b.getAttribute("data-a");
      $filters.querySelectorAll(".chip").forEach(function (c) {
        c.setAttribute("aria-pressed", String(c === b));
      });
      shown = PAGE;
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
      var u = new URL(location.href);
      if ($q.value.trim()) u.searchParams.set("q", $q.value.trim());
      else u.searchParams.delete("q");
      history.replaceState(null, "", u);
    }, 130);
  });

  document.querySelectorAll("[data-try]").forEach(function (b) {
    b.addEventListener("click", function () {
      $q.value = b.getAttribute("data-try");
      shown = PAGE;
      render();
      $q.focus();
    });
  });

  // stats on hero
  var $stat = document.getElementById("stat-entities");
  if ($stat) $stat.textContent = DATA.entities.length.toLocaleString();

  var params = new URL(location.href).searchParams;
  var initialList = params.get("list");
  if (initialList && DATA.lists[initialList]) {
    activeList = initialList;
    $q.placeholder = "Search within " + DATA.lists[initialList].short_name + "…";
  }
  var initial = params.get("q");
  if (initial) { $q.value = initial; }
  render();
})();

/* checklist persistence (checklist.html) */
(function () {
  var boxes = document.querySelectorAll(".check-item input[type=checkbox]");
  if (!boxes.length) return;
  var KEY = "nsf-re-checklist";
  var saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
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
