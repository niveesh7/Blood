import os
import re
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

import cv2
import numpy as np
import requests
import tensorflow as tf
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
MODEL_PATH = BASE_DIR / "blood_group_model.keras"
BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,29}$")

app = Flask(__name__)
app.config.update(SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "change-before-production"), MAX_CONTENT_LENGTH=5 * 1024 * 1024)
_model = None


def configured():
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_ANON_KEY") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))


def valid_username(value):
    return bool(USERNAME_RE.fullmatch(value.lower()))


def allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {"png", "jpg", "jpeg"}


def auth(path, payload):
    response = requests.post(
        f"{os.environ['SUPABASE_URL'].rstrip('/')}/auth/v1/{path}",
        headers={"apikey": os.environ["SUPABASE_ANON_KEY"], "Content-Type": "application/json"}, json=payload, timeout=20,
    )
    if not response.ok:
        try:
            message = response.json().get("msg") or response.json().get("message")
        except ValueError:
            message = None
        raise ValueError(message or "Unable to complete authentication. Please try again.")
    return response.json()


def db_headers():
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise ValueError("Server authentication is not configured.")
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def profiles_query(params):
    response = requests.get(f"{os.environ['SUPABASE_URL'].rstrip('/')}/rest/v1/profiles", headers=db_headers(), params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def profile_for_username(username):
    rows = profiles_query({"select": "id,username,role,auth_email", "username": f"eq.{username.lower()}", "limit": 1})
    return rows[0] if rows else None


def profile_for_user_id(user_id):
    rows = profiles_query({"select": "id,username,role", "id": f"eq.{user_id}", "limit": 1})
    return rows[0] if rows else None


def set_session(auth_data, profile):
    session.clear()
    session.update(access_token=auth_data["access_token"], user_id=auth_data["user"]["id"], username=profile["username"], role=profile["role"])


def current_profile():
    if not session.get("access_token") or not session.get("user_id"):
        return None
    try:
        return profile_for_user_id(session["user_id"])
    except (ValueError, requests.RequestException):
        return None


def is_admin():
    return session.get("role") == "admin"


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_profile():
            session.clear()
            flash("Please sign in to continue.", "error")
            return redirect(url_for("home"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        profile = current_profile()
        if not profile:
            session.clear()
            flash("Please sign in to continue.", "error")
            return redirect(url_for("home"))
        if profile["role"] != "admin":
            session["role"] = "user"
            flash("You do not have permission to access the Admin Panel.", "error")
            return redirect(url_for("dashboard"))
        session["role"] = "admin"
        return view(*args, **kwargs)
    return wrapped


def authenticate_username(username, password, admin_only=False):
    profile = profile_for_username(username)
    if not profile:
        raise ValueError("Invalid username or password.")
    data = auth("token?grant_type=password", {"email": profile["auth_email"], "password": password})
    if data.get("user", {}).get("id") != profile["id"]:
        raise ValueError("Invalid username or password.")
    if admin_only and profile["role"] != "admin":
        raise PermissionError("You do not have permission to access the Admin Panel.")
    return data, profile


def get_history(all_records=False):
    params = {"select": "id,user_email,file_name,blood_group,confidence,created_at", "order": "created_at.desc", "limit": 100}
    if not all_records:
        params["user_id"] = f"eq.{session['user_id']}"
    response = requests.get(f"{os.environ['SUPABASE_URL'].rstrip('/')}/rest/v1/prediction_history", headers=db_headers(), params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def save_history(file_name, blood_group, confidence):
    record = {"user_id": session["user_id"], "user_email": session["username"], "file_name": file_name, "blood_group": blood_group, "confidence": round(confidence * 100, 2), "created_at": datetime.now(timezone.utc).isoformat()}
    response = requests.post(f"{os.environ['SUPABASE_URL'].rstrip('/')}/rest/v1/prediction_history", headers={**db_headers(), "Prefer": "return=minimal"}, json=record, timeout=20)
    response.raise_for_status()


def predict(path):
    global _model
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError("The file could not be read as an image.")
    if _model is None:
        _model = tf.keras.models.load_model(MODEL_PATH)
    values = _model.predict(np.expand_dims(cv2.resize(image, (128, 128)).astype("float32") / 255.0, 0), verbose=0)[0]
    index = int(np.argmax(values))
    return BLOOD_GROUPS[index], float(values[index])


@app.route("/")
def home():
    profile = current_profile()
    if profile:
        return redirect(url_for("admin_dashboard" if profile["role"] == "admin" else "dashboard"))
    return render_template("auth.html")


@app.post("/register")
def register():
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    if not configured():
        flash("The authentication service is not configured.", "error")
        return redirect(url_for("home"))
    if not valid_username(username):
        flash("Username must start with a letter and use 3–30 lowercase letters, numbers, or underscores.", "error")
        return redirect(url_for("home"))
    if len(password) < 8:
        flash("Password must contain at least 8 characters.", "error")
        return redirect(url_for("home"))
    try:
        if profile_for_username(username):
            raise ValueError("That username is already in use.")
        data = auth("signup", {"email": f"{username}@hemascan.internal", "password": password, "data": {"username": username}})
        profile = profile_for_username(username)
        if not data.get("access_token") or not profile:
            raise ValueError("Registration needs an administrator configuration update. Disable Confirm email in Supabase, then try again.")
        set_session(data, profile)
        flash("Your account is ready.", "success")
        return redirect(url_for("dashboard"))
    except (ValueError, requests.RequestException) as error:
        flash(str(error), "error")
        return redirect(url_for("home"))


@app.post("/login")
def login():
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    if not username or not password:
        flash("Enter your username and password.", "error")
        return redirect(url_for("home"))
    try:
        data, profile = authenticate_username(username, password)
        set_session(data, profile)
        return redirect(url_for("admin_dashboard" if profile["role"] == "admin" else "dashboard"))
    except (ValueError, requests.RequestException) as error:
        flash("Invalid username or password.", "error")
        return redirect(url_for("home"))


@app.post("/admin/login")
def admin_login():
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    if not username or not password:
        flash("Enter your Admin User ID and password.", "error")
        return redirect(url_for("home") + "#admin")
    try:
        data, profile = authenticate_username(username, password, admin_only=True)
        set_session(data, profile)
        return redirect(url_for("admin_dashboard"))
    except PermissionError as error:
        flash(str(error), "error")
    except (ValueError, requests.RequestException):
        flash("Invalid Admin User ID or password.", "error")
    return redirect(url_for("home") + "#admin")


@app.route("/dashboard")
@login_required
def dashboard():
    try:
        records = get_history()
    except (ValueError, requests.RequestException):
        records = []
        flash("Could not load your history. Please try again.", "error")
    return render_template("dashboard.html", records=records, admin=is_admin())


@app.route("/admin")
@admin_required
def admin_dashboard():
    try:
        records = get_history(True)
    except (ValueError, requests.RequestException):
        records = []
        flash("Could not load screening history. Please try again.", "error")
    return render_template("admin.html", records=records, admin=True)


@app.route("/check")
@login_required
def check():
    return render_template("check.html", admin=is_admin())


@app.post("/predict")
@login_required
def make_prediction():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename or not allowed(uploaded.filename):
        flash("Choose a PNG, JPG, or JPEG fingerprint image.", "error")
        return redirect(url_for("check"))
    UPLOAD_DIR.mkdir(exist_ok=True)
    name = secure_filename(uploaded.filename)
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{name}"
    try:
        uploaded.save(path)
        group, confidence = predict(path)
        save_history(name, group, confidence)
        return render_template("result.html", blood_group=group, confidence=round(confidence * 100, 1), admin=is_admin())
    except (ValueError, requests.RequestException, OSError):
        flash("Prediction could not be completed. Please try again.", "error")
        return redirect(url_for("check"))
    finally:
        path.unlink(missing_ok=True)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("home"))


@app.errorhandler(413)
def too_large(_):
    flash("The image is too large. Use a file below 5 MB.", "error")
    return redirect(url_for("check"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG") == "1")
