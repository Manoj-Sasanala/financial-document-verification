/* UI-01: same-origin upload wiring for POST /api/v1/cases (multipart). */

(function () {
  "use strict";

  function showError(message) {
    var box = document.getElementById("error");
    box.textContent = message;
    box.hidden = false;
    document.getElementById("result").hidden = true;
  }

  var FIELD_ORDER = [
    "customer_name",
    "address",
    "document_type",
    "document_date",
    "issuer_name",
    "document_number",
    "postal_code"
  ];

  function displayValue(value) {
    if (value === null || value === undefined || value === "") {
      return "—";
    }
    return String(value);
  }

  function renderFields(payload) {
    var body = document.getElementById("fields-body");
    var fields = payload.fields || {};
    var normalized = payload.normalized_fields || {};
    body.innerHTML = "";
    FIELD_ORDER.forEach(function (name) {
      var raw = fields[name] || {};
      var norm = normalized[name] || {};
      var status = raw.status || "missing";
      var row = document.createElement("tr");
      row.setAttribute("data-field", name);
      row.setAttribute("data-status", status);
      [
        name,
        displayValue(raw.raw_value),
        displayValue(norm.normalized_value),
        status
      ].forEach(function (text) {
        var cell = document.createElement("td");
        cell.textContent = text;
        row.appendChild(cell);
      });
      body.appendChild(row);
    });
  }

  function renderComparisons(payload) {
    var body = document.getElementById("comparisons-body");
    body.innerHTML = "";
    (payload.comparisons || []).forEach(function (item) {
      var row = document.createElement("tr");
      row.setAttribute("data-field", item.field_name);
      row.setAttribute("data-status", item.status);
      [
        item.field_name,
        item.status,
        displayValue(item.observed_value),
        displayValue(item.reference_value)
      ].forEach(function (text) {
        var cell = document.createElement("td");
        cell.textContent = text;
        row.appendChild(cell);
      });
      body.appendChild(row);
    });
  }

  function renderIndicators(payload) {
    var list = document.getElementById("indicators-list");
    list.innerHTML = "";
    (payload.risk_indicators || []).forEach(function (item) {
      var entry = document.createElement("li");
      entry.setAttribute("data-indicator", item.indicator_code);
      entry.setAttribute("data-severity", item.severity);
      var title = document.createElement("strong");
      title.textContent = item.indicator_code + " (" + item.severity + ") ";
      var reason = document.createElement("span");
      reason.textContent = item.reason || "";
      var rule = document.createElement("small");
      rule.textContent = " rule " + (item.rule_id || "?") + " v" + (item.rule_version || "?");
      entry.appendChild(title);
      entry.appendChild(reason);
      entry.appendChild(rule);
      list.appendChild(entry);
    });
    if (!list.children.length) {
      var none = document.createElement("li");
      none.textContent = "No attention signals.";
      list.appendChild(none);
    }
  }

  function showResult(payload) {
    document.getElementById("error").hidden = true;
    document.getElementById("result-status").textContent = payload.status || "unknown";
    renderFields(payload);
    renderComparisons(payload);
    renderIndicators(payload);
    document.getElementById("result-body").textContent = JSON.stringify(payload, null, 2);
    document.getElementById("result").hidden = false;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("upload-form");
    if (!form) {
      return;
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var data = new FormData(form);

      fetch(form.action, { method: "POST", body: data })
        .then(function (response) {
          if (!response.ok) {
            return response.json().then(function (body) {
              throw new Error(body.detail || ("Upload failed: " + response.status));
            }).catch(function (err) {
              if (err instanceof Error) {
                throw err;
              }
              throw new Error("Upload failed: " + response.status);
            });
          }
          return response.json();
        })
        .then(showResult)
        .catch(function (err) {
          showError(err && err.message ? err.message : "Upload failed.");
        });
    });
  });
})();
