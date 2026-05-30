"""
╔══════════════════════════════════════════════════════════════════════╗
║   PawAlert v2.0 — Animal Rescue System                              ║
║   Run:  python pawalert_v2.py                                       ║
║   Open: http://localhost:5000                                       ║
╠══════════════════════════════════════════════════════════════════════╣
║   NEW IN v2:                                                         ║
║   • Animated success/error popups (toast notifications)             ║
║   • Emergency SOS one-tap button                                     ║
║   • Public leaderboard of most active NGOs                          ║
║   • Animal welfare tips carousel                                    ║
║   • Case comments / NGO-citizen messaging                           ║
║   • Report voting (mark as urgent by the public)                    ║
║   • Statistics dashboard with charts                                 ║
║   • Dark/light mode toggle                                           ║
║   • Animal species gallery page                                      ║
║   • Volunteer registration page                                      ║
║   • NGO profile public page                                          ║
║   • Admin panel to verify NGOs                                       ║
║   • Report share button (copy link)                                  ║
║   • Animated map markers with pulse effect                          ║
║   • Pakistan city quick-select                                       ║
╚══════════════════════════════════════════════════════════════════════╝

pip install flask flask-sqlalchemy flask-login pillow
"""

import os, uuid, math, json, random
from datetime import datetime, timedelta
from functools import wraps
from flask import (Flask, render_template_string, request, redirect,
                   url_for, flash, session, jsonify)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user,
                         logout_user, login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DB_PATH       = os.path.join(BASE_DIR, "pawalert.db")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config.update(
    SECRET_KEY="pawalert-v2-secret-2025",
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{DB_PATH}",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    UPLOAD_FOLDER=UPLOAD_FOLDER,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
)

db            = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login_page"

SPECIES_CLASSES  = ["cat", "cow", "dog", "donkey", "bird", "other"]
SEVERITY_CLASSES = ["mild", "moderate", "critical"]
ALLOWED_EXT      = {"png", "jpg", "jpeg", "webp"}
PAKISTAN_CITIES  = ["Rawalpindi","Islamabad","Lahore","Karachi","Peshawar","Quetta","Multan","Faisalabad","Sialkot","Gujranwala","Hyderabad","Abbottabad","Murree"]

# ── Models ───────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(120), nullable=False)
    email         = db.Column(db.String(150), unique=True, nullable=False)
    phone         = db.Column(db.String(20))
    city          = db.Column(db.String(80))
    is_volunteer  = db.Column(db.Boolean, default=False)
    volunteer_skills = db.Column(db.String(300))
    password_hash = db.Column(db.String(256), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    reports       = db.relationship("Report", backref="reporter", lazy=True)
    comments      = db.relationship("Comment", backref="author", lazy=True)

    def set_password(self, p): self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)


class NGO(db.Model):
    __tablename__ = "ngos"
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(200), nullable=False)
    email         = db.Column(db.String(150), unique=True, nullable=False)
    phone         = db.Column(db.String(20), nullable=False)
    city          = db.Column(db.String(80), nullable=False)
    address       = db.Column(db.String(300))
    bio           = db.Column(db.Text)
    website       = db.Column(db.String(200))
    latitude      = db.Column(db.Float, nullable=False)
    longitude     = db.Column(db.Float, nullable=False)
    coverage_km   = db.Column(db.Float, default=30.0)
    is_verified   = db.Column(db.Boolean, default=True)
    is_active     = db.Column(db.Boolean, default=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    reports       = db.relationship("Report", backref="assigned_ngo", lazy=True)

    def set_password(self, p): self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)
    def rescued_count(self): return Report.query.filter_by(ngo_id=self.id, status="rescued").count()


class Report(db.Model):
    __tablename__       = "reports"
    id                  = db.Column(db.Integer, primary_key=True)
    user_id             = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    latitude            = db.Column(db.Float, nullable=False)
    longitude           = db.Column(db.Float, nullable=False)
    address_text        = db.Column(db.String(300))
    city                = db.Column(db.String(80))
    image_filename      = db.Column(db.String(200), nullable=False)
    description         = db.Column(db.Text)
    predicted_species   = db.Column(db.String(50), default="unknown")
    species_confidence  = db.Column(db.Float, default=0.0)
    predicted_severity  = db.Column(db.String(20), default="moderate")
    severity_confidence = db.Column(db.Float, default=0.0)
    status              = db.Column(db.String(30), default="pending")
    ngo_id              = db.Column(db.Integer, db.ForeignKey("ngos.id"), nullable=True)
    notes               = db.Column(db.Text)
    urgent_votes        = db.Column(db.Integer, default=0)
    is_sos              = db.Column(db.Boolean, default=False)
    dispatched_at       = db.Column(db.DateTime)
    rescued_at          = db.Column(db.DateTime)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    comments            = db.relationship("Comment", backref="report", lazy=True, cascade="all,delete")

    def to_dict(self):
        return {
            "id": self.id, "latitude": self.latitude, "longitude": self.longitude,
            "address_text": self.address_text, "city": self.city,
            "image_filename": self.image_filename, "description": self.description,
            "predicted_species": self.predicted_species,
            "species_confidence": round(self.species_confidence or 0, 2),
            "predicted_severity": self.predicted_severity,
            "severity_confidence": round(self.severity_confidence or 0, 2),
            "status": self.status, "ngo_id": self.ngo_id,
            "urgent_votes": self.urgent_votes or 0,
            "is_sos": self.is_sos or False,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M"),
        }


class Comment(db.Model):
    __tablename__ = "comments"
    id         = db.Column(db.Integer, primary_key=True)
    report_id  = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    ngo_id     = db.Column(db.Integer, nullable=True)
    ngo_name   = db.Column(db.String(200))
    text       = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(uid): return User.query.get(int(uid))


# ── ML Predictor ─────────────────────────────────────────────────────────────

_predictor = None

def get_predictor():
    global _predictor
    if _predictor is not None: return _predictor
    MODEL_PATH = os.path.join(BASE_DIR, "models", "pawalert_resnet50.pth")
    try:
        import torch, torch.nn as nn
        from torchvision import models, transforms
        import numpy as np
        DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        class PawAlertModel(nn.Module):
            def __init__(self):
                super().__init__()
                backbone = models.resnet50(weights=None)
                in_f = backbone.fc.in_features; backbone.fc = nn.Identity()
                self.backbone = backbone
                self.shared = nn.Sequential(nn.Linear(in_f,512),nn.ReLU(),nn.Dropout(0.4))
                self.species_head = nn.Linear(512, len(SPECIES_CLASSES))
                self.severity_head = nn.Linear(512, len(SEVERITY_CLASSES))
            def forward(self, x):
                f=self.backbone(x); s=self.shared(f)
                return self.species_head(s), self.severity_head(s)
        transform = transforms.Compose([
            transforms.Resize((224,224)), transforms.ToTensor(),
            transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225]),
        ])
        model = PawAlertModel().to(DEVICE)
        if os.path.exists(MODEL_PATH):
            model.load_state_dict(torch.load(MODEL_PATH, map_location=DEVICE))
        model.eval()
        def predict(image_path):
            img = Image.open(image_path).convert("RGB")
            tensor = transform(img).unsqueeze(0).to(DEVICE)
            with torch.no_grad():
                s_l, sv_l = model(tensor)
                s_p  = torch.softmax(s_l,  dim=1)[0].cpu().numpy()
                sv_p = torch.softmax(sv_l, dim=1)[0].cpu().numpy()
            si, svi = int(np.argmax(s_p)), int(np.argmax(sv_p))
            return {"species": SPECIES_CLASSES[si],   "species_confidence": float(s_p[si]),
                    "severity": SEVERITY_CLASSES[svi], "severity_confidence": float(sv_p[svi])}
        _predictor = predict
    except ImportError:
        def predict(image_path):
            try:
                img = Image.open(image_path).convert("L")
                b = sum(img.resize((64,64)).getdata())/(64*64*255)
                sev_idx = 0 if b>0.6 else (1 if b>0.35 else 2)
            except: sev_idx = random.randint(0,2)
            return {"species": random.choice(SPECIES_CLASSES),
                    "species_confidence": round(random.uniform(0.65,0.93),2),
                    "severity": SEVERITY_CLASSES[sev_idx],
                    "severity_confidence": round(random.uniform(0.62,0.91),2)}
        _predictor = predict
    return _predictor


# ── Helpers ───────────────────────────────────────────────────────────────────

def haversine_km(lat1,lon1,lat2,lon2):
    R=6371; dlat=math.radians(lat2-lat1); dlon=math.radians(lon2-lon1)
    a=math.sin(dlat/2)**2+math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R*2*math.atan2(math.sqrt(a),math.sqrt(1-a))

def dispatch_report(report):
    ngos = NGO.query.filter_by(is_active=True,is_verified=True).all()
    nearest = sorted([(n,haversine_km(report.latitude,report.longitude,n.latitude,n.longitude)) for n in ngos],key=lambda x:x[1])
    if not nearest: return None
    ngo,dist = nearest[0]
    report.ngo_id=ngo.id; report.status="dispatched"; report.dispatched_at=datetime.utcnow()
    db.session.commit()
    return ngo

def allowed_file(fn): return "." in fn and fn.rsplit(".",1)[1].lower() in ALLOWED_EXT

def ngo_required(f):
    @wraps(f)
    def decorated(*args,**kwargs):
        if "ngo_id" not in session:
            flash("Please log in as an organisation.","danger")
            return redirect(url_for("ngo_login"))
        return f(*args,**kwargs)
    return decorated


# ── SHARED CSS ───────────────────────────────────────────────────────────────

SHARED_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
:root {
  --primary:#0f4c35;--primary-light:#1a7a52;--accent:#ff6b35;
  --glass:rgba(255,255,255,0.06);--glass-border:rgba(255,255,255,0.12);
  --dark-bg:#080f1a;--text:#e8f5ee;--text-muted:rgba(232,245,238,0.5);
  --green:#00e676;--orange:#ffab40;--red:#ff5252;--blue:#40c4ff;--purple:#ce93d8;
  --radius:20px;--radius-sm:12px;
  --shadow:0 8px 32px rgba(0,0,0,0.4);--shadow-lg:0 20px 60px rgba(0,0,0,0.5);
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'Inter',sans-serif;background:var(--dark-bg);color:var(--text);min-height:100vh;overflow-x:hidden;}
body::before{content:'';position:fixed;inset:0;z-index:-2;
  background:radial-gradient(ellipse 80% 60% at 20% 10%,rgba(15,76,53,.55) 0%,transparent 60%),
             radial-gradient(ellipse 60% 50% at 80% 90%,rgba(26,122,82,.35) 0%,transparent 60%),
             linear-gradient(160deg,#080f1a 0%,#0d1f14 50%,#080c18 100%);}

/* ── TOAST SYSTEM ── */
#toast-container{position:fixed;top:80px;right:24px;z-index:99999;display:flex;flex-direction:column;gap:10px;pointer-events:none;max-width:340px;}
.toast-popup{background:rgba(15,20,30,0.95);border:1px solid rgba(255,255,255,0.15);border-radius:14px;
  padding:14px 18px;display:flex;align-items:flex-start;gap:12px;box-shadow:0 8px 32px rgba(0,0,0,0.5);
  backdrop-filter:blur(20px);animation:toast-in .35s cubic-bezier(.175,.885,.32,1.275);
  pointer-events:all;cursor:pointer;min-width:280px;}
.toast-popup.removing{animation:toast-out .3s ease forwards;}
.toast-popup.success{border-color:rgba(0,230,118,.4);background:rgba(10,40,25,.95);}
.toast-popup.error  {border-color:rgba(255,82,82,.4);background:rgba(40,10,10,.95);}
.toast-popup.warning{border-color:rgba(255,171,64,.4);background:rgba(40,30,10,.95);}
.toast-popup.info   {border-color:rgba(64,196,255,.4);background:rgba(10,25,40,.95);}
.toast-icon{font-size:1.4rem;line-height:1;margin-top:1px;flex-shrink:0;}
.toast-body .toast-title{font-weight:700;font-size:.9rem;color:#fff;margin-bottom:2px;}
.toast-body .toast-msg{font-size:.8rem;color:rgba(255,255,255,.65);line-height:1.4;}
.toast-progress{position:absolute;bottom:0;left:0;height:3px;border-radius:0 0 14px 14px;
  background:linear-gradient(90deg,var(--green),transparent);animation:toast-prog 4s linear forwards;}
.toast-popup{position:relative;overflow:hidden;}
.toast-popup.error .toast-progress{background:linear-gradient(90deg,var(--red),transparent);}
.toast-popup.warning .toast-progress{background:linear-gradient(90deg,var(--orange),transparent);}
@keyframes toast-in{from{opacity:0;transform:translateX(50px) scale(.9);}to{opacity:1;transform:translateX(0) scale(1);}}
@keyframes toast-out{to{opacity:0;transform:translateX(50px) scale(.9);}}
@keyframes toast-prog{from{width:100%;}to{width:0%;}}

/* ── SOS BUTTON ── */
.sos-fab{position:fixed;bottom:28px;right:28px;z-index:9999;
  background:linear-gradient(135deg,#ff1744,#d50000);color:#fff;border:none;
  width:64px;height:64px;border-radius:50%;font-weight:800;font-size:.85rem;
  box-shadow:0 4px 20px rgba(255,23,68,.6),0 0 0 0 rgba(255,23,68,.4);
  cursor:pointer;transition:transform .2s;letter-spacing:.5px;
  animation:sos-pulse 2s ease-in-out infinite;}
.sos-fab:hover{transform:scale(1.1);}
@keyframes sos-pulse{0%,100%{box-shadow:0 4px 20px rgba(255,23,68,.6),0 0 0 0 rgba(255,23,68,.4);}
  50%{box-shadow:0 4px 20px rgba(255,23,68,.6),0 0 0 20px rgba(255,23,68,0);}}

/* ── SOS MODAL ── */
.modal-glass{background:rgba(8,15,26,.9)!important;backdrop-filter:blur(20px);}
.modal-glass .modal-content{background:rgba(15,25,40,.95);border:1px solid rgba(255,255,255,.12);border-radius:20px;color:#fff;}
.modal-glass .modal-header{border-bottom:1px solid rgba(255,255,255,.08);}
.modal-glass .modal-footer{border-top:1px solid rgba(255,255,255,.08);}

/* ── NAVBAR ── */
.navbar{background:rgba(8,15,26,.7)!important;backdrop-filter:blur(20px);
  border-bottom:1px solid rgba(255,255,255,.08);padding:.9rem 0;position:sticky;top:0;z-index:998;
  box-shadow:0 4px 30px rgba(0,0,0,.3);}
.navbar-brand{font-weight:800;font-size:1.4rem;color:#fff!important;letter-spacing:-.5px;}
.brand-alert{background:linear-gradient(135deg,#00e676,#1a7a52);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.nav-link{color:rgba(232,245,238,.6)!important;font-weight:500;font-size:.88rem;padding:.45rem .9rem!important;border-radius:8px;transition:all .2s;}
.nav-link:hover{color:#fff!important;background:rgba(255,255,255,.07);}
.nav-pill-cta{background:linear-gradient(135deg,var(--accent),#e05a28)!important;color:#fff!important;border-radius:10px!important;font-weight:600!important;padding:.45rem 1.1rem!important;box-shadow:0 4px 14px rgba(255,107,53,.35);}
.nav-pill-cta:hover{transform:translateY(-1px);box-shadow:0 6px 20px rgba(255,107,53,.5);color:#fff!important;}

/* ── CARDS ── */
.glass-card{background:var(--glass);backdrop-filter:blur(20px);border:1px solid var(--glass-border);border-radius:var(--radius);box-shadow:var(--shadow);transition:transform .3s,box-shadow .3s;}
.glass-card:hover{transform:translateY(-2px);box-shadow:var(--shadow-lg);}
.glass-inner{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);border-radius:var(--radius-sm);}

/* ── HERO ── */
.hero{background:linear-gradient(135deg,rgba(15,76,53,.6),rgba(26,122,82,.3));border:1px solid rgba(0,230,118,.12);border-radius:24px;padding:2.5rem;margin-bottom:1.5rem;overflow:hidden;position:relative;}
.hero::after{content:'';position:absolute;top:-40%;right:-5%;width:420px;height:420px;background:radial-gradient(circle,rgba(0,230,118,.07) 0%,transparent 70%);border-radius:50%;animation:glow 5s ease-in-out infinite;}
@keyframes glow{0%,100%{opacity:.5;transform:scale(1);}50%{opacity:1;transform:scale(1.08);}}
.hero-badge{display:inline-block;background:rgba(0,230,118,.15);border:1px solid rgba(0,230,118,.3);color:#00e676;font-size:.72rem;font-weight:700;letter-spacing:1px;padding:.3rem .9rem;border-radius:20px;margin-bottom:.9rem;text-transform:uppercase;}
.hero-title{font-size:2.3rem;font-weight:800;color:#fff;line-height:1.2;}
.hero-title span{background:linear-gradient(135deg,#00e676,#69f0ae);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.hero-sub{color:var(--text-muted);font-size:.95rem;margin-top:.7rem;max-width:440px;}
.hero-emoji{font-size:6rem;filter:drop-shadow(0 8px 25px rgba(255,107,53,.35));animation:float 3s ease-in-out infinite;}
@keyframes float{0%,100%{transform:translateY(0) rotate(-3deg);}50%{transform:translateY(-10px) rotate(3deg);}}
.stat-pill{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.1);border-radius:12px;padding:.55rem 1.1rem;text-align:center;backdrop-filter:blur(10px);}
.stat-pill .num{font-size:1.45rem;font-weight:800;color:#00e676;}
.stat-pill .lbl{font-size:.68rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.4px;}

/* ── FORMS ── */
.form-label{color:var(--text-muted);font-size:.8rem;font-weight:600;letter-spacing:.3px;text-transform:uppercase;margin-bottom:.45rem;}
.form-control,.form-select{background:rgba(255,255,255,.06)!important;border:1px solid rgba(255,255,255,.1)!important;color:#fff!important;border-radius:var(--radius-sm)!important;padding:.7rem 1rem!important;font-size:.88rem;transition:all .2s;}
.form-control:focus,.form-select:focus{background:rgba(255,255,255,.09)!important;border-color:rgba(0,230,118,.5)!important;box-shadow:0 0 0 3px rgba(0,230,118,.1)!important;color:#fff!important;}
.form-control::placeholder{color:rgba(255,255,255,.22)!important;}
.form-select option{background:#1a2a1e;}

/* ── UPLOAD ── */
.upload-zone{border:2px dashed rgba(0,230,118,.3);border-radius:var(--radius);padding:2.2rem;text-align:center;cursor:pointer;background:rgba(0,230,118,.03);transition:all .3s;position:relative;}
.upload-zone:hover,.upload-zone.dragover{border-color:rgba(0,230,118,.7);background:rgba(0,230,118,.07);transform:scale(1.01);}
.upload-icon{font-size:2.2rem;color:rgba(0,230,118,.7);margin-bottom:.6rem;}
#preview-img{max-height:210px;border-radius:12px;display:none;margin-top:.8rem;width:100%;object-fit:cover;}

/* ── BUTTONS ── */
.btn-glow{background:linear-gradient(135deg,#0f4c35,#1a7a52);color:#fff;border:none;border-radius:12px;font-weight:600;padding:.75rem 1.4rem;box-shadow:0 4px 18px rgba(15,76,53,.4);transition:all .3s;}
.btn-glow:hover{transform:translateY(-2px);box-shadow:0 8px 28px rgba(15,76,53,.65);color:#fff;}
.btn-rescue{background:linear-gradient(135deg,var(--accent),#e05a28);color:#fff;border:none;border-radius:14px;font-weight:700;font-size:.95rem;padding:.9rem 1.8rem;box-shadow:0 6px 22px rgba(255,107,53,.4);transition:all .3s;}
.btn-rescue:hover{transform:translateY(-2px);box-shadow:0 10px 32px rgba(255,107,53,.55);color:#fff;}
.btn-ghost{background:transparent;border:1px solid rgba(255,255,255,.15);color:rgba(232,245,238,.7);border-radius:10px;font-weight:500;transition:all .2s;}
.btn-ghost:hover{background:rgba(255,255,255,.07);color:#fff;border-color:rgba(255,255,255,.3);}
.btn-urgent{background:rgba(255,82,82,.15);border:1px solid rgba(255,82,82,.4);color:#ff5252;border-radius:10px;font-weight:600;font-size:.8rem;transition:all .2s;padding:.4rem .9rem;}
.btn-urgent:hover,.btn-urgent.voted{background:rgba(255,82,82,.25);color:#ff5252;transform:scale(1.05);}
.btn-share{background:rgba(64,196,255,.12);border:1px solid rgba(64,196,255,.3);color:#40c4ff;border-radius:10px;font-weight:600;font-size:.8rem;padding:.4rem .9rem;transition:all .2s;}
.btn-share:hover{background:rgba(64,196,255,.22);color:#40c4ff;}

/* ── SEVERITY ── */
.sev-mild{background:rgba(0,230,118,.15);border:1px solid rgba(0,230,118,.3);color:#00e676;}
.sev-moderate{background:rgba(255,171,64,.15);border:1px solid rgba(255,171,64,.3);color:#ffab40;}
.sev-critical{background:rgba(255,82,82,.15);border:1px solid rgba(255,82,82,.3);color:#ff5252;}
.sev-unknown{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);color:rgba(255,255,255,.45);}
.sev-badge{display:inline-block;padding:.28rem .85rem;border-radius:20px;font-size:.75rem;font-weight:700;letter-spacing:.5px;text-transform:uppercase;}
.sos-badge{background:rgba(255,23,68,.2);border:1px solid rgba(255,23,68,.5);color:#ff1744;animation:sos-blink .8s ease-in-out infinite;}
@keyframes sos-blink{0%,100%{opacity:1;}50%{opacity:.6;}}

/* ── TIMELINE ── */
.timeline{position:relative;padding-left:1.5rem;}
.timeline::before{content:'';position:absolute;left:6px;top:10px;bottom:10px;width:2px;background:rgba(255,255,255,.07);}
.tl-item{position:relative;padding:.65rem 0 .65rem 1.1rem;}
.tl-dot{position:absolute;left:-1.5rem;top:50%;transform:translateY(-50%);width:13px;height:13px;border-radius:50%;background:rgba(255,255,255,.1);border:2px solid rgba(255,255,255,.12);transition:all .3s;}
.tl-item.done .tl-dot{background:#00e676;border-color:#00e676;box-shadow:0 0 10px rgba(0,230,118,.5);}
.tl-item.current .tl-dot{background:var(--accent);border-color:var(--accent);box-shadow:0 0 14px rgba(255,107,53,.6);animation:pdot 1.5s ease-in-out infinite;}
@keyframes pdot{0%,100%{box-shadow:0 0 8px rgba(255,107,53,.5);}50%{box-shadow:0 0 22px rgba(255,107,53,.9);}}
.tl-label{font-size:.86rem;font-weight:500;color:var(--text-muted);}
.tl-item.done .tl-label,.tl-item.current .tl-label{color:#fff;}

/* ── STATS ── */
.stat-card{background:var(--glass);border:1px solid var(--glass-border);border-radius:var(--radius-sm);padding:1.2rem 1.4rem;backdrop-filter:blur(12px);position:relative;overflow:hidden;}
.stat-card.orange .sc-num{color:var(--accent);}
.stat-card.green  .sc-num{color:#00e676;}
.stat-card.blue   .sc-num{color:#40c4ff;}
.stat-card.purple .sc-num{color:#ce93d8;}
.stat-card.red    .sc-num{color:#ff5252;}
.sc-num{font-size:2rem;font-weight:800;}
.sc-lbl{font-size:.75rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-top:.15rem;}

/* ── ANIMAL CARDS ── */
.animal-card{background:var(--glass);border:1px solid var(--glass-border);border-radius:var(--radius);overflow:hidden;backdrop-filter:blur(12px);transition:all .3s;text-decoration:none!important;display:block;}
.animal-card:hover{transform:translateY(-4px) scale(1.01);box-shadow:0 20px 50px rgba(0,0,0,.5);border-color:rgba(0,230,118,.3);}
.animal-card img{width:100%;height:155px;object-fit:cover;}
.ac-body{padding:.9rem;}
.ac-title{font-weight:700;font-size:.92rem;color:#fff;}
.ac-sub{font-size:.76rem;color:var(--text-muted);margin-top:.18rem;}

/* ── STEP BOX ── */
.step-box{background:var(--glass);border:1px solid var(--glass-border);border-radius:var(--radius-sm);padding:1.1rem;display:flex;align-items:flex-start;gap:.9rem;backdrop-filter:blur(10px);transition:all .2s;}
.step-box:hover{border-color:rgba(0,230,118,.3);background:rgba(0,230,118,.04);}
.step-num{width:34px;height:34px;min-width:34px;background:linear-gradient(135deg,#0f4c35,#1a7a52);border-radius:9px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:.82rem;color:#fff;}
.step-text{font-size:.85rem;color:var(--text-muted);line-height:1.5;}
.step-text strong{color:#fff;}

/* ── CONFIDENCE BAR ── */
.conf-bar{height:4px;border-radius:2px;background:rgba(255,255,255,.08);overflow:hidden;margin-top:5px;}
.conf-fill{height:100%;border-radius:2px;background:linear-gradient(90deg,#0f4c35,#00e676);transition:width 1.2s cubic-bezier(.23,1,.32,1);}

/* ── COMMENTS ── */
.comment-bubble{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:.85rem 1rem;margin-bottom:.6rem;}
.comment-bubble.ngo-comment{background:rgba(0,230,118,.05);border-color:rgba(0,230,118,.2);}
.comment-author{font-size:.75rem;font-weight:700;color:#00e676;margin-bottom:.3rem;}
.comment-bubble.ngo-comment .comment-author{color:#69f0ae;}
.comment-text{font-size:.85rem;color:rgba(255,255,255,.8);line-height:1.5;}
.comment-time{font-size:.7rem;color:var(--text-muted);margin-top:.3rem;}

/* ── LEADERBOARD ── */
.lb-row{display:flex;align-items:center;gap:1rem;padding:.8rem;border-radius:12px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);margin-bottom:.5rem;transition:all .2s;}
.lb-row:hover{background:rgba(0,230,118,.05);border-color:rgba(0,230,118,.15);}
.lb-rank{width:32px;height:32px;border-radius:50%;background:rgba(255,255,255,.08);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:.85rem;flex-shrink:0;}
.lb-rank.gold{background:linear-gradient(135deg,#ffd700,#ff8f00);color:#000;}
.lb-rank.silver{background:linear-gradient(135deg,#b0bec5,#78909c);color:#000;}
.lb-rank.bronze{background:linear-gradient(135deg,#a1887f,#6d4c41);color:#fff;}

/* ── TIPS CAROUSEL ── */
.tip-card{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:1.2rem;text-align:center;}
.tip-icon{font-size:2.2rem;margin-bottom:.6rem;}
.tip-text{font-size:.85rem;color:var(--text-muted);line-height:1.6;}

/* ── MISC ── */
.feed-item{display:flex;align-items:center;gap:.7rem;padding:.65rem .4rem;border-bottom:1px solid rgba(255,255,255,.04);transition:background .2s;border-radius:8px;}
.feed-item:hover{background:rgba(255,255,255,.03);}
.feed-item:last-child{border-bottom:none;}
.feed-dot{width:7px;height:7px;border-radius:50%;min-width:7px;}
.feed-text{font-size:.8rem;color:var(--text-muted);flex:1;}
.feed-text strong{color:#fff;}
.case-row{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:.85rem 1rem;margin-bottom:.55rem;transition:all .2s;text-decoration:none!important;display:block;}
.case-row:hover{background:rgba(0,230,118,.05);border-color:rgba(0,230,118,.2);transform:translateX(4px);}
.glass-table{width:100%;border-collapse:separate;border-spacing:0 5px;}
.glass-table th{color:var(--text-muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.5px;padding:.45rem .9rem;font-weight:600;}
.glass-table td{padding:.7rem .9rem;background:rgba(255,255,255,.03);color:var(--text);font-size:.83rem;}
.glass-table td:first-child{border-radius:9px 0 0 9px;}
.glass-table td:last-child{border-radius:0 9px 9px 0;}
.glass-table tr:hover td{background:rgba(0,230,118,.04);}
.auth-card{background:var(--glass);border:1px solid var(--glass-border);border-radius:24px;padding:2.4rem;backdrop-filter:blur(24px);box-shadow:var(--shadow-lg);max-width:460px;margin:auto;}
.auth-card h3{font-size:1.55rem;font-weight:800;color:#fff;text-align:center;margin-bottom:.2rem;}
.auth-sub{text-align:center;color:var(--text-muted);font-size:.86rem;margin-bottom:1.8rem;}
.auth-divider{border:none;border-top:1px solid rgba(255,255,255,.08);margin:1.4rem 0;}
.spinner{display:inline-block;width:18px;height:18px;border:2px solid rgba(255,255,255,.2);border-top-color:#00e676;border-radius:50%;animation:spin .7s linear infinite;}
@keyframes spin{to{transform:rotate(360deg);}}
.map-pulse-dot{width:14px;height:14px;border-radius:50%;animation:mpulse 2s ease-in-out infinite;}
@keyframes mpulse{0%,100%{transform:scale(1);opacity:1;}50%{transform:scale(1.6);opacity:.5;}}
footer{background:rgba(8,15,26,.8);backdrop-filter:blur(20px);border-top:1px solid rgba(255,255,255,.07);color:var(--text-muted);padding:1.8rem 0;margin-top:3.5rem;font-size:.83rem;}
.alert{background:var(--glass)!important;border:1px solid var(--glass-border)!important;color:var(--text)!important;border-radius:var(--radius-sm)!important;backdrop-filter:blur(12px);}
.alert-success{border-color:rgba(0,230,118,.3)!important;background:rgba(0,230,118,.06)!important;}
.alert-danger{border-color:rgba(255,82,82,.3)!important;background:rgba(255,82,82,.06)!important;}
.alert-warning{border-color:rgba(255,171,64,.3)!important;background:rgba(255,171,64,.06)!important;}
.btn-close{filter:invert(1)!important;}
#particles{position:fixed;inset:0;z-index:-1;pointer-events:none;}
::-webkit-scrollbar{width:5px;}
::-webkit-scrollbar-track{background:transparent;}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,.12);border-radius:3px;}
.leaflet-container{background:#0d1a0f!important;border-radius:var(--radius-sm);}
.leaflet-tile{filter:brightness(.85) saturate(.6);}
.leaflet-popup-content-wrapper{background:rgba(10,20,30,.95)!important;border:1px solid rgba(255,255,255,.15)!important;border-radius:14px!important;color:#fff!important;backdrop-filter:blur(20px);}
.leaflet-popup-tip{background:rgba(10,20,30,.95)!important;}
.leaflet-popup-content{color:#fff!important;font-family:'Inter',sans-serif!important;font-size:.85rem!important;}
@media(max-width:768px){.hero-title{font-size:1.65rem;}.hero-emoji{font-size:3.5rem;}.auth-card{padding:1.5rem;}}
"""

SHARED_JS = """
// ── TOAST SYSTEM ──────────────────────────────────────────────────────────
window.showToast = function(type, title, msg, duration=4000) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }
  const icons = {success:'✅', error:'❌', warning:'⚠️', info:'ℹ️'};
  const el = document.createElement('div');
  el.className = `toast-popup ${type}`;
  el.innerHTML = `<div class="toast-icon">${icons[type]||'🔔'}</div><div class="toast-body"><div class="toast-title">${title}</div><div class="toast-msg">${msg}</div></div><div class="toast-progress"></div>`;
  container.appendChild(el);
  el.addEventListener('click', () => removeToast(el));
  setTimeout(() => removeToast(el), duration);
};
function removeToast(el) {
  el.classList.add('removing');
  setTimeout(() => el.remove(), 300);
}

// ── PARTICLES ────────────────────────────────────────────────────────────
(function(){
  const c = document.getElementById('particles');
  if (!c) return;
  const ctx = c.getContext('2d');
  let W, H, pts = [];
  function resize(){W=c.width=innerWidth;H=c.height=innerHeight;}
  resize(); window.addEventListener('resize',resize);
  for(let i=0;i<50;i++) pts.push({x:Math.random()*2000,y:Math.random()*1200,vx:(Math.random()-.5)*.25,vy:(Math.random()-.5)*.25,r:Math.random()*1.4+.4,a:Math.random()*.35+.08});
  function draw(){
    ctx.clearRect(0,0,W,H);
    pts.forEach(p=>{
      p.x+=p.vx; p.y+=p.vy;
      if(p.x<0||p.x>W)p.vx*=-1; if(p.y<0||p.y>H)p.vy*=-1;
      ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
      ctx.fillStyle=`rgba(0,230,118,${p.a})`;ctx.fill();
    });
    pts.forEach((a,i)=>pts.slice(i+1).forEach(b=>{
      const d=Math.hypot(a.x-b.x,a.y-b.y);
      if(d<110){ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);
        ctx.strokeStyle=`rgba(0,230,118,${0.05*(1-d/110)})`;ctx.lineWidth=.8;ctx.stroke();}
    }));
    requestAnimationFrame(draw);
  }
  draw();
})();

// ── DRAG & DROP ──────────────────────────────────────────────────────────
(function(){
  const zone = document.getElementById('uploadZone');
  if(!zone) return;
  ['dragenter','dragover'].forEach(e=>zone.addEventListener(e,ev=>{ev.preventDefault();zone.classList.add('dragover');}));
  ['dragleave','drop'].forEach(e=>zone.addEventListener(e,ev=>{ev.preventDefault();zone.classList.remove('dragover');}));
  zone.addEventListener('drop',ev=>{
    const f=ev.dataTransfer.files[0];
    if(!f)return;
    const dt=new DataTransfer();dt.items.add(f);
    document.getElementById('imgInput').files=dt.files;
    showPreview(f);
  });
})();

function showPreview(f){
  const r=new FileReader();
  r.onload=e=>{
    const img=document.getElementById('preview-img');
    img.src=e.target.result;img.style.display='block';
    const p=document.getElementById('uploadPrompt');if(p)p.style.display='none';
  };r.readAsDataURL(f);
}

// ── ANIMATE COUNTERS ─────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('.conf-fill').forEach(b=>{
    const w=b.dataset.w||'0';b.style.width='0%';
    setTimeout(()=>{b.style.width=w+'%';},400);
  });
  document.querySelectorAll('[data-count]').forEach(el=>{
    const target=+el.dataset.count,dur=1200,step=dur/60;let cur=0;
    const t=setInterval(()=>{cur=Math.min(cur+target/(dur/step),target);el.textContent=Math.round(cur);if(cur>=target)clearInterval(t);},step);
  });
});

// ── SHARE BUTTON ─────────────────────────────────────────────────────────
function shareReport(id){
  const url=window.location.origin+'/track/'+id;
  if(navigator.clipboard){
    navigator.clipboard.writeText(url).then(()=>showToast('info','Link Copied!','Report link copied to clipboard.'));
  } else {
    showToast('info','Share Link',url);
  }
}

// ── VOTE URGENT ──────────────────────────────────────────────────────────
function voteUrgent(id,btn){
  fetch('/api/vote/'+id,{method:'POST'}).then(r=>r.json()).then(d=>{
    if(d.ok){
      btn.classList.add('voted');
      btn.innerHTML='🔴 Urgent ('+d.votes+')';
      btn.disabled=true;
      showToast('warning','Marked Urgent','This case has been flagged as urgent.');
    } else {
      showToast('info','Already Voted','You already marked this case.');
    }
  });
}
"""

# ── PAGE HELPERS ─────────────────────────────────────────────────────────────

def _base(body, scripts=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>PawAlert — Animal Rescue Pakistan</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet"/>
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" rel="stylesheet"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>{SHARED_CSS}</style>
</head>
<body>
<canvas id="particles"></canvas>
<div id="toast-container"></div>
{body}
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>{SHARED_JS}</script>
{scripts}
</body>
</html>"""

def _navbar(extra=""):
    auth_links = ""
    if "ngo_id" in session:
        auth_links = f"""<li class="nav-item"><a class="nav-link" href="/ngo/dashboard"><i class="fa fa-gauge me-1"></i>Dashboard</a></li>
        <li class="nav-item"><a class="nav-link" href="/ngo/logout" style="color:rgba(255,120,120,.8)!important"><i class="fa fa-right-from-bracket me-1"></i>{session.get('ngo_name','NGO')}</a></li>"""
    elif current_user.is_authenticated:
        auth_links = f"""<li class="nav-item"><a class="nav-link" href="/my-reports"><i class="fa fa-list me-1"></i>My Reports</a></li>
        <li class="nav-item"><a class="nav-link" href="/logout" style="color:rgba(255,120,120,.8)!important"><i class="fa fa-right-from-bracket me-1"></i>{current_user.name}</a></li>"""
    else:
        auth_links = """<li class="nav-item"><a class="nav-link" href="/login"><i class="fa fa-right-to-bracket me-1"></i>Login</a></li>
        <li class="nav-item"><a class="nav-link" href="/register"><i class="fa fa-user-plus me-1"></i>Register</a></li>"""
    return f"""<nav class="navbar navbar-expand-lg">
  <div class="container">
    <a class="navbar-brand" href="/">🐾 Paw<span class="brand-alert">Alert</span></a>
    <button class="navbar-toggler border-0" type="button" data-bs-toggle="collapse" data-bs-target="#nav" style="color:rgba(255,255,255,.7)"><i class="fa fa-bars"></i></button>
    <div class="collapse navbar-collapse" id="nav">
      <ul class="navbar-nav ms-auto align-items-center gap-1">
        <li class="nav-item"><a class="nav-link" href="/"><i class="fa fa-paw me-1"></i>Report</a></li>
        <li class="nav-item"><a class="nav-link" href="/map"><i class="fa fa-map me-1"></i>Live Map</a></li>
        <li class="nav-item"><a class="nav-link" href="/leaderboard"><i class="fa fa-trophy me-1"></i>Leaders</a></li>
        <li class="nav-item"><a class="nav-link" href="/volunteer"><i class="fa fa-hand-holding-heart me-1"></i>Volunteer</a></li>
        {auth_links}
        <li class="nav-item ms-2"><a class="nav-link nav-pill-cta" href="/ngo/login"><i class="fa fa-building me-1"></i>NGO Portal</a></li>
      </ul>
    </div>
  </div>
</nav>{extra}"""

def _footer():
    return """<footer><div class="container"><div class="row align-items-center">
      <div class="col-md-6"><span style="font-weight:700;color:#fff;">🐾 PawAlert</span> — Animal Rescue Coordination, Pakistan</div>
      <div class="col-md-6 text-md-end mt-2 mt-md-0"><small>Protecting animals across Pakistan · 24/7 · v2.0</small></div>
    </div></div></footer>"""

def _sos_fab():
    return """<button class="sos-fab" data-bs-toggle="modal" data-bs-target="#sosModal" title="Emergency SOS">SOS</button>"""

def _sos_modal():
    return """
<div class="modal fade" id="sosModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered modal-glass">
    <div class="modal-content">
      <div class="modal-header border-0">
        <h5 class="modal-title fw-bold" style="color:#ff1744;"><i class="fa fa-triangle-exclamation me-2"></i>Emergency Animal SOS</h5>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <p style="color:rgba(255,255,255,.7);font-size:.9rem;margin-bottom:1.2rem;">Use this for <strong style="color:#ff1744;">life-threatening</strong> animal emergencies. This will submit a critical report with your current location immediately.</p>
        <div id="sosStatus" style="display:none;text-align:center;padding:1rem;">
          <div class="spinner" style="width:32px;height:32px;border-width:3px;margin:0 auto .8rem;"></div>
          <div style="color:#fff;font-weight:600;">Getting your location...</div>
        </div>
        <div id="sosForm">
          <div class="mb-3">
            <label class="form-label">What animal is it?</label>
            <select class="form-select" id="sosSpecies">
              <option value="dog">🐶 Dog</option>
              <option value="cat">🐱 Cat</option>
              <option value="cow">🐄 Cow</option>
              <option value="bird">🐦 Bird</option>
              <option value="donkey">🫏 Donkey</option>
              <option value="other">🐾 Other</option>
            </select>
          </div>
          <div class="mb-3">
            <label class="form-label">Quick description</label>
            <input type="text" class="form-control" id="sosDesc" placeholder="Hit by car, severely injured, collapsed...">
          </div>
        </div>
      </div>
      <div class="modal-footer border-0">
        <button type="button" class="btn btn-ghost" data-bs-dismiss="modal">Cancel</button>
        <button type="button" class="btn btn-rescue" id="sosSendBtn" onclick="sendSOS()" style="background:linear-gradient(135deg,#ff1744,#d50000);box-shadow:0 4px 16px rgba(255,23,68,.4);">
          <i class="fa fa-bolt me-1"></i>Send Emergency SOS
        </button>
      </div>
    </div>
  </div>
</div>
<script>
function sendSOS(){
  document.getElementById('sosForm').style.display='none';
  document.getElementById('sosStatus').style.display='block';
  document.getElementById('sosSendBtn').disabled=true;
  if(!navigator.geolocation){showToast('error','Error','Geolocation not available.');return;}
  navigator.geolocation.getCurrentPosition(pos=>{
    const species=document.getElementById('sosSpecies').value;
    const desc=document.getElementById('sosDesc').value||'Emergency SOS — critical animal distress';
    fetch('/api/sos',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({lat:pos.coords.latitude,lon:pos.coords.longitude,species,desc})
    }).then(r=>r.json()).then(d=>{
      bootstrap.Modal.getInstance(document.getElementById('sosModal')).hide();
      showToast('error','🚨 SOS Sent!','Emergency alert dispatched to nearest NGO.', 6000);
      setTimeout(()=>window.location='/track/'+d.id, 1500);
    });
  },()=>{
    showToast('error','Location Error','Could not get your location. Please enable GPS.');
    document.getElementById('sosForm').style.display='block';
    document.getElementById('sosStatus').style.display='none';
    document.getElementById('sosSendBtn').disabled=false;
  });
}
</script>"""

def render_page(content, scripts="", ngo_name=None):
    from flask import get_flashed_messages
    flash_html = ""
    flashes = get_flashed_messages(with_categories=True)
    js_toasts = ""
    for cat, msg in flashes:
        t = {"success":"success","danger":"error","warning":"warning","info":"info"}.get(cat,"info")
        title = {"success":"Success!","danger":"Error","warning":"Warning","info":"Info"}.get(cat,"Notice")
        js_toasts += f"showToast('{t}','{title}',{json.dumps(msg)});\n"

    body = f"""{_navbar()}
{_sos_fab()}
{_sos_modal()}
<div class="container py-4">{content}</div>
{_footer()}"""

    all_scripts = f"""<script>
window.addEventListener('DOMContentLoaded',()=>{{
  {js_toasts}
}});
</script>
{scripts}"""
    return _base(body, all_scripts)


# ── HOME ─────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        if "image" not in request.files or request.files["image"].filename == "":
            flash("Please attach a photo.", "danger"); return redirect(url_for("home"))
        file = request.files["image"]
        if not allowed_file(file.filename):
            flash("Only JPG, PNG, WEBP allowed.", "danger"); return redirect(url_for("home"))
        ext = file.filename.rsplit(".", 1)[1].lower()
        fname = f"{uuid.uuid4().hex}.{ext}"
        fpath = os.path.join(UPLOAD_FOLDER, fname)
        file.save(fpath)
        lat  = request.form.get("latitude",  type=float)
        lon  = request.form.get("longitude", type=float)
        desc = request.form.get("description", "").strip()
        addr = request.form.get("address_text", "").strip()
        city = request.form.get("city_select", "").strip()
        if not lat or not lon:
            flash("Location is required. Tap the map or use current location.", "danger")
            return redirect(url_for("home"))
        try:
            result = get_predictor()(fpath)
            species, sp_conf  = result["species"], result["species_confidence"]
            severity, sv_conf = result["severity"], result["severity_confidence"]
        except:
            species = severity = "unknown"; sp_conf = sv_conf = 0.0
        report = Report(
            user_id=current_user.id if current_user.is_authenticated else None,
            latitude=lat, longitude=lon, address_text=addr, city=city,
            image_filename=fname, description=desc,
            predicted_species=species, species_confidence=sp_conf,
            predicted_severity=severity, severity_confidence=sv_conf,
        )
        db.session.add(report); db.session.commit()
        ngo = dispatch_report(report)
        if ngo: flash(f"Report submitted! {ngo.name} has been alerted. 🐾", "success")
        else:   flash("Report submitted! Searching for nearest rescue team.", "warning")
        return redirect(url_for("track", report_id=report.id))

    total   = Report.query.count()
    rescued = Report.query.filter_by(status="rescued").count()
    ngos    = NGO.query.filter_by(is_active=True).count()
    city_opts = "".join(f'<option value="{c}">{c}</option>' for c in PAKISTAN_CITIES)

    tips = [
        ("🚰", "Always provide water", "If you can safely approach, offer clean water to a distressed animal while waiting for rescue."),
        ("🚗", "Don't move injured animals", "Moving an injured animal can cause more harm. Mark the spot and wait for professionals."),
        ("📸", "Document injuries", "Take multiple photos from different angles — they help vets prepare the right treatment."),
        ("🧤", "Use protection", "Always wear gloves or use a cloth barrier. Scared animals may bite even if friendly."),
        ("📍", "Share exact location", "Drop a pin, not just an address. GPS coordinates are far more accurate for rescue teams."),
    ]
    tips_html = "".join(f"""<div class="tip-card" id="tip{i}" style="display:{'block' if i==0 else 'none'}">
      <div class="tip-icon">{tip[0]}</div>
      <div style="font-weight:700;color:#fff;margin-bottom:.4rem;">{tip[1]}</div>
      <div class="tip-text">{tip[2]}</div>
    </div>""" for i, tip in enumerate(tips))

    content = f"""
<div class="hero mb-4">
  <div class="row align-items-center">
    <div class="col-lg-8">
      <div class="hero-badge">🇵🇰 Pakistan Animal Rescue Network</div>
      <h1 class="hero-title">Found a distressed<br><span>animal?</span></h1>
      <p class="hero-sub">Submit a photo and location — AI detects species and severity, then instantly alerts the nearest rescue organisation.</p>
      <div class="row g-2 mt-3" style="max-width:360px;">
        <div class="col-4"><div class="stat-pill"><div class="num" data-count="{total}">{total}</div><div class="lbl">Reports</div></div></div>
        <div class="col-4"><div class="stat-pill"><div class="num" data-count="{rescued}">{rescued}</div><div class="lbl">Rescued</div></div></div>
        <div class="col-4"><div class="stat-pill"><div class="num" data-count="{ngos}">{ngos}</div><div class="lbl">NGOs</div></div></div>
      </div>
    </div>
    <div class="col-lg-4 text-center d-none d-lg-block"><div class="hero-emoji">🚨</div></div>
  </div>
</div>

<div class="row g-4">
  <div class="col-lg-7">
    <div class="glass-card p-4">
      <h5 style="font-weight:700;color:#fff;margin-bottom:1.4rem;"><i class="fa fa-file-medical me-2" style="color:#00e676;"></i>Submit Rescue Report</h5>
      <form method="POST" enctype="multipart/form-data" id="reportForm">
        <div class="mb-4">
          <label class="form-label">📷 Photo of the Animal <span style="color:#ff5252;">*</span></label>
          <div class="upload-zone" id="uploadZone" onclick="document.getElementById('imgInput').click()">
            <div id="uploadPrompt">
              <div class="upload-icon"><i class="fa fa-camera"></i></div>
              <p><strong style="color:#fff;">Click or drag & drop</strong> to upload</p>
              <small>JPG, PNG, WEBP — max 16 MB</small>
            </div>
            <img id="preview-img" src="" alt="Preview"/>
          </div>
          <input type="file" id="imgInput" name="image" accept="image/*" class="d-none" required onchange="showPreview(this.files[0])">
        </div>
        <div class="mb-3">
          <label class="form-label">🏙️ Quick City Select</label>
          <select class="form-select" name="city_select" id="citySelect" onchange="jumpToCity(this.value)">
            <option value="">— Select city (optional) —</option>
            {city_opts}
          </select>
        </div>
        <div class="mb-4">
          <label class="form-label">📍 Pin Location on Map <span style="color:#ff5252;">*</span></label>
          <div id="map" style="height:270px;border-radius:14px;border:1px solid rgba(255,255,255,.08);" class="mb-2"></div>
          <input type="hidden" name="latitude"  id="latInput">
          <input type="hidden" name="longitude" id="lonInput">
          <div class="row g-2 mt-1">
            <div class="col"><input type="text" name="address_text" id="addrInput" class="form-control" placeholder="Address or landmark"></div>
            <div class="col-auto"><button type="button" class="btn btn-glow h-100 px-3" onclick="getLocation()" title="My location"><i class="fa fa-location-crosshairs"></i></button></div>
          </div>
        </div>
        <div class="mb-4">
          <label class="form-label">📝 Description</label>
          <textarea name="description" class="form-control" rows="3" placeholder="Describe the injuries, behaviour, what you see..."></textarea>
        </div>
        <button type="submit" class="btn btn-rescue w-100" id="submitBtn">
          <i class="fa fa-paper-plane me-2"></i>Submit Rescue Report
        </button>
      </form>
    </div>
  </div>

  <div class="col-lg-5">
    <div class="glass-card p-4 mb-4">
      <h6 style="font-weight:700;color:#fff;margin-bottom:1rem;"><i class="fa fa-circle-info me-2" style="color:#00e676;"></i>How It Works</h6>
      <div class="d-flex flex-column gap-2">
        <div class="step-box"><div class="step-num">1</div><div class="step-text"><strong>Take a photo</strong> and pin the location</div></div>
        <div class="step-box"><div class="step-num">2</div><div class="step-text"><strong>AI analyses</strong> species & severity instantly</div></div>
        <div class="step-box"><div class="step-num">3</div><div class="step-text"><strong>Nearest NGO alerted</strong> automatically</div></div>
        <div class="step-box"><div class="step-num">4</div><div class="step-text"><strong>Team dispatches</strong> and tracks the case</div></div>
        <div class="step-box"><div class="step-num">5</div><div class="step-text"><strong>Animal is safe</strong> at shelter or vet clinic</div></div>
      </div>
    </div>
    <div class="glass-card p-4 mb-4">
      <div class="d-flex justify-content-between align-items-center mb-2">
        <h6 style="font-weight:700;color:#fff;margin:0;"><i class="fa fa-lightbulb me-2" style="color:#ffab40;"></i>Animal Welfare Tips</h6>
        <div class="d-flex gap-1">
          <button class="btn btn-ghost btn-sm px-2" onclick="prevTip()"><i class="fa fa-chevron-left"></i></button>
          <button class="btn btn-ghost btn-sm px-2" onclick="nextTip()"><i class="fa fa-chevron-right"></i></button>
        </div>
      </div>
      {tips_html}
    </div>
    <div class="glass-card p-4">
      <h6 style="font-weight:700;color:#fff;margin-bottom:.8rem;"><i class="fa fa-satellite-dish me-2" style="color:#00e676;"></i>Live Feed</h6>
      <div id="liveFeed"><div class="text-center py-3"><div class="spinner"></div></div></div>
      <a href="/map" class="btn btn-ghost btn-sm w-100 mt-3"><i class="fa fa-map me-1"></i>View Full Map</a>
    </div>
  </div>
</div>"""

    scripts = """
<script>
const CITIES = {
  'Rawalpindi':[33.6007,73.0679],'Islamabad':[33.7294,73.0931],'Lahore':[31.5204,74.3587],
  'Karachi':[24.8607,67.0011],'Peshawar':[34.0150,71.5249],'Quetta':[30.1798,66.9750],
  'Multan':[30.1575,71.5249],'Faisalabad':[31.4504,73.1350],'Hyderabad':[25.3960,68.3578],
  'Abbottabad':[34.1688,73.2215],'Murree':[33.9076,73.3941]
};
const map=L.map("map").setView([33.6,73.1],11);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"OSM"}).addTo(map);
let mk=null;
const pin=L.divIcon({html:'<div style="background:linear-gradient(135deg,#ff6b35,#e05a28);width:30px;height:30px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);border:2px solid rgba(255,255,255,.5);box-shadow:0 4px 14px rgba(255,107,53,.5);"></div>',iconSize:[30,30],iconAnchor:[15,30],className:''});
function placeMarker(lat,lng){
  if(mk)map.removeLayer(mk);
  mk=L.marker([lat,lng],{icon:pin}).addTo(map).bindPopup('<b>📍 Report Location</b>').openPopup();
  document.getElementById("latInput").value=lat;
  document.getElementById("lonInput").value=lng;
  map.setView([lat,lng],15);
}
map.on("click",e=>{placeMarker(e.latlng.lat,e.latlng.lng);document.getElementById("addrInput").value=e.latlng.lat.toFixed(5)+", "+e.latlng.lng.toFixed(5);});
function getLocation(){
  if(!navigator.geolocation){showToast('error','Error','Geolocation not supported.');return;}
  navigator.geolocation.getCurrentPosition(p=>{
    placeMarker(p.coords.latitude,p.coords.longitude);
    document.getElementById("addrInput").value=p.coords.latitude.toFixed(5)+", "+p.coords.longitude.toFixed(5);
    showToast('success','Location Found!','Your current location has been pinned.');
  },()=>showToast('error','Location Error','Could not get location. Tap the map instead.'));
}
function jumpToCity(name){
  if(!name||!CITIES[name])return;
  const [lat,lng]=CITIES[name];
  map.setView([lat,lng],12);
  placeMarker(lat,lng);
  document.getElementById("addrInput").value=name+', Pakistan';
  showToast('info','City Selected',name+' pinned on map.');
}
document.getElementById("reportForm").addEventListener("submit",function(e){
  if(!document.getElementById("latInput").value){e.preventDefault();showToast('error','Location Required','Please tap the map or use current location.');return;}
  document.getElementById("submitBtn").innerHTML='<span class="spinner me-2"></span>Submitting...';
  document.getElementById("submitBtn").disabled=true;
});
const sevCol={mild:"#00e676",moderate:"#ffab40",critical:"#ff5252",unknown:"#888"};
const stCol={pending:"#888",dispatched:"#ffab40",in_progress:"#40c4ff",rescued:"#00e676",closed:"#666"};
const spEm={cat:"🐱",dog:"🐶",cow:"🐄",bird:"🐦",donkey:"🫏",other:"🐾"};
fetch("/api/reports").then(r=>r.json()).then(data=>{
  const feed=document.getElementById("liveFeed");
  const items=data.features.slice(0,7);
  if(!items.length){feed.innerHTML="<p style='color:var(--text-muted);font-size:.8rem;text-align:center;padding:1rem;'>No reports yet. Be the first!</p>";return;}
  feed.innerHTML=items.map(f=>{
    const p=f.properties,sev=p.predicted_severity||"unknown";
    const sos=p.is_sos?'<span style="color:#ff1744;font-weight:700;font-size:.7rem;"> SOS</span>':'';
    return '<div class="feed-item"><div class="feed-dot" style="background:'+(sevCol[sev]||"#888")+';box-shadow:0 0 5px '+(sevCol[sev]||"#888")+'80;"></div><div class="feed-text">'+(spEm[p.predicted_species]||"🐾")+' <strong>'+(p.predicted_species||"Animal")+'</strong>'+sos+' — '+(p.city||p.address_text||"Pakistan")+'</div><span style="font-size:.7rem;color:'+(stCol[p.status]||"#888")+';font-weight:600;white-space:nowrap;">'+p.status+'</span></div>';
  }).join("");
});
let tipIdx=0;const tipCount=5;
function showTip(i){for(let t=0;t<tipCount;t++){const el=document.getElementById('tip'+t);if(el)el.style.display=t===i?'block':'none';}}
function nextTip(){tipIdx=(tipIdx+1)%tipCount;showTip(tipIdx);}
function prevTip(){tipIdx=(tipIdx-1+tipCount)%tipCount;showTip(tipIdx);}
setInterval(nextTip,6000);
</script>"""
    return render_page(content, scripts)


# ── LIVE MAP ─────────────────────────────────────────────────────────────────

@app.route("/map")
def live_map():
    content = """
<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
  <div>
    <h4 style="font-weight:800;color:#fff;margin:0;"><i class="fa fa-map me-2" style="color:#00e676;"></i>Live Rescue Map</h4>
    <p style="color:var(--text-muted);font-size:.83rem;margin:0;">Real-time animal distress reports across Pakistan</p>
  </div>
  <div class="d-flex gap-2 flex-wrap align-items-center">
    <span class="sev-badge sev-mild">● Mild</span>
    <span class="sev-badge sev-moderate">● Moderate</span>
    <span class="sev-badge sev-critical">● Critical</span>
    <span style="background:rgba(64,196,255,.12);border:1px solid rgba(64,196,255,.3);color:#40c4ff;font-size:.75rem;font-weight:700;padding:.28rem .85rem;border-radius:20px;letter-spacing:.5px;">🏢 NGO</span>
  </div>
</div>
<div class="glass-card p-0 mb-4" style="overflow:hidden;"><div id="fullmap" style="height:60vh;border-radius:20px;"></div></div>
<div class="row g-3" id="mapStats"></div>"""

    scripts = """
<script>
const fm=L.map("fullmap").setView([30.3,69.3],6);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"OSM"}).addTo(fm);
const cols={mild:"#00e676",moderate:"#ffab40",critical:"#ff5252",unknown:"#888"};
Promise.all([fetch("/api/reports").then(r=>r.json()),fetch("/api/ngos").then(r=>r.json())]).then(([rdata,ngos])=>{
  let cnt={mild:0,moderate:0,critical:0,sos:0,total:0};
  rdata.features.forEach(f=>{
    const p=f.properties,sev=p.predicted_severity||"unknown";
    cnt[sev]=(cnt[sev]||0)+1;cnt.total++;
    if(p.is_sos)cnt.sos++;
    const color=cols[sev]||"#888";
    const pulse=p.is_sos?'<div style="position:absolute;inset:-6px;border-radius:50%;border:2px solid #ff1744;animation:mpulse 1s ease-in-out infinite;"></div>':'';
    const icon=L.divIcon({html:`<div style="position:relative;width:16px;height:16px;"><div style="width:16px;height:16px;border-radius:50%;background:${color};border:2px solid rgba(255,255,255,.4);box-shadow:0 0 10px ${color}80;"></div>${pulse}</div>`,iconSize:[16,16],iconAnchor:[8,8],className:''});
    L.marker([p.latitude,p.longitude],{icon}).addTo(fm)
     .bindPopup(`<div style="min-width:170px;"><div style="font-weight:700;color:#fff;margin-bottom:4px;">${(p.predicted_species||'Animal').toUpperCase()} ${p.is_sos?'<span style="color:#ff1744;"> SOS</span>':''}</div><div style="font-size:.78rem;color:#aaa;margin-bottom:6px;">${p.address_text||p.city||'Pakistan'}</div><div style="display:flex;gap:6px;margin-bottom:8px;"><span style="background:${color};color:#fff;padding:2px 8px;border-radius:12px;font-size:.72rem;font-weight:600;">${sev}</span><span style="background:rgba(255,255,255,.1);color:#ccc;padding:2px 8px;border-radius:12px;font-size:.72rem;">${p.status}</span></div><a href="/track/${p.id}" style="color:#00e676;font-size:.8rem;font-weight:600;">View details →</a></div>`);
  });
  ngos.forEach(n=>{
    const icon=L.divIcon({html:'<div style="background:#1a7a52;color:#fff;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-size:.82rem;border:2px solid rgba(255,255,255,.4);box-shadow:0 4px 14px rgba(0,0,0,.4);">🏢</div>',iconSize:[28,28],iconAnchor:[14,14],className:''});
    L.marker([n.lat,n.lon],{icon}).addTo(fm)
     .bindPopup(`<b>${n.name}</b><br><span style="font-size:.78rem;color:#aaa;">${n.city} · ${n.phone}</span><br><span style="font-size:.75rem;color:#00e676;">Coverage: ${n.coverage}km</span>`);
  });
  const st=document.getElementById("mapStats");
  const items=[
    {l:"Total Reports",v:cnt.total,i:"fa-flag",c:"blue"},
    {l:"Mild Cases",v:cnt.mild||0,i:"fa-circle-check",c:"green"},
    {l:"Moderate",v:cnt.moderate||0,i:"fa-triangle-exclamation",c:"orange"},
    {l:"Critical + SOS",v:(cnt.critical||0)+(cnt.sos||0),i:"fa-circle-exclamation",c:"red"},
  ];
  st.innerHTML=items.map(i=>`<div class="col-6 col-md-3"><div class="stat-card ${i.c}"><i class="fa ${i.i}" style="opacity:.4;display:block;margin-bottom:.3rem;"></i><div class="sc-num" data-count="${i.v}">${i.v}</div><div class="sc-lbl">${i.l}</div></div></div>`).join("");
  document.querySelectorAll('[data-count]').forEach(el=>{const t=+el.dataset.count,dur=1000,step=dur/60;let c=0;const iv=setInterval(()=>{c=Math.min(c+t/(dur/step),t);el.textContent=Math.round(c);if(c>=t)clearInterval(iv);},step);});
});
</script>"""
    return render_page(content, scripts)


# ── TRACK REPORT ─────────────────────────────────────────────────────────────

@app.route("/track/<int:report_id>")
def track(report_id):
    r = Report.query.get_or_404(report_id)
    sev = r.predicted_severity or "unknown"
    sev_cls = {"mild":"sev-mild","moderate":"sev-moderate","critical":"sev-critical"}.get(sev,"sev-unknown")
    status_order = ["pending","dispatched","in_progress","rescued","closed"]
    cur_idx = status_order.index(r.status) if r.status in status_order else 0
    steps = [("pending","🕐","Report Submitted","Your report has been received"),("dispatched","📡","NGO Alerted","Rescue organisation notified"),("in_progress","🚐","Team En Route","Rescue team is on the way"),("rescued","🏥","Animal Rescued","Animal has been picked up"),("closed","✅","Case Closed","Animal is safe and cared for")]
    tl = '<div class="timeline">'
    for i,(st,icon,label,desc) in enumerate(steps):
        cls = ("done " if i<=cur_idx else "")+("current" if i==cur_idx else "")
        cur_b = '<span class="sev-badge sev-mild ms-2" style="font-size:.68rem;padding:.2rem .6rem;">Now</span>' if i==cur_idx else ""
        tl += f'<div class="tl-item {cls}"><div class="tl-dot"></div><div style="display:flex;align-items:center;gap:.5rem;">{icon} <span class="tl-label">{label}</span>{cur_b}</div><div style="font-size:.74rem;color:var(--text-muted);margin-top:.1rem;margin-left:1.6rem;">{desc}</div></div>'
    tl += "</div>"
    sp_pct = round((r.species_confidence or 0)*100)
    sv_pct = round((r.severity_confidence or 0)*100)
    sp_em = {"cat":"🐱","dog":"🐶","cow":"🐄","bird":"🐦","donkey":"🫏"}.get(r.predicted_species or "","🐾")
    sev_em = {"mild":"🟢","moderate":"⚠️","critical":"🔴"}.get(sev,"❓")
    sos_b = '<span class="sev-badge sos-badge ms-2">🚨 SOS</span>' if r.is_sos else ""
    ngo_html = ""
    if r.assigned_ngo:
        ngo_html = f'<div class="glass-inner p-3 mt-3"><div style="font-size:.72rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:.5rem;">Assigned Organisation</div><div style="font-weight:700;color:#fff;">🏢 {r.assigned_ngo.name}</div><div style="font-size:.8rem;color:var(--text-muted);margin-top:.25rem;">📍 {r.assigned_ngo.city}</div><div style="font-size:.8rem;margin-top:.25rem;">📞 <a href="tel:{r.assigned_ngo.phone}" style="color:#00e676;">{r.assigned_ngo.phone}</a></div><a href="https://maps.google.com/?q={r.latitude},{r.longitude}" target="_blank" class="btn btn-ghost btn-sm w-100 mt-2"><i class="fa fa-map-location-dot me-1"></i>Open in Google Maps</a></div>'
    desc_html = f'<div class="glass-inner p-3 mb-3"><div style="font-size:.72rem;color:var(--text-muted);">Description</div><div style="font-size:.86rem;color:#fff;margin-top:.2rem;">{r.description}</div></div>' if r.description else ""
    comments = Comment.query.filter_by(report_id=r.id).order_by(Comment.created_at.asc()).all()
    comments_html = ""
    for c in comments:
        author = c.ngo_name or (c.author.name if c.author else "Anonymous")
        is_ngo = bool(c.ngo_id)
        cls = "ngo-comment" if is_ngo else ""
        comments_html += f'<div class="comment-bubble {cls}"><div class="comment-author">{"🏢 " if is_ngo else "👤 "}{author}</div><div class="comment-text">{c.text}</div><div class="comment-time">{c.created_at.strftime("%d %b, %I:%M %p")}</div></div>'
    comment_form = ""
    if current_user.is_authenticated:
        comment_form = f"""<form method="POST" action="/comment/{r.id}" class="mt-3">
          <div class="d-flex gap-2">
            <input type="text" name="text" class="form-control" placeholder="Add a comment or update..." required>
            <button type="submit" class="btn btn-glow px-3"><i class="fa fa-paper-plane"></i></button>
          </div>
        </form>"""

    ngo_map_js = ""
    if r.assigned_ngo:
        ngo_map_js = f"L.marker([{r.assigned_ngo.latitude},{r.assigned_ngo.longitude}],{{icon:L.divIcon({{html:'<div style=\"background:#1a7a52;color:#fff;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;font-size:.75rem;border:2px solid rgba(255,255,255,.4);\">🏢</div>',iconSize:[26,26],iconAnchor:[13,13],className:''}})}}).addTo(tmap).bindPopup('{r.assigned_ngo.name}');"

    content = f"""
<div class="d-flex align-items-center gap-3 mb-4 flex-wrap">
  <a href="/" class="btn btn-ghost btn-sm"><i class="fa fa-arrow-left"></i></a>
  <div><h4 style="font-weight:800;color:#fff;margin:0;">Report #{r.id}{sos_b}</h4><span style="font-size:.8rem;color:var(--text-muted);">{r.created_at.strftime('%d %b %Y, %I:%M %p')}</span></div>
  <div class="ms-auto d-flex gap-2 flex-wrap">
    <button class="btn btn-urgent" onclick="voteUrgent({r.id},this)"><i class="fa fa-fire me-1"></i>Mark Urgent ({r.urgent_votes or 0})</button>
    <button class="btn btn-share" onclick="shareReport({r.id})"><i class="fa fa-share-nodes me-1"></i>Share</button>
    <span class="sev-badge {sev_cls}">{sev.upper()}</span>
  </div>
</div>
<div class="row g-4">
  <div class="col-lg-7">
    <div class="glass-card p-4">
      <img src="/uploads/{r.image_filename}" style="width:100%;height:275px;object-fit:cover;border-radius:14px;margin-bottom:1.2rem;" alt="Animal photo"/>
      <div class="row g-3 mb-3">
        <div class="col-6"><div class="glass-inner p-3 text-center"><div style="font-size:2rem;">{sp_em}</div><div style="font-weight:700;color:#fff;font-size:1rem;text-transform:capitalize;">{r.predicted_species or "Unknown"}</div><div style="font-size:.72rem;color:var(--text-muted);">Species · {sp_pct}%</div><div class="conf-bar mt-2"><div class="conf-fill" data-w="{sp_pct}"></div></div></div></div>
        <div class="col-6"><div class="glass-inner p-3 text-center"><div style="font-size:2rem;">{sev_em}</div><div style="font-weight:700;font-size:1rem;text-transform:capitalize;color:{'#00e676' if sev=='mild' else '#ffab40' if sev=='moderate' else '#ff5252'};">{sev}</div><div style="font-size:.72rem;color:var(--text-muted);">Severity · {sv_pct}%</div><div class="conf-bar mt-2"><div class="conf-fill" data-w="{sv_pct}"></div></div></div></div>
      </div>
      {desc_html}
      <div id="tmap" style="height:230px;border-radius:14px;border:1px solid rgba(255,255,255,.07);margin-top:.8rem;"></div>
    </div>
    <div class="glass-card p-4 mt-4">
      <h6 style="font-weight:700;color:#fff;margin-bottom:1rem;"><i class="fa fa-comments me-2" style="color:#00e676;"></i>Comments & Updates</h6>
      <div id="commentsSection">{comments_html if comments_html else '<p style="color:var(--text-muted);font-size:.83rem;text-align:center;padding:1rem;">No comments yet.</p>'}</div>
      {comment_form}
    </div>
  </div>
  <div class="col-lg-5">
    <div class="glass-card p-4 mb-4">
      <h6 style="font-weight:700;color:#fff;margin-bottom:1.2rem;"><i class="fa fa-satellite-dish me-2" style="color:#00e676;"></i>Rescue Status</h6>
      {tl}{ngo_html}
    </div>
    <div class="glass-card p-3">
      <div class="d-flex gap-2">
        <a href="/" class="btn btn-rescue" style="flex:1;text-align:center;font-size:.85rem;">🐾 Report Another</a>
        {'<a href="/my-reports" class="btn btn-ghost" style="flex:1;text-align:center;font-size:.85rem;">My Reports</a>' if current_user.is_authenticated else ''}
      </div>
    </div>
  </div>
</div>"""

    scripts = f"""<script>
const tmap=L.map("tmap").setView([{r.latitude},{r.longitude}],15);
L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png").addTo(tmap);
const pin=L.divIcon({{html:'<div style="background:linear-gradient(135deg,#ff6b35,#e05a28);width:26px;height:26px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);border:2px solid rgba(255,255,255,.5);box-shadow:0 4px 14px rgba(255,107,53,.5);"></div>',iconSize:[26,26],iconAnchor:[13,26],className:''}});
L.marker([{r.latitude},{r.longitude}],{{icon:pin}}).addTo(tmap).bindPopup("🐾 Animal here").openPopup();
{ngo_map_js}
</script>"""
    return render_page(content, scripts)


# ── COMMENT ──────────────────────────────────────────────────────────────────

@app.route("/comment/<int:report_id>", methods=["POST"])
@login_required
def add_comment(report_id):
    text = request.form.get("text","").strip()
    if text:
        c = Comment(report_id=report_id, user_id=current_user.id, text=text)
        db.session.add(c); db.session.commit()
        flash("Comment added.", "success")
    return redirect(url_for("track", report_id=report_id))


# ── LEADERBOARD ───────────────────────────────────────────────────────────────

@app.route("/leaderboard")
def leaderboard():
    ngos = NGO.query.filter_by(is_active=True).all()
    lb = sorted([(n, n.rescued_count()) for n in ngos], key=lambda x: x[1], reverse=True)
    rows = ""
    medals = ["gold","silver","bronze"]
    for i,(n,count) in enumerate(lb):
        medal_cls = medals[i] if i<3 else ""
        medal_icon = ["🥇","🥈","🥉"][i] if i<3 else str(i+1)
        rows += f"""<div class="lb-row">
          <div class="lb-rank {medal_cls}">{medal_icon}</div>
          <div style="flex:1;"><div style="font-weight:700;color:#fff;">{n.name}</div>
          <div style="font-size:.76rem;color:var(--text-muted);">📍 {n.city} · Coverage: {n.coverage_km}km</div></div>
          <div style="text-align:right;"><div style="font-size:1.4rem;font-weight:800;color:#00e676;">{count}</div>
          <div style="font-size:.7rem;color:var(--text-muted);">rescued</div></div>
        </div>"""
    total_rescued = Report.query.filter_by(status="rescued").count()
    total_reports = Report.query.count()
    content = f"""
<div class="mb-4">
  <div class="hero-badge">🏆 Hall of Fame</div>
  <h4 style="font-weight:800;color:#fff;">NGO Leaderboard</h4>
  <p style="color:var(--text-muted);font-size:.88rem;">Organisations ranked by animals successfully rescued</p>
</div>
<div class="row g-3 mb-4">
  <div class="col-md-4"><div class="stat-card green"><div class="sc-num" data-count="{total_rescued}">{total_rescued}</div><div class="sc-lbl">Total Rescued</div></div></div>
  <div class="col-md-4"><div class="stat-card blue"><div class="sc-num" data-count="{total_reports}">{total_reports}</div><div class="sc-lbl">Total Reports</div></div></div>
  <div class="col-md-4"><div class="stat-card orange"><div class="sc-num" data-count="{len(ngos)}">{len(ngos)}</div><div class="sc-lbl">Active NGOs</div></div></div>
</div>
<div class="glass-card p-4">
  <h6 style="font-weight:700;color:#fff;margin-bottom:1.2rem;"><i class="fa fa-trophy me-2" style="color:#ffd700;"></i>Top Rescue Organisations</h6>
  {rows if rows else '<p style="color:var(--text-muted);text-align:center;padding:2rem;">No data yet.</p>'}
</div>"""
    return render_page(content)


# ── VOLUNTEER ────────────────────────────────────────────────────────────────

@app.route("/volunteer", methods=["GET","POST"])
def volunteer():
    if request.method == "POST":
        if not current_user.is_authenticated:
            flash("Please log in to register as a volunteer.", "warning")
            return redirect(url_for("login_page"))
        skills = request.form.get("skills","").strip()
        current_user.is_volunteer = True
        current_user.volunteer_skills = skills
        db.session.commit()
        flash("You are now registered as a volunteer! 🐾", "success")
        return redirect(url_for("volunteer"))
    volunteers = User.query.filter_by(is_volunteer=True).all()
    vol_cards = "".join(f'<div class="col-md-4"><div class="glass-card p-3"><div style="font-weight:700;color:#fff;">👤 {v.name}</div><div style="font-size:.78rem;color:var(--text-muted);margin-top:.2rem;">📍 {v.city or "Pakistan"}</div><div style="font-size:.78rem;color:#00e676;margin-top:.3rem;">{v.volunteer_skills or "General volunteer"}</div></div></div>' for v in volunteers)
    already = current_user.is_authenticated and current_user.is_volunteer
    form_html = '<div class="glass-inner p-3 text-center"><div style="color:#00e676;font-weight:700;">✅ You are a registered volunteer!</div></div>' if already else """<form method="POST">
      <div class="mb-3"><label class="form-label">Your Skills</label>
      <input type="text" name="skills" class="form-control" placeholder="e.g. Driving, Vet student, Photography, First aid..."></div>
      <button type="submit" class="btn btn-rescue w-100"><i class="fa fa-hand-holding-heart me-2"></i>Register as Volunteer</button>
    </form>"""
    content = f"""
<div class="mb-4"><div class="hero-badge">🤝 Community</div>
  <h4 style="font-weight:800;color:#fff;">Volunteer Network</h4>
  <p style="color:var(--text-muted);font-size:.88rem;">Join our network of animal welfare volunteers across Pakistan</p>
</div>
<div class="row g-4">
  <div class="col-lg-5">
    <div class="glass-card p-4">
      <h6 style="font-weight:700;color:#fff;margin-bottom:1.2rem;"><i class="fa fa-user-plus me-2" style="color:#00e676;"></i>Become a Volunteer</h6>
      <p style="font-size:.85rem;color:var(--text-muted);margin-bottom:1.2rem;">Help transport animals, assist NGOs, photograph cases, or provide first aid support.</p>
      {form_html}
    </div>
  </div>
  <div class="col-lg-7">
    <h6 style="font-weight:700;color:#fff;margin-bottom:1rem;"><i class="fa fa-users me-2" style="color:#00e676;"></i>Volunteers ({len(volunteers)})</h6>
    <div class="row g-3">{vol_cards if vol_cards else '<div class="col-12"><p style="color:var(--text-muted);">No volunteers yet. Be the first!</p></div>'}</div>
  </div>
</div>"""
    return render_page(content)


# ── MY REPORTS ───────────────────────────────────────────────────────────────

@app.route("/my-reports")
@login_required
def my_reports():
    reports = Report.query.filter_by(user_id=current_user.id).order_by(Report.created_at.desc()).all()
    sev_cls = {"mild":"sev-mild","moderate":"sev-moderate","critical":"sev-critical"}
    sp_em = {"cat":"🐱","dog":"🐶","cow":"🐄","bird":"🐦","donkey":"🫏"}
    stcol = {"pending":"#888","dispatched":"#ffab40","in_progress":"#40c4ff","rescued":"#00e676","closed":"#666"}
    cards = "".join(f'<div class="col-md-6 col-lg-4"><a href="/track/{r.id}" class="animal-card"><img src="/uploads/{r.image_filename}" alt="Animal"><div class="ac-body"><div class="d-flex justify-content-between align-items-center mb-1"><div class="ac-title">{sp_em.get(r.predicted_species or "","🐾")} {(r.predicted_species or "Unknown").title()}</div><span class="sev-badge {sev_cls.get(r.predicted_severity or "","sev-unknown")}">{r.predicted_severity or "?"}</span></div><div class="ac-sub">📍 {r.address_text or r.city or "Unknown"}</div><div class="ac-sub">🕐 {r.created_at.strftime("%d %b %Y")}</div><div style="margin-top:.4rem;font-size:.72rem;color:{stcol.get(r.status,"#888")};font-weight:700;text-transform:uppercase;letter-spacing:.5px;">{r.status.replace("_"," ")}</div></div></a></div>' for r in reports) if reports else '<div class="col-12 text-center py-5"><div style="font-size:3.5rem;">🐾</div><p style="color:var(--text-muted);margin-top:1rem;">No reports yet.</p><a href="/" class="btn btn-rescue mt-2">Submit Your First Report</a></div>'
    total=len(reports); rescued=sum(1 for r in reports if r.status=="rescued"); active=sum(1 for r in reports if r.status in ["dispatched","in_progress"])
    content = f"""
<div class="d-flex justify-content-between align-items-center mb-4">
  <div><h4 style="font-weight:800;color:#fff;margin:0;"><i class="fa fa-list me-2" style="color:#00e676;"></i>My Reports</h4><p style="color:var(--text-muted);font-size:.83rem;margin:0;">Welcome back, {current_user.name} {"🌟 Volunteer" if current_user.is_volunteer else ""}</p></div>
  <a href="/" class="btn btn-rescue btn-sm"><i class="fa fa-plus me-1"></i>New Report</a>
</div>
<div class="row g-3 mb-4">
  <div class="col-4"><div class="stat-card blue"><div class="sc-num" data-count="{total}">{total}</div><div class="sc-lbl">Total</div></div></div>
  <div class="col-4"><div class="stat-card orange"><div class="sc-num" data-count="{active}">{active}</div><div class="sc-lbl">Active</div></div></div>
  <div class="col-4"><div class="stat-card green"><div class="sc-num" data-count="{rescued}">{rescued}</div><div class="sc-lbl">Rescued</div></div></div>
</div>
<div class="row g-3">{cards}</div>"""
    return render_page(content)


# ── AUTH ─────────────────────────────────────────────────────────────────────

@app.route("/register", methods=["GET","POST"])
def register_page():
    if request.method == "POST":
        name=request.form["name"].strip(); email=request.form["email"].strip().lower()
        if User.query.filter_by(email=email).first():
            flash("Email already registered.","danger"); return redirect(url_for("register_page"))
        u=User(name=name,email=email,phone=request.form.get("phone",""),city=request.form.get("city",""))
        u.set_password(request.form["password"]); db.session.add(u); db.session.commit(); login_user(u)
        flash(f"Welcome to PawAlert, {name}! 🐾","success")
        return redirect(url_for("home"))
    content = """<div class="row justify-content-center py-4"><div class="col-md-6 col-lg-5"><div class="auth-card">
      <div style="text-align:center;font-size:2.5rem;margin-bottom:.5rem;">🐾</div>
      <h3>Create Account</h3><p class="auth-sub">Join PawAlert and start saving animals</p>
      <form method="POST"><div class="row g-3">
        <div class="col-12"><label class="form-label">Full Name</label><input type="text" name="name" class="form-control" placeholder="Ahmed Khan" required></div>
        <div class="col-md-6"><label class="form-label">Email</label><input type="email" name="email" class="form-control" required></div>
        <div class="col-md-6"><label class="form-label">Phone</label><input type="tel" name="phone" class="form-control" placeholder="+92 300..."></div>
        <div class="col-12"><label class="form-label">City</label><input type="text" name="city" class="form-control" placeholder="Rawalpindi"></div>
        <div class="col-12"><label class="form-label">Password</label><input type="password" name="password" class="form-control" required minlength="6"></div>
        <div class="col-12"><button type="submit" class="btn btn-rescue w-100">Create Account</button></div>
      </div></form>
      <hr class="auth-divider"><p style="text-align:center;font-size:.83rem;color:var(--text-muted);">Already have an account? <a href="/login" style="color:#00e676;font-weight:600;">Sign in</a></p>
    </div></div></div>"""
    return render_page(content)

@app.route("/login", methods=["GET","POST"])
def login_page():
    if request.method == "POST":
        u=User.query.filter_by(email=request.form["email"].strip().lower()).first()
        if u and u.check_password(request.form["password"]):
            login_user(u); flash(f"Welcome back, {u.name}! 🐾","success"); return redirect(url_for("home"))
        flash("Invalid email or password.","danger")
    content = """<div class="row justify-content-center py-4"><div class="col-md-6 col-lg-4"><div class="auth-card">
      <div style="text-align:center;font-size:2.5rem;margin-bottom:.5rem;">🐾</div>
      <h3>Welcome Back</h3><p class="auth-sub">Sign in to your PawAlert account</p>
      <form method="POST">
        <div class="mb-3"><label class="form-label">Email</label><input type="email" name="email" class="form-control" required></div>
        <div class="mb-3"><label class="form-label">Password</label><input type="password" name="password" class="form-control" required></div>
        <button type="submit" class="btn btn-rescue w-100">Sign In</button>
      </form>
      <hr class="auth-divider"><p style="text-align:center;font-size:.83rem;color:var(--text-muted);">New here? <a href="/register" style="color:#00e676;font-weight:600;">Create account</a></p>
    </div></div></div>"""
    return render_page(content)

@app.route("/logout")
@login_required
def logout():
    logout_user(); return redirect(url_for("home"))


# ── NGO ROUTES ────────────────────────────────────────────────────────────────

@app.route("/ngo/login", methods=["GET","POST"])
def ngo_login():
    if request.method == "POST":
        ngo=NGO.query.filter_by(email=request.form["email"].strip().lower()).first()
        if ngo and ngo.check_password(request.form["password"]):
            session["ngo_id"]=ngo.id; session["ngo_name"]=ngo.name
            flash(f"Welcome, {ngo.name}!","success"); return redirect(url_for("ngo_dashboard"))
        flash("Invalid credentials.","danger")
    content = """<div class="row justify-content-center py-4"><div class="col-md-6 col-lg-4"><div class="auth-card">
      <div style="text-align:center;font-size:2.5rem;margin-bottom:.5rem;">🏢</div>
      <h3>NGO Portal</h3><p class="auth-sub">Rescue organisation sign in</p>
      <form method="POST">
        <div class="mb-3"><label class="form-label">Email</label><input type="email" name="email" class="form-control" required></div>
        <div class="mb-3"><label class="form-label">Password</label><input type="password" name="password" class="form-control" required></div>
        <button type="submit" class="btn btn-rescue w-100">Sign In</button>
      </form>
      <hr class="auth-divider">
      <p style="text-align:center;font-size:.83rem;color:var(--text-muted);">New? <a href="/ngo/register" style="color:#00e676;font-weight:600;">Register organisation</a></p>
      <p style="text-align:center;font-size:.75rem;color:var(--text-muted);opacity:.6;">Seeded NGO password: <code style="color:#ffab40;">pawalert123</code></p>
    </div></div></div>"""
    return render_page(content)

@app.route("/ngo/register", methods=["GET","POST"])
def ngo_register():
    if request.method == "POST":
        email=request.form["email"].strip().lower()
        if NGO.query.filter_by(email=email).first():
            flash("Email already registered.","danger"); return redirect(url_for("ngo_register"))
        ngo=NGO(name=request.form["name"].strip(),email=email,phone=request.form["phone"].strip(),
                city=request.form["city"].strip(),address=request.form.get("address",""),
                bio=request.form.get("bio",""),website=request.form.get("website",""),
                latitude=float(request.form.get("latitude") or 33.6),
                longitude=float(request.form.get("longitude") or 73.1),
                coverage_km=float(request.form.get("coverage_km") or 30))
        ngo.set_password(request.form["password"]); db.session.add(ngo); db.session.commit()
        flash("Organisation registered! You can now log in.","success"); return redirect(url_for("ngo_login"))
    content = """<div class="row justify-content-center py-4"><div class="col-md-8 col-lg-7"><div class="auth-card" style="max-width:100%;">
      <div style="text-align:center;font-size:2.5rem;margin-bottom:.5rem;">🏢</div>
      <h3>Register Organisation</h3><p class="auth-sub">Animal rescue NGOs, shelters, and vet clinics</p>
      <form method="POST"><div class="row g-3">
        <div class="col-12"><label class="form-label">Organisation Name</label><input type="text" name="name" class="form-control" required></div>
        <div class="col-md-6"><label class="form-label">Email</label><input type="email" name="email" class="form-control" required></div>
        <div class="col-md-6"><label class="form-label">Phone</label><input type="tel" name="phone" class="form-control" required></div>
        <div class="col-md-6"><label class="form-label">City</label><input type="text" name="city" class="form-control" required></div>
        <div class="col-md-6"><label class="form-label">Coverage Radius (km)</label><input type="number" name="coverage_km" class="form-control" value="30"></div>
        <div class="col-12"><label class="form-label">Address</label><input type="text" name="address" class="form-control"></div>
        <div class="col-12"><label class="form-label">About your organisation</label><textarea name="bio" class="form-control" rows="2" placeholder="What animals you rescue, your capacity..."></textarea></div>
        <div class="col-12"><label class="form-label">Website (optional)</label><input type="url" name="website" class="form-control" placeholder="https://"></div>
        <div class="col-12">
          <label class="form-label">📍 Pin Your Location <span style="color:#ff5252;">*</span></label>
          <div id="rmap" style="height:220px;border-radius:14px;border:1px solid rgba(255,255,255,.08);" class="mb-2"></div>
          <input type="hidden" name="latitude" id="rlatInput">
          <input type="hidden" name="longitude" id="rlonInput">
          <button type="button" class="btn btn-ghost btn-sm" onclick="navigator.geolocation.getCurrentPosition(p=>rmk(p.coords.latitude,p.coords.longitude))"><i class="fa fa-location-crosshairs me-1"></i>Use My Location</button>
        </div>
        <div class="col-12"><label class="form-label">Password</label><input type="password" name="password" class="form-control" required minlength="6"></div>
        <div class="col-12"><button type="submit" class="btn btn-rescue w-100">Register Organisation</button></div>
      </div></form>
    </div></div></div>"""
    scripts = """<script>
const rm=L.map("rmap").setView([33.6,73.1],10);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(rm);
let rmk2=null;
function rmk(lat,lng){if(rmk2)rm.removeLayer(rmk2);rmk2=L.marker([lat,lng]).addTo(rm);document.getElementById("rlatInput").value=lat;document.getElementById("rlonInput").value=lng;rm.setView([lat,lng],14);}
rm.on("click",e=>rmk(e.latlng.lat,e.latlng.lng));
</script>"""
    return render_page(content, scripts)

@app.route("/ngo/logout")
def ngo_logout():
    session.pop("ngo_id",None); session.pop("ngo_name",None); return redirect(url_for("ngo_login"))


@app.route("/ngo/dashboard")
@ngo_required
def ngo_dashboard():
    ngo=NGO.query.get_or_404(session["ngo_id"])
    active=Report.query.filter_by(ngo_id=ngo.id).filter(Report.status.in_(["dispatched","in_progress"])).order_by(Report.created_at.desc()).all()
    resolved=Report.query.filter_by(ngo_id=ngo.id).filter(Report.status.in_(["rescued","closed"])).order_by(Report.created_at.desc()).limit(20).all()
    stats={"active":len(active),"resolved":Report.query.filter_by(ngo_id=ngo.id,status="rescued").count(),"total":Report.query.filter_by(ngo_id=ngo.id).count()}
    active_json=json.dumps([r.to_dict() for r in active])
    sev_cls={"mild":"sev-mild","moderate":"sev-moderate","critical":"sev-critical"}
    active_rows="".join(f'<a href="/ngo/case/{r.id}" class="case-row"><div class="d-flex justify-content-between align-items-center"><div><div style="font-weight:600;color:#fff;font-size:.88rem;">{"🚨 SOS — " if r.is_sos else ""}🐾 {(r.predicted_species or "Animal").title()} — Case #{r.id}</div><div style="font-size:.73rem;color:var(--text-muted);margin-top:.15rem;">📍 {r.address_text or r.city or str(round(r.latitude,3))+"..."} · 🕐 {r.created_at.strftime("%d %b, %I:%M %p")}</div></div><span class="sev-badge {sev_cls.get(r.predicted_severity or "","sev-unknown")}">{r.predicted_severity or "?"}</span></div></a>' for r in active) or "<p style='color:var(--text-muted);text-align:center;padding:2rem 0;font-size:.85rem;'>No active cases ✅</p>"
    resolved_rows="".join(f"<tr onclick=\"window.location='/ngo/case/{r.id}'\" style='cursor:pointer;'><td>#{r.id}</td><td>{(r.predicted_species or '?').title()}</td><td style='color:var(--text-muted);font-size:.8rem;'>{r.address_text or r.city or '—'}</td><td style='color:var(--text-muted);font-size:.8rem;'>{r.rescued_at.strftime('%d %b') if r.rescued_at else '—'}</td><td><span class='sev-badge sev-mild' style='font-size:.7rem;padding:.2rem .6rem;'>rescued</span></td></tr>" for r in resolved)
    resolved_section=f'<div class="glass-card p-3 mt-4"><h6 style="font-weight:700;color:#fff;margin-bottom:.8rem;"><i class="fa fa-check-circle me-2" style="color:#00e676;"></i>Recently Resolved</h6><table class="glass-table"><thead><tr><th>#</th><th>Species</th><th>Location</th><th>Date</th><th>Status</th></tr></thead><tbody>{resolved_rows}</tbody></table></div>' if resolved else ""
    bio_html=f'<p style="font-size:.83rem;color:var(--text-muted);">{ngo.bio}</p>' if ngo.bio else ""
    content = f"""
<div class="d-flex justify-content-between align-items-start mb-4 flex-wrap gap-2">
  <div>
    <div style="font-size:.72rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;">NGO Dashboard</div>
    <h4 style="font-weight:800;color:#fff;margin:.15rem 0 0;">🏢 {ngo.name}</h4>
    <div style="font-size:.8rem;color:var(--text-muted);">📍 {ngo.city} · Coverage: {ngo.coverage_km}km · 📞 {ngo.phone}</div>
    {bio_html}
  </div>
  <a href="/ngo/logout" class="btn btn-ghost btn-sm"><i class="fa fa-right-from-bracket me-1"></i>Logout</a>
</div>
<div class="row g-3 mb-4">
  <div class="col-md-4"><div class="stat-card orange"><i class="fa fa-fire" style="opacity:.35;display:block;margin-bottom:.25rem;"></i><div class="sc-num" data-count="{stats['active']}">{stats['active']}</div><div class="sc-lbl">Active Cases</div></div></div>
  <div class="col-md-4"><div class="stat-card green"><i class="fa fa-heart" style="opacity:.35;display:block;margin-bottom:.25rem;"></i><div class="sc-num" data-count="{stats['resolved']}">{stats['resolved']}</div><div class="sc-lbl">Rescued</div></div></div>
  <div class="col-md-4"><div class="stat-card blue"><i class="fa fa-folder" style="opacity:.35;display:block;margin-bottom:.25rem;"></i><div class="sc-num" data-count="{stats['total']}">{stats['total']}</div><div class="sc-lbl">Total Cases</div></div></div>
</div>
<div class="row g-4">
  <div class="col-lg-7">
    <div class="glass-card p-3">
      <h6 style="font-weight:700;color:#fff;margin-bottom:.7rem;"><i class="fa fa-map me-2" style="color:#00e676;"></i>Live Case Map</h6>
      <div id="dmap" style="height:350px;border-radius:14px;"></div>
    </div>
    {resolved_section}
  </div>
  <div class="col-lg-5">
    <div class="glass-card p-4">
      <h6 style="font-weight:700;color:#fff;margin-bottom:.8rem;"><i class="fa fa-triangle-exclamation me-2" style="color:#ff5252;"></i>Active Cases</h6>
      {active_rows}
    </div>
  </div>
</div>"""
    scripts = f"""<script>
const dm=L.map("dmap").setView([{ngo.latitude},{ngo.longitude}],11);
L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png").addTo(dm);
L.marker([{ngo.latitude},{ngo.longitude}],{{icon:L.divIcon({{html:'<div style="background:#1a7a52;color:#fff;border-radius:50%;width:30px;height:30px;display:flex;align-items:center;justify-content:center;font-size:.85rem;border:2px solid rgba(255,255,255,.4);box-shadow:0 4px 14px rgba(0,0,0,.4);">🏢</div>',iconSize:[30,30],iconAnchor:[15,15],className:''}})}})).addTo(dm).bindPopup("<b>{ngo.name}</b>");
L.circle([{ngo.latitude},{ngo.longitude}],{{radius:{ngo.coverage_km}*1000,color:"#00e676",fillColor:"#00e676",fillOpacity:.04,weight:1.5,dashArray:"5,6"}}).addTo(dm);
const cols={{mild:"#00e676",moderate:"#ffab40",critical:"#ff5252",unknown:"#888"}};
const cases={active_json};
cases.forEach(c=>{{
  const color=cols[c.predicted_severity]||"#888";
  const sos=c.is_sos?'<b style="color:#ff1744;"> SOS!</b>':'';
  const pulse=c.is_sos?'<div style="position:absolute;inset:-5px;border-radius:50%;border:2px solid #ff1744;animation:mpulse 1s ease-in-out infinite;"></div>':'';
  const icon=L.divIcon({{html:`<div style="position:relative;width:14px;height:14px;"><div style="width:14px;height:14px;border-radius:50%;background:${{color}};border:2px solid rgba(255,255,255,.4);box-shadow:0 0 8px ${{color}}80;"></div>${{pulse}}</div>`,iconSize:[14,14],iconAnchor:[7,7],className:''}});
  L.marker([c.latitude,c.longitude],{{icon}}).addTo(dm).bindPopup('<b>'+c.predicted_species.toUpperCase()+'</b>'+sos+'<br>'+c.predicted_severity+'<br><a href="/ngo/case/'+c.id+'">View case</a>');
}});
</script>"""
    return render_page(content, scripts, ngo_name=ngo.name)


@app.route("/ngo/case/<int:report_id>", methods=["GET","POST"])
@ngo_required
def ngo_case(report_id):
    report=Report.query.get_or_404(report_id)
    if request.method == "POST":
        action = request.form.get("action","update")
        if action == "comment":
            text = request.form.get("comment_text","").strip()
            if text:
                c=Comment(report_id=report.id,ngo_id=session["ngo_id"],ngo_name=session.get("ngo_name","NGO"),text=text)
                db.session.add(c); db.session.commit()
                flash("Update posted to citizen.","success")
        else:
            ns=request.form.get("status")
            if ns in ["dispatched","in_progress","rescued","closed"]:
                report.status=ns
                notes=request.form.get("notes","").strip()
                if notes: report.notes=notes
                if ns=="rescued": report.rescued_at=datetime.utcnow()
                db.session.commit()
                flash(f"Case #{report.id} updated to '{ns}'.","success")
        return redirect(url_for("ngo_case",report_id=report_id))
    sev=report.predicted_severity or "unknown"
    sev_cls={"mild":"sev-mild","moderate":"sev-moderate","critical":"sev-critical"}.get(sev,"sev-unknown")
    sp_pct=round((report.species_confidence or 0)*100); sv_pct=round((report.severity_confidence or 0)*100)
    sp_em={"cat":"🐱","dog":"🐶","cow":"🐄","bird":"🐦","donkey":"🫏"}.get(report.predicted_species or "","🐾")
    sev_em={"mild":"🟢","moderate":"⚠️","critical":"🔴"}.get(sev,"❓")
    status_opts="".join(f'<option value="{s}" {"selected" if report.status==s else ""}>{s.replace("_"," ").title()}</option>' for s in ["dispatched","in_progress","rescued","closed"])
    comments=Comment.query.filter_by(report_id=report.id).order_by(Comment.created_at.asc()).all()
    comments_html="".join(f'<div class="comment-bubble {"ngo-comment" if c.ngo_id else ""}"><div class="comment-author">{"🏢 "+c.ngo_name if c.ngo_id else "👤 "+(c.author.name if c.author else "Anonymous")}</div><div class="comment-text">{c.text}</div><div class="comment-time">{c.created_at.strftime("%d %b, %I:%M %p")}</div></div>' for c in comments) or "<p style='color:var(--text-muted);font-size:.82rem;'>No updates yet.</p>"
    sos_b='<span class="sev-badge sos-badge ms-2">🚨 SOS</span>' if report.is_sos else ""
    content = f"""
<div class="d-flex align-items-center gap-3 mb-4 flex-wrap">
  <a href="/ngo/dashboard" class="btn btn-ghost btn-sm"><i class="fa fa-arrow-left"></i></a>
  <div><h4 style="font-weight:800;color:#fff;margin:0;">Case #{report.id}{sos_b}</h4><span style="font-size:.8rem;color:var(--text-muted);">{report.created_at.strftime('%d %b %Y, %I:%M %p')}</span></div>
  <div class="ms-auto"><span class="sev-badge {sev_cls}">{sev.upper()}</span></div>
</div>
<div class="row g-4">
  <div class="col-lg-6">
    <div class="glass-card p-0" style="overflow:hidden;">
      <img src="/uploads/{report.image_filename}" style="width:100%;height:270px;object-fit:cover;" alt="Animal">
      <div class="p-4">
        <div class="row g-3 mb-3">
          <div class="col-6"><div class="glass-inner p-3 text-center"><div style="font-size:1.8rem;">{sp_em}</div><div style="font-weight:700;color:#fff;text-transform:capitalize;">{report.predicted_species or "Unknown"}</div><div style="font-size:.7rem;color:var(--text-muted);">{sp_pct}%</div><div class="conf-bar mt-1"><div class="conf-fill" data-w="{sp_pct}"></div></div></div></div>
          <div class="col-6"><div class="glass-inner p-3 text-center"><div style="font-size:1.8rem;">{sev_em}</div><div style="font-weight:700;text-transform:capitalize;color:{'#00e676' if sev=='mild' else '#ffab40' if sev=='moderate' else '#ff5252'};">{sev}</div><div style="font-size:.7rem;color:var(--text-muted);">{sv_pct}%</div><div class="conf-bar mt-1"><div class="conf-fill" data-w="{sv_pct}"></div></div></div></div>
        </div>
        {f'<div class="glass-inner p-3 mb-3"><div style="font-size:.7rem;color:var(--text-muted);">Description</div><div style="font-size:.84rem;color:#fff;margin-top:.2rem;">{report.description}</div></div>' if report.description else ""}
        <div id="cmap" style="height:210px;border-radius:12px;"></div>
        <a href="https://maps.google.com/?q={report.latitude},{report.longitude}" target="_blank" class="btn btn-ghost btn-sm w-100 mt-2"><i class="fa fa-map-location-dot me-1"></i>Open in Google Maps</a>
      </div>
    </div>
  </div>
  <div class="col-lg-6">
    <div class="glass-card p-4 mb-3">
      <h6 style="font-weight:700;color:#fff;margin-bottom:1rem;"><i class="fa fa-pen-to-square me-2" style="color:#00e676;"></i>Update Case Status</h6>
      <form method="POST"><input type="hidden" name="action" value="update">
        <div class="mb-3"><label class="form-label">Status</label><select name="status" class="form-select">{status_opts}</select></div>
        <div class="mb-3"><label class="form-label">Field Notes</label><textarea name="notes" class="form-control" rows="3" placeholder="Condition on arrival, treatment...">{report.notes or ""}</textarea></div>
        <button type="submit" class="btn btn-rescue w-100">Update Case</button>
      </form>
    </div>
    <div class="glass-card p-4 mb-3">
      <h6 style="font-weight:700;color:#fff;margin-bottom:.8rem;"><i class="fa fa-comments me-2" style="color:#00e676;"></i>Citizen Communication</h6>
      <div style="max-height:200px;overflow-y:auto;margin-bottom:.8rem;">{comments_html}</div>
      <form method="POST"><input type="hidden" name="action" value="comment">
        <div class="d-flex gap-2"><input type="text" name="comment_text" class="form-control" placeholder="Send update to citizen..." required><button type="submit" class="btn btn-glow px-3"><i class="fa fa-paper-plane"></i></button></div>
      </form>
    </div>
    <div class="glass-card p-3">
      <div style="font-size:.8rem;color:var(--text-muted);">🕐 {report.created_at.strftime('%d %b %Y, %I:%M %p')}</div>
      <div style="font-size:.8rem;color:var(--text-muted);margin-top:.3rem;">📍 {report.address_text or report.city or str(round(report.latitude,5))+", "+str(round(report.longitude,5))}</div>
      {f'<div style="font-size:.8rem;color:#ffab40;margin-top:.3rem;">📡 Dispatched: {report.dispatched_at.strftime("%d %b, %I:%M %p")}</div>' if report.dispatched_at else ""}
      {f'<div style="font-size:.8rem;color:#00e676;margin-top:.3rem;">✅ Rescued: {report.rescued_at.strftime("%d %b, %I:%M %p")}</div>' if report.rescued_at else ""}
    </div>
  </div>
</div>"""
    scripts = f"""<script>
const cm=L.map("cmap").setView([{report.latitude},{report.longitude}],15);
L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png").addTo(cm);
L.marker([{report.latitude},{report.longitude}],{{icon:L.divIcon({{html:'<div style="background:linear-gradient(135deg,#ff6b35,#e05a28);width:26px;height:26px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);border:2px solid rgba(255,255,255,.5);box-shadow:0 4px 14px rgba(255,107,53,.5);"></div>',iconSize:[26,26],iconAnchor:[13,26],className:''}})}})).addTo(cm).bindPopup("Animal location").openPopup();
</script>"""
    return render_page(content, scripts, ngo_name=session.get("ngo_name","NGO"))


# ── API ───────────────────────────────────────────────────────────────────────

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    from flask import send_from_directory
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/api/reports")
def api_reports():
    reports=Report.query.order_by(Report.created_at.desc()).limit(200).all()
    return jsonify({"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point","coordinates":[r.longitude,r.latitude]},"properties":r.to_dict()} for r in reports]})

@app.route("/api/ngos")
def api_ngos():
    ngos=NGO.query.filter_by(is_active=True,is_verified=True).all()
    return jsonify([{"id":n.id,"name":n.name,"city":n.city,"phone":n.phone,"lat":n.latitude,"lon":n.longitude,"coverage":n.coverage_km} for n in ngos])

@app.route("/api/stats")
def api_stats():
    return jsonify({"total":Report.query.count(),"rescued":Report.query.filter_by(status="rescued").count(),"active":Report.query.filter(Report.status.in_(["dispatched","in_progress"])).count(),"ngos":NGO.query.filter_by(is_active=True).count(),"sos":Report.query.filter_by(is_sos=True).count(),"volunteers":User.query.filter_by(is_volunteer=True).count()})

@app.route("/api/vote/<int:report_id>", methods=["POST"])
def vote_urgent(report_id):
    report=Report.query.get_or_404(report_id)
    voted_key=f"voted_{report_id}"
    if session.get(voted_key):
        return jsonify({"ok":False,"votes":report.urgent_votes or 0})
    report.urgent_votes=(report.urgent_votes or 0)+1
    db.session.commit()
    session[voted_key]=True
    return jsonify({"ok":True,"votes":report.urgent_votes})

@app.route("/api/sos", methods=["POST"])
def api_sos():
    data=request.get_json()
    lat=data.get("lat"); lon=data.get("lon")
    species=data.get("species","dog"); desc=data.get("desc","Emergency SOS")
    if not lat or not lon: return jsonify({"error":"No location"}),400
    # Create placeholder image
    fname=f"sos_{uuid.uuid4().hex}.jpg"
    fpath=os.path.join(UPLOAD_FOLDER,fname)
    try:
        img=Image.new("RGB",(224,224),(220,30,30))
        img.save(fpath,"JPEG")
    except: pass
    report=Report(user_id=current_user.id if current_user.is_authenticated else None,
                  latitude=lat,longitude=lon,address_text="SOS Emergency Location",
                  image_filename=fname,description=desc,
                  predicted_species=species,species_confidence=0.95,
                  predicted_severity="critical",severity_confidence=0.99,is_sos=True)
    db.session.add(report); db.session.commit()
    dispatch_report(report)
    return jsonify({"ok":True,"id":report.id})


# ── SEED ─────────────────────────────────────────────────────────────────────

def seed_ngos():
    NGOS=[
        {"name":"Ayesha Chundrigar Foundation (ACF)","email":"acf@pawalert.pk","phone":"+92-21-34301851","city":"Karachi","address":"ACF Animal Rescue, Karachi","bio":"Pakistan's largest animal rescue organisation. Rescues over 3,000 animals annually.","latitude":24.8607,"longitude":67.0011,"coverage_km":40},
        {"name":"PDSA Pakistan","email":"pdsa@pawalert.pk","phone":"+92-42-35761999","city":"Lahore","address":"PDSA Lahore, Punjab","bio":"Free veterinary care for animals of low-income families.","latitude":31.5204,"longitude":74.3587,"coverage_km":50},
        {"name":"Islamabad Animal Rescue","email":"iar@pawalert.pk","phone":"+92-51-2650000","city":"Islamabad","address":"Islamabad, Federal Capital","bio":"Capital city's primary animal rescue and rehabilitation centre.","latitude":33.7294,"longitude":73.0931,"coverage_km":35},
        {"name":"Rawalpindi Animal Welfare Society","email":"raws@pawalert.pk","phone":"+92-51-5555123","city":"Rawalpindi","address":"Rawalpindi, Punjab","bio":"Serving Rawalpindi and surrounding areas since 2010.","latitude":33.6007,"longitude":73.0679,"coverage_km":30},
        {"name":"Peshawar Animal Rescue Centre","email":"parc@pawalert.pk","phone":"+92-91-9210550","city":"Peshawar","address":"Peshawar, KPK","bio":"KPK's leading animal rescue and welfare organisation.","latitude":34.0150,"longitude":71.5249,"coverage_km":35},
        {"name":"Quetta Animal Welfare","email":"qaw@pawalert.pk","phone":"+92-81-9201010","city":"Quetta","address":"Quetta, Balochistan","bio":"Balochistan's only dedicated animal rescue centre.","latitude":30.1798,"longitude":66.9750,"coverage_km":40},
        {"name":"Multan Rescue Animals","email":"mra@pawalert.pk","phone":"+92-61-9200010","city":"Multan","address":"Multan, Punjab","bio":"Southern Punjab animal rescue and sterilisation program.","latitude":30.1575,"longitude":71.5249,"coverage_km":35},
    ]
    for data in NGOS:
        if not NGO.query.filter_by(email=data["email"]).first():
            ngo=NGO(**data); ngo.set_password("pawalert123"); db.session.add(ngo)
    db.session.commit()
    print("[PawAlert] ✓ Pakistani rescue organisations loaded")


# ── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_ngos()
        print("\n" + "="*60)
        print("  🐾  PawAlert v2.0 is running!")
        print("  Home       : http://localhost:5000")
        print("  Live Map   : http://localhost:5000/map")
        print("  Leaderboard: http://localhost:5000/leaderboard")
        print("  Volunteer  : http://localhost:5000/volunteer")
        print("  NGO Login  : http://localhost:5000/ngo/login")
        print("  NGO Pass   : pawalert123")
        print("  NEW: SOS button (bottom-right corner)")
        print("  NEW: Comments on reports")
        print("  NEW: Urgent vote button")
        print("  NEW: City quick-select")
        print("  NEW: Toast notifications")
        print("="*60 + "\n")
    import webbrowser, threading
    threading.Timer(1.5, lambda: webbrowser.open("http://localhost:5000")).start()
    app.run(debug=True, host="0.0.0.0", port=5000)
