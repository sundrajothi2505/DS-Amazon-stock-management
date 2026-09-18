// Confirm dialogs on forms marked with data-confirm
document.addEventListener("submit", function (e) {
  const form = e.target.closest("[data-confirm]");
  if (form && !window.confirm(form.getAttribute("data-confirm"))) {
    e.preventDefault();
  }
});

// Toggle reveal rows (e.g. "Reset password" inline form on the Employees page)
document.addEventListener("click", function (e) {
  const trigger = e.target.closest("[data-reveal]");
  if (!trigger) return;
  const target = document.getElementById(trigger.getAttribute("data-reveal"));
  if (target) {
    target.hidden = !target.hidden;
    if (!target.hidden) {
      const input = target.querySelector("input");
      if (input) input.focus();
    }
  }
});

// Auto-dismiss flash messages after a few seconds
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-autohide]").forEach(function (el) {
    setTimeout(function () {
      el.style.transition = "opacity 0.4s ease";
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 400);
    }, 4000);
  });
});

// Searchable product picker: turns a text input + hidden input into a
// lightweight autocomplete backed by a JSON list of {id, sku, name, stock}.
// Used anywhere a form needs to pick one product from a long catalog.
function initSearchableSelects() {
  document.querySelectorAll(".searchable-select").forEach(function (wrap) {
    if (wrap.dataset.ssInit) return;
    wrap.dataset.ssInit = "1";

    var dataScript = document.getElementById(wrap.dataset.optionsId);
    var options = [];
    try { options = dataScript ? JSON.parse(dataScript.textContent) : []; } catch (e) { options = []; }

    var input = wrap.querySelector(".ss-input");
    var hidden = wrap.querySelector(".ss-hidden-value");
    var dropdown = wrap.querySelector(".ss-dropdown");
    var MAX_RESULTS = 60;

    function labelFor(opt) {
      var label = opt.sku + " — " + opt.name;
      if (opt.stock !== undefined && opt.stock !== null) label += " (" + opt.stock + " on hand)";
      return label;
    }

    function findById(id) {
      return options.find(function (o) { return String(o.id) === String(id); });
    }

    // Pre-fill the visible text if a product is already selected (edit mode).
    if (hidden.value) {
      var match = findById(hidden.value);
      if (match) input.value = labelFor(match);
    }

    function render(filterText) {
      var q = (filterText || "").trim().toLowerCase();
      var matches = options.filter(function (o) {
        return !q || o.sku.toLowerCase().indexOf(q) !== -1 || o.name.toLowerCase().indexOf(q) !== -1;
      }).slice(0, MAX_RESULTS);

      dropdown.innerHTML = "";
      if (matches.length === 0) {
        var empty = document.createElement("div");
        empty.className = "ss-empty";
        empty.textContent = "No matching products";
        dropdown.appendChild(empty);
      } else {
        matches.forEach(function (o) {
          var item = document.createElement("div");
          item.className = "ss-option";
          item.textContent = labelFor(o);
          item.addEventListener("mousedown", function (e) {
            e.preventDefault();
            hidden.value = o.id;
            input.value = labelFor(o);
            dropdown.hidden = true;
          });
          dropdown.appendChild(item);
        });
        if (options.length > MAX_RESULTS && !q) {
          var hint = document.createElement("div");
          hint.className = "ss-empty";
          hint.textContent = "Keep typing to narrow down " + options.length + " products…";
          dropdown.appendChild(hint);
        }
      }
      dropdown.hidden = false;
    }

    input.addEventListener("focus", function () { render(""); });
    input.addEventListener("input", function () {
      hidden.value = "";
      render(input.value);
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { dropdown.hidden = true; input.blur(); }
      if (e.key === "Enter") {
        e.preventDefault();
        var first = dropdown.querySelector(".ss-option");
        if (first) first.dispatchEvent(new MouseEvent("mousedown"));
      }
    });
    document.addEventListener("click", function (e) {
      if (!wrap.contains(e.target)) dropdown.hidden = true;
    });
  });
}
document.addEventListener("DOMContentLoaded", initSearchableSelects);
