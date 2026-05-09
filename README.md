# icelandfact.alit.is – Í dag í sögunni

A QR-code-friendly webpage that shows an AI-generated Icelandic historical fact for today's date. Powered by Google Gemini (free tier). Hosted on GitHub Pages with the custom domain `icelandfact.alit.is`.

---

## Setup guide

### 1. Get a free Gemini API key (5 minutes)

1. Go to **https://aistudio.google.com**
2. Sign in with your Google account
3. Click **"Get API key"** → **"Create API key"**
4. Copy the key (it starts with `AIza…`)

### 2. Put your key in index.html

Open `index.html` and find this line near the bottom:

```js
const GEMINI_API_KEY = "";
```

Replace `` with your actual key.

> ⚠️ The key is visible in the page source. This is fine for a personal/low-traffic
> project. If you want to hide it, see the "Securing the key" section below.

### 3. Create the GitHub repository

1. Go to **github.com** → **New repository**
2. Name it exactly: `icelandfact` (or any name you like)
3. Make it **Public**
4. Do NOT add README or .gitignore (you already have files)
5. Click **Create repository**

### 4. Push the files

```bash
cd alit-history
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/Lubenz007/icelandfact.git
git push -u origin main
```

### 5. Enable GitHub Pages

1. Go to your repo → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` / `/ (root)`
4. Click **Save**
5. GitHub will show you a URL like `https://Lubenz007.github.io/icelandfact/`

### 6. Set up the custom domain on GitHub

1. Still in **Settings → Pages**
2. Under **Custom domain**, type `icelandfact.alit.is`
3. Click **Save**
4. Check **"Enforce HTTPS"** (appears after DNS is configured)

### 7. Configure DNS in Azure

In your Azure DNS zone for `alit.is`, add this record:

| Type  | Name          | Value                   | TTL  |
|-------|---------------|-------------------------|------|
| CNAME | icelandfact   | Lubenz007.github.io     | 3600 |

> This points the subdomain `icelandfact.alit.is` to your GitHub Pages site.
> A records (185.199.x.x) are only needed for apex domains (e.g. `alit.is` directly) — not for subdomains.
> Replace `Lubenz007` with your actual GitHub username if different.

DNS changes take 5–60 minutes to propagate.

### 8. Generate the QR code

Once your site is live at `https://icelandfact.alit.is`:

1. Go to **https://qr.io** or **https://qrcode.com**
2. Enter `https://icelandfact.alit.is`
3. Set **error correction to H** (30%) — important for 3D prints
4. Download as SVG or PNG

---

## 3D printing the QR code

**Recommended workflow:**
1. Go to **Makerworld.com** → search "QR Code Generator" (by Bambu Lab) — it takes a URL and exports STL directly
2. OR import the SVG into **Fusion 360** / **FreeCAD** and extrude 2mm
3. Print at minimum **5×5 cm** for reliable scanning
4. Use **two-colour printing**: white base plate, black QR layer (pause and swap filament)
5. Use **0.2mm layer height** or finer

---

## Securing the API key (optional)

Exposing the key in HTML is fine for personal use. To hide it:

- Use a **Cloudflare Worker** as a tiny proxy (free tier: 100k requests/day)
- The worker holds the key server-side and forwards requests to Gemini
- Your HTML calls your worker URL instead of Gemini directly

Ask for help setting this up if needed.

---

## Free tier limits

| Provider | Model              | Free limit          |
|----------|--------------------|---------------------|
| Google   | Gemini 2.5 Flash-Lite | 15 RPM, 1000 req/day |

For a QR-code page with occasional visitors this is more than enough.
