# TrucksDeal – Buy & Sell Trucks & Buses

Flask + MySQL website for commercial vehicles. Designed to run on **Vercel** with a free **PlanetScale** or **Aiven** MySQL database.

---

## 🗄️ Step 1 — Get a FREE MySQL Database

### Option A: PlanetScale (Recommended — Easiest)
1. Go to https://planetscale.com → Sign up free
2. Click **Create database** → name it `trucksdeal` → Region: closest to you
3. Click **Connect** → choose **Connect with: PyMySQL**
4. Copy the connection string — it looks like:
   ```
   mysql://username:password@host/trucksdeal?ssl-mode=REQUIRED
   ```
5. Save this — you'll need it in Step 3

### Option B: Aiven (Also free)
1. Go to https://aiven.io → Sign up free
2. Create a **MySQL** service (free tier)
3. Go to **Connection Information** → copy the **Service URI**
4. It looks like: `mysql://user:password@host:port/defaultdb?ssl-mode=REQUIRED`

---

## 🚀 Step 2 — Deploy to Vercel

### 2a. Push code to GitHub
```bash
# In your trucks-deal folder:
git add .
git commit -m "Switch to MySQL - Vercel ready"
git push origin main
```

### 2b. Import to Vercel
1. Go to https://vercel.com → **New Project**
2. Import your **Tanyadahiya1/trucks-deal** GitHub repo
3. Framework Preset: **Other**
4. Leave Build Command and Output Directory **blank**
5. Click **Deploy** (it will fail first time — that's OK, we need to add env vars next)

---

## ⚙️ Step 3 — Set Environment Variables on Vercel

Go to your Vercel project → **Settings** → **Environment Variables** → add these:

| Key | Value | Notes |
|-----|-------|-------|
| `MYSQL_URL` | `mysql://user:pass@host/dbname` | From PlanetScale or Aiven |
| `SECRET_KEY` | `any-long-random-string-here` | e.g. `TrucksDeal@2026!xK9mP` |
| `ADMIN_EMAIL` | `your@gmail.com` | Where enquiries are sent |
| `SMTP_HOST` | `smtp.gmail.com` | |
| `SMTP_PORT` | `587` | |
| `SMTP_USER` | `your@gmail.com` | |
| `SMTP_PASS` | `xxxx xxxx xxxx xxxx` | Gmail App Password (see below) |

### Getting a Gmail App Password:
1. Enable **2-Step Verification** on your Google account
2. Go to: https://myaccount.google.com/apppasswords
3. Create new → App name: `TrucksDeal` → Copy the 16-character password
4. Paste it as `SMTP_PASS`

After adding all env vars → go to **Deployments** → **Redeploy** the latest deployment.

---

## ✅ Your site is now live!

- **Website**: `https://your-project.vercel.app`
- **Admin login**: `https://your-project.vercel.app/admin/login`
- **Default credentials**: `admin` / `admin123`
- ⚠️ **Change your password immediately** after first login!

The database tables and sample data are **auto-created on first visit** — no manual setup needed.

---

## 💻 Local Development

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create a .env file (copy from .env.example below)
# Fill in your MySQL URL or local MySQL credentials

# 3. Run
python app.py
# → http://127.0.0.1:5000
```

### .env file for local development:
```
SECRET_KEY=local-dev-secret
MYSQL_URL=mysql://root:yourpassword@localhost:3306/trucksdeal
ADMIN_EMAIL=you@gmail.com
SMTP_USER=
SMTP_PASS=
```

Or if using individual vars instead of MYSQL_URL:
```
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=yourpassword
MYSQL_DB=trucksdeal
```

---

## 📁 Project Structure

```
trucks-deal/
├── app.py                      # Flask app — all routes, MySQL, email
├── requirements.txt            # Python dependencies (Flask, PyMySQL)
├── vercel.json                 # Vercel deployment config
├── .gitignore                  # Excludes .env, __pycache__, uploads
├── README.md
├── static/
│   ├── css/
│   │   ├── style.css           # Main styles + scroll animations
│   │   └── admin.css           # Admin panel styles
│   ├── js/
│   │   └── main.js             # Scroll reveal, parallax, counters
│   └── uploads/                # Local dev only (not used on Vercel)
└── templates/
    ├── base.html               # Public navbar + footer
    ├── index.html              # Homepage
    ├── vehicles.html           # Browse + filter page
    ├── vehicle_detail.html     # Single vehicle + enquiry/deal forms
    ├── admin_base.html         # Admin sidebar layout
    ├── admin_login.html
    ├── admin_dashboard.html
    ├── admin_vehicles.html
    ├── admin_vehicle_form.html # Add/Edit with 10-photo manager
    ├── admin_enquiries.html
    └── admin_deals.html
```

---

## ✨ Features

**Public site:**
- Hero with parallax + scroll reveal animations
- Browse + filter by type, brand, price, year, keyword
- Vehicle gallery with prev/next arrows + thumbnails
- AJAX enquiry + deal forms (no page reload)
- Email notification to admin on every enquiry/deal

**Admin panel** (`/admin/login`):
- Live stats dashboard
- Add / Edit / Delete vehicles
- Upload up to **10 photos** per vehicle (URL input + file upload)
- Live character counter on description
- Show/hide password toggle
- View all enquiries and deals

---

## ⚠️ Important Notes

### Image Uploads on Vercel
Vercel's filesystem is **read-only** except `/tmp`, which resets between requests.  
**For production image uploads, use Cloudinary (free tier):**
1. Sign up at https://cloudinary.com (free)
2. Install: `pip install cloudinary`
3. Add env vars: `CLOUDINARY_URL=cloudinary://api_key:api_secret@cloud_name`
4. Replace the file-save code in `_save_vehicle()` with a Cloudinary upload

For now, **adding images by URL** (from Google Drive, Unsplash, etc.) works perfectly on Vercel without any changes.

### Why MySQL instead of SQLite?
Vercel is **serverless** — each function runs in isolation with no persistent disk. SQLite files get wiped between requests. MySQL is a proper server that lives separately and persists all data permanently.

---

## 🔧 Troubleshooting

**500 error on Vercel?**
- Check **Vercel → Functions → Logs** for the exact error
- Most common cause: `MYSQL_URL` not set or wrong format
- Make sure to **Redeploy** after adding env vars

**Can't connect to PlanetScale?**
- PlanetScale requires SSL. The code includes `ssl={"ssl": {}}` which handles this automatically.
- Make sure your connection string ends with `?ssl-mode=REQUIRED`

**Emails not sending?**
- Double check `SMTP_USER` and `SMTP_PASS` are set
- Make sure you used an **App Password** (not your Gmail account password)
- Check Vercel function logs for SMTP error details
