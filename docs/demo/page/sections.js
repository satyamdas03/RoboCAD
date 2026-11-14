/**
 * Section navigation for the living page.
 *
 * The voice shell embeds this page and says "show me the torque". It sends exactly one message,
 * `{type: "robocad.section", section: "torque"}`, and this answers it by flashing the card that
 * section lives in. Two rules keep the channel from being a way for anyone else to drive the page:
 * only this page's own origin is obeyed, and only the seven section names below exist. Everything
 * else is ignored silently -- a page that answers "I refused that" tells a sender what to try next.
 *
 * On a cockpit page there is nothing to scroll: every card is on screen at once. The flash is
 * therefore the whole answer, and `show` also dispatches a `robocad:section` event on the document
 * so the page can open the matching drawer entry in presenter mode without this file knowing what a
 * drawer is.
 *
 * A second message type, `{type: "robocad.infill", infill: 0.30}`, names a print fraction instead of
 * a card. It travels the same channel under the same origin rule and dispatches `robocad:infill`, so
 * "change infill to 30 percent" moves the switch the audience is looking at rather than answering in
 * chat while the card behind it still shows the other bake.
 *
 * Opened from `file://` there is no parent frame and the origin is opaque, so the listener never
 * accepts anything and the page behaves exactly as it did before. The `#torque` fragment still
 * works, which is what a person following a link in the README gets.
 */
(function (root) {
  "use strict";

  // The seven sections the voice knows, and the card each lives in. `overview` is the HUD over the
  // 3D stage. `comparison` and `masses` both lead to the mass card: comparison is the whole
  // compiled-versus-published story, masses is the figure the spoken sentence names, and the KPI
  // strip carries the same comparison in the header. `revision` is the switch in the footer.
  var MAP = {
    overview: "hud",
    checks: "checks-grp",
    comparison: "kpis",
    masses: "masses",
    torque: "torque-grp",
    revision: "revswitch",
    twin: "twin-grp",
  };
  var TYPE = "robocad.section";
  // The second thing the voice can change: the infill fraction. It travels on the same channel and
  // under the same origin rule, because it drives numbers the audience reads off the page -- the
  // print mass, the delta, the saving and the whole torque card -- and a stranger who can set it is
  // a stranger who can make the page say a weight the bundle never measured.
  var TYPE_INFILL = "robocad.infill";
  // Two seconds, not one: the card is flashed while a spoken sentence is still running, and a
  // 1.5 s glow that ends mid-sentence reads as a page that flickered rather than one that answered.
  var FLASH_MS = 2000;

  function owns(object, key) {
    return Object.prototype.hasOwnProperty.call(object, key);
  }

  /** True when this origin may drive the page at all. Shared by both message types. */
  function trusted(origin, location) {
    if (!location) return false;
    if (location.protocol !== "http:" && location.protocol !== "https:") return false;
    // A sandboxed frame and its sender both report the origin "null", so comparing the two would
    // accept a stranger. An opaque origin is never a caller with authority over this page.
    if (!origin || origin === "null" || !location.origin || location.origin === "null") return false;
    return origin === location.origin;
  }

  /**
   * The section a message names, or null if this page must ignore it.
   *
   * `location` is passed in rather than read here so that the rule is testable without a browser,
   * and so that a page served from `file://` can be refused explicitly instead of by accident.
   */
  function accept(data, origin, location) {
    if (!trusted(origin, location)) return null;
    if (!data || data.type !== TYPE || typeof data.section !== "string") return null;
    return owns(MAP, data.section) ? data.section : null;
  }

  /**
   * The infill fraction a message names, or null if this page must ignore it.
   *
   * A fraction outside 0..1, a string that looks like a number, and a NaN are all refusals: the page
   * prints whatever it is given as a mass, so the only accepted value is a finite number in range.
   */
  function acceptInfill(data, origin, location) {
    if (!trusted(origin, location)) return null;
    if (!data || data.type !== TYPE_INFILL) return null;
    var value = data.infill;
    if (typeof value !== "number" || !isFinite(value) || value < 0 || value > 1) return null;
    return value;
  }

  function filled(element) {
    if (typeof element.querySelector === "function" && element.querySelector("canvas")) return true;
    return typeof element.textContent === "string" && element.textContent.trim() !== "";
  }

  /**
   * Flash a section's card and tell the page which section was asked for. Returns false when there
   * is nothing to show.
   *
   * A panel the payload did not fill stays hidden: flashing an empty box answers "show me the
   * torque" with nothing, and reads as a page that lost its numbers rather than one that never had
   * them.
   */
  function show(document, section, options) {
    if (!owns(MAP, section)) return false;
    var element = document.getElementById(MAP[section]);
    if (!element) return false;
    var style = element.style || {};
    if (style.display === "none" && !filled(element)) return false;
    style.display = "";
    var reduce = !!(options && options.reducedMotion);
    if (typeof element.scrollIntoView === "function") {
      element.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
    }
    if (element.classList && typeof element.classList.add === "function") {
      element.classList.add("nav-flash");
      var timer = (options && options.setTimeout) || root.setTimeout;
      if (typeof timer === "function") {
        timer(function () { element.classList.remove("nav-flash"); }, FLASH_MS);
      }
    }
    // The page decides what else a named section means -- opening a drawer entry, in presenter
    // mode. Guarded because a page with no CustomEvent (and the node fake) must keep working.
    if (typeof document.dispatchEvent === "function" && typeof root.CustomEvent === "function") {
      document.dispatchEvent(new root.CustomEvent("robocad:section", { detail: { section: section } }));
    }
    return true;
  }

  function wire(document, view) {
    document = document || root.document;
    view = view || root;
    if (!document || typeof view.addEventListener !== "function") return;

    function dispatch(name, detail) {
      if (typeof document.dispatchEvent === "function" && typeof root.CustomEvent === "function") {
        document.dispatchEvent(new root.CustomEvent(name, { detail: detail }));
      }
    }

    view.addEventListener("message", function (event) {
      // Only the embedding frame may drive this page. `event.source` is set by the browser and cannot
      // be forged, so it pins the sender to the parent even when origins are spoofed, mirrored, or
      // opaque. A page opened standalone has no usable parent and refuses everything.
      if (!view.parent || event.source !== view.parent) return;
      var reduced = reducedMotion(view);
      var section = accept(event.data, event.origin, view.location);
      if (section) show(document, section, { reducedMotion: reduced });
      var infill = acceptInfill(event.data, event.origin, view.location);
      if (infill !== null) dispatch("robocad:infill", { infill: infill });
    });

    function fromHash() {
      var hash = String((view.location && view.location.hash) || "").replace(/^#/, "");
      if (hash) show(document, hash, { reducedMotion: reducedMotion(view) });
    }
    fromHash();
    view.addEventListener("hashchange", fromHash);
  }

  function reducedMotion(view) {
    try {
      return !!(view.matchMedia && view.matchMedia("(prefers-reduced-motion: reduce)").matches);
    } catch (error) {
      return false;
    }
  }

  root.ROBOCAD_SECTIONS = { MAP: MAP, TYPE: TYPE, TYPE_INFILL: TYPE_INFILL, FLASH_MS: FLASH_MS,
                            accept: accept, acceptInfill: acceptInfill, show: show, wire: wire };
})(this);
