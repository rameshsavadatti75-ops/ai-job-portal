import hashlib
import os
import secrets
import sqlite3
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, render_template, request, redirect, url_for, session
from database import get_db_connection

auth_bp = Blueprint("auth", __name__)
oauth = OAuth()
google = None
linkedin = None


def init_oauth(app):
    global google, linkedin
    oauth.init_app(app)

    google = oauth.register(
        name="google",
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    linkedin = oauth.register(
        name="linkedin",
        client_id=os.environ.get("LINKEDIN_CLIENT_ID"),
        client_secret=os.environ.get("LINKEDIN_CLIENT_SECRET"),
        server_metadata_url="https://www.linkedin.com/oauth/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid profile email",
            "token_endpoint_auth_method": "client_secret_post",
        },
    )


def _hash_password(raw_password):
    return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()


def _login_or_create_oauth_user(email, full_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, full_name, email FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()

        if not user:
            random_secret = secrets.token_urlsafe(24)
            cursor.execute(
                "INSERT INTO users (full_name, email, password) VALUES (?, ?, ?)",
                (full_name, email, _hash_password(random_secret))
            )
            conn.commit()
            cursor.execute("SELECT id, full_name, email FROM users WHERE email = ?", (email,))
            user = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not user:
        return False

    session["user_id"] = user["id"]
    session["full_name"] = user["full_name"]
    return True


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = (request.form.get("full_name") or request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()

        if not full_name or not email or not password:
            return render_template("register.html", error="All fields are required.")

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (full_name, email, password) VALUES (?, ?, ?)",
                (full_name, email, _hash_password(password))
            )
            conn.commit()
            return redirect(url_for("auth.login"))
        except sqlite3.IntegrityError:
            conn.rollback()
            return render_template("register.html", error="Email already registered. Please sign in.")
        except Exception as exc:
            conn.rollback()
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                return render_template("register.html", error="Email already registered. Please sign in.")
            return render_template("register.html", error="Could not register account right now.")
        finally:
            cursor.close()
            conn.close()

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, full_name, email FROM users WHERE email = ? AND password = ?",
                (email, _hash_password(password))
            )
            user = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

        if user:
            session["user_id"] = user["id"]
            session["full_name"] = user["full_name"]
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="Invalid email or password.")

    return render_template("login.html")


@auth_bp.route("/auth/google")
def google_login():
    if not os.environ.get("GOOGLE_CLIENT_ID") or not os.environ.get("GOOGLE_CLIENT_SECRET"):
        return render_template("login.html", error="Google login is not configured on the server yet.")
    redirect_uri = url_for("auth.google_callback", _external=True)
    return google.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/google/callback")
def google_callback():
    try:
        token = google.authorize_access_token()
        userinfo = token.get("userinfo") or google.userinfo()
    except Exception:
        return render_template("login.html", error="Google sign-in was cancelled or failed. Please try again.")

    email = (userinfo.get("email") or "").strip().lower()
    if not email:
        return render_template("login.html", error="Could not retrieve email from your Google account.")

    full_name = (userinfo.get("name") or email.split("@")[0]).strip()
    if not _login_or_create_oauth_user(email, full_name):
        return render_template("login.html", error="Could not complete Google login.")

    return redirect(url_for("dashboard"))


@auth_bp.route("/auth/linkedin")
def linkedin_login():
    if not os.environ.get("LINKEDIN_CLIENT_ID") or not os.environ.get("LINKEDIN_CLIENT_SECRET"):
        return render_template("login.html", error="LinkedIn login is not configured on the server yet.")
    redirect_uri = url_for("auth.linkedin_callback", _external=True)
    return linkedin.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/linkedin/callback")
def linkedin_callback():
    try:
        token = linkedin.authorize_access_token()
        userinfo = token.get("userinfo") or linkedin.userinfo()
    except Exception:
        return render_template("login.html", error="LinkedIn sign-in was cancelled or failed. Please try again.")

    email = (userinfo.get("email") or "").strip().lower()
    if not email:
        return render_template("login.html", error="Could not retrieve email from your LinkedIn account.")

    full_name = (
        userinfo.get("name")
        or f"{userinfo.get('given_name', '')} {userinfo.get('family_name', '')}".strip()
        or email.split("@")[0]
    ).strip()

    if not _login_or_create_oauth_user(email, full_name):
        return render_template("login.html", error="Could not complete LinkedIn login.")

    return redirect(url_for("dashboard"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))