/* UI-01: same-origin upload wiring for POST /api/v1/cases (multipart). */

(function () {
  "use strict";

  function showError(message) {
    var box = document.getElementById("error");
    box.textContent = message;
    box.hidden = false;
    document.getElementById("result").hidden = true;
  }

  function showResult(payload) {
    document.getElementById("error").hidden = true;
    document.getElementById("result-status").textContent = payload.status || "unknown";
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
