// Step 2C - Data types. One compact row per column, showing only the conversions that suit its type.
// A conversion that meets an invalid value is skipped for that whole column (the server explains why).
import { append, chip, h, plural } from "./dom.js";
import { emptyNote, filterControls } from "./cards.js";
import { dict } from "./state.js";

function row(info, plan, onChange) {
  const step = () => plan.convert[info.name];
  const select = h("select", { "aria-label": `Convert ${info.name} to` },
    info.options.map((o) => h("option", { value: o.value, disabled: o.value === "date" && info.date_ambiguous }, o.label)));
  const extra = h("span", { class: "types-extra" });
  const note = h("span", { class: "types-note" });

  const draw = () => {
    extra.replaceChildren();
    const s = step();
    if (s && s.to === "decimal") {
      const input = h("input", { type: "number", min: String(info.min_decimals), max: "10", step: "1",
        value: s.decimals ?? info.default_decimals, "aria-label": `Decimal places for ${info.name}` });
      s.decimals = Number(input.value);
      input.addEventListener("input", () => { s.decimals = input.value === "" ? undefined : Number(input.value); onChange(); });
      extra.append(h("label", { class: "inline-label" }, "places ", input));
    }
  };

  const warnings = [];
  if (info.invalid_numbers > 0) warnings.push(`${plural(info.invalid_numbers, "value")} are not numbers`);
  if (info.date_ambiguous) warnings.push("day/month order unclear: choose it above");
  else if ((info.kind === "date" || info.options.some((o) => o.value === "date")) && info.date_ratio < 1) {
    warnings.push(`only ${Math.round(info.date_ratio * 100)}% of values are valid dates`);
  }
  if (info.kind === "identifier") warnings.push("identifier: stays text, leading zeros protected");
  note.append(...warnings.map((w) => chip(w, w.startsWith("identifier") ? "" : "warn")));

  select.value = step() ? step().to : "keep";
  if (select.value !== (step() ? step().to : "keep")) delete plan.convert[info.name];
  select.addEventListener("change", () => {
    if (select.value === "keep") delete plan.convert[info.name];
    else plan.convert[info.name] = { to: select.value };
    draw();
    onChange();
  });
  draw();

  const sample = info.sample.length ? info.sample.map((s) => (s.length > 18 ? s.slice(0, 17) + "…" : s)).join(", ") : "";
  return h("tr", { dataset: { name: info.name.toLowerCase() } },
    h("th", { scope: "row", class: "types-name", title: info.name }, info.name),
    h("td", {}, chip(info.kind_label), sample ? h("span", { class: "types-sample" }, sample) : null, note),
    h("td", {}, select, extra));
}

export function render(container, analysis, plan, onChange) {
  container.replaceChildren();
  const infos = analysis.convert;
  if (!infos.length) {
    container.append(emptyNote("info", "No conversions available", "None of the columns offers a type conversion."));
    return;
  }
  container.append(h("p", { class: "tab-intro" },
    `${plural(infos.length, "column")} can be converted. Columns left on “Keep original” are not changed. If any value in a column cannot be converted, that column is skipped and its original values are kept.`));
  const rows = infos.map((info) => row(info, plan, onChange));
  const scroll = h("div", { class: "sheet-scroll types-scroll" },
    h("table", { class: "types-table" },
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Column"), h("th", { scope: "col" }, "Detected as"), h("th", { scope: "col" }, "Convert to"))),
      h("tbody", {}, rows)));
  const { bar, empty } = filterControls(scroll, "tr[data-name]", rows.length);
  append(container, [bar, scroll, empty]);          // bar/empty are null for short lists; native append() would print "null"
  container.append(h("div", { class: "btn-row tab-tools" },
    h("button", { type: "button", class: "btn btn-quiet", onclick: () => { plan.convert = dict(); render(container, analysis, plan, onChange); onChange(); } },
      "Reset this tab")));
}
