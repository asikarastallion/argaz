/* ArgazUI — shell primitives and the section router.
 *
 * WHY THIS IS A SEPARATE FILE FROM app.js
 * ---------------------------------------
 * app.js drives the aircraft: it owns the WebSocket, the status bar, the
 * procedure runner's events and every panel's data. None of that should have
 * to know how a section is switched or how a table's empty row is built. What
 * lives here is only the frame — the navigation between modules and the few
 * builders that keep every page's markup identical — so a change to the shell
 * cannot reach the code that starts a simulation.
 *
 * Two globals, both frozen in intent if not in fact: `ArgazUI` (builders) and
 * `ArgazNav` (the router).
 */
(() => {
  "use strict";

  // --------------------------------------------------------------- builders
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /** el("td", {class: "x", text: "y"}, child, child) */
  function el(tag, props, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "text") node.textContent = value;
      else if (key === "html") node.innerHTML = value;
      else if (key === "class") node.className = value;
      else if (key === "on") for (const [ev, fn] of Object.entries(value)) node.addEventListener(ev, fn);
      else if (key === "data") for (const [k, v] of Object.entries(value)) node.dataset[k] = v;
      else if (key in node) node[key] = value;
      else node.setAttribute(key, value);
    }
    for (const child of children) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child.nodeType ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  /** A table body's "there is nothing here, and here is why" row. */
  function emptyRow(columns, text) {
    const tr = document.createElement("tr");
    const td = el("td", { class: "empty", colspan: String(columns), text });
    tr.append(td);
    return tr;
  }

  /** A verdict/level/category chip. `kind` is one of ok|bad|warn|info|"". */
  function badge(text, kind) {
    return el("span", { class: "badge" + (kind ? " " + kind : ""), text });
  }

  /** The state indicator used in panel headers: a dot and one word. */
  function setState(node, state, text) {
    if (!node) return;
    node.dataset.state = state || "none";
    node.textContent = text;
  }

  window.ArgazUI = { el, esc, emptyRow, badge, setState };

  // ----------------------------------------------------------------- router
  // One module is visible at a time. Which one is a function of the hash, so
  // every section is linkable and the browser's back button works — the same
  // contract `#run=` and `#docs=` already had, extended to the whole shell.
  //
  // Hashes containing "=" belong to a page (a run, a documentation page) and
  // are decoded by app.js. A bare "#name" is a section.
  const nav = {
    current: null,
    anchor: null,
    onChange: null,

    views() { return Array.from(document.querySelectorAll("[data-view]")); },
    items() { return Array.from(document.querySelectorAll(".rail-item[data-nav]")); },

    has(name) { return !!document.querySelector(`[data-view="${CSS.escape(name)}"]`); },

    /** Switch section. `opts.hash === false` leaves the URL alone. */
    show(name, opts) {
      const options = opts || {};
      if (!this.has(name)) name = "operations";
      const changed = this.current !== name;
      this.current = name;
      this.anchor = options.anchor || null;

      for (const view of this.views()) view.hidden = view.dataset.view !== name;
      for (const item of this.items()) {
        const mine = item.dataset.nav === name;
        const exact = mine && (!this.anchor || item.dataset.anchor === this.anchor
                               || (!item.dataset.anchor && !this.anchor));
        item.classList.toggle("active", !!exact);
        item.classList.toggle("in-view", mine && !exact);
        if (mine) item.setAttribute("aria-current", "true");
        else item.removeAttribute("aria-current");
      }

      if (options.hash !== false && !/=/.test(location.hash || "")) {
        const wanted = "#" + name;
        if (location.hash !== wanted) history.replaceState(null, "", wanted);
      }

      const main = document.getElementById("app-main");
      const target = this.anchor && document.getElementById(this.anchor);
      if (target) target.scrollIntoView({ block: "start" });
      else if (main && changed) {
        const view = document.querySelector(`[data-view="${CSS.escape(name)}"]`);
        if (view) view.scrollTop = 0;
      }

      if (this.onChange) {
        try {
          this.onChange(name, changed);
        } catch (e) {
          console.error("ArgazUI: a section change handler failed", e);
        }
      }
    },

    /** The section a bare "#name" hash asks for, or null. */
    fromHash() {
      const hash = (location.hash || "").replace(/^#/, "");
      if (!hash || hash.includes("=")) return null;
      return this.has(hash) ? hash : null;
    },

    init(options) {
      this.onChange = (options || {}).onChange || null;

      for (const item of this.items()) {
        item.addEventListener("click", () => {
          this.show(item.dataset.nav, { anchor: item.dataset.anchor || null });
        });
      }

      // Alt+<digit> reaches a section without leaving the keyboard.
      //
      // Bound on `window` in the CAPTURE phase, not on the document in the
      // bubble phase: the terminal usually holds focus, and xterm.js stops
      // propagation of the keys it handles — so a bubbling listener never
      // sees the event and the shortcut works everywhere except the one place
      // an operator's hands actually are.
      window.addEventListener("keydown", (event) => {
        if (!event.altKey || event.ctrlKey || event.metaKey) return;
        if (!/^[1-9]$/.test(event.key)) return;
        const item = document.querySelector(`.rail-item[data-key="${event.key}"]`);
        if (!item) return;
        event.preventDefault();
        event.stopPropagation();
        item.click();
      }, true);

      window.addEventListener("hashchange", () => {
        const wanted = this.fromHash();
        if (wanted && wanted !== this.current) this.show(wanted, { hash: false });
      });

      this.show(this.fromHash() || "operations", { hash: false });
    },
  };

  window.ArgazNav = nav;
})();
