import hashlib
import os
import secrets
import smtplib
import sqlite3
from email.message import EmailMessage
import requests
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, current_app, render_template, request, redirect, url_for, session
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
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


def _get_serializer():
    secret = current_app.secret_key or os.environ.get("SECRET_KEY") or "alvas-career-portal-secret"
    return URLSafeTimedSerializer(secret, salt="password-reset-salt")


def _send_reset_email(recipient_email, reset_url):
    mail_from = (os.environ.get("MAIL_FROM") or os.environ.get("MAIL_USERNAME") or "").strip()
    brevo_api_key = (os.environ.get("BREVO_API_KEY") or "").strip()

    html_body = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #0f172a; max-width: 520px;">
        <h2 style="color: #1d4ed8; margin-bottom: 8px;">Password Reset Request</h2>
        <p>Hello,</p>
        <p>We received a request to reset your password for <strong>Alva's College Student Career Portal</strong>.</p>
        <p style="margin: 20px 0;">
            <a href="{reset_url}" style="background: #1d63dc; color: #ffffff; padding: 11px 20px; border-radius: 8px; text-decoration: none; font-weight: 600;">
                Reset Password
            </a>
        </p>
        <p style="font-size: 13px; color: #475569;">This link expires in 30 minutes. If you didn't request this, ignore this email.</p>
    </div>
    """

    # 1. HTTPS API via Brevo (works on Render Free Tier where SMTP ports are blocked)
    if brevo_api_key:
        if not mail_from:
            return False, "Set MAIL_FROM in Render to your verified Brevo sender email."
        try:
            resp = requests.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "api-key": brevo_api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "sender": {"name": "Alva's Career Portal", "email": mail_from},
                    "to": [{"email": recipient_email}],
                    "subject": "Reset Your Password - Alva's College Student Career Portal",
                    "htmlContent": html_body,
                },
                timeout=15,
            )
            if resp.status_code in (200, 201, 202):
                return True, None
            return False, f"Email service error ({resp.status_code}): {resp.text[:180]}"
        except Exception as exc:
            return False, f"Could not send reset email via API: {exc}"

    # 2. Fallback to standard SMTP (works locally)
    mail_username = (os.environ.get("MAIL_USERNAME") or "").strip()
    mail_password = (os.environ.get("MAIL_PASSWORD") or "").strip()
    mail_server = (os.environ.get("MAIL_SERVER") or "smtp.gmail.com").strip()
    mail_port = int(os.environ.get("MAIL_PORT") or "587")

    if not mail_username or not mail_password:
        return False, "Set BREVO_API_KEY (recommended on Render) or MAIL_USERNAME/MAIL_PASSWORD in Environment."

    msg = EmailMessage()
    msg["Subject"] = "Reset Your Password - Alva's College Student Career Portal"
    msg["From"] = mail_from or mail_username
    msg["To"] = recipient_email
    msg.set_content(f"Reset your password (valid 30 mins): {reset_url}")
    msg.add_alternative(html_body, subtype="html")

    try:
        if mail_port == 465:
            with smtplib.SMTP_SSL(mail_server, mail_port, timeout=15) as server:
                server.login(mail_username, mail_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(mail_server, mail_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(mail_username, mail_password)
                server.send_message(msg)
        return True, None
    except OSError as exc:
        if getattr(exc, "errno", None) == 101:
            return False, "Render blocks SMTP ports (587/465). Add BREVO_API_KEY in Render Environment to send via HTTPS."
        return False, f"Could not send reset email: {exc}"
    except Exception as exc:
        return False, f"Could not send reset email: {exc}"


def _login_or_create_oauth_user(email, full_name, avatar_url=""):
    avatar_clean = (avatar_url or "").strip() or None
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, full_name, email, avatar_url FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()

        if not user:
            random_secret = secrets.token_urlsafe(24)
            cursor.execute(
                "INSERT INTO users (full_name, email, password, avatar_url) VALUES (?, ?, ?, ?)",
                (full_name, email, _hash_password(random_secret), avatar_clean)
            )
            conn.commit()
            cursor.execute("SELECT id, full_name, email, avatar_url FROM users WHERE email = ?", (email,))
            user = cursor.fetchone()
        elif avatar_clean and user.get("avatar_url") != avatar_clean:
            cursor.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (avatar_clean, user["id"]))
            conn.commit()
            user["avatar_url"] = avatar_clean
    finally:
        cursor.close()
        conn.close()

    if not user:
        return False

    session["user_id"] = user["id"]
    session["full_name"] = user["full_name"]
    session["avatar_url"] = user.get("avatar_url") or ""
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
                "SELECT id, full_name, email, avatar_url FROM users WHERE email = ? AND password = ?",
                (email, _hash_password(password))
            )
            user = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

        if user:
            session["user_id"] = user["id"]
            session["full_name"] = user["full_name"]
            session["avatar_url"] = user.get("avatar_url") or ""
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="Invalid email or password.")

    return render_template("login.html")


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    email = (request.form.get("email") or "").strip().lower()
    if not email:
        return render_template("login.html", error="Please enter your registered email address.")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, email FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not user:
        return render_template("login.html", error="No account found with that email address.")

    token = _get_serializer().dumps(email)
    reset_url = url_for("auth.reset_password", token=token, _external=True)
    sent, err_msg = _send_reset_email(email, reset_url)

    if not sent:
        return render_template("login.html", error=err_msg)

    return render_template(
        "login.html",
        info=f"Password reset link sent to {email}. Check your inbox (and spam folder); it expires in 30 minutes."
    )


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = _get_serializer().loads(token, max_age=1800)
    except SignatureExpired:
        return render_template("reset_password.html", token=token, error="This password reset link has expired. Please request a new one.")
    except BadSignature:
        return render_template("reset_password.html", token=token, error="Invalid password reset link.")

    if request.method == "POST":
        password = (request.form.get("password") or "").strip()
        confirm = (request.form.get("confirm_password") or "").strip()

        if len(password) < 6:
            return render_template("reset_password.html", token=token, email=email, error="Password must be at least 6 characters.")
        if password != confirm:
            return render_template("reset_password.html", token=token, email=email, error="Passwords do not match.")

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE users SET password = ? WHERE email = ?",
                (_hash_password(password), email)
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

        return render_template("login.html", info="Your password has been updated. You can sign in now.")

    return render_template("reset_password.html", token=token, email=email)


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
    avatar_url = (userinfo.get("picture") or "").strip()

    if not _login_or_create_oauth_user(email, full_name, avatar_url):
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
    avatar_url = (userinfo.get("picture") or "").strip()

    if not _login_or_create_oauth_user(email, full_name, avatar_url):
        return render_template("login.html", error="Could not complete LinkedIn login.")

    return redirect(url_for("dashboard"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))