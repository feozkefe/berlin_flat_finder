const state = {
  districts: [],
  listing_types: ["wg", "apartment", "sublet"],
  sources: ["wg_gesucht", "kleinanzeigen", "immoscout"],
  interval_hours: 12,
};

const $ = (id) => document.getElementById(id);

function toggleIn(list, value) {
  const next = new Set(list);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return [...next];
}

function paintChips(selector, selected, attr) {
  document.querySelectorAll(selector).forEach((btn) => {
    btn.classList.toggle("on", selected.includes(btn.dataset[attr]));
  });
}

function renderDistricts(all) {
  const box = $("districts");
  box.innerHTML = "";
  all.forEach((district) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip district";
    btn.dataset.id = district.id;
    btn.textContent = district.name;
    btn.addEventListener("click", () => {
      state.districts = toggleIn(state.districts, district.id);
      paintChips(".district", state.districts, "id");
    });
    box.appendChild(btn);
  });
}

function fillForm(settings) {
  state.districts = settings.districts || [];
  state.listing_types = settings.listing_types || [];
  state.sources = settings.sources || [];
  state.interval_hours = settings.interval_hours || 12;
  $("max_rent").value = settings.max_rent;
  $("min_rooms").value = settings.min_rooms;
  $("min_sqm").value = settings.min_sqm;
  $("start_from").value = settings.start_from || "";
  $("min_months").value = settings.min_months ?? 1;
  $("max_months").value = settings.max_months ?? 0;
  $("telegram_chat_id").value = settings.telegram_chat_id || "";
  paintChips(".district", state.districts, "id");
  paintChips(".type", state.listing_types, "type");
  paintChips(".source", state.sources, "source");
  document.querySelectorAll(".interval").forEach((btn) => {
    btn.classList.toggle("on", Number(btn.dataset.hours) === state.interval_hours);
  });
}

function collect() {
  return {
    districts: state.districts,
    max_rent: Number($("max_rent").value),
    min_rooms: Number($("min_rooms").value),
    min_sqm: Number($("min_sqm").value),
    start_from: $("start_from").value || "",
    min_months: Number($("min_months").value) || 1,
    max_months: Number($("max_months").value) || 0,
    listing_types: state.listing_types,
    sources: state.sources,
    interval_hours: state.interval_hours,
    telegram_chat_id: $("telegram_chat_id").value.trim(),
    enabled: true,
  };
}

function providerLabel(name) {
  return { wg_gesucht: "WG-Gesucht", kleinanzeigen: "Kleinanzeigen", immoscout: "ImmoScout24" }[name] || name;
}

function writableAlts(item) {
  return (item.alt_urls || []).filter((alt) => alt.provider !== item.provider);
}

function canMessage(item) {
  return item.contactable || writableAlts(item).length > 0;
}

function metaLine(item) {
  const rooms = item.listing_kind === "wg"
    ? (item.flatmates ? `room in ${item.flatmates + 1}-person WG` : "WG room")
    : (item.rooms ? `${item.rooms} Zi` : "");
  const timing = [
    item.available_from ? `from ${item.available_from}` : "",
    item.available_to ? `until ${item.available_to}` : (item.duration_months ? `${item.duration_months} months` : ""),
  ].filter(Boolean).join(" · ");
  return [item.district || "Berlin", rooms, item.size_sqm ? `${item.size_sqm} m²` : "", item.price ? `${item.price} €` : "", timing]
    .filter(Boolean)
    .join(" · ");
}

function renderListings(payload) {
  const scan = payload.scan;
  $("scan-meta").textContent = scan
    ? `Last scan: ${scan.finished_at} · ${scan.new_count} new / ${scan.total_count} matches`
    : "No scan yet.";

  const box = $("listings");
  box.innerHTML = "";
  // Same order as Telegram: ads you can actually write to come first.
  const items = payload.listings || [];
  const ordered = [...items.filter(canMessage), ...items.filter((item) => !canMessage(item))];

  ordered.forEach((item) => {
    const el = document.createElement("article");
    el.className = canMessage(item) ? "listing writable" : "listing";
    const alts = writableAlts(item)
      .map((alt) => `<a href="${alt.url}" target="_blank" rel="noreferrer">${providerLabel(alt.provider)}</a>`)
      .join(" · ");
    let contact;
    if (item.contactable) {
      contact = `<span class="badge ok">✉️ can message</span>`;
    } else if (alts) {
      contact = `<span class="badge ok">✉️ write via ${alts}</span>`;
    } else {
      contact = `<span class="badge warn">👀 view only</span>`;
    }
    el.innerHTML = `
      <h3><a href="${item.url}" target="_blank" rel="noreferrer">${item.title}</a></h3>
      <p>${metaLine(item)}</p>
      <p>${item.address || ""}</p>
      <div class="badges">
        <span class="badge">${providerLabel(item.provider)}</span>
        ${item.listing_kind === "wg" ? '<span class="badge">WG</span>' : ""}
        ${item.is_sublet ? '<span class="badge">sublet</span>' : ""}
        ${item.private_landlord ? '<span class="badge">private</span>' : ""}
        ${contact}
      </div>
    `;
    box.appendChild(el);
  });
}

async function load() {
  const [meta, settings, listings] = await Promise.all([
    fetch("/api/meta").then((r) => r.json()),
    fetch("/api/settings").then((r) => r.json()),
    fetch("/api/listings").then((r) => r.json()),
  ]);
  renderDistricts(meta.districts);
  $("bot-hint").textContent = meta.bot_configured
    ? "Telegram bot is on. Send /start to the bot; chat ID fills in here."
    : "Put TELEGRAM_BOT_TOKEN in .env or only the web UI runs.";
  fillForm(settings);
  renderListings(listings);
}

document.querySelectorAll(".type").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.listing_types = toggleIn(state.listing_types, btn.dataset.type);
    paintChips(".type", state.listing_types, "type");
  });
});

document.querySelectorAll(".source").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.sources = toggleIn(state.sources, btn.dataset.source);
    paintChips(".source", state.sources, "source");
  });
});

document.querySelectorAll(".interval").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.interval_hours = Number(btn.dataset.hours);
    document.querySelectorAll(".interval").forEach((b) => b.classList.toggle("on", b === btn));
  });
});

$("save").addEventListener("click", async () => {
  $("status").textContent = "Saving…";
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collect()),
  });
  fillForm(await res.json());
  $("status").textContent = "Saved. Scan interval updated.";
});

$("scan").addEventListener("click", async () => {
  $("status").textContent = "Scanning, 20-40 seconds…";
  const res = await fetch("/api/scan", { method: "POST" });
  const data = await res.json();
  if (!res.ok) {
    $("status").textContent = data.detail || "Scan failed.";
    return;
  }
  $("status").textContent = data.first_scan
    ? `First scan: ${data.total_found} listings. Links sent to Telegram.`
    : `${data.new_count} new · ${data.total_found} matches.`;
  renderListings(await fetch("/api/listings").then((r) => r.json()));
});

load();
