/* Parallax docs site: shared header, navigation, table of contents, tabs, filters and copy buttons.
   Pages set <body data-root="" data-page="..."> (data-root is "../" for pages inside pipelines/).
   The home page adds class="splash": no sidebar and no table of contents. */
(function () {
  "use strict";
  var REPO = "https://github.com/mayusi/parallax";
  var NAV = [
    { title: "Start", items: [
      ["overview", "Overview", "index.html"],
      ["setup", "Setup guide", "setup.html"],
      ["hardware", "Hardware tiers & models", "hardware.html"]
    ] },
    { title: "Pipelines", items: [
      ["pipelines", "All eight pipelines", "pipelines/index.html"],
      ["lane-3d", "3D models", "pipelines/3d.html"],
      ["lane-vfx", "Visual effects", "pipelines/vfx.html"],
      ["lane-anim", "Animation", "pipelines/anim.html"],
      ["lane-world", "Worlds", "pipelines/world.html"],
      ["lane-ui", "Interfaces", "pipelines/ui.html"],
      ["lane-sfx", "Sound", "pipelines/sfx.html"],
      ["lane-code", "Gameplay systems", "pipelines/code.html"],
      ["lane-qa", "QA", "pipelines/qa.html"]
    ] },
    { title: "How it works", items: [
      ["enforcement", "Enforcement", "enforcement.html"],
      ["learning", "The learning loop", "learning.html"],
      ["mcp", "MCP server & AI clients", "mcp.html"],
      ["commands", "Command reference", "commands.html"]
    ] },
    { title: "Project", items: [
      ["roadmap", "Roadmap", "roadmap.html"],
      ["ext-repo", "Source on GitHub", REPO],
      ["ext-release", "Latest release", REPO + "/releases/latest"],
      ["ext-changelog", "Changelog", REPO + "/blob/main/CHANGELOG.md"]
    ] }
  ];
  var TOP = [["setup", "Setup", "setup.html"], ["pipelines", "Pipelines", "pipelines/index.html"],
    ["hardware", "Hardware", "hardware.html"], ["commands", "Commands", "commands.html"], ["roadmap", "Roadmap", "roadmap.html"]];
  var ICON_EXT = '<svg class="ext" viewBox="0 0 16 16" aria-hidden="true"><path d="M5.5 3.5h7v7M12.5 3.5l-9 9" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  var ICON_MENU = '<svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true"><path d="M3 6h14M3 10h14M3 14h14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';

  var body = document.body;
  var root = body.getAttribute("data-root") || "";
  var page = body.getAttribute("data-page") || "";
  function href(h) { return /^https?:/.test(h) ? h : root + h; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function each(sel, fn, scope) { Array.prototype.forEach.call((scope || document).querySelectorAll(sel), fn); }

  var navHtml = NAV.map(function (g) {
    return '<div class="group"><div class="group-title">' + esc(g.title) + "</div>" + g.items.map(function (it) {
      var ext = /^https?:/.test(it[2]);
      return '<a href="' + href(it[2]) + '"' + (it[0] === page ? ' class="active" aria-current="page"' : "") +
        (ext ? ' rel="noopener"' : "") + ">" + esc(it[1]) + (ext ? ICON_EXT : "") + "</a>";
    }).join("") + "</div>";
  }).join("");

  // header, plus the menu used on small screens
  var headerSlot = document.getElementById("site-header");
  if (headerSlot) {
    var top = TOP.map(function (t) {
      var on = t[0] === page || (t[0] === "pipelines" && page.indexOf("lane-") === 0);
      return '<a href="' + href(t[2]) + '"' + (on ? ' class="active"' : "") + ">" + esc(t[1]) + "</a>";
    }).join("");
    headerSlot.outerHTML =
      '<header class="site-header">' +
      '<a class="brand" href="' + href("index.html") + '"><img src="' + href("assets/logo-64.png") + '" alt="" width="30" height="30"><span>Parallax</span></a>' +
      '<nav class="top-links" aria-label="Main">' + top + '<span class="sep" aria-hidden="true"></span>' +
      '<a class="gh" href="' + REPO + '" rel="noopener">GitHub' + ICON_EXT + "</a></nav>" +
      '<button class="nav-toggle" type="button" aria-label="Menu" aria-expanded="false" aria-controls="mobile-nav">' + ICON_MENU + "</button>" +
      '</header><nav class="mobile-nav navtree" id="mobile-nav" aria-label="Site menu">' + navHtml + "</nav>";
  }
  var toggle = document.querySelector(".nav-toggle");
  function setMenu(open) {
    body.classList.toggle("nav-open", open);
    if (toggle) toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }
  if (toggle) {
    toggle.addEventListener("click", function () { setMenu(!body.classList.contains("nav-open")); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && body.classList.contains("nav-open")) { setMenu(false); toggle.focus(); }
    });
    window.addEventListener("pageshow", function () { setMenu(false); });  // never come back open after Back
  }

  // sidebar
  var side = document.querySelector(".sidebar");
  if (side) {
    side.classList.add("navtree");
    side.setAttribute("aria-label", "Site");
    side.innerHTML = navHtml;
  }

  // footer
  var footSlot = document.getElementById("site-footer");
  if (footSlot) {
    footSlot.outerHTML = '<footer class="site-footer"><div class="foot-inner">' +
      '<span class="foot-brand"><img src="' + href("assets/logo-64.png") + '" alt="" width="22" height="22">Parallax</span>' +
      '<nav class="foot-links" aria-label="Project">' +
      '<a href="' + REPO + '">GitHub</a><a href="' + REPO + '/releases/latest">Releases</a>' +
      '<a href="' + REPO + '/blob/main/CHANGELOG.md">Changelog</a><a href="' + REPO + '/security/policy">Security</a>' +
      '<a href="' + REPO + '/blob/main/LICENSE">MIT License</a></nav></div></footer>';
  }

  // on-page table of contents from h2[id]
  var toc = document.querySelector(".toc");
  var heads = Array.prototype.slice.call(document.querySelectorAll(".content h2[id]"));
  if (toc) {
    if (heads.length < 2) { toc.remove(); var lay = document.querySelector(".layout"); if (lay) lay.classList.add("no-toc"); }
    else {
      toc.setAttribute("aria-label", "On this page");
      toc.innerHTML = '<div class="toc-title">On this page</div>' + heads.map(function (h) {
        return '<a href="#' + esc(encodeURIComponent(h.id)) + '">' + esc(h.textContent) + "</a>";
      }).join("");
      if ("IntersectionObserver" in window) {
        var links = {};
        each("a", function (a) { links[decodeURIComponent(a.getAttribute("href").slice(1))] = a; }, toc);
        var io = new IntersectionObserver(function (entries) {
          entries.forEach(function (e) {
            if (e.isIntersecting) {
              Object.keys(links).forEach(function (k) { links[k].classList.remove("on"); });
              if (links[e.target.id]) links[e.target.id].classList.add("on");
            }
          });
        }, { rootMargin: "-20% 0px -70% 0px" });
        heads.forEach(function (h) { io.observe(h); });
      }
    }
  }

  // a link on each section heading (added after the table of contents has read the heading text)
  each(".content h2[id], .content h3[id], .splash-main h2[id]", function (h) {
    var a = document.createElement("a");
    a.className = "anchor"; a.href = "#" + encodeURIComponent(h.id); a.textContent = "#";
    a.setAttribute("aria-label", "Link to this section");
    h.appendChild(a);
  });

  // every table scrolls inside its own frame
  each(".content table, .splash-main table", function (t) {
    if (t.parentElement.classList.contains("table-wrap")) return;
    var w = document.createElement("div");
    w.className = "table-wrap";
    t.parentNode.insertBefore(w, t);
    w.appendChild(t);
  });

  // tabs: <div class="tabs"><div class="tab-list"><button class="tab" data-tab="x">..</button></div><div class="tab-panel" data-panel="x" id="x">..</div></div>
  function selectTab(tabs, key) {
    each(":scope > .tab-list > .tab", function (b) {
      var on = b.getAttribute("data-tab") === key;
      b.setAttribute("aria-selected", on ? "true" : "false");
      b.tabIndex = on ? 0 : -1;
    }, tabs);
    each(":scope > .tab-panel", function (p) { p.hidden = p.getAttribute("data-panel") !== key; }, tabs);
  }
  each(".tabs", function (tabs) {
    var list = tabs.querySelector(":scope > .tab-list");
    if (!list) return;
    list.setAttribute("role", "tablist");
    var buttons = Array.prototype.slice.call(list.querySelectorAll(".tab"));
    buttons.forEach(function (b, i) {
      b.setAttribute("role", "tab");
      b.setAttribute("type", "button");
      b.addEventListener("click", function () { selectTab(tabs, b.getAttribute("data-tab")); });
      b.addEventListener("keydown", function (e) {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        var n = buttons[(i + (e.key === "ArrowRight" ? 1 : buttons.length - 1)) % buttons.length];
        n.focus(); n.click();
      });
    });
    each(":scope > .tab-panel", function (p) { p.setAttribute("role", "tabpanel"); }, tabs);
    var first = buttons.filter(function (b) { return b.getAttribute("aria-selected") === "true"; })[0] || buttons[0];
    if (first) selectTab(tabs, first.getAttribute("data-tab"));
  });
  function openHash() {
    var id = decodeURIComponent(location.hash.slice(1));
    if (!id) return;
    var el = document.getElementById(id);
    if (!el) return;
    var panel = el.closest(".tab-panel");
    while (panel) {
      selectTab(panel.parentElement, panel.getAttribute("data-panel"));
      panel = panel.parentElement.closest(".tab-panel");
    }
    var det = el.closest("details");
    while (det) { det.open = true; det = det.parentElement.closest("details"); }
    if (el.tagName === "DETAILS") el.open = true;
  }
  window.addEventListener("hashchange", openHash);
  openHash();

  // copy buttons on code blocks
  each("pre", function (pre) {
    var code = pre.querySelector("code");
    if (!code || pre.querySelector(".copy")) return;
    var b = document.createElement("button");
    b.className = "copy"; b.type = "button"; b.textContent = "Copy";
    b.addEventListener("click", function () {
      var text = code.textContent.replace(/\n$/, "");
      var done = function () { b.textContent = "Copied"; b.classList.add("done"); setTimeout(function () { b.textContent = "Copy"; b.classList.remove("done"); }, 1400); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, function () {});
    });
    pre.appendChild(b);
  });

  // table filters: <input class="filter" data-filter-target="#t"> and <div class="chips" data-chip-target="#t" data-chip-attr="tier">
  var state = {};
  function apply(sel) {
    var table = document.querySelector(sel);
    if (!table) return;
    var s = state[sel] || {};
    var q = (s.q || "").toLowerCase().trim();
    var shown = 0;
    each("tbody tr:not(.empty-row)", function (tr) {
      var okText = !q || tr.textContent.toLowerCase().indexOf(q) !== -1;
      var okChip = !s.attr || !s.val || s.val === "all" || (" " + (tr.getAttribute("data-" + s.attr) || "") + " ").indexOf(" " + s.val + " ") !== -1;
      tr.hidden = !(okText && okChip);
      if (!tr.hidden) shown++;
    }, table);
    var empty = table.querySelector("tbody tr.empty-row");
    if (!empty) {
      empty = document.createElement("tr"); empty.className = "empty-row";
      var td = document.createElement("td"); td.colSpan = 99; td.textContent = "Nothing matches.";
      empty.appendChild(td); table.querySelector("tbody").appendChild(empty);
    }
    empty.hidden = shown !== 0;
  }
  each("input.filter[data-filter-target]", function (inp) {
    var sel = inp.getAttribute("data-filter-target");
    inp.addEventListener("input", function () { (state[sel] = state[sel] || {}).q = inp.value; apply(sel); });
  });
  each(".chips[data-chip-target]", function (box) {
    var sel = box.getAttribute("data-chip-target");
    var attr = (box.getAttribute("data-chip-attr") || "group").replace(/^data-/, "");
    each(".chip", function (c) {
      c.setAttribute("type", "button");
      c.addEventListener("click", function () {
        each(".chip", function (o) { o.classList.toggle("active", o === c); }, box);
        var st = (state[sel] = state[sel] || {});
        st.attr = attr; st.val = c.getAttribute("data-value");
        apply(sel);
      });
    }, box);
    var act = box.querySelector(".chip.active");
    if (act) { var st = (state[sel] = state[sel] || {}); st.attr = attr; st.val = act.getAttribute("data-value"); apply(sel); }
  });

  // expand / collapse every <details> inside a target
  each("[data-expand-target]", function (b) {
    b.setAttribute("type", "button");
    b.addEventListener("click", function () {
      var box = document.querySelector(b.getAttribute("data-expand-target"));
      if (!box) return;
      var all = box.querySelectorAll("details");
      var open = Array.prototype.some.call(all, function (d) { return !d.open; });
      Array.prototype.forEach.call(all, function (d) { d.open = open; });
      b.textContent = open ? "Collapse all" : "Expand all";
    });
  });
})();
