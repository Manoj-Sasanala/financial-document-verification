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

  function showResult(payload) {
    document.getElementById("error").hidden = true;
    document.getElementById("result-status").textContent = payload.status || "unknown";
    renderFields(payload);
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
