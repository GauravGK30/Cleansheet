// DOM helpers. Everything that comes from an uploaded file is inserted as text (never as HTML),
// so a cell containing "<script>" is displayed literally and can never run.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === false || value === null || value === undefined) continue;
    if (key === "class") el.className = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (key === "value") el.value = value;
    else if (key === "checked" || key === "disabled" || key === "hidden" || key === "selected") el[key] = !!value;
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  append(el, children);
  return el;
}

export function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function clear(el) {
  el.replaceChildren();
  return el;
}

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

export const num = (n) => Number(n).toLocaleString("en-US");
export const plural = (n, one, many) => `${num(n)} ${n === 1 ? one : many || one + "s"}`;

let uid = 0;
export const nextId = (prefix = "id") => `${prefix}-${++uid}`;

export function chip(text, kind = "") {
  return h("span", { class: `chip ${kind ? "chip-" + kind : ""}`.trim() }, text);
}

export function alertBox(kind, title, body) {
  const el = h("div", { class: `alert alert-${kind}` });
  if (title) el.append(h("p", { class: "alert-title" }, title));
  if (Array.isArray(body)) {
    if (body.length) el.append(h("ul", {}, body.map((line) => h("li", {}, line))));
  } else if (body) {
    el.append(h("p", {}, body));
  }
  return el;
}

export function labelled(labelText, control, hint) {
  const id = control.id || (control.id = nextId("f"));
  return h("div", { class: "field" },
    h("label", { for: id }, labelText), control, hint ? h("span", { class: "hint" }, hint) : null);
}
