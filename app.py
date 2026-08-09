import os, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from datetime import datetime
import secrets
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, make_response)
from functools import lru_cache
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pymysql
import pymysql.cursors
import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME",""),
    api_key    = os.environ.get("CLOUDINARY_API_KEY",""),
    api_secret = os.environ.get("CLOUDINARY_API_SECRET",""),
)

def upload_to_cloudinary(file_obj):
    """Upload file to Cloudinary and return URL."""
    if not os.environ.get("CLOUDINARY_CLOUD_NAME"):
        app.logger.warning("Cloudinary not configured")
        return None
    try:
        result = cloudinary.uploader.upload(
            file_obj,
            folder       = "trucksdeal",
            quality      = "auto:low",
            fetch_format = "auto",
            width        = 900,
            crop         = "limit",
            timeout      = 30,
        )
        return result.get("secure_url")
    except Exception as e:
        app.logger.error(f"Cloudinary upload failed: {e}")
        return None

# ─── App setup ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = 86400  # 1 day
app.secret_key = os.environ.get("SECRET_KEY", "trucksdeal-secret-2026")

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "gif"}
MAX_PICS    = 10

app.config["UPLOAD_FOLDER"]       = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"]  = 32 * 1024 * 1024   # 32 MB

# ─── Email config ─────────────────────────────────────────────────────────────
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@trucksdeal.in")
SMTP_HOST   = os.environ.get("SMTP_HOST",   "smtp.gmail.com")
SMTP_PORT   = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER   = os.environ.get("SMTP_USER",   "")
SMTP_PASS   = os.environ.get("SMTP_PASS",   "")

# ─── MySQL connection ──────────────────────────────────────────────────────────
# Set MYSQL_URL in Vercel env as:
#   mysql://user:password@host:3306/dbname
# OR set individual vars: MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB

def get_db():
    """Return a new PyMySQL connection per request."""
    url = os.environ.get("MYSQL_URL", "")
    if url:
        # Parse mysql://user:pass@host:port/dbname
        import urllib.parse as up
        u = up.urlparse(url)
        conn = pymysql.connect(
            host     = u.hostname,
            port     = u.port or 3306,
            user     = u.username,
            password = u.password,
            db       = u.path.lstrip("/"),
            charset  = "utf8mb4",
            cursorclass = pymysql.cursors.DictCursor,
            autocommit  = False,
            ssl      = {"ssl": {"ssl_disabled": False}},       # PlanetScale / Aiven require SSL
        )
    else:
        conn = pymysql.connect(
            host     = os.environ.get("MYSQL_HOST",     "localhost"),
            port     = int(os.environ.get("MYSQL_PORT", 3306)),
            user     = os.environ.get("MYSQL_USER",     "root"),
            password = os.environ.get("MYSQL_PASSWORD", ""),
            db       = os.environ.get("MYSQL_DB",       "trucksdeal"),
            charset  = "utf8mb4",
            cursorclass = pymysql.cursors.DictCursor,
            autocommit  = False,
        )
    return conn

def q(conn, sql, params=()):
    """Execute and return all rows."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()

def q1(conn, sql, params=()):
    """Execute and return one row."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()

def ex(conn, sql, params=()):
    """Execute a write query, return lastrowid."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.lastrowid

# ─── DB init ──────────────────────────────────────────────────────────────────
def init_db():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id           INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(80)  UNIQUE NOT NULL,
                password VARCHAR(256) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            try:
               cur.execute("ALTER TABLE admins ADD COLUMN reset_token VARCHAR(100)")
            except:
                pass
            try:
                cur.execute("ALTER TABLE admins ADD COLUMN reset_expiry DATETIME")
            except:
                pass
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS vehicles (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                title       VARCHAR(200) NOT NULL,
                type        ENUM('Truck','Bus') NOT NULL,
                brand       VARCHAR(100) NOT NULL,
                model       VARCHAR(100) NOT NULL,
                year        INT NOT NULL,
                km_driven   INT NOT NULL,
                fuel        VARCHAR(30) NOT NULL DEFAULT 'Diesel',
                engine_cc   INT,
                tonnage     VARCHAR(30),
                permit      VARCHAR(50),
                rc_number   VARCHAR(50),
                location    VARCHAR(100) NOT NULL,
                price_lakh  DECIMAL(8,2) NOT NULL,
                negotiable  TINYINT(1) NOT NULL DEFAULT 1,
                description TEXT,
                featured    TINYINT(1) NOT NULL DEFAULT 0,
                status      ENUM('Active','Sold','Inactive') NOT NULL DEFAULT 'Active',
                views       INT NOT NULL DEFAULT 0,
                created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS vehicle_images (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                vehicle_id INT NOT NULL,
                url        TEXT NOT NULL,
                sort_order INT NOT NULL DEFAULT 0,
                FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS enquiries (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                vehicle_id INT NOT NULL,
                name       VARCHAR(100) NOT NULL,
                phone      VARCHAR(20)  NOT NULL,
                message    TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS deals (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                vehicle_id INT NOT NULL,
                name       VARCHAR(100) NOT NULL,
                phone      VARCHAR(20)  NOT NULL,
                email      VARCHAR(150),
                message    TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS sell_requests (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                name        VARCHAR(100) NOT NULL,
                phone       VARCHAR(20)  NOT NULL,
                email       VARCHAR(150),
                vtype       VARCHAR(30),
                brand       VARCHAR(100),
                model       VARCHAR(100),
                year        VARCHAR(10),
                km_driven   VARCHAR(20),
                price       VARCHAR(20),
                location    VARCHAR(100),
                description TEXT,
                created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS loan_enquiries (
                 id           INT AUTO_INCREMENT PRIMARY KEY,
                 name         VARCHAR(100) NOT NULL,
                 phone        VARCHAR(20)  NOT NULL,
                 email        VARCHAR(150),
                 vtype        VARCHAR(30),
                 vehicle_cond VARCHAR(30),
                 amount       VARCHAR(20),
                 location     VARCHAR(100),
                 created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                 id         INT AUTO_INCREMENT PRIMARY KEY,
                 name       VARCHAR(100) NOT NULL,
                 email      VARCHAR(150) UNIQUE NOT NULL,
                 phone      VARCHAR(20),
                 password   VARCHAR(256) NOT NULL,
                 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            try:
             cur.execute("ALTER TABLE sell_requests ADD COLUMN image_urls TEXT")
            except:
             pass

            # Seed admin
            cur.execute("SELECT id FROM admins WHERE username='admin'")
            if not cur.fetchone():
                cur.execute("INSERT INTO admins(username,password) VALUES(%s,%s)",
                            ("admin", generate_password_hash("admin123")))

            # Seed sample vehicles
            cur.execute("SELECT COUNT(*) as cnt FROM vehicles")
            if cur.fetchone()["cnt"] == 0:
                vehicles = [
                    ("Tata LPT 2518 Heavy Truck","Truck","Tata Motors","LPT 2518",2019,82000,"Diesel",5700,"25 Ton","All India","DL 01 AA 2518","Okhla, Delhi",18.5,1,"Well maintained. Single owner. All documents clear.",1),
                    ("Ashok Leyland Viking 52-Seat Bus","Bus","Ashok Leyland","Viking",2017,125000,"Diesel",4000,"12.5 Ton","All India","DL 01 BB 5200","Mayur Vihar, Delhi",14.0,1,"Fully serviced. AC unit operational. New tyres fitted.",1),
                    ("Eicher Pro 1059 Mini Truck","Truck","Eicher","Pro 1059",2020,48500,"Diesel",3300,"5.9 Ton","Delhi NCR","DL 01 CC 1059","Narela, Delhi",9.2,1,"Excellent condition. GPS fitted. No accidents.",0),
                    ("Tata LPT 1109 Medium Truck","Truck","Tata Motors","LPT 1109",2018,97000,"Diesel",3800,"11 Ton","All India","HR 26 DD 1109","Faridabad",11.8,1,"Regular service history. Strong chassis.",0),
                    ("BharatBenz 2523R Heavy Truck","Truck","BharatBenz","2523R",2021,62000,"Diesel",5100,"25 Ton","All India","DL 14 EE 2523","Badarpur, Delhi",26.5,1,"Low mileage for year. Hydraulic body. Top condition.",1),
                    ("Mahindra FURIO 7 Mini Truck","Truck","Mahindra","FURIO 7",2022,28000,"Diesel",2000,"7 Ton","Delhi NCR","DL 01 FF 0007","Rohini, Delhi",7.8,1,"2022 model almost new. Under warranty period.",0),
                    ("Tata 407 Mini Truck","Truck","Tata Motors","407",2016,160000,"Diesel",2400,"4 Ton","Delhi NCR","DL 01 GG 0407","Kashmere Gate, Delhi",4.5,1,"Budget buy. Good for last-mile delivery.",0),
                    ("Volvo 9400 AC Sleeper Bus","Bus","Volvo","9400",2019,210000,"Diesel",7000,"18 Ton","All India","DL 01 HH 9400","Anand Vihar, Delhi",32.0,1,"Luxury sleeper coach. 45 seats. AC in perfect condition.",1),
                ]
                for v in vehicles:
                    cur.execute("""INSERT INTO vehicles
                        (title,type,brand,model,year,km_driven,fuel,engine_cc,tonnage,permit,
                         rc_number,location,price_lakh,negotiable,description,featured)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", v)

                imgs = [
                    "https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=900&q=85",
                    "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=900&q=85",
                    "https://images.unsplash.com/photo-1519003722824-194d4455a60c?w=900&q=85",
                    "https://images.unsplash.com/photo-1519003722824-194d4455a60c?w=900&q=85",
                    "https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=900&q=85",
                    "https://images.unsplash.com/photo-1519003722824-194d4455a60c?w=900&q=85",
                    "https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=900&q=85",
                    "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=900&q=85",
                ]
                # Get the IDs of the just-inserted vehicles
                cur.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 8")
                vids = [r["id"] for r in reversed(cur.fetchall())]
                for vid, url in zip(vids, imgs):
                    cur.execute("INSERT INTO vehicle_images(vehicle_id,url,sort_order) VALUES(%s,%s,0)",
                                (vid, url))
        conn.commit()
    finally:
        conn.close()

# ─── Helpers ──────────────────────────────────────────────────────────────────
def allowed_file(fn):
    return "." in fn and fn.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def admin_required(f):
    @wraps(f)
    def deco(*a, **kw):
        if not session.get("admin"):
            session.clear()
            flash("Please login as admin.", "error")
            return redirect(url_for("login"))
        return f(*a, **kw)
    return deco

def send_email(subject, body_html, to=None):
    if not SMTP_USER or not SMTP_PASS:
        app.logger.error("SMTP not configured")
        return
    try:
        recipients = []
        if isinstance(to, list):
            recipients = [r for r in to if r]
        elif to:
            recipients = [to]
        if ADMIN_EMAIL not in recipients:
            recipients.append(ADMIN_EMAIL)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = SMTP_USER
        msg["To"]      = ", ".join(recipients)
        msg["Content-Type"] = "text/html; charset=utf-8"
        msg.attach(MIMEText(body_html, "html", "utf-8"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, recipients, msg.as_string())
            app.logger.info(f"Email sent to {recipients}: {subject}")
    except Exception as e:
        app.logger.error(f"Email error: {type(e).__name__}: {e}")
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = SMTP_USER
        msg["To"]      = ADMIN_EMAIL
        msg.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.ehlo(); s.starttls(); s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, ADMIN_EMAIL, msg.as_string())
    except Exception as e:
        app.logger.error(f"Email error: {e}")

def vehicle_images(conn, vid):
    rows = q(conn, "SELECT url FROM vehicle_images WHERE vehicle_id=%s ORDER BY sort_order,id", (vid,))
    return [r["url"] for r in rows]

# ─── Public routes ─────────────────────────────────────────────────────────────
@app.route("/")
def index():
    conn = get_db()
    try:
        featured = q(conn, "SELECT * FROM vehicles WHERE featured=1 AND status='Active' ORDER BY created_at DESC LIMIT 4")
        latest   = q(conn, "SELECT * FROM vehicles WHERE status='Active' ORDER BY created_at DESC LIMIT 6")
        total_vehicles = q1(conn, "SELECT COUNT(*) as c FROM vehicles WHERE status='Active'")["c"]
        total_enquiries = q1(conn, "SELECT COUNT(*) as c FROM enquiries")["c"]
        total_deals = q1(conn, "SELECT COUNT(*) as c FROM deals")["c"]
        stats = {"listings": total_vehicles + total_enquiries + total_deals}
        all_ids = list({v["id"] for v in featured} | {v["id"] for v in latest})
        if all_ids:
          fmt = ",".join(["%s"]*len(all_ids))
          all_imgs = q(conn, f"SELECT vehicle_id,url FROM vehicle_images WHERE vehicle_id IN ({fmt}) ORDER BY sort_order,id", all_ids)
          imgs_map = {}
          for r in all_imgs:
            imgs_map.setdefault(r["vehicle_id"], []).append(r["url"])
        else:
          imgs_map = {}
        fimgs = {v["id"]: imgs_map.get(v["id"],[]) for v in featured}
        limgs = {v["id"]: imgs_map.get(v["id"],[]) for v in latest}
        return render_template("index.html", featured=featured, latest=latest,
                               stats=stats, fimgs=fimgs, limgs=limgs)
    finally:
        conn.close()

@app.route("/vehicles")
def vehicles():
    conn  = get_db()
    try:
        qstr  = request.args.get("q","").strip()
        vtype = request.args.get("type","")
        brand = request.args.get("brand","")
        min_p = request.args.get("min_price","")
        max_p = request.args.get("max_price","")
        min_y = request.args.get("min_year","")
        max_y = request.args.get("max_year","")
        sort  = request.args.get("sort","newest")

        sql    = "SELECT * FROM vehicles WHERE status='Active'"
        params = []
        if qstr:
            sql += " AND (title LIKE %s OR brand LIKE %s OR model LIKE %s OR location LIKE %s)"
            params += [f"%{qstr}%"]*4
        if vtype:
            sql += " AND type=%s";  params.append(vtype)
        if brand:
            sql += " AND brand=%s"; params.append(brand)
        if min_p:
            sql += " AND price_lakh>=%s"; params.append(float(min_p))
        if max_p:
            sql += " AND price_lakh<=%s"; params.append(float(max_p))
        if min_y:
            sql += " AND year>=%s"; params.append(int(min_y))
        if max_y:
            sql += " AND year<=%s"; params.append(int(max_y))
        order = {"newest":"created_at DESC","price_asc":"price_lakh ASC",
                 "price_desc":"price_lakh DESC","views":"views DESC"}.get(sort,"created_at DESC")
        sql += f" ORDER BY {order}"

        rows   = q(conn, sql, params)
        brands = q(conn, "SELECT DISTINCT brand FROM vehicles ORDER BY brand")
        imgs   = {v["id"]: vehicle_images(conn, v["id"]) for v in rows}
        return render_template("vehicles.html", vehicles=rows, brands=brands,
                               imgs=imgs, args=request.args)
    finally:
        conn.close()

@app.route("/vehicle/<int:vid>")
def vehicle_detail(vid):
    conn = get_db()
    try:
        v = q1(conn, "SELECT * FROM vehicles WHERE id=%s", (vid,))
        if not v:
            return "Vehicle not found", 404
        ex(conn, "UPDATE vehicles SET views=views+1 WHERE id=%s", (vid,))
        conn.commit()
        imgs    = vehicle_images(conn, vid)
        similar = q(conn, "SELECT * FROM vehicles WHERE type=%s AND id!=%s AND status='Active' LIMIT 3",
                    (v["type"], vid))
        simgs   = {s["id"]: vehicle_images(conn, s["id"]) for s in similar}
        return render_template("vehicle_detail.html", v=v, imgs=imgs,
                               similar=similar, simgs=simgs)
    finally:
        conn.close()
@app.route("/test-email")
def test_email():
    try:
        send_email("TrucksDeal Test Email", "<h2>Email is working!</h2>")
        return "Email sent successfully! Check info.trucksdeal@gmail.com"
    except Exception as e:
        return f"Email failed: {str(e)}", 500
@app.route("/enquiry/<int:vid>", methods=["POST"])
def send_enquiry(vid):
    conn = get_db()
    try:
        v     = q1(conn, "SELECT * FROM vehicles WHERE id=%s", (vid,))
        if not v:
            return jsonify({"ok": False}), 404
        name  = request.form.get("name","").strip()
        phone = request.form.get("phone","").strip()
        email = request.form.get("email","").strip()
        msg   = request.form.get("message","").strip()
        if not name or not phone:
            return jsonify({"ok": False, "error": "Name and phone required"}), 400
              
        ex(conn, "INSERT INTO enquiries(vehicle_id,name,phone,message) VALUES(%s,%s,%s,%s)",
           (vid, name, phone, msg))
        conn.commit()
        title = v.get("title") or f"Vehicle #{vid}"
        price = v.get("price_lakh") or "N/A"
        

        # Email to admin
        admin_html = f"""
        <h2 style="color:#f97316">New Enquiry – TrucksDeal</h2>
        <table border="1" cellpadding="8" style="border-collapse:collapse;width:100%">
          <tr><td><b>Vehicle</b></td><td>{title} (ID #{vid})</td></tr>
          <tr><td><b>Price</b></td><td>₹{price}L</td></tr>
          <tr><td><b>Buyer Name</b></td><td>{name}</td></tr>
          <tr><td><b>Phone</b></td><td>{phone}</td></tr>
          <tr><td><b>Email</b></td><td>{email or 'N/A'}</td></tr>
          <tr><td><b>Message</b></td><td>{msg or 'N/A'}</td></tr>
          <tr><td><b>Time</b></td><td>{datetime.now().strftime('%d %b %Y %H:%M')}</td></tr>
        </table>
        """

        # Email to user
        user_html = f"""
        <h2 style="color:#f97316">Your Enquiry is Received – TrucksDeal</h2>
        <p>Dear {name},</p>
        <p>Thank you for your enquiry on <b>{title}</b>. Our team will contact you on <b>{phone}</b> within 2 hours.</p>
        <table border="1" cellpadding="8" style="border-collapse:collapse;width:100%">
          <tr><td><b>Vehicle</b></td><td>{title}</td></tr>
          <tr><td><b>Price</b></td><td>₹{price}L</td></tr>
          <tr><td><b>Your Message</b></td><td>{msg or 'N/A'}</td></tr>
        </table>
        <p style="margin-top:1rem">Regards,<br><b>TrucksDeal Team</b><br>📞 +91 99537 34477</p>
        """
        try:
            send_email(f"New Enquiry – {title}", admin_html)
            if email:
                send_email(f"Enquiry Received – {title}", user_html, to=email)
        except Exception as e:
            app.logger.error(f"Enquiry email failed: {e}")
        return jsonify({"ok": True})
    finally:
        conn.close()

@app.route("/deal/<int:vid>", methods=["POST"])
def send_deal(vid):
    conn = get_db()
    try:
        v     = q1(conn, "SELECT * FROM vehicles WHERE id=%s", (vid,))
        if not v:
            return jsonify({"ok": False}), 404
        name  = request.form.get("name","").strip()
        phone = request.form.get("phone","").strip()
        email = request.form.get("email","").strip()
        msg   = request.form.get("message","").strip()
        if not name or not phone:
            return jsonify({"ok": False, "error": "Name and phone required"}), 400
        ex(conn, "INSERT INTO deals(vehicle_id,name,phone,email,message) VALUES(%s,%s,%s,%s,%s)",
           (vid, name, phone, email, msg))
        conn.commit()
        title = v.get("title") or f"Vehicle #{vid}"
        price = v.get("price_lakh") or "N/A"

        admin_html = f"""
        <h2 style="color:#f97316">New Deal Request – TrucksDeal</h2>
        <table border="1" cellpadding="8" style="border-collapse:collapse;width:100%">
          <tr><td><b>Vehicle</b></td><td>{title} (ID #{vid})</td></tr>
          <tr><td><b>Price</b></td><td>₹{price}L</td></tr>
          <tr><td><b>Buyer Name</b></td><td>{name}</td></tr>
          <tr><td><b>Phone</b></td><td>{phone}</td></tr>
          <tr><td><b>Email</b></td><td>{email or 'N/A'}</td></tr>
          <tr><td><b>Message</b></td><td>{msg or 'N/A'}</td></tr>
          <tr><td><b>Time</b></td><td>{datetime.now().strftime('%d %b %Y %H:%M')}</td></tr>
        </table>
        """

        user_html = f"""
        <h2 style="color:#f97316">Deal Request Received – TrucksDeal</h2>
        <p>Dear {name},</p>
        <p>Your deal request for <b>{title}</b> at <b>₹{price}L</b> has been received.</p>
        <p>Our team will contact you on <b>{phone}</b> within 2 hours to finalize the deal.</p>
        <table border="1" cellpadding="8" style="border-collapse:collapse;width:100%">
          <tr><td><b>Vehicle</b></td><td>{title}</td></tr>
          <tr><td><b>Price</b></td><td>₹{price}L</td></tr>
          <tr><td><b>Your Message</b></td><td>{msg or 'N/A'}</td></tr>
        </table>
        <p style="margin-top:1rem">Regards,<br><b>TrucksDeal Team</b><br>📞 +91 99537 34477</p>
        """
        try:
            send_email(f"New Deal Request – {title}", admin_html)
            if email:
                send_email(f"Deal Request Received – {title}", user_html, to=email)
        except Exception as e:
            app.logger.error(f"Deal email failed: {e}")
        return jsonify({"ok": True})
    finally:
        conn.close()

# ─── Admin routes ──────────────────────────────────────────────────────────────
@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    return redirect(url_for("login"))

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("login"))
@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db()
    try:
        stats = {
            "vehicles":      q1(conn, "SELECT COUNT(*) as c FROM vehicles")["c"],
            "active":        q1(conn, "SELECT COUNT(*) as c FROM vehicles WHERE status='Active'")["c"],
            "enquiries":     q1(conn, "SELECT COUNT(*) as c FROM enquiries")["c"],
            "deals":         q1(conn, "SELECT COUNT(*) as c FROM deals")["c"],
            "sell_requests":  q1(conn, "SELECT COUNT(*) as c FROM sell_requests")["c"],
            "loan_enquiries": q1(conn, "SELECT COUNT(*) as c FROM loan_enquiries")["c"],
        }
        recent_enq   = q(conn, "SELECT e.id,e.vehicle_id,e.name,e.phone,e.message,DATE_FORMAT(e.created_at,'%%Y-%%m-%%d %%H:%%i') as created_at,v.title FROM enquiries e JOIN vehicles v ON e.vehicle_id=v.id ORDER BY e.created_at DESC LIMIT 10")
        recent_deals = q(conn, "SELECT d.id,d.vehicle_id,d.name,d.phone,d.email,d.message,DATE_FORMAT(d.created_at,'%%Y-%%m-%%d %%H:%%i') as created_at,v.title FROM deals d JOIN vehicles v ON d.vehicle_id=v.id ORDER BY d.created_at DESC LIMIT 10")
        sell_requests  = q(conn, "SELECT * FROM sell_requests ORDER BY created_at DESC LIMIT 10")
        loan_enquiries = q(conn, "SELECT * FROM loan_enquiries ORDER BY created_at DESC LIMIT 10")
        return render_template("admin_dashboard.html", stats=stats,
                               recent_enq=recent_enq, recent_deals=recent_deals,
                               sell_requests=sell_requests,
                               loan_enquiries=loan_enquiries)

    finally:
        conn.close()
@app.route("/admin/vehicles")
@admin_required
def admin_vehicles():
    conn = get_db()
    try:
        rows = q(conn, "SELECT * FROM vehicles ORDER BY created_at DESC")
        if rows:
          fmt = ",".join(["%s"]*len(rows))
          all_ids = [v["id"] for v in rows]
          all_imgs = q(conn, f"SELECT vehicle_id,url FROM vehicle_images WHERE vehicle_id IN ({fmt}) ORDER BY sort_order,id", all_ids)
          imgs_map = {}
          for r in all_imgs:
              imgs_map.setdefault(r["vehicle_id"], []).append(r["url"])
          imgs = {v["id"]: imgs_map.get(v["id"],[]) for v in rows}
        else:
          
          mgs = {}
        return render_template("admin_vehicles.html", vehicles=rows, imgs=imgs)
    finally:
        conn.close()

@app.route("/admin/vehicle/new", methods=["GET","POST"])
@admin_required
def admin_vehicle_new():
    if request.method == "POST":
        return _save_vehicle(None)
    return render_template("admin_vehicle_form.html", v=None, imgs=[])
@app.route("/admin/vehicle/<int:vid>/edit", methods=["GET","POST"])
@admin_required
def admin_vehicle_edit(vid):
    conn = get_db()
    try:
        v = q1(conn, "SELECT * FROM vehicles WHERE id=%s", (vid,))
        if not v:
            return "Not found", 404
        if request.method == "POST":
            conn.close()
            return _save_vehicle(vid)
        imgs_raw = q(conn, "SELECT id,url FROM vehicle_images WHERE vehicle_id=%s ORDER BY sort_order,id", (vid,))
        imgs = [r["url"] for r in imgs_raw]
        imgs_with_ids = [(r["id"], r["url"]) for r in imgs_raw]
        return render_template("admin_vehicle_form.html", v=v, imgs=imgs, imgs_with_ids=imgs_with_ids)
    finally:
        try: conn.close()
        except: pass
def _save_vehicle(vid):
    conn = get_db()
    try:
        f    = request.form
        data = (
            f.get("title","").strip(),
            f.get("type","Truck"),
            f.get("brand","").strip(),
            f.get("model","").strip(),
            int(f.get("year",2020)),
            int(f.get("km_driven",0)),
            f.get("fuel","Diesel"),
            int(f.get("engine_cc",0) or 0),
            f.get("tonnage","").strip(),
            f.get("permit","").strip(),
            f.get("rc_number","").strip(),
            f.get("location","").strip(),
            float(f.get("price_lakh",0)),
            1 if f.get("negotiable") else 0,
            f.get("description","").strip(),
            1 if f.get("featured") else 0,
            f.get("status","Active"),
        )
        if vid is None:
            vid = ex(conn, """INSERT INTO vehicles
                (title,type,brand,model,year,km_driven,fuel,engine_cc,tonnage,permit,
                 rc_number,location,price_lakh,negotiable,description,featured,status)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", data)
        else:
            ex(conn, """UPDATE vehicles SET
                title=%s,type=%s,brand=%s,model=%s,year=%s,km_driven=%s,fuel=%s,engine_cc=%s,
                tonnage=%s,permit=%s,rc_number=%s,location=%s,price_lakh=%s,negotiable=%s,
                description=%s,featured=%s,status=%s WHERE id=%s""", data+(vid,))

        existing = q1(conn, "SELECT COUNT(*) as c FROM vehicle_images WHERE vehicle_id=%s", (vid,))["c"]

        # File uploads – NOTE: on Vercel /tmp is writable but not persistent.
        # Images are stored as URLs (external). For file uploads to persist,
        # you need Cloudinary (see README). We still support it for local dev.
        files = request.files.getlist("images")
        for fobj in files:
           if existing >= MAX_PICS:
              break
           if fobj and fobj.filename and fobj.filename.strip() and allowed_file(fobj.filename):
             files = request.files.getlist("images")
        for fobj in files:
          if existing >= MAX_PICS:
               break
          if fobj and fobj.filename and allowed_file(fobj.filename):
           url = upload_to_cloudinary(fobj)
           if url:
            ex(conn, "INSERT INTO vehicle_images(vehicle_id,url,sort_order) VALUES(%s,%s,%s)",
               (vid, url, existing))
            existing += 1

        img_urls = f.getlist("img_url")
        for url in img_urls:
            url = url.strip()
            if url and existing < MAX_PICS:
                ex(conn, "INSERT INTO vehicle_images(vehicle_id,url,sort_order) VALUES(%s,%s,%s)",
                   (vid, url, existing))
                existing += 1

        del_ids = request.form.getlist("delete_img")
        for iid in del_ids:
          try:
            row = q1(conn, "SELECT url FROM vehicle_images WHERE id=%s AND vehicle_id=%s", (iid, vid))
            if row:
              url = row["url"]
            # Delete from Cloudinary if cloudinary URL
              if "cloudinary.com" in url:
                try:
                    # Extract public_id from URL
                    public_id = "trucksdeal/" + url.split("/trucksdeal/")[-1].rsplit(".", 1)[0]
                    cloudinary.uploader.destroy(public_id)
                except Exception as e:
                    app.logger.error(f"Cloudinary delete failed: {e}")
            # Delete from local storage if local
            elif url.startswith("/static/"):
                try:
                    os.remove(os.path.join(app.root_path, url.lstrip("/")))
                except:
                    pass
            # Delete from DB
            ex(conn, "DELETE FROM vehicle_images WHERE id=%s", (iid,))
          except Exception as e:
            app.logger.error(f"Image delete error: {e}")

        conn.commit()
        flash("Vehicle saved successfully.", "success")
        return redirect(url_for("admin_vehicles"))
    finally:
        conn.close()

@app.route("/admin/vehicle/<int:vid>/delete", methods=["POST"])
@admin_required
def admin_vehicle_delete(vid):
    conn = get_db()
    try:
        ex(conn, "DELETE FROM vehicles WHERE id=%s", (vid,))
        conn.commit()
        flash("Vehicle deleted.", "success")
        return redirect(url_for("admin_vehicles"))
    finally:
        conn.close()

@app.route("/admin/enquiries")
@admin_required
def admin_enquiries():
    conn = get_db()
    try:
        rows = q(conn, "SELECT e.id,e.vehicle_id,e.name,e.phone,e.message,DATE_FORMAT(e.created_at,'%%Y-%%m-%%d %%H:%%i') as created_at,v.title FROM enquiries e JOIN vehicles v ON e.vehicle_id=v.id ORDER BY e.created_at DESC")
        return render_template("admin_enquiries.html", rows=rows)
    finally:
        conn.close()

@app.route("/admin/deals")
@admin_required
def admin_deals():
    conn = get_db()
    try:
        rows = q(conn, "SELECT d.id,d.vehicle_id,d.name,d.phone,d.email,d.message,DATE_FORMAT(d.created_at,'%%Y-%%m-%%d %%H:%%i') as created_at,v.title FROM deals d JOIN vehicles v ON d.vehicle_id=v.id ORDER BY d.created_at DESC")
        return render_template("admin_deals.html", rows=rows)
    finally:
        conn.close()

@app.route("/admin/change-password", methods=["POST"])
@admin_required
def admin_change_password():
    conn = get_db()
    try:
        old  = request.form.get("old_password","")
        new  = request.form.get("new_password","")
        user = session["admin"]
        row  = q1(conn, "SELECT * FROM admins WHERE username=%s", (user,))
        if not row or not check_password_hash(row["password"], old):
            flash("Old password incorrect.", "error")
        elif len(new) < 6:
            flash("New password must be at least 6 characters.", "error")
        else:
            ex(conn, "UPDATE admins SET password=%s WHERE username=%s",
               (generate_password_hash(new), user))
            conn.commit()
            flash("Password updated.", "success")
        return redirect(url_for("admin_dashboard"))
    finally:
        conn.close()

# ─── Vercel: run init_db once on cold start ───────────────────────────────────
_initialized = False

@app.before_request
@app.before_request
def ensure_db():
    global _initialized
    if not _initialized:
        try:
            init_db()
            _initialized = True
        except Exception as e:
            return f"<h2>DB Error</h2><pre>{str(e)}</pre>", 500
@app.route("/admin/forgot-password", methods=["GET","POST"])
def admin_forgot_password():
    if request.method == "POST":
        conn = get_db()
        try:
            username = request.form.get("username","").strip()
            row = q1(conn, "SELECT * FROM admins WHERE username=%s", (username,))
            if row:
                token = secrets.token_urlsafe(32)
                expiry = datetime.now().replace(microsecond=0)
                from datetime import timedelta
                expiry = expiry + timedelta(hours=1)
                ex(conn, "UPDATE admins SET reset_token=%s, reset_expiry=%s WHERE username=%s",
                   (token, expiry, username))
                conn.commit()
                reset_url = url_for("admin_reset_password", token=token, _external=True)
                html = f"""
                <h2>TrucksDeal – Password Reset</h2>
                <p>You requested a password reset for admin account: <b>{username}</b></p>
                <p>Click the link below to reset your password. This link expires in 1 hour.</p>
                <p><a href="{reset_url}" style="background:#f97316;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:600;">Reset Password</a></p>
                <p>Or copy this URL: {reset_url}</p>
                <p>If you did not request this, ignore this email.</p>
                """
                reset_html = f"""
                <h2 style="color:#f97316">Password Reset – TrucksDeal Admin</h2>
                <p>You requested a password reset for admin account: <b>{username}</b></p>
                <p>Click the button below to reset your password. This link expires in <b>1 hour</b>.</p>
                <p style="text-align:center;margin:2rem 0">
                 <a href="{reset_url}" style="background:#f97316;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:1rem">
                    Reset My Password
                 </a>
                </p>
                <p style="color:#666;font-size:.85rem">Or copy this link: {reset_url}</p>
                <p style="color:#666;font-size:.85rem">If you did not request this, ignore this email. Your password will not change.</p>
                <p style="margin-top:1rem">Regards,<br><b>TrucksDeal System</b></p>
                """
            send_email("TrucksDeal – Password Reset Link", reset_html)
            # Always show success (don't reveal if username exists)
            flash("If that username exists, a reset link has been sent to the admin email.", "success")
            return redirect(url_for("admin_forgot_password"))
        finally:
            conn.close()
    return render_template("admin_forgot_password.html")


@app.route("/admin/reset-password/<token>", methods=["GET","POST"])
def admin_reset_password(token):
    conn = get_db()
    try:
        row = q1(conn, "SELECT * FROM admins WHERE reset_token=%s AND reset_expiry > NOW()", (token,))
        if not row:
            flash("Reset link is invalid or has expired.", "error")
            return redirect(url_for("admin_login"))
        if request.method == "POST":
            new_pw = request.form.get("password","")
            confirm = request.form.get("confirm","")
            if len(new_pw) < 6:
                flash("Password must be at least 6 characters.", "error")
            elif new_pw != confirm:
                flash("Passwords do not match.", "error")
            else:
                ex(conn, "UPDATE admins SET password=%s, reset_token=NULL, reset_expiry=NULL WHERE id=%s",
                   (generate_password_hash(new_pw), row["id"]))
                conn.commit()
                flash("Password reset successfully. Please log in.", "success")
                return redirect(url_for("admin_login"))
        return render_template("admin_reset_password.html", token=token)
    finally:
        conn.close()
@app.route("/sell", methods=["GET","POST"])
def sell_vehicle():
    if request.method == "POST":
        name     = request.form.get("name","").strip()
        phone    = request.form.get("phone","").strip()
        email    = request.form.get("email","").strip()
        vtype    = request.form.get("type","").strip()
        brand    = request.form.get("brand","").strip()
        model    = request.form.get("model","").strip()
        year     = request.form.get("year","").strip()
        km       = request.form.get("km_driven","").strip()
        price    = request.form.get("price","").strip()
        location = request.form.get("location","").strip()
        desc     = request.form.get("description","").strip()

        if not name or not phone:
            return jsonify({"ok": False, "error": "Name and phone required"}), 400

        # Upload images to Cloudinary
        image_urls = []
        try:
            files = request.files.getlist("images")
            for fobj in files:
                if len(image_urls) >= 5:
                    break
                if fobj and fobj.filename and fobj.filename.strip() and allowed_file(fobj.filename):
                    url = upload_to_cloudinary(fobj)
                    if url:
                        image_urls.append(url)
        except Exception as e:
            app.logger.error(f"Image upload error: {e}")

        # Save to database
        conn2 = get_db()
        try:
            ex(conn2, """INSERT INTO sell_requests
                (name,phone,email,vtype,brand,model,year,km_driven,price,location,description)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (name,phone,email,vtype,brand,model,year,km,price,location,desc,
                 ",".join(image_urls) if image_urls else ""))
            conn2.commit()
        except Exception as e:
            app.logger.error(f"Sell request save failed: {e}")
        finally:
            conn2.close()

        # Email to admin
        images_html = "".join([
            f'<img src="{u}" style="width:120px;margin:4px;border-radius:4px">'
            for u in image_urls
        ]) or "No images uploaded"

        admin_html = f"""
        <h2 style="color:#f97316">New Vehicle Listing Request – TrucksDeal</h2>
        <table border="1" cellpadding="8" style="border-collapse:collapse;width:100%">
          <tr><td><b>Seller Name</b></td><td>{name}</td></tr>
          <tr><td><b>Phone</b></td><td>{phone}</td></tr>
          <tr><td><b>Email</b></td><td>{email or 'N/A'}</td></tr>
          <tr><td><b>Vehicle Type</b></td><td>{vtype}</td></tr>
          <tr><td><b>Brand</b></td><td>{brand}</td></tr>
          <tr><td><b>Model</b></td><td>{model}</td></tr>
          <tr><td><b>Year</b></td><td>{year}</td></tr>
          <tr><td><b>KM Driven</b></td><td>{km}</td></tr>
          <tr><td><b>Expected Price</b></td><td>₹{price} Lakh</td></tr>
          <tr><td><b>Location</b></td><td>{location}</td></tr>
          <tr><td><b>Description</b></td><td>{desc or 'N/A'}</td></tr>
          <tr><td><b>Images</b></td><td>{images_html}</td></tr>
          <tr><td><b>Time</b></td><td>{datetime.now().strftime('%d %b %Y %H:%M')}</td></tr>
        </table>
        """

        user_html = f"""
        <h2 style="color:#f97316">Listing Request Received – TrucksDeal</h2>
        <p>Dear {name},</p>
        <p>Thank you for submitting your <b>{vtype} – {brand} {model} ({year})</b> for listing on TrucksDeal.</p>
        <p>Our team will review your request and contact you on <b>{phone}</b> within 24 hours.</p>
        <table border="1" cellpadding="8" style="border-collapse:collapse;width:100%">
          <tr><td><b>Vehicle</b></td><td>{brand} {model} {year}</td></tr>
          <tr><td><b>Expected Price</b></td><td>₹{price} Lakh</td></tr>
          <tr><td><b>Location</b></td><td>{location}</td></tr>
        </table>
        <p style="margin-top:1rem">Regards,<br><b>TrucksDeal Team</b><br>📞 +91 99537 34477</p>
        """

        try:
            send_email(f"New Listing Request – {vtype} by {name}", admin_html)
            if email:
                send_email("Your Listing Request is Received – TrucksDeal", user_html, to=email)
        except Exception as e:
            app.logger.error(f"Sell email failed: {e}")

        return jsonify({"ok": True})
    return render_template("sell.html")

@app.route("/api/stats")
def api_stats():
    conn = get_db()
    try:
        total_vehicles  = q1(conn, "SELECT COUNT(*) as c FROM vehicles WHERE status='Active'")["c"]
        total_enquiries = q1(conn, "SELECT COUNT(*) as c FROM enquiries")["c"]
        total_deals     = q1(conn, "SELECT COUNT(*) as c FROM deals")["c"]
        return jsonify({"listings": total_vehicles + total_enquiries + total_deals})
    finally:
        conn.close()    
@app.route("/loan-enquiry", methods=["POST"])
def loan_enquiry():
    name      = request.form.get("name","").strip()
    phone     = request.form.get("phone","").strip()
    email     = request.form.get("email","").strip()
    vtype     = request.form.get("vehicle_type","").strip()
    condition = request.form.get("vehicle_condition","").strip()
    amount    = request.form.get("loan_amount","").strip()
    location  = request.form.get("location","").strip()
    if not name or not phone:
        return jsonify({"ok": False, "error": "Name and phone required"}), 400
    conn2 = get_db()
    try:
        ex(conn2, """INSERT INTO loan_enquiries
         (name,phone,email,vtype,vehicle_cond,amount,location)
         VALUES(%s,%s,%s,%s,%s,%s,%s)""",
         (name,phone,email,vtype,condition,amount,location))
        conn2.commit()
    except Exception as e:
        app.logger.error(f"Loan save failed: {e}")
    finally:
     conn2.close()

    admin_html = f"""
    <h2 style="color:#f97316">New Loan Enquiry – TrucksDeal</h2>
    <table border="1" cellpadding="8" style="border-collapse:collapse;width:100%">
      <tr><td><b>Name</b></td><td>{name}</td></tr>
      <tr><td><b>Phone</b></td><td>{phone}</td></tr>
      <tr><td><b>Email</b></td><td>{email or 'N/A'}</td></tr>
      <tr><td><b>Vehicle Type</b></td><td>{vtype or 'N/A'}</td></tr>
      <tr><td><b>New / Old</b></td><td>{condition or 'N/A'}</td></tr>
      <tr><td><b>Loan Amount</b></td><td>₹{amount or 'N/A'} Lakh</td></tr>
      <tr><td><b>Location</b></td><td>{location or 'N/A'}</td></tr>
      <tr><td><b>Time</b></td><td>{datetime.now().strftime('%d %b %Y %H:%M')}</td></tr>
    </table>
    """

    user_html = f"""
    <h2 style="color:#f97316">Loan Enquiry Received – TrucksDeal</h2>
    <p>Dear {name},</p>
    <p>Thank you for applying for a vehicle loan on TrucksDeal.</p>
    <p>Our finance team will call you on <b>{phone}</b> within 2 hours on working days.</p>
    <table border="1" cellpadding="8" style="border-collapse:collapse;width:100%">
      <tr><td><b>Vehicle Type</b></td><td>{vtype or 'N/A'}</td></tr>
      <tr><td><b>New / Old</b></td><td>{condition or 'N/A'}</td></tr>
      <tr><td><b>Loan Amount</b></td><td>₹{amount or 'N/A'} Lakh</td></tr>
      <tr><td><b>Location</b></td><td>{location or 'N/A'}</td></tr>
    </table>
    <p style="margin-top:1rem">Regards,<br><b>TrucksDeal Finance Team</b><br>📞 +91 99537 34477</p>
    """
    try:
        send_email(f"New Loan Enquiry – {name} – {phone}", admin_html)
        if email:
            send_email("Loan Enquiry Received – TrucksDeal", user_html, to=email)
    except Exception as e:
        app.logger.error(f"Loan email failed: {e}")
    return jsonify({"ok": True}) 

@app.route("/signup", methods=["GET","POST"])
def signup():
    if session.get("user") or session.get("admin"):
        return redirect(url_for("index"))
    if request.method == "POST":
        name     = request.form.get("name","").strip()
        email    = request.form.get("email","").strip()
        phone    = request.form.get("phone","").strip()
        password = request.form.get("password","")
        confirm  = request.form.get("confirm","")
        if not name or not email or not password:
            flash("All fields required.", "error")
            return render_template("signup.html")
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("signup.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("signup.html")
        conn = get_db()
        try:
            existing = q1(conn, "SELECT id FROM users WHERE email=%s", (email,))
            if existing:
                flash("Email already registered. Please login.", "error")
                return render_template("signup.html")
            ex(conn, "INSERT INTO users(name,email,phone,password) VALUES(%s,%s,%s,%s)",
               (name, email, phone, generate_password_hash(password)))
            conn.commit()
            session["user"] = {"email": email, "name": name}
            flash(f"Welcome {name}! You are now logged in.", "success")
            return redirect(url_for("index"))
        finally:
            conn.close()
    return render_template("signup.html")


@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email","").strip()
        password = request.form.get("password","")
        conn = get_db()
        try:
            # Check admin by username
            admin = q1(conn, "SELECT * FROM admins WHERE username=%s", (email,))
            if admin and check_password_hash(admin["password"], password):
                session.clear()
                session["admin"] = admin["username"]
                return redirect(url_for("admin_dashboard"))
            # Check user by email
            user = q1(conn, "SELECT * FROM users WHERE email=%s", (email,))
            if user and check_password_hash(user["password"], password):
                session.clear()
                session["user"] = {"email": str(user["email"]), "name": str(user["name"])}
                flash(f"Welcome back {user['name']}!", "success")
                return redirect(url_for("index"))
            flash("Invalid email or password.", "error")
            return render_template("login.html")
        except Exception as e:
            app.logger.error(f"Login error: {e}")
            flash(f"Error: {str(e)}", "error")
            return render_template("login.html")
        finally:
            conn.close()
    return render_template("login.html")
@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("admin", None)
    return redirect(url_for("index")) 
@app.route("/admin/sell-requests")
@admin_required
def admin_sell_requests():
    conn = get_db()
    try:
        rows = q(conn, "SELECT * FROM sell_requests ORDER BY created_at DESC")
        return render_template("admin_sell_requests.html", rows=rows)
    finally:
        conn.close()  
@app.route("/cloudinary-sign", methods=["POST"])
def cloudinary_sign():
    import hashlib, time
    timestamp = int(time.time())
    params = f"folder=trucksdeal&timestamp={timestamp}{os.environ.get('CLOUDINARY_API_SECRET','')}"
    signature = hashlib.sha1(params.encode()).hexdigest()
    return jsonify({
        "signature":  signature,
        "timestamp":  timestamp,
        "cloud_name": os.environ.get("CLOUDINARY_CLOUD_NAME",""),
        "api_key":    os.environ.get("CLOUDINARY_API_KEY",""),
    })
if __name__ == "__main__":
    app.run(debug=True)
