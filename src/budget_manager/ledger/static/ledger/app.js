// Small progressive enhancements. Every page also works without JavaScript.
(function () {
  "use strict";

  const MINUS = "−";

  // Parse "1.234,56" the same way as the server (see engine/money.py). Returns hundredths.
  function parseAmount(text) {
    let s = (text || "").trim().replace(/[\s ']/g, "").replace(MINUS, "-");
    if (!s) return null;
    let sign = 1;
    if (s[0] === "-" || s[0] === "+") {
      sign = s[0] === "-" ? -1 : 1;
      s = s.slice(1);
    }
    let whole = s, fraction = "";
    if (s.includes(",")) {
      [whole, fraction] = s.split(",", 2);
      whole = whole.replace(/\./g, "");
    } else if (s.includes(".")) {
      const parts = s.split(".");
      if (parts.length === 2 && parts[1].length >= 1 && parts[1].length <= 2) {
        [whole, fraction] = parts;
      } else {
        whole = parts.join("");
      }
    }
    if (!/^\d*$/.test(whole) || !/^\d{0,2}$/.test(fraction)) return NaN;
    return sign * (parseInt(whole || "0", 10) * 100 + parseInt((fraction + "00").slice(0, 2), 10));
  }

  function formatAmount(value) {
    const sign = value < 0 ? MINUS : "";
    const abs = Math.abs(value);
    const units = Math.floor(abs / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return sign + units + "," + String(abs % 100).padStart(2, "0");
  }

  function csrfToken() {
    const field = document.querySelector("input[name=csrfmiddlewaretoken]");
    if (field) return field.value;
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : "";
  }

  function toast(message) {
    let el = document.querySelector(".toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast";
      el.setAttribute("role", "status");
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.hidden = false;
    clearTimeout(el._timer);
    el._timer = setTimeout(() => { el.hidden = true; }, 4500);
  }

  // Live "balance after" while typing actual spending.
  function updateLive(input) {
    const target = document.getElementById(input.dataset.live);
    if (!target) return;
    const base = parseInt(input.dataset.base, 10);
    const spent = parseAmount(input.value);
    if (Number.isNaN(spent)) {
      target.textContent = "Check the amount";
      target.classList.add("neg");
      return;
    }
    const after = base - (spent || 0);
    target.textContent = formatAmount(after);
    target.classList.toggle("neg", after < 0);
  }
  document.querySelectorAll("input[data-live]").forEach((input) => {
    input.addEventListener("input", () => updateLive(input));
  });

  // "Fill expected" buttons fill empty fields in their scope.
  document.querySelectorAll("[data-fill]").forEach((button) => {
    button.hidden = false;
    button.addEventListener("click", () => {
      const scope = button.closest("form") || document;
      let filled = 0;
      scope.querySelectorAll(button.dataset.fill).forEach((input) => {
        if (!input.value.trim() && input.dataset.expected) {
          input.value = input.dataset.expected;
          input.dispatchEvent(new Event("input"));
          filled += 1;
        }
      });
      toast(filled ? `Filled ${filled} field${filled === 1 ? "" : "s"}. Check them before saving.` : "Nothing left to fill.");
    });
  });

  // Copy an amount to the clipboard.
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.hidden = false;
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      try {
        await navigator.clipboard.writeText(button.dataset.copy);
        toast(`Copied ${button.dataset.copy}`);
      } catch (error) {
        toast(button.dataset.copy);
      }
    });
  });

  // Compare typed bank balances with the app.
  document.querySelectorAll("input[data-bank]").forEach((input) => {
    const out = document.getElementById(input.dataset.bank);
    const expected = parseInt(input.dataset.expected, 10);
    const link = document.getElementById(input.dataset.bank + "-fix");
    const update = () => {
      const bank = parseAmount(input.value);
      if (bank === null) {
        out.textContent = "";
        out.className = "muted";
        if (link) link.hidden = true;
        return;
      }
      if (Number.isNaN(bank)) {
        out.textContent = "Check the amount";
        out.className = "neg";
        return;
      }
      const diff = bank - expected;
      out.textContent = diff === 0 ? "Matches" : `Differs by ${diff > 0 ? "+" : ""}${formatAmount(diff)}`;
      out.className = diff === 0 ? "pos" : "neg";
      if (link) {
        link.hidden = diff === 0;
        link.href = link.dataset.base + "&amount=" + encodeURIComponent(formatAmount(diff).replace(MINUS, "-"));
      }
    };
    input.addEventListener("input", update);
  });

  // Running budgets are monthly from the 1st: hide the frequency and due date for them.
  document.querySelectorAll("form").forEach((form) => {
    const choices = form.querySelectorAll("[name=kind]");
    const fields = form.querySelectorAll("[data-hide-when-running]");
    if (!choices.length || !fields.length) return;
    const update = () => {
      const chosen = form.querySelector("select[name=kind], input[name=kind]:checked");
      const running = chosen && chosen.value === "running";
      fields.forEach((field) => { field.hidden = running; });
    };
    choices.forEach((choice) => choice.addEventListener("change", update));
    update();
  });

  // Work out what was spent from the NemKonto from its balance.
  document.querySelectorAll("input[data-spent-from]").forEach((input) => {
    input.closest(".calc").hidden = false;
    const target = document.getElementById(input.dataset.spentTo);
    const start = parseInt(input.dataset.spentFrom, 10);
    input.addEventListener("input", () => {
      const balance = parseAmount(input.value);
      if (balance === null || Number.isNaN(balance)) return;
      target.value = formatAmount(Math.max(0, start - balance)).replace(MINUS, "-");
    });
  });

  // Forms that submit as soon as a control changes.
  document.querySelectorAll("[data-autosubmit]").forEach((control) => {
    control.addEventListener("change", () => control.form.requestSubmit());
  });

  // Month slider on the forecast.
  // Collapsible groups remember whether they were open, per page, in this browser only.
  function remembered(details) {
    return location.pathname + "#" + details.dataset.remember;
  }
  document.querySelectorAll("details[data-remember]").forEach((details) => {
    try {
      const stored = localStorage.getItem(remembered(details));
      if (stored !== null) details.open = stored === "open";
    } catch (error) {
      /* storage unavailable: every group starts open */
    }
    details.addEventListener("toggle", () => {
      try {
        localStorage.setItem(remembered(details), details.open ? "open" : "closed");
      } catch (error) {
        /* not remembered */
      }
      refreshToggles();
    });
  });
  function refreshToggles() {
    document.querySelectorAll("[data-toggle-groups]").forEach((button) => {
      const groups = document.querySelectorAll(button.dataset.toggleGroups + " > details");
      const anyOpen = [...groups].some((details) => details.open);
      button.textContent = anyOpen ? "Collapse all" : "Expand all";
    });
  }
  document.querySelectorAll("[data-toggle-groups]").forEach((button) => {
    button.addEventListener("click", () => {
      const groups = document.querySelectorAll(button.dataset.toggleGroups + " > details");
      const open = ![...groups].some((details) => details.open);
      groups.forEach((details) => (details.open = open));
    });
  });
  refreshToggles();

  const slider = document.querySelector("input[data-months]");
  if (slider) {
    const months = JSON.parse(slider.dataset.months);
    const out = document.getElementById("slider-month");
    slider.addEventListener("input", () => { if (out) out.textContent = months[slider.value][1]; });
    slider.addEventListener("change", () => {
      window.location.search = "?month=" + months[slider.value][0];
    });
  }

  // Drag expenses between categories or accounts.
  const board = document.querySelector("[data-board]");
  if (board) {
    const field = board.dataset.board;
    let dragged = null;
    board.querySelectorAll(".xcard[draggable]").forEach((card) => {
      card.addEventListener("dragstart", (event) => {
        dragged = card;
        card.classList.add("dragging");
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", card.dataset.id);
      });
      card.addEventListener("dragend", () => {
        card.classList.remove("dragging");
        dragged = null;
        board.querySelectorAll(".column.over").forEach((c) => c.classList.remove("over"));
      });
    });
    board.querySelectorAll(".column[data-value]").forEach((column) => {
      column.addEventListener("dragover", (event) => {
        if (!dragged) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        column.classList.add("over");
      });
      column.addEventListener("dragleave", (event) => {
        if (!column.contains(event.relatedTarget)) column.classList.remove("over");
      });
      column.addEventListener("drop", async (event) => {
        event.preventDefault();
        column.classList.remove("over");
        const card = dragged;
        if (!card) return;
        const list = column.querySelector(".cards");
        const origin = card.parentElement;
        const originNext = card.nextElementSibling;
        // Drop above the first card whose middle is below the pointer.
        const after = [...list.querySelectorAll(".xcard")].find((other) => {
          if (other === card) return false;
          const box = other.getBoundingClientRect();
          return event.clientY < box.top + box.height / 2;
        });
        list.insertBefore(card, after || null);
        const order = [...list.querySelectorAll(".xcard")].map((item) => item.dataset.id).join(",");
        const body = new URLSearchParams({ field: field, value: column.dataset.value, order: order });
        try {
          const response = await fetch(card.dataset.move, {
            method: "POST",
            headers: { "X-CSRFToken": csrfToken(), Accept: "application/json" },
            body: body,
          });
          const data = await response.json();
          if (!response.ok || !data.ok) throw new Error(data.error || "Could not move the expense.");
          toast(data.message);
          board.querySelectorAll(".column").forEach(refreshCount);
        } catch (error) {
          origin.insertBefore(card, originNext);
          toast(error.message);
        }
      });
    });
    function refreshCount(column) {
      const count = column.querySelectorAll(".xcard").length;
      const el = column.querySelector("[data-count]");
      if (el) el.textContent = count;
      const hint = column.querySelector(".hint");
      if (hint) hint.hidden = count > 0;
    }
  }
})();
