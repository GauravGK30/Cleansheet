// Step 1 - Basic cleaning: upload, options, result, and the choice between downloading and continuing.
import { api } from "./api.js";
import { $, $$, alertBox, chip, clear, h, num, plural } from "./dom.js";
import { renderPreview } from "./preview.js";
import { dict, state } from "./state.js";

const BINARY_CHOICES = [
  ["keep", "Keep as is"], ["true_false", "TRUE / FALSE"], ["yes_no", "Yes / No"], ["one_zero", "1 / 0"],
];

let ctx;
const el = {};

export function init(context) {
  ctx = context;
  for (const id of ["dropzone", "file-input", "upload-card", "loaded", "file-name", "file-meta", "replace-file",
    "load-notes", "scan-found", "basic-form", "opt-dedupe", "dedupe-sub", "dedupe-picker", "dedupe-filter",
    "dedupe-all", "dedupe-none", "dedupe-list", "opt-trim", "opt-missing", "token-note", "op-binary",
    "binary-list", "apply-basic", "basic-stale", "basic-results"]) {
    el[id] = document.getElementById(id);
  }

  el["file-input"].addEventListener("change", () => {
    const file = el["file-input"].files[0];
    if (file) upload(file);
    el["file-input"].value = "";
  });
  for (const type of ["dragenter", "dragover"]) {
    el.dropzone.addEventListener(type, (e) => { e.preventDefault(); el.dropzone.classList.add("is-over"); });
  }
  for (const type of ["dragleave", "drop"]) {
    el.dropzone.addEventListener(type, (e) => { e.preventDefault(); el.dropzone.classList.remove("is-over"); });
  }
  el.dropzone.addEventListener("drop", (e) => {
    const file = e.dataTransfer && e.dataTransfer.files[0];
    if (file) upload(file);
  });
  el["replace-file"].addEventListener("click", replaceFile);

  el["basic-form"].addEventListener("submit", (e) => { e.preventDefault(); applyBasic(); });
  el["basic-form"].addEventListener("change", onOptionsChanged);
  el["opt-dedupe"].addEventListener("change", syncDedupeUi);
  for (const radio of $$("input[name=dedupe-mode]")) radio.addEventListener("change", syncDedupeUi);
  el["dedupe-filter"].addEventListener("input", filterDedupeList);
  el["dedupe-all"].addEventListener("click", () => setVisibleDedupe(true));
  el["dedupe-none"].addEventListener("click", () => setVisibleDedupe(false));
}

// ------------------------------------------------------------------ upload
async function upload(file) {
  ctx.clearMessages();
  el.dropzone.classList.add("is-busy");
  ctx.status("Uploading and checking the file…");
  try {
    const data = await api.upload(file);
    state.data = data;
    state.basic = state.final = state.analysis = null;
    state.step1Dirty = state.step2Dirty = false;
    ctx.resetPlan();
    show(data);
    ctx.refresh();
    ctx.status("File loaded.");
  } catch (err) {
    ctx.showError(err);
  } finally {
    el.dropzone.classList.remove("is-busy");
  }
}

async function replaceFile() {
  try { await api.post("/api/reset"); } catch { /* the page resets either way */ }
  ctx.reset();
}

export function showUploader() {
  el["upload-card"].hidden = false;
  el.loaded.hidden = true;
}

// ------------------------------------------------------------------ the loaded file
export function show(data) {
  el["upload-card"].hidden = true;
  el.loaded.hidden = false;
  el["file-name"].textContent = data.filename;
  el["file-meta"].textContent = `${plural(data.rows, "row")} × ${plural(data.columns, "column")} · ${data.format.toUpperCase()}`;

  clear(el["load-notes"]);
  for (const warning of data.load_warnings || []) el["load-notes"].append(alertBox("warn", "Check your data", warning));
  for (const note of data.notes || []) el["load-notes"].append(alertBox("info", null, note));

  const scan = data.scan;
  clear(el["scan-found"]).append(
    foundItem(scan.duplicate_rows, "duplicate row", "duplicate rows"),
    foundItem(scan.whitespace_cells, "cell with extra spaces", "cells with extra spaces"),
    foundItem(scan.missing_token_cells, "placeholder cell (N/A, null…)", "placeholder cells (N/A, null…)"),
    foundItem(scan.binary_columns.length, "yes/no column", "yes/no columns"));

  el["token-note"].textContent = `Placeholders recognised: ${data.limits.missing_tokens.join(", ")}, and blank cells.`;

  buildDedupeList(data);
  buildBinaryList(scan);
  syncDedupeUi();
  setDefaultsFromBasic();
  if (state.basic) renderResults(state.basic);
  else { clear(el["basic-results"]); el["basic-results"].hidden = true; }
  markDirty(false);
}

function foundItem(n, one, many) {
  return h("li", { class: n ? "found-item has-some" : "found-item" }, h("strong", {}, num(n)), " ", n === 1 ? one : many);
}

function buildDedupeList(data) {
  clear(el["dedupe-list"]);
  data.scan.columns.forEach((c, i) => {
    const id = `dd-${i}`;
    el["dedupe-list"].append(h("label", { class: "check picker-item", for: id, dataset: { name: c.name.toLowerCase() } },
      h("input", { type: "checkbox", id, value: c.name, checked: true }), h("span", {}, c.name)));
  });
}

function buildBinaryList(scan) {
  clear(el["binary-list"]);
  el["op-binary"].hidden = scan.binary_columns.length === 0;
  scan.binary_columns.forEach((b, i) => {
    const id = `bin-${i}`;
    const select = h("select", { id, dataset: { column: b.name } },
      BINARY_CHOICES.map(([value, label]) => h("option", { value }, label)));
    el["binary-list"].append(h("div", { class: "binary-row" },
      h("label", { for: id, class: "binary-name" }, b.name),
      chip(`now ${b.style}`),
      b.numeric_only ? chip("only 1s and 0s: may be a number", "warn") : null,
      select));
  });
}

// When the form is rebuilt for a restored session, show the options that were actually applied.
function setDefaultsFromBasic() {
  const opts = state.basic && state.basic.options;
  if (!opts) return;
  el["opt-dedupe"].checked = !!opts.remove_duplicates;
  el["opt-trim"].checked = !!opts.trim;
  el["opt-missing"].checked = !!opts.normalise_missing;
  for (const r of $$("input[name=dedupe-mode]")) r.checked = r.value === opts.dedupe_mode;
  const chosen = new Set(opts.dedupe_columns || []);
  if (opts.dedupe_mode === "subset") for (const box of $$("input", el["dedupe-list"])) box.checked = chosen.has(box.value);
  const chosenBinary = dict(opts.binary);
  for (const sel of $$("select", el["binary-list"])) sel.value = chosenBinary[sel.dataset.column] || "keep";
  syncDedupeUi();
}

function syncDedupeUi() {
  const on = el["opt-dedupe"].checked;
  el["dedupe-sub"].classList.toggle("is-off", !on);
  for (const input of $$("input", el["dedupe-sub"])) input.disabled = !on && input !== el["opt-dedupe"];
  const subset = on && selectedMode() === "subset";
  el["dedupe-picker"].hidden = !subset;
  el["dedupe-filter"].disabled = el["dedupe-all"].disabled = el["dedupe-none"].disabled = !subset;
}

const selectedMode = () => ($("input[name=dedupe-mode]:checked") || {}).value || "all";

function filterDedupeList() {
  const q = el["dedupe-filter"].value.trim().toLowerCase();
  for (const item of $$(".picker-item", el["dedupe-list"])) item.hidden = q && !item.dataset.name.includes(q);
}

function setVisibleDedupe(value) {
  for (const item of $$(".picker-item", el["dedupe-list"])) {
    if (!item.hidden) $("input", item).checked = value;
  }
  onOptionsChanged();
}

// ------------------------------------------------------------------ options -> request
function collectOptions() {
  const binary = dict();
  for (const sel of $$("select", el["binary-list"])) if (sel.value !== "keep") binary[sel.dataset.column] = sel.value;
  return {
    remove_duplicates: el["opt-dedupe"].checked,
    dedupe_mode: selectedMode(),
    dedupe_columns: $$("input:checked", el["dedupe-list"]).map((box) => box.value),
    trim: el["opt-trim"].checked,
    normalise_missing: el["opt-missing"].checked,
    binary,
  };
}

function onOptionsChanged() {
  if (state.basic) markDirty(true);
}

function markDirty(value) {
  state.step1Dirty = value;
  el["basic-stale"].hidden = !value;
  el["basic-results"].classList.toggle("is-stale", value);
  for (const button of $$("[data-needs-fresh]", el["basic-results"])) button.disabled = value;
  ctx.refresh();
}

async function applyBasic() {
  ctx.clearMessages();
  const options = collectOptions();
  if (options.remove_duplicates && options.dedupe_mode === "subset" && !options.dedupe_columns.length) {
    ctx.showError("Select at least one column to compare for duplicates, or choose “Compare all columns”.");
    return;
  }
  el["apply-basic"].disabled = true;
  el["apply-basic"].textContent = "Cleaning…";
  try {
    const result = await api.post("/api/basic/apply", options);
    state.basic = { report: result.report, preview: result.preview, options: result.options };
    state.analysis = null;                              // Step 2 must look at the new dataset
    if (result.advanced_discarded) state.final = null;
    state.step2Dirty = false;
    renderResults(state.basic);
    markDirty(false);
    if (result.advanced_discarded) {
      el["basic-results"].prepend(alertBox("info", "Step 2 results were cleared",
        "They were built from the earlier Step 1 result. Your Step 2 selections are kept where they still apply; apply Step 2 again to rebuild the final file."));
    }
    ctx.status("Basic cleaning applied.");
    el["basic-results"].scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    ctx.showError(err);
  } finally {
    el["apply-basic"].disabled = false;
    el["apply-basic"].textContent = "Apply basic cleaning";
  }
}

// ------------------------------------------------------------------ results
const tile = (label, value, caption, tone = "") =>
  h("div", { class: `tile ${tone}`.trim() }, h("dt", {}, label), h("dd", {}, value), caption ? h("p", { class: "tile-cap" }, caption) : null);

function renderResults({ report, preview }) {
  const box = clear(el["basic-results"]);
  box.hidden = false;
  box.append(h("h2", { id: "basic-result-title" }, "Result of basic cleaning"));
  box.append(h("dl", { class: "tiles" },
    tile("Original rows", num(report.original_rows)),
    tile("Cleaned rows", num(report.cleaned_rows)),
    tile("Duplicate rows removed", num(report.duplicates_removed), report.duplicates_removed ? null : "None found or not requested"),
    tile("Missing values detected", num(report.missing_after),
      report.missing_tokens_normalised ? `${plural(report.missing_tokens_normalised, "placeholder")} turned into empty cells` : "empty cells in the cleaned data"),
    tile("Whitespace changes", num(report.whitespace_cells_changed),
      report.whitespace_cells_changed ? `in ${plural(report.whitespace_columns_changed, "column")}` : "cells needed trimming"),
    tile("Yes/No columns", `${report.binary_converted} of ${report.binary_detected}`,
      report.binary_skipped.length ? `${plural(report.binary_skipped.length, "conversion")} skipped, see below` : "detected and converted")));

  if (report.binary_columns.length) {
    box.append(h("ul", { class: "result-list" }, report.binary_columns.map((b) => h("li", {},
      h("strong", {}, b.column), ": ", b.converted_to ? `${b.detected_as} → ${b.converted_to}` : `${b.detected_as}, left as is`))));
  }
  if (report.binary_skipped.length) {
    box.append(alertBox("warn", "Some yes/no conversions were skipped", report.warnings));
  }

  box.append(h("h3", {}, "Before and after"), renderPreview(preview, { beforeLabel: "Original upload", afterLabel: "Basic-cleaned" }));

  box.append(h("h3", {}, "What next?"));
  box.append(h("div", { class: "choices" },
    h("section", { class: "choice" },
      h("p", { class: "choice-tag" }, "Option A"),
      h("h4", {}, "Download and finish"),
      h("p", {}, "Save the basic-cleaned data now. You can stop here."),
      h("div", { class: "btn-row" },
        downloadButton("basic", "csv", "Download CSV"), downloadButton("basic", "xlsx", "Download XLSX")),
      bigFileNote(report.cleaned_rows)),
    h("section", { class: "choice" },
      h("p", { class: "choice-tag" }, "Option B"),
      h("h4", {}, "Continue to Advanced cleaning"),
      h("p", {}, "Fill missing values, standardize text and convert types. It starts from this basic-cleaned data, not the original."),
      h("div", { class: "btn-row" },
        h("button", { type: "button", class: "btn btn-primary", "data-needs-fresh": "", onclick: () => ctx.go(2) }, "Continue to Step 2 →")))));
  box.append(h("p", { class: "result-hint" },
    "Changing the options above and applying again always starts from your original upload, so nothing is cleaned twice."));
}

function downloadButton(stage, fmt, label) {
  const button = h("button", { type: "button", class: "btn", "data-needs-fresh": "" }, label);
  button.addEventListener("click", () => ctx.download(`/api/download/${stage}/${fmt}`, button));
  return button;
}

// Building an .xlsx takes about a minute per 500,000 rows (a .csv is near-instant), so say so up front.
const BIG_XLSX_ROWS = 100_000;
function bigFileNote(rows) {
  return rows >= BIG_XLSX_ROWS
    ? h("p", { class: "result-hint" }, `Large file: preparing the XLSX can take a minute or more. The CSV is much faster.`)
    : null;
}

export { downloadButton, bigFileNote };
