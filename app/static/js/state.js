// The one place the page keeps its data. The datasets themselves live on the server; this holds what the
// server reported plus the person's current selections for Step 2.

// Choices are stored by COLUMN NAME, and names come from the person's file. A plain {} inherits keys such as
// "constructor", "toString" and "valueOf" (so an untouched column would look as if it already had a choice) and
// treats "__proto__" as a setter (so a choice for it would silently vanish). A null-prototype object has no
// inherited keys, which makes every header an ordinary key. Use dict() for any object keyed by a column name.
export const dict = (source) => Object.assign(Object.create(null), source || {});

export const emptyPlan = () => ({ types: dict(), date_orders: dict(), missing: dict(), text: dict(), convert: dict() });

export const state = {
  data: null,        // upload payload: filename, rows, columns, scan, notes, preview, limits
  basic: null,       // { report, preview, options } once Step 1 has been applied
  final: null,       // { report, preview } once Step 2 has been applied
  analysis: null,    // Step 2 analysis of the basic-cleaned data
  plan: emptyPlan(), // Step 2 selections (what "Apply and review" sends)
  step1Dirty: false, // Step 1 options changed since the last Apply
  step2Dirty: false, // Step 2 selections changed since the last Apply
  step: 1,
};

export function resetAll() {
  state.data = state.basic = state.final = state.analysis = null;
  state.plan = emptyPlan();
  state.step1Dirty = state.step2Dirty = false;
  state.step = 1;
}

// A plan with the "do nothing" entries removed, ready to send.
export function effectivePlan(plan = state.plan) {
  const out = emptyPlan();
  out.types = dict(plan.types);
  out.date_orders = dict(plan.date_orders);
  for (const [col, step] of Object.entries(plan.missing)) {
    if (step && step.action && step.action !== "keep") out.missing[col] = step;
  }
  for (const [col, step] of Object.entries(plan.text)) {
    const rules = (step.replace || []).filter((r) => r.find);
    if (step.case !== "preserve" && step.case || step.trim || step.collapse || rules.length) {
      out.text[col] = { ...step, replace: rules };
    }
  }
  for (const [col, step] of Object.entries(plan.convert)) {
    if (step && step.to && step.to !== "keep") out.convert[col] = step;
  }
  return out;
}
