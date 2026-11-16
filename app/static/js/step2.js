// Step 2 - Advanced cleaning shell: type confirmation, the three tabs, the plan summary and Apply.
// Every choice is optional. Nothing is sent to the server until "Apply and review" is pressed, and the
// server always rebuilds the result from the basic-cleaned data, so applying again never stacks changes.
import { api } from "./api.js";
import { $$, alertBox, chip, clear, h, num, plural } from "./dom.js";
import { effectivePlan, state } from "./state.js";
import * as missingUi from "./missing-ui.js";
import * as textUi from "./text-ui.js";
import * as typesUi from "./types-ui.js";

const KINDS = [["numeric", "Number"], ["text", "Text"], ["categorical", "Category"], ["date", "Date"],
  ["identifier", "Identifier"], ["boolean", "Yes/No flag"]];
const kindLabel = (k) => (KINDS.find(([v]) => v === k) || [k, k])[1];

let ctx;
const el = {};
let activeTab = "missing";

export function init(context) {
  ctx = context;
  for (const id of ["s2-intro", "s2-loading", "s2-body", "s2-confirm", "tabpanel-missing", "tabpanel-text",
    "tabpanel-types", "plan-summary", "s2-back", "s2-apply"]) {
    el[id] = document.getElementById(id);
  }
  for (const tab of $$(".subtab")) {
    tab.addEventListener("click", () => selectTab(tab.dataset.tab));
    tab.addEventListener("keydown", (e) => {
      const tabs = $$(".subtab");
      const i = tabs.indexOf(tab);
      const next = e.key === "ArrowRight" ? tabs[(i + 1) % tabs.length] : e.key === "ArrowLeft" ? tabs[(i + tabs.length - 1) % tabs.length] : null;
      if (next) { e.preventDefault(); selectTab(next.dataset.tab); next.focus(); }
    });
  }
  el["s2-back"].addEventListener("click", () => ctx.go(1));
  el["s2-apply"].addEventListener("click", apply);
}

function selectTab(name) {
  activeTab = name;
  for (const tab of $$(".subtab")) {
    const on = tab.dataset.tab === name;
    tab.setAttribute("aria-selected", String(on));
    tab.tabIndex = on ? 0 : -1;
    document.getElementById(`tabpanel-${tab.dataset.tab}`).hidden = !on;
  }
}

// ------------------------------------------------------------------ entering the step
export async function enter() {
  const rows = state.basic.report.cleaned_rows;
  const cols = state.basic.report.columns;
  el["s2-intro"].replaceChildren(
    `Working on your basic-cleaned data: ${plural(rows, "row")} × ${plural(cols, "column")}. Everything here is optional, and nothing changes until you press “Apply and review”.`);
  if (state.step1Dirty) {
    el["s2-intro"].append(h("span", { class: "stale-note" }, " Step 1 options were changed but not applied; this step uses the last applied Step 1 result."));
  }
  if (!state.analysis) await analyse();
}

async function analyse() {
  ctx.clearMessages();
  el["s2-loading"].hidden = false;
  el["s2-body"].hidden = true;
  try {
    state.analysis = await api.post("/api/advanced/analysis", { types: state.plan.types, date_orders: state.plan.date_orders });
    prune();
    renderAll();
    el["s2-body"].hidden = false;
  } catch (err) {
    ctx.showError(err);
  } finally {
    el["s2-loading"].hidden = true;
  }
}

// Drop selections that no longer apply (a column that stopped having gaps, a confirmed type that changed...).
function prune() {
  const a = state.analysis;
  const plan = state.plan;
  const missingBy = new Map(a.missing.map((m) => [m.name, m]));
  for (const [col, step] of Object.entries(plan.missing)) {
    const info = missingBy.get(col);
    const ok = info && !info.locked && info.options.some((o) => o.value === step.action)
      && (step.action !== "mapping" || info.mappings.some((m) => m.key === step.key))
      && (step.action !== "formula" || (step.formula && info.formulas.some((f) => f.op === step.formula.op && f.a === step.formula.a && f.b === step.formula.b)));
    if (!ok) delete plan.missing[col];
  }
  const textNames = new Set(a.text.map((t) => t.name));
  for (const col of Object.keys(plan.text)) if (!textNames.has(col)) delete plan.text[col];
  const convBy = new Map(a.convert.map((c) => [c.name, c]));
  for (const [col, step] of Object.entries(plan.convert)) {
    const info = convBy.get(col);
    if (!info || !info.options.some((o) => o.value === step.to) || (step.to === "date" && info.date_ambiguous)) delete plan.convert[col];
  }
}

// ------------------------------------------------------------------ rendering
function renderAll() {
  renderConfirm();
  const change = onPlanChanged;
  missingUi.render(el["tabpanel-missing"], state.analysis, state.plan, change);
  textUi.render(el["tabpanel-text"], state.analysis, state.plan, change);
  typesUi.render(el["tabpanel-types"], state.analysis, state.plan, change);
  updateTabLabels();
  updateSummary();
  selectTab(activeTab);
}

function onPlanChanged() {
  if (state.final) state.step2Dirty = true;
  updateTabLabels();
  updateSummary();
  ctx.refresh();
}

function updateTabLabels() {
  const a = state.analysis;
  const p = effectivePlan();
  const set = { missing: Object.keys(p.missing).length, text: Object.keys(p.text).length, types: Object.keys(p.convert).length };
  const label = (id, text, n, total) => {
    const tab = document.getElementById(id);
    // Native replaceChildren() turns a null argument into the text "null", so only real nodes are passed.
    const parts = [text, h("span", { class: "tab-count", title: `${total} column(s) available` }, String(total))];
    if (n) parts.push(h("span", { class: "tab-set", title: `${n} choice(s) made` }, `${n} set`));
    tab.replaceChildren(...parts);
  };
  label("tab-missing", "Missing values", set.missing, a.missing.length);
  label("tab-text", "Text standardization", set.text, a.text.length);
  label("tab-types", "Data types", set.types, a.convert.length);
}

function updateSummary() {
  const p = effectivePlan();
  let fill = 0;
  let remove = 0;
  for (const [col, step] of Object.entries(p.missing)) {
    const info = state.analysis.missing.find((m) => m.name === col);
    if (!info) continue;
    if (step.action === "remove") remove += info.missing;
    else fill += missingUi.fillCount(info, step);
  }
  const parts = [];
  if (fill) parts.push(`fill ${plural(fill, "cell")}`);
  if (remove) parts.push(`remove up to ${plural(remove, "row")}`);
  const t = Object.keys(p.text).length;
  const c = Object.keys(p.convert).length;
  if (t) parts.push(`standardize ${plural(t, "text column")}`);
  if (c) parts.push(`convert ${plural(c, "column")}`);
  el["plan-summary"].textContent = parts.length
    ? `Your plan: ${parts.join(" · ")}.`
    : "Nothing selected yet. You can continue without changes; the final file will equal the basic-cleaned data.";
}

// ------------------------------------------------------------------ confirming column types
function dateOrderLabel(fmt) {
  const shown = fmt.replace("%d", "DD").replace("%m", "MM").replace("%Y", "YYYY").replace("%H", "HH").replace("%M", "mm").replace("%S", "ss");
  return `${fmt.indexOf("%d") < fmt.indexOf("%m") ? "Day first" : "Month first"} (${shown})`;
}

function renderConfirm() {
  const box = clear(el["s2-confirm"]);
  const a = state.analysis;
  const cols = new Map(a.columns.map((c) => [c.name, c]));
  const uncertain = a.uncertain.map((n) => cols.get(n));
  const ambiguous = a.columns.filter((c) => c.date_ambiguous);

  if (uncertain.length || ambiguous.length) {
    const card = h("section", { class: "confirm-card", "aria-labelledby": "confirm-title" },
      h("h2", { id: "confirm-title" }, "Please confirm these columns"),
      h("p", {}, "CleanSheet is not sure about the columns below, and it would rather ask than guess. Options for a column stay locked until you confirm it."));
    for (const c of uncertain) card.append(confirmRow(c));
    for (const c of ambiguous) card.append(dateOrderRow(c));
    box.append(card);
  }

  const details = h("details", { class: "all-types" },
    h("summary", {}, `Review detected column types (${a.columns.length})`),
    h("p", { class: "col-note" }, "Change a type if CleanSheet got it wrong. Operations on that column will follow the type you choose."),
    h("div", { class: "sheet-scroll types-scroll" }, h("table", { class: "types-table" },
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Column"), h("th", { scope: "col" }, "Detected as"), h("th", { scope: "col" }, "Why"), h("th", { scope: "col" }, "Your choice"))),
      h("tbody", {}, a.columns.map((c) => overrideRow(c))))));
  box.append(details);
}

function sampleText(c) {
  return c.sample.length ? "e.g. " + c.sample.map((s) => `“${s.length > 20 ? s.slice(0, 19) + "…" : s}”`).join(", ") : "";
}

function confirmRow(c) {
  const kinds = [c.kind, ...c.alternatives.filter((k) => k !== c.kind)];
  const select = h("select", { "aria-label": `Type of ${c.name}` }, kinds.map((k) => h("option", { value: k }, kindLabel(k))));
  const button = h("button", { type: "button", class: "btn btn-primary" }, "Confirm");
  button.addEventListener("click", async () => { state.plan.types[c.name] = select.value; await analyse(); onPlanChanged(); });
  return h("div", { class: "confirm-row" },
    h("div", { class: "confirm-what" }, h("strong", {}, c.name), h("span", { class: "col-note" }, `${c.reasons[0]} ${sampleText(c)}`)),
    h("div", { class: "confirm-do" }, h("label", {}, "This column is "), select, button));
}

function dateOrderRow(c) {
  const select = h("select", { "aria-label": `Date order of ${c.name}` }, c.date_candidates.map((f) => h("option", { value: f }, dateOrderLabel(f))));
  const button = h("button", { type: "button", class: "btn btn-primary" }, "Confirm");
  button.addEventListener("click", async () => { state.plan.date_orders[c.name] = select.value; await analyse(); onPlanChanged(); });
  return h("div", { class: "confirm-row" },
    h("div", { class: "confirm-what" }, h("strong", {}, c.name), h("span", { class: "col-note" }, `The dates fit both day-first and month-first (for example 03/04/2024). ${sampleText(c)}`)),
    h("div", { class: "confirm-do" }, h("label", {}, "Dates are written "), select, button));
}

function overrideRow(c) {
  const chosen = state.plan.types[c.name] || "";
  const select = h("select", { "aria-label": `Override the type of ${c.name}` },
    h("option", { value: "" }, `Keep (${c.kind_label})`), KINDS.filter(([k]) => k !== c.kind || chosen).map(([k, l]) => h("option", { value: k }, l)));
  select.value = chosen;
  select.addEventListener("change", async () => {
    if (select.value) state.plan.types[c.name] = select.value;
    else delete state.plan.types[c.name];
    await analyse();
    onPlanChanged();
  });
  return h("tr", {},
    h("th", { scope: "row", class: "types-name", title: c.name }, c.name),
    h("td", {}, chip(c.kind_label, c.needs_confirmation && !c.confirmed ? "warn" : "")),
    h("td", { class: "col-note" }, c.reasons[0]),
    h("td", {}, select));
}

// ------------------------------------------------------------------ apply
async function apply() {
  ctx.clearMessages();
  el["s2-apply"].disabled = true;
  el["s2-apply"].textContent = "Applying…";
  try {
    const result = await api.post("/api/advanced/apply", effectivePlan());
    state.final = { report: result.report, preview: result.preview };
    state.step2Dirty = false;
    ctx.status("Advanced cleaning applied.");
    ctx.go(3);
  } catch (err) {
    ctx.showError(err);
  } finally {
    el["s2-apply"].disabled = false;
    el["s2-apply"].textContent = "Apply and review →";
  }
}

export { alertBox, num };
