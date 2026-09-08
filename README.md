# Berlin Flat Finder

Personal Berlin rental / WG / sublet radar.  
Kişisel Berlin ev / WG / sublet radarı.

It searches **WG-Gesucht**, **Kleinanzeigen**, and **ImmoScout24**, keeps listings that match your filters, and scans again on an interval **you choose** (12 or 24 hours). New matches go to Telegram.

Üç siteden ilan çeker, filtrene uyanları tutar, **senin seçtiğin** aralıkta (12 veya 24 saat) tekrar tarar. Yeni ilan Telegram’a düşer.

ImmoScout landlords cannot be contacted in-app. If the same ad also exists on WG-Gesucht or Kleinanzeigen, that writable link is highlighted.

ImmoScout’tan ev sahibine yazılamaz. Aynı ilan diğer iki sitede de varsa o yazılabilir link öne çıkar.

---

## English

### 12 hours or 24 hours?

You choose. It is not hardcoded.

- Telegram: `/setup` → last step, tap **12 hours** or **24 hours**
- Web UI: “Scan interval” chips → **Save**

| Choice | Meaning |
|---|---|
| 12 hours | Two scans per day. New ads show up sooner. |
| 24 hours | One scan per day. Quieter. |

The first scan is a silent baseline (no spam of whatever is already online). After that, only **new listing IDs** are sent.

Do not want to wait? `/scan` or **Scan now** on the web.

The process must stay running (`python -m app` on your PC, or Railway) or nothing is scanned.

### How to set filters

Both paths write the same settings.

**Telegram**

```
/start
/setup
```

1. Districts (multi-select) → Continue
2. Max warm rent, e.g. `1100`
3. Min rooms, e.g. `2`
4. Type: WG room / apartment / sublet → Continue
5. **12 hours** or **24 hours**

Commands: `/status` `/scan` `/latest` `/pause` `/resume` `/cancel`

**Web:** open the app, pick chips, type numbers, **Save**.

**Example:** Neukölln + Britz + Kreuzberg + Tempelhof + Treptow, 2+ rooms, max €1100, apartment + sublet, 12 hours.

### Sources

| Site | Note |
|---|---|
| WG-Gesucht | WG and sublets, contactable |
| Kleinanzeigen | Flats / WG / sublets, contactable |
| ImmoScout24 | Often early; not contactable; we look for a copy elsewhere |

No Immowelt (JS-heavy page).

### Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

```
TELEGRAM_BOT_TOKEN=BotFather_token
HOST=127.0.0.1
PORT=8080
```

```powershell
python -m app
```

Web: http://127.0.0.1:8080 — then `/start` the bot. Never commit `.env` or `data/`.

### Railway (always on)

1. Repo: [github.com/feozkefe/berlin_flat_finder](https://github.com/feozkefe/berlin_flat_finder)
2. [railway.app](https://railway.app) → New Project → this GitHub repo
3. Variables:

```
TELEGRAM_BOT_TOKEN=BotFather_token
DATA_DIR=/data
SCAN_ON_START=false
```

`/data` is not a placeholder. Leave it exactly like that. It is a folder **on the Railway server**. In Railway: Volume → mount path `/data`. The app then writes `finder.db` there so seen ads survive restarts. Do not put your Windows path here.

4. Add a volume, mount path `/data` (otherwise seen-ads reset on every deploy)
5. Start command: `python -m app`

After deploy, `/start` + `/setup` again so the chat ID is stored on that server.

### WhatsApp?

Possible, but **more hassle than it is worth** for this bot. Telegram is built for bots (BotFather, buttons, free push). WhatsApp is not.

Official path (WhatsApp Cloud API / Twilio):

- Meta Business account + a dedicated phone number
- Webhook instead of simple polling
- **Template messages** must be approved before you can push “new listing” alerts. Without a template you only have a 24-hour window after the user writes you — a 12/24h scanner often misses that window
- Per-conversation pricing
- Filter setup is worse (no Telegram-style inline keyboards)

Unofficial WhatsApp-Web scrapers break ToS and get numbers banned. Not for Railway.

**Practical setup:** keep Telegram for alerts. Use the web UI on your phone if you want. Adding WhatsApp later is a separate Meta/Twilio project, not a small toggle.

---

## Türkçe

### 12 saat mi 24 saat mi?

Sen seçiyorsun. Kodda sabit değil.

- Telegram: `/setup` → en sonda **12 saat** veya **24 saat**
- Web: “Tarama aralığı” → **Kaydet**

| Seçim | Anlamı |
|---|---|
| 12 saat | Günde iki tarama. Yeni ilan daha çabuk gelir. |
| 24 saat | Günde bir tarama. Daha sakin. |

İlk tarama sessiz baseline: o anda duran ilanlar spam olmaz. Sonra sadece **yeni ID** mesaj olur.

Beklemek istemezsen `/scan` veya sitede **Şimdi tara**.

Süreç açık kalmalı (evde `python -m app` veya Railway), yoksa tarama olmaz.

### Filtre nasıl kurulur?

İki yol aynı ayarı yazar.

**Telegram**

```
/start
/setup
```

1. Mahalle (birden fazla) → Devam
2. Max warm kira, örn. `1100`
3. Min oda, örn. `2`
4. Tip: WG odası / daire / Zwischenmiete → Devam
5. **12 saat** veya **24 saat**

Komutlar: `/status` `/scan` `/latest` `/pause` `/resume` `/cancel`

**Web:** chip + sayı, **Kaydet**.

**Örnek:** Neukölln, Britz, Kreuzberg, Tempelhof, Treptow · 2+ oda · 1100 € · daire + Zwischenmiete · 12 saat.

### Kaynaklar

| Site | Not |
|---|---|
| WG-Gesucht | WG ve Zwischenmiete, yazılabilir |
| Kleinanzeigen | Daire / WG / sublet, yazılabilir |
| ImmoScout24 | Erken düşer, yazılamaz; kopyası aranır |

Immowelt yok.

### Yerelde

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

```
TELEGRAM_BOT_TOKEN=BotFather_token
HOST=127.0.0.1
PORT=8080
```

```powershell
python -m app
```

Web: http://127.0.0.1:8080 — bota `/start`. `.env` ve `data/` commit etme.

### Railway (hep açık)

1. Repo: [github.com/feozkefe/berlin_flat_finder](https://github.com/feozkefe/berlin_flat_finder)
2. [railway.app](https://railway.app) → New Project → bu GitHub repo
3. Variables:

```
TELEGRAM_BOT_TOKEN=BotFather_token
DATA_DIR=/data
SCAN_ON_START=false
```

`/data` yerine ev yolu yazma, olduğu gibi bırak. Railway sunucusundaki klasör adı. Railway’de Volume ekle, mount path: `/data`. Uygulama `finder.db`’yi oraya yazar, restart’ta silinmez.

4. Volume ekle, mount path `/data` (yoksa her deploy’da ilan hafızası silinir)
5. Start: `python -m app`

Deploy’dan sonra yine `/start` + `/setup` — chat ID o sunucuya yazılır.

### WhatsApp’a taşır mıyız? Uğraştırır mı?

**Evet, uğraştırır.** Bu iş için Telegram doğru kanal. WhatsApp bot için tasarlanmamış.

Resmi yol (WhatsApp Cloud API / Twilio):

- Meta Business hesap + ayrı bir telefon numarası
- Basit polling yok, webhook şart
- “Yeni ilan” için **şablon mesaj** onayı gerekir. Onaysız sadece kullanıcı yazdıktan sonraki 24 saat konuşabilirsin — 12/24 saatlik tarama bu pencereyi kaçırır
- Konuşma başına ücret
- Filtre kurmak Telegram’daki butonlar kadar rahat değil

WhatsApp Web’i taklit eden gayriresmi kütüphaneler ToS’a aykırı, numara ban yiyebilir. Railway’de kullanma.

**Pratik:** bildirimi Telegram’da bırak. Telefondan web arayüzünü de kullanırsın. WhatsApp ayrı bir Meta/Twilio işi, bir ayar kutusu değil.

---

## Architecture / Mimari

One Python process: FastAPI + Telegram + APScheduler + SQLite.

```
web / telegram  →  filters (12h or 24h, your choice)
        ↓
     scheduler
        ↓
 WG + Kleinanzeigen + ImmoScout
        ↓
 district / rent / rooms / type
        ↓
 street + price + m² duplicate match
        ↓
 new id → Telegram
```

Site HTML/API changes can break parsers. Home IP or Railway is usually enough; a VPN sometimes returns 403.
