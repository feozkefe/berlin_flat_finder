# Berlin Flat Finder

Kişisel Berlin ev / WG / sublet radarı.

Üç siteden ilan çeker, senin filtrene uyanları tutar, **senin seçtiğin aralıkta** (12 veya 24 saat) tekrar tarar. Yeni ilan gelince Telegram’a mesaj atar.

ImmoScout’tan ev sahibine yazılamaz. Aynı ilan WG-Gesucht veya Kleinanzeigen’de de varsa o yazılabilir link mesajda öne çıkar.

## 12 saat mi 24 saat mi?

Bunu sen seçiyorsun. Kod sabit değil.

- Telegram: `/setup` → en sonda **12 saat** veya **24 saat** butonu
- Web: “Tarama aralığı” chip’leri → **Kaydet**

Ne anlama geliyor:

| Seçim | Davranış |
|---|---|
| 12 saat | Günde iki tarama. Yeni ilan daha çabuk düşer. |
| 24 saat | Günde bir tarama. Daha sakin. |

İlk tarama sessiz baseline’dır: o anda duran ilanlar spam olarak gelmez. Sonrakilerde sadece **yeni ID** mesaj olur.

İstersen beklemeden `/scan` veya web’de **Şimdi tara**.

Botun sürekli taraması için süreç açık kalmalı (bilgisayarda `python -m app` veya Railway).

## Filtre nasıl kurulur?

İki yol aynı ayarı yazar.

### Telegram

Bota yaz:

```
/start
/setup
```

Sırayla:

1. Mahalle butonları (birden fazla) → **Devam**
2. Max warm kira, örn. `1100`
3. Min oda, örn. `2`
4. Tip: WG odası / Daire / Zwischenmiete → **Devam**
5. **12 saat** veya **24 saat**

Komutlar: `/status` `/scan` `/latest` `/pause` `/resume` `/cancel`

### Web

Tarayıcıda uygulamayı aç, chip + sayıları doldur, **Kaydet**.

### Örnek: Neukölln çevre, 2+ oda, 1100 €

`/setup` içinde:

- Mahalle: Neukölln, Britz, Kreuzberg, Tempelhof, Treptow
- Max kira: `1100`
- Min oda: `2`
- Tip: Daire + Zwischenmiete (WG kapalı)
- Aralık: 12 saat

## Kaynaklar

| Site | Not |
|---|---|
| WG-Gesucht | WG ve Zwischenmiete, yazılabilir |
| Kleinanzeigen | Daire / WG / sublet, yazılabilir |
| ImmoScout24 | Erken düşer, yazılamaz; kopyası başka sitede aranır |

Immowelt yok (JS sayfa, tarayıcı ister).

## Yerelde çalıştır

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

`.env`:

```
TELEGRAM_BOT_TOKEN=BotFather_token
HOST=127.0.0.1
PORT=8080
```

```powershell
python -m app
```

- Web: http://127.0.0.1:8080
- Telegram’da bota `/start`

Token yoksa sadece web açılır.

`.env` ve `data/` git’e girmez. Token’ı asla commit etme.

## Railway’de hep açık

1. Bu repo GitHub’da olsun (`feozkefede/berlin_flat_finder`)
2. [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
3. Variables:

```
TELEGRAM_BOT_TOKEN=BotFather_token
DATA_DIR=/data
SCAN_ON_START=false
```

4. Volume ekle, mount path: `/data`  
   Yoksa her deploy’da görülen ilan hafızası silinir.
5. Start command: `python -m app` (Procfile var)

Railway `PORT` verir, uygulama `0.0.0.0` dinler.

Deploy’dan sonra Telegram’da **yine** `/start` ve `/setup` yaz. Chat ID o sunucunun veritabanına kaydolur. Filtre (mahalle, kira, 12/24 saat) orada tutulur.

Küçük Hobby plan yeter. Ücretsiz kredi bitince süreç durur.

## Mimari

Tek Python süreci: FastAPI + Telegram bot + APScheduler + SQLite.

```
web / telegram  →  filtre (12h veya 24h sen seçersin)
        ↓
     scheduler
        ↓
 WG + Kleinanzeigen + ImmoScout
        ↓
 mahalle / kira / oda / tip
        ↓
 sokak + fiyat + m² ile kopya eşle
        ↓
 yeni id → Telegram
```

Siteler HTML/API değiştirirse parser kırılabilir. Ev IP’si veya Railway genelde yeter; VPN bazen 403 getirir.
