// Before/after preview tables. Rows the step changed or removed come first; changed cells are highlighted,
// empty cells are hatched, removed rows are struck through, and leading/trailing spaces are shown as dots.
import { h, num } from "./dom.js";

function cellContent(value) {
  if (value === null || value === undefined) return h("span", { class: "empty-mark" }, "empty");
  const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(value);
  if (!m || (!m[1] && !m[3])) return value;
  const dots = (s) => (s ? h("span", { class: "ws", title: "space" }, s.replace(/[  ]/g, "·").replace(/\t/g, "→")) : null);
  return [dots(m[1]), m[2], dots(m[3])];
}

function table(columns, rows, { dim = false } = {}) {
  const head = h("tr", {}, h("th", { class: "gutter", scope: "col" }, h("span", { class: "visually-hidden" }, "Row")),
    columns.map((c) => h("th", { scope: "col", title: c }, c)));
  const body = rows.map((r) => h("tr", { class: r.removed ? "is-removed" : "" },
    h("th", { class: "gutter", scope: "row" }, r.row),
    r.cells.map((value, i) => {
      if (value === null || value === undefined) return h("td", { class: "is-empty" }, cellContent(value));
      return h("td", { class: !dim && r.changed.includes(i) ? "is-changed" : "" }, cellContent(value));
    })));
  return h("div", { class: "sheet-scroll" }, h("table", { class: "sheet" }, h("thead", {}, head), h("tbody", {}, body)));
}

// `preview` comes from the server: { mode, columns, columns_hidden, before, after, total_before, total_after }
export function renderPreview(preview, { beforeLabel = "Before", afterLabel = "After" } = {}) {
  const wrap = h("div", { class: "preview" });
  const note = preview.mode === "changed"
    ? "Showing the first rows that changed or were removed."
    : "Nothing changed in this step, so these are the first rows.";
  wrap.append(h("p", { class: "preview-note" }, note,
    preview.columns_hidden ? ` ${num(preview.columns_hidden)} more column(s) are not shown.` : ""));
  // Side by side only when the tables are narrow; wide files are stacked so each stays readable.
  const pair = h("div", { class: preview.columns.length > 6 ? "preview-pair is-stacked" : "preview-pair" });
  pair.append(
    h("div", { class: "preview-side" },
      h("h4", {}, `${beforeLabel} · ${num(preview.total_before)} rows`),
      preview.before.length ? table(preview.columns, preview.before) : h("p", { class: "preview-empty" }, "No rows.")),
    h("div", { class: "preview-side" },
      h("h4", {}, `${afterLabel} · ${num(preview.total_after)} rows`),
      preview.after.length ? table(preview.columns, preview.after) : h("p", { class: "preview-empty" }, "No rows.")));
  wrap.append(pair);
  return wrap;
}

// Plain preview of a dataset with no comparison (used right after upload).
export function renderSimple(preview) {
  const rows = preview.rows;
  const wrap = h("div", { class: "preview" },
    h("p", { class: "preview-note" }, `The first ${num(rows.length)} of ${num(preview.total)} rows.`,
      preview.columns_hidden ? ` ${num(preview.columns_hidden)} more column(s) are not shown.` : ""),
    table(preview.columns, rows));
  return wrap;
}
