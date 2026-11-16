// CleanSheet workspace controller: navigation between the three steps, messages, downloads, and restoring
// the page after a reload (the datasets live on the server, so going back never loses or repeats work).
import { api, ApiError } from "./api.js";
import { $, $$, alertBox, clear, h } from "./dom.js";
import { dict, emptyPlan, resetAll, state } from "./state.js";
import * as step1 from "./step1.js";
import * as step2 from "./step2.js";
import * as step3 from "./step3.js";

const messages = document.getElementById("messages");
const statusRegion = document.getElementById("status");

const PAGE_ERROR = "Something went wrong in the page. Reload it and try again; a file you loaded is kept.";

const canGo = (n) => n === 1 || (n === 2 && !!state.basic) || (n === 3 && !!state.final);

const ctx = {
  go(n) {
    if (!canGo(n)) return;
    state.step = n;
    for (const panel of $$(".panel")) panel.hidden = Number(panel.dataset.step) !== n;
    ctx.refresh();
    if (n === 2) step2.enter();
    if (n === 3) step3.render();
    const heading = document.getElementById(`h-${n}`);
    window.scrollTo({ top: 0 });
    if (heading) heading.focus({ preventScroll: true });
  },

  refresh() {
    for (const tab of $$(".step-tab")) {
      const n = Number(tab.dataset.step);
      tab.disabled = !canGo(n);
      if (state.step === n) tab.setAttribute("aria-current", "step"); else tab.removeAttribute("aria-current");
      tab.classList.toggle("is-done", n === 1 ? !!state.basic : n === 2 ? !!state.final : false);
    }
    const label = (n, text) => { document.querySelector(`[data-state-for="${n}"]`).textContent = text; };
    label(1, state.basic ? (state.step1Dirty ? "options changed" : "done") : state.data ? "in progress" : "");
    label(2, state.final ? (state.step2Dirty ? "choices changed" : "done") : state.basic ? "optional" : "locked");
    label(3, state.final ? (state.step2Dirty ? "out of date" : "ready") : "locked");
  },

  status(text) { statusRegion.textContent = text; },

  // Server messages (ApiError) are written for people and shown as they are. Anything else is a fault in the page
  // itself: its technical detail goes to this browser's console only, and the person sees a plain sentence.
  showError(error) {
    let text = error;
    if (typeof error !== "string") {
      text = error instanceof ApiError ? error.message : PAGE_ERROR;
      if (!(error instanceof ApiError)) console.error(error);
    }
    clear(messages).append(h("div", { class: "alert alert-error message" },
      h("p", {}, text),
      h("button", { type: "button", class: "btn btn-quiet", onclick: () => clear(messages) }, "Dismiss")));
    messages.scrollIntoView({ block: "nearest" });
  },

  clearMessages() { clear(messages); },

  resetPlan() { state.plan = emptyPlan(); },

  reset(confirmFirst = false) {
    if (confirmFirst && !window.confirm("Start over with a new file? The file loaded now will be forgotten.")) return;
    if (confirmFirst) api.post("/api/reset").catch(() => {});
    resetAll();
    step1.showUploader();
    ctx.clearMessages();
    ctx.go(1);
    ctx.refresh();
  },

  async download(url, button) {
    ctx.clearMessages();
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Preparing…";
    try {
      const name = await api.download(url);
      ctx.status(`Downloaded ${name}.`);
    } catch (err) {
      ctx.showError(err);
    } finally {
      button.textContent = original;
      button.disabled = (url.includes("/final/") && state.step2Dirty) || (url.includes("/basic/") && state.step1Dirty);
    }
  },
};

async function boot() {
  step1.init(ctx);
  step2.init(ctx);
  step3.init(ctx);
  for (const tab of $$(".step-tab")) tab.addEventListener("click", () => ctx.go(Number(tab.dataset.step)));

  try {
    const saved = await api.get("/api/state");
    if (saved.has_data) {
      state.data = saved;
      state.basic = saved.basic;
      state.final = saved.final;
      if (saved.final && saved.final.plan) {
        const plan = emptyPlan();
        for (const key of Object.keys(plan)) {
          const part = saved.final.plan[key];
          if (part && typeof part === "object") plan[key] = dict(part);
        }
        state.plan = plan;
      }
      step1.show(saved);
      ctx.go(saved.final ? 3 : saved.basic ? 2 : 1);
      return;
    }
  } catch (err) {
    ctx.showError(err);
  }
  ctx.go(1);
}

boot();
