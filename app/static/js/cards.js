// Compact, collapsible per-column cards plus a filter box, so datasets with many columns stay manageable.
import { $$, chip, h } from "./dom.js";

export const FILTER_FROM = 6;       // a filter box appears when a list has more columns than this
export const OPEN_UP_TO = 4;        // lists this short start expanded

export function columnCard({ name, kindLabel, meta, open }) {
  const choice = h("span", { class: "col-choice" });
  const summary = h("summary", {},
    h("span", { class: "col-name", title: name }, name),
    kindLabel ? chip(kindLabel) : null,
    meta ? h("span", { class: "col-meta" }, meta) : null,
    choice);
  const body = h("div", { class: "col-body" });
  const root = h("details", { class: "col-card", dataset: { name: name.toLowerCase() }, open: !!open }, summary, body);
  return {
    root, body,
    setChoice(text) {
      choice.textContent = text || "";
      choice.classList.toggle("is-set", !!text);
    },
  };
}

// A name filter for a long list. `scope` holds the items, each matched by `itemSelector` and carrying data-name.
// Returns { bar, empty } to place above and below the list (both are null-safe empty fragments for short lists).
export function filterControls(scope, itemSelector, count) {
  if (count <= FILTER_FROM) return { bar: null, empty: null };
  const input = h("input", { type: "text", placeholder: "Filter columns by name", "aria-label": "Filter columns by name" });
  const empty = h("p", { class: "filter-empty", hidden: true }, "No column matches that name.");
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    let shown = 0;
    for (const item of $$(itemSelector, scope)) {
      const match = !q || item.dataset.name.includes(q);
      item.hidden = !match;
      if (match) shown += 1;
    }
    empty.hidden = shown > 0;
  });
  return { bar: h("div", { class: "filter-row" }, input, h("span", { class: "hint" }, `${count} columns`)), empty };
}

export function filterable(items) {
  const list = h("div", { class: "col-list" }, items);
  const { bar, empty } = filterControls(list, "[data-name]", items.length);
  return h("div", {}, bar, list, empty);
}

export function emptyNote(kind, title, body) {
  return h("div", { class: `alert alert-${kind}` }, h("p", { class: "alert-title" }, title), body ? h("p", {}, body) : null);
}
