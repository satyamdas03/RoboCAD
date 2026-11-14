/**
 * Section navigation for the living page.
 *
 * The voice shell embeds this page and says "show me the torque". It sends exactly one message,
 * `{type: "robocad.section", section: "torque"}`, and this answers it by scrolling that panel into
 * view and flashing it for a second and a half. Two rules keep the channel from being a way for
 * anyone else to drive the page: only this page's own origin is obeyed, and only the six section
 * names below exist. Everything else is ignored silently -- a page that answers "I refused that"
 * tells a sender what to try next.
 *
 * Opened from `file://` there is no parent frame and the origin is opaque, so the listener never
 * accepts anything and the page behaves exactly as it did before. The `#torque` fragment still
 * works, which is what a person following a link in the README gets.
 */
(function (root) {
  "use strict";

  // The six sections the voice knows, and the element each lives in. `overview` is the HUD over the
  // 3D stage rather than a side panel, which is why it has no panel row of its own.
  var MAP = {
    overview: "hud",
    checks: "checks-grp",
    comparison: "cmp-grp",
    torque: "torque-grp",
    revision: "rev-grp",
    twin: "twin-grp",
  };
  var TYPE = "robocad.section";
  var FLASH_MS = 1500;

  function owns(object, key) {
    return Object.prototype.hasOwnProperty.call(object, key);
  }

  /**
   * The section a message names, or null if this page must ignore it.
   *
   * `location` is passed in rather than read here so that the rule is testable without a browser,
   * and so that a page served from `file://` can be refused explicitly instead of by accident.
   */
  function accept(data, origin, location) {
    if (!location) return null;
    if (location.protocol !== "http:" && location.protocol !== "https:") return null;
    if (!origin || !location.origin || origin !== location.origin) return null;
    if (!data || data.type !== TYPE || typeof data.section !== "string") return null;
    return owns(MAP, data.section) ? data.section : null;
  }

  function filled(element) {
    if (typeof element.querySelector === "function" && element.querySelector("canvas")) return true;
    return typeof element.textContent === "string" && element.textContent.trim() !== "";
  }

  /**
   * Scroll a section into view and flash it. Returns false when there is nothing to show.
   *
   * A panel the payload did not fill stays hidden: scrolling to an empty box answers "show me the
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
    return true;
  }

  function wire(document, view) {
    document = document || root.document;
    view = view || root;
    if (!document || typeof view.addEventListener !== "function") return;

    view.addEventListener("message", function (event) {
      var section = accept(event.data, event.origin, view.location);
      if (section) show(document, section, { reducedMotion: reducedMotion(view) });
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

  root.ROBOCAD_SECTIONS = { MAP: MAP, TYPE: TYPE, FLASH_MS: FLASH_MS, accept: accept, show: show, wire: wire };
})(this);
