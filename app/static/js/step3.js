// Step 3 - Review & export: the numbers, every warning and skipped operation, a before/after preview, downloads.
import { alertBox, append, chip, clear, h, num, plural } from "./dom.js";
import { renderPreview } from "./preview.js";
import { state } from "./state.js";
import { bigFileNote, downloadButton } from "./step1.js";

let ctx;
let root;

export function init(context) {
  ctx = context;
  root = document.getElementById("s3-body");
}

const tile = (label, value, caption) =>
  h("div", { class: "tile" }, h("dt", {}, label), h("dd", {}, value), caption ? h("p", { class: "tile-cap" }, caption) : null);

const STEP_NAMES = { missing: "Missing values", text: "Text", convert: "Data type" };

export function render() {
  clear(root);
  if (!state.final) {
    root.append(alertBox("info", "Nothing to review yet", "Apply Step 2 first. You can apply it without choosing anything."));
    return;
  }
  const r = state.final.report;

  if (state.step2Dirty) {
    root.append(alertBox("warn", "This review is out of date",
      "You changed your Step 2 choices after applying them. Go back and press “Apply and review” again to update it. Downloads are paused until then."));
  }
  if (r.empty_plan) {
    root.append(alertBox("info", "No advanced operations were chosen",
      "The final dataset is identical to the basic-cleaned dataset."));
  }

  root.append(h("dl", { class: "tiles" },
    tile("Original rows", num(r.rows_original), "as uploaded"),
    tile("Basic-cleaned rows", num(r.rows_basic), "after Step 1"),
    tile("Final rows", num(r.rows_final), "after Step 2"),
    tile("Missing values", `${num(r.missing_basic)} → ${num(r.missing_final)}`,
      `after Step 1 → after Step 2 (${num(r.missing_original)} blank cells in the upload)`),
    tile("Duplicate rows removed", num(r.duplicates_removed), "in Step 1"),
    tile("Rows removed", num(r.rows_basic - r.rows_final), "in Step 2"),
    tile("Columns modified", `${num(r.columns_modified)} of ${num(r.columns_total)}`,
      r.modified_columns.length ? r.modified_columns.slice(0, 4).join(", ") + (r.modified_columns.length > 4 ? "…" : "") : "none"),
    tile("Conversions completed", num(r.conversions_completed), r.conversions_skipped ? `${num(r.conversions_skipped)} skipped` : "none skipped")));

  if (r.warnings.length || r.operations_skipped) {
    root.append(alertBox("warn",
      `${plural(r.warnings.length, "warning")}${r.operations_skipped ? ` · ${plural(r.operations_skipped, "operation")} skipped` : ""}`,
      r.warnings.length ? r.warnings : "Some operations were skipped. See the details below."));
  } else if (!r.empty_plan) {
    root.append(alertBox("success", "Everything you chose was applied", null));
  }

  if (r.operations.length) {
    const rows = r.operations.map((o) => h("tr", { class: o.status === "skipped" ? "row-skipped" : "" },
      h("td", {}, STEP_NAMES[o.step]),
      h("th", { scope: "row" }, o.column),
      h("td", {}, o.label),
      h("td", {}, o.detail),
      h("td", {}, chip(o.status === "applied" ? "Applied" : "Skipped", o.status === "applied" ? "accent" : "warn"))));
    root.append(h("details", { class: "ops-log", open: r.operations.length <= 8 },
      h("summary", {}, `What was done (${r.operations.length})`),
      h("div", { class: "sheet-scroll types-scroll" }, h("table", { class: "types-table" },
        h("thead", {}, h("tr", {}, ["Section", "Column", "Choice", "Result", "Status"].map((t) => h("th", { scope: "col" }, t)))),
        h("tbody", {}, rows)))));
  }

  root.append(h("h2", {}, "Before and after"),
    renderPreview(state.final.preview, { beforeLabel: "Basic-cleaned", afterLabel: "Final" }));

  const disabled = state.step2Dirty;
  const csv = downloadButton("final", "csv", "Download final CSV");
  const xlsx = downloadButton("final", "xlsx", "Download final XLSX");
  csv.classList.add("btn-primary");
  xlsx.classList.add("btn-primary");
  csv.disabled = xlsx.disabled = disabled;
  // dom.js append() skips null; the native Element.append() would print the word "null" for the large-file
  // note, which is null for every file under 100,000 rows.
  append(root, [h("h2", {}, "Download"),
    h("div", { class: "btn-row" }, csv, xlsx),
    bigFileNote(r.rows_final),
    h("p", { class: "result-hint" },
      "XLSX stores numbers and converted dates as real Excel values and keeps identifiers as text with their leading zeros. Excel can drop leading zeros when it opens a CSV file."),
    h("div", { class: "btn-row nav-row" },
      h("button", { type: "button", class: "btn", onclick: () => ctx.go(2) }, "← Back to Advanced cleaning"),
      h("button", { type: "button", class: "btn", onclick: () => ctx.go(1) }, "Back to Basic cleaning"),
      h("button", { type: "button", class: "btn btn-danger-quiet", onclick: () => ctx.reset(true) }, "Start over with a new file"))]);
}
