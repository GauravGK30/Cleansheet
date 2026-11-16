// Step 2A - Missing values. Only columns that really have missing values appear, and each one offers only
// the methods that suit its type (identifiers never get averages; dates never get mean or median...).
import { h, num, plural } from "./dom.js";
import { columnCard, emptyNote, filterable, OPEN_UP_TO } from "./cards.js";
import { dict } from "./state.js";

const SHORT = {
  mean: "Mean", median: "Median", mode: "Most common value", custom: "Custom value",
  mapping: "From related column", formula: "From formula", remove: "Remove rows",
};
const KEEP_LABEL = "Keep missing values";

function optionLabel(opt, info) {
  const s = info.stats || {};
  let label = opt.label;
  if (opt.value === "mean" && s.mean !== undefined) label += ` (${s.mean})`;
  if (opt.value === "median" && s.median !== undefined) label += ` (${s.median})`;
  if (opt.value === "mode" && s.mode !== undefined) label += ` (${s.mode})`;
  if (opt.value === info.suggested) label += " · suggested";
  return label;
}

function outcome(info, step) {
  const n = info.missing;
  switch (step && step.action) {
    case "mean": case "median": case "mode": case "custom":
      return `Will fill ${plural(n, "cell")}.`;
    case "mapping": {
      const m = info.mappings.find((x) => x.key === step.key);
      return m ? `Will fill ${num(m.recoverable)} of ${num(m.total_missing)}; ${num(m.total_missing - m.recoverable)} stay missing.` : "";
    }
    case "formula": {
      const f = info.formulas.find((x) => x.op === step.formula.op && x.a === step.formula.a && x.b === step.formula.b);
      return f ? `Will calculate ${num(f.recoverable)} of ${num(n)} (only rows where every source value is present); the rest stay missing.` : "";
    }
    case "remove":
      return `Will remove up to ${plural(n, "row")} (every row that has a missing value here).`;
    default:
      return `No change: ${plural(n, "value")} stay missing.`;
  }
}

// How many cells a step fills (used by the plan summary).
export function fillCount(info, step) {
  if (!step) return 0;
  if (["mean", "median", "mode", "custom"].includes(step.action)) return info.missing;
  if (step.action === "mapping") return (info.mappings.find((x) => x.key === step.key) || {}).recoverable || 0;
  if (step.action === "formula") {
    return (info.formulas.find((x) => x.op === step.formula.op && x.a === step.formula.a && x.b === step.formula.b) || {}).recoverable || 0;
  }
  return 0;
}

function customInput(info, step, onInput) {
  let control;
  if (info.kind === "boolean") {
    control = h("select", { "aria-label": `Value to fill ${info.name} with` },
      info.values.map((v) => h("option", { value: v }, v)));
    step.value = step.value && info.values.includes(step.value) ? step.value : info.values[0];
    control.value = step.value;
    control.addEventListener("change", () => onInput(control.value));
    return control;
  }
  if (info.kind === "date") {
    control = h("input", { type: "date", "aria-label": `Date to fill ${info.name} with`, value: step.value || "" });
  } else if (info.kind === "numeric" || info.kind === "calculated") {
    control = h("input", { type: "text", inputmode: "decimal", placeholder: "Number", "aria-label": `Number to fill ${info.name} with`, value: step.value || "" });
  } else {
    control = h("input", { type: "text", placeholder: "Text to fill in", maxlength: 200, "aria-label": `Text to fill ${info.name} with`, value: step.value || "" });
  }
  control.addEventListener("input", () => onInput(control.value));
  return control;
}

function buildCard(info, plan, open, onChange) {
  const card = columnCard({
    name: info.name, kindLabel: info.kind_label, open,
    meta: `${plural(info.missing, "missing value")} · ${info.missing_pct}%`,
  });
  const body = card.body;

  if (info.locked) {
    body.append(h("p", { class: "col-note" }, "Confirm this column’s type above to unlock its options."));
    return card.root;
  }

  const select = h("select", { "aria-label": `What to do with missing values in ${info.name}` });
  const options = [{ value: "keep", label: KEEP_LABEL }, ...info.options.filter((o) => o.value !== "keep")];
  for (const opt of options) select.append(h("option", { value: opt.value }, opt.value === "keep" ? KEEP_LABEL : optionLabel(opt, info)));
  const extra = h("div", { class: "extra" });
  const result = h("p", { class: "outcome" });
  body.append(h("div", { class: "field" }, h("label", {}, "Missing values"), select), extra, result);

  if (info.suggested && info.suggested_reason) {
    body.append(h("p", { class: "col-note" }, h("strong", {}, "Suggested: "), SHORT[info.suggested] + ". ", info.suggested_reason));
  }
  if (info.kind === "identifier") body.append(h("p", { class: "col-note" }, "Identifiers are never averaged or guessed."));
  if (info.kind === "boolean") body.append(h("p", { class: "col-note" }, "Unknown stays unknown unless you choose a value."));
  if (info.kind === "date" && info.date_ambiguous) body.append(h("p", { class: "col-note" }, "The day/month order of this column is unclear; choose it above before typing a date."));

  const refresh = () => {
    const step = plan.missing[info.name];
    card.setChoice(step ? SHORT[step.action] : "");
    result.textContent = outcome(info, step);
  };

  const drawExtra = () => {
    extra.replaceChildren();
    const step = plan.missing[info.name];
    if (!step) return;
    if (step.action === "custom") {
      extra.append(h("div", { class: "field" }, h("label", {}, "Value"), customInput(info, step, (v) => { step.value = v; onChange(); })));
    } else if (step.action === "mapping") {
      const sel = h("select", { "aria-label": "Related column to recover from" },
        info.mappings.map((m) => h("option", { value: m.key }, `${m.key} (fills ${m.recoverable} of ${m.total_missing})`)));
      step.key = info.mappings.some((m) => m.key === step.key) ? step.key : info.mappings[0].key;
      sel.value = step.key;
      sel.addEventListener("change", () => { step.key = sel.value; refresh(); onChange(); });
      extra.append(h("div", { class: "field" }, h("label", {}, "Recover from"), sel));
    } else if (step.action === "formula") {
      const sel = h("select", { "aria-label": "Formula to recalculate from" },
        info.formulas.map((f, i) => h("option", { value: String(i) }, `${f.label} (fills ${f.recoverable})`)));
      const idx = Math.max(0, info.formulas.findIndex((f) => step.formula && f.op === step.formula.op && f.a === step.formula.a && f.b === step.formula.b));
      sel.value = String(idx);
      const pick = () => { const f = info.formulas[Number(sel.value)]; step.formula = { op: f.op, a: f.a, b: f.b }; };
      pick();
      sel.addEventListener("change", () => { pick(); refresh(); onChange(); });
      extra.append(h("div", { class: "field" }, h("label", {}, "Formula"), sel));
    }
  };

  select.addEventListener("change", () => {
    const action = select.value;
    if (action === "keep") delete plan.missing[info.name];
    else {
      const step = { action };
      if (action === "mapping") step.key = info.mappings[0].key;
      if (action === "formula") step.formula = { op: info.formulas[0].op, a: info.formulas[0].a, b: info.formulas[0].b };
      plan.missing[info.name] = step;
    }
    drawExtra();
    refresh();
    onChange();
  });

  const current = plan.missing[info.name];
  select.value = current ? current.action : "keep";
  if (select.value !== (current ? current.action : "keep")) delete plan.missing[info.name];   // stale choice
  drawExtra();
  refresh();
  return card.root;
}

export function render(container, analysis, plan, onChange) {
  container.replaceChildren();
  const infos = analysis.missing;
  if (!infos.length) {
    container.append(emptyNote("success", "No missing values", "Every column is complete, so there is nothing to fill here."));
    return;
  }
  container.append(h("p", { class: "tab-intro" },
    `${plural(infos.length, "column")} ${infos.length === 1 ? "has" : "have"} missing values. Leave a column on “${KEEP_LABEL}” to change nothing.`));
  const open = infos.length <= OPEN_UP_TO;
  container.append(filterable(infos.map((info) => buildCard(info, plan, open, onChange))));
  container.append(h("div", { class: "btn-row tab-tools" },
    h("button", { type: "button", class: "btn btn-quiet", onclick: () => { plan.missing = dict(); render(container, analysis, plan, onChange); onChange(); } },
      "Reset this tab")));
}
