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
  $("min_months").value = settings.min_months ?? 0;
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
    min_months: Number($("min_months").value) || 0,
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

function renderListings(payload) {
  const scan = payload.scan;
  $("scan-meta").textContent = scan
    ? `Son tarama: ${scan.finished_at} · ${scan.new_count} yeni / ${scan.total_count} eşleşen`
    : "Henüz tarama yok.";

  const box = $("listings");
  box.innerHTML = "";
  (payload.listings || []).forEach((item) => {
    const el = document.createElement("article");
    el.className = "listing";
    const alts = (item.alt_urls || [])
      .filter((alt) => alt.provider !== item.provider)
      .map((alt) => `<a href="${alt.url}" target="_blank" rel="noreferrer">${providerLabel(alt.provider)}</a>`)
      .join(" · ");
    const contact = item.provider === "immoscout"
      ? (alts
        ? `<span class="badge ok">ImmoScout yazılamaz · kopya: ${alts}</span>`
        : `<span class="badge warn">ImmoScout · başka sitede kopya yok</span>`)
      : `<span class="badge ok">yazılabilir</span>`;
    el.innerHTML = `
      <h3><a href="${item.url}" target="_blank" rel="noreferrer">${item.title}</a></h3>
      <p>${[item.district || "Berlin", item.rooms ? item.rooms + " Zi" : "", item.size_sqm ? item.size_sqm + " m²" : "", item.price ? item.price + " €" : "", item.available_from ? "ab " + item.available_from : "", item.duration_months ? item.duration_months + " ay" : ""].filter(Boolean).join(" · ")}</p>
      <p>${item.address || ""}</p>
      <div class="badges">
        <span class="badge">${providerLabel(item.provider)}</span>
        ${item.is_sublet ? '<span class="badge">sublet</span>' : ""}
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
    ? "Telegram bot açık. Telefonda bota /start yaz, chat ID buraya düşer."
    : ".env içine TELEGRAM_BOT_TOKEN koy, yoksa sadece web çalışır.";
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
  $("status").textContent = "Kaydediliyor…";
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collect()),
  });
  fillForm(await res.json());
  $("status").textContent = "Kaydedildi. Tarama aralığı güncellendi.";
});

$("scan").addEventListener("click", async () => {
  $("status").textContent = "Taranıyor, 20-40 sn sürebilir…";
  const res = await fetch("/api/scan", { method: "POST" });
  const data = await res.json();
  if (!res.ok) {
    $("status").textContent = data.detail || "Tarama olmadı.";
    return;
  }
  $("status").textContent = data.first_scan
    ? `İlk tarama: ${data.total_found} ilan. Linkler Telegram'a gitti.`
    : `${data.new_count} yeni ilan · ${data.total_found} eşleşen.`;
  renderListings(await fetch("/api/listings").then((r) => r.json()));
});

load();
