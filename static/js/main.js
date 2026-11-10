/* GeoSage · BHOOMI VISION - shared front-end helpers */
"use strict";

const GeoSage = {
  csrfToken: () => document.querySelector('meta[name="csrf-token"]')?.content || "",

  /** fetch() wrapper that sends the CSRF token and parses JSON replies. */
  async api(url, options = {}) {
    const opts = Object.assign({ headers: {} }, options);
    opts.headers["X-CSRFToken"] = GeoSage.csrfToken();
    if (opts.json !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.json);
      delete opts.json;
    }
    const response = await fetch(url, opts);
    let data = null;
    try { data = await response.json(); } catch (e) { /* non-JSON reply */ }
    if (!response.ok) {
      const message = (data && (data.error || data.message)) || `Request failed (${response.status})`;
      GeoSage.toast(message, "danger");
      throw new Error(message);
    }
    return data;
  },

  toast(message, kind = "info", timeout = 5000) {
    let stack = document.querySelector(".toast-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "toast-stack";
      document.body.appendChild(stack);
    }
    const el = document.createElement("div");
    el.className = `toast-gs ${kind}`;
    el.textContent = message;
    stack.appendChild(el);
    setTimeout(() => el.remove(), timeout);
  },
};

document.addEventListener("DOMContentLoaded", () => {
  // Mobile sidebar toggle
  const toggle = document.querySelector(".sidebar-toggle");
  if (toggle) {
    toggle.addEventListener("click", () =>
      document.querySelector(".sidebar").classList.toggle("show"));
  }

  // Server flash messages -> toasts, then remove placeholders
  document.querySelectorAll(".flash-data").forEach((el) => {
    GeoSage.toast(el.dataset.message, el.dataset.category || "info");
    el.remove();
  });

  // Confirmation dialogs on destructive forms
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
});
