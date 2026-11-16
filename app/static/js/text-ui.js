// Step 2B - Text standardization. Only text and category columns are listed: identifiers, numbers and
// dates are protected, so casing and replacing can never touch an ID or a leading zero.
import { h, plural } from "./dom.js";
import { columnCard, emptyNote, filterable, OPEN_UP_TO } from "./cards.js";
import { dict } from "./state.js";

const CASES = [["preserve", "Keep original case"], ["lower", "lowercase"], ["upper", "UPPERCASE"], ["title", "Title Case"]];
const MAX_RULES = 10;

const blank = () => ({ case: "preserve", trim: false, collapse: false, replace: [] });

function summaryOf(step) {
  if (!step) return "";
  const parts = [];
  if (step.trim) parts.push("trim");
  if (step.collapse) parts.push("collapse spaces");
  if (step.case !== "preserve") parts.push(CASES.find(([v]) => v === step.case)[1]);
  const rules = step.replace.filter((r) => r.find).length;
  if (rules) parts.push(plural(rules, "rule"));
  return parts.join(" · ");
}

function ruleRow(rule, onChange, onRemove) {
  const find = h("input", { type: "text", maxlength: 200, placeholder: "Find", "aria-label": "Text to find", value: rule.find });
  const repl = h("input", { type: "text", maxlength: 200, placeholder: "Replace with (can be empty)", "aria-label": "Replace with", value: rule.replace });
  const matchCase = h("input", { type: "checkbox", checked: rule.match_case });
  const whole = h("input", { type: "checkbox", checked: rule.whole_cell });
  find.addEventListener("input", () => { rule.find = find.value; onChange(); });
  repl.addEventListener("input", () => { rule.replace = repl.value; onChange(); });
  matchCase.addEventListener("change", () => { rule.match_case = matchCase.checked; onChange(); });
  whole.addEventListener("change", () => { rule.whole_cell = whole.checked; onChange(); });
  return h("div", { class: "rule" },
    find, h("span", { class: "rule-arrow", "aria-hidden": "true" }, "→"), repl,
    h("label", { class: "check" }, matchCase, "match case"),
    h("label", { class: "check" }, whole, "whole cell only"),
    h("button", { type: "button", class: "btn btn-danger-quiet", "aria-label": "Remove this rule", onclick: onRemove }, "Remove"));
}

function buildCard(info, plan, open, onChange) {
  const card = columnCard({ name: info.name, kindLabel: info.kind_label, open, meta: `${plural(info.unique, "different value")}` });
  const body = card.body;
  const get = () => plan.text[info.name];
  const ensure = () => (plan.text[info.name] = plan.text[info.name] || blank());
  const touched = () => { card.setChoice(summaryOf(get())); onChange(); };

  const hints = [];
  if (info.edge_space) hints.push(`${plural(info.edge_space, "cell")} with spaces at the start or end`);
  if (info.repeated_space) hints.push(`${plural(info.repeated_space, "cell")} with repeated spaces`);
  if (info.mixed_case) hints.push("same words in different capitals");
  if (hints.length) body.append(h("p", { class: "col-note" }, "Found: " + hints.join("; ") + "."));
  if (info.sample.length) body.append(h("p", { class: "col-note" }, "Examples: " + info.sample.map((s) => `“${s}”`).join(", ")));

  const current = get() || blank();
  const caseSel = h("select", { "aria-label": `Letter case for ${info.name}` }, CASES.map(([v, l]) => h("option", { value: v }, l)));
  caseSel.value = current.case;
  const trim = h("input", { type: "checkbox", checked: current.trim });
  const collapse = h("input", { type: "checkbox", checked: current.collapse });
  caseSel.addEventListener("change", () => { ensure().case = caseSel.value; touched(); });
  trim.addEventListener("change", () => { ensure().trim = trim.checked; touched(); });
  collapse.addEventListener("change", () => { ensure().collapse = collapse.checked; touched(); });

  body.append(h("div", { class: "text-controls" },
    h("div", { class: "field" }, h("label", {}, "Letter case"), caseSel),
    h("label", { class: "check" }, trim, "Trim spaces at the start and end"),
    h("label", { class: "check" }, collapse, "Collapse repeated spaces")));

  const rules = h("div", { class: "rules" });
  const addBtn = h("button", { type: "button", class: "btn btn-quiet" }, "+ Add find and replace rule");
  const drawRules = () => {
    rules.replaceChildren();
    const step = get();
    for (const rule of step ? step.replace : []) {
      rules.append(ruleRow(rule, touched, () => { step.replace.splice(step.replace.indexOf(rule), 1); drawRules(); touched(); }));
    }
    addBtn.disabled = !!step && step.replace.length >= MAX_RULES;
  };
  addBtn.addEventListener("click", () => {
    ensure().replace.push({ find: "", replace: "", match_case: false, whole_cell: false });
    drawRules();
    touched();
    const inputs = rules.querySelectorAll("input[type=text]");
    if (inputs.length) inputs[inputs.length - 2].focus();
  });
  body.append(h("h4", { class: "mini-head" }, "Find and replace"), rules, addBtn,
    h("p", { class: "col-note" }, "Runs in this order: trim, collapse spaces, case, then find and replace. Matching is exact text, not patterns."));
  drawRules();
  card.setChoice(summaryOf(plan.text[info.name]));
  return card.root;
}

export function render(container, analysis, plan, onChange) {
  container.replaceChildren();
  const infos = analysis.text;
  const protectedIds = analysis.columns.filter((c) => c.kind === "identifier").map((c) => c.name);
  if (!infos.length) {
    container.append(emptyNote("info", "No text columns to standardize",
      "Only text and category columns offer these tools. Numbers, dates and identifiers are protected."));
    return;
  }
  container.append(h("p", { class: "tab-intro" },
    `${plural(infos.length, "text column")} can be standardized.`,
    protectedIds.length ? ` Identifier columns (${protectedIds.slice(0, 4).join(", ")}${protectedIds.length > 4 ? "…" : ""}) are protected and not listed.` : ""));
  const open = infos.length <= OPEN_UP_TO;
  container.append(filterable(infos.map((info) => buildCard(info, plan, open, onChange))));
  container.append(h("div", { class: "btn-row tab-tools" },
    h("button", { type: "button", class: "btn btn-quiet", onclick: () => { plan.text = dict(); render(container, analysis, plan, onChange); onChange(); } },
      "Reset this tab")));
}
