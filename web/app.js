/**
 * Configure API base (same host/port if using a reverse proxy).
 * Default assumes uvicorn on localhost:8000.
 */
const API_BASE = window.API_BASE || "http://127.0.0.1:8000";

const logEl = document.getElementById("log");
const cardsEl = document.getElementById("cards");
const btn = document.getElementById("go");
const input = document.getElementById("q");

function log(line) {
  logEl.textContent += line + "\n";
}

function clearUi() {
  logEl.textContent = "";
  cardsEl.innerHTML = "";
}

async function streamSearch(message) {
  clearUi();
  btn.disabled = true;
  const res = await fetch(`${API_BASE}/v1/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok || !res.body) {
    log(`Request failed: ${res.status}`);
    btn.disabled = false;
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 2);
      if (!chunk.startsWith("data:")) continue;
      const payload = JSON.parse(chunk.replace(/^data:\s*/, ""));
      if (payload.type === "plan") {
        log(`Plan: ${JSON.stringify(payload.car_query, null, 2)}`);
        log(`Rationale: ${payload.rationale}`);
      } else if (payload.type === "result_count") {
        log(`Results: ${payload.count}`);
      } else if (payload.type === "listing") {
        const li = payload.listing;
        const div = document.createElement("div");
        div.className = "card";
        div.innerHTML = `
          <div><strong>${li.title}</strong></div>
          <div>${li.year || "?"} · ${li.make || ""} ${li.model || ""}</div>
          <div>Price: ${li.price_amount ?? "?"} ${li.currency || ""}</div>
          <div>Mileage: ${li.mileage ?? "?"}</div>
          <div><a href="${li.listing_url}" target="_blank" rel="noreferrer">Listing</a> · id ${li.id}</div>
        `;
        cardsEl.appendChild(div);
      } else if (payload.type === "done") {
        log("Done.");
      }
    }
  }
  btn.disabled = false;
}

btn.addEventListener("click", () => {
  const message = input.value.trim();
  if (!message) return;
  streamSearch(message).catch((err) => {
    log(`Error: ${err}`);
    btn.disabled = false;
  });
});
