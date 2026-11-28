import hashlib
import os
import random
import re
import secrets
import smtplib
import sqlite3
import time
from email.message import EmailMessage
import requests
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, current_app, jsonify, render_template, request, redirect, url_for, session
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from database import get_db_connection

auth_bp = Blueprint("auth", __name__)
oauth = OAuth()
google = None
linkedin = None

DEFAULT_COURSE_INFO = "Alva's College Student"


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


def _send_brevo_html_email(recipient_email, subject, html_body, plain_fallback=""):
    mail_from = (os.environ.get("MAIL_FROM") or os.environ.get("MAIL_USERNAME") or "").strip()
    brevo_api_key = (os.environ.get("BREVO_API_KEY") or "").strip()

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
                    "subject": subject,
                    "htmlContent": html_body,
                },
                timeout=15,
            )
            if resp.status_code in (200, 201, 202):
                return True, None
            return False, f"Email service error ({resp.status_code}): {resp.text[:180]}"
        except Exception as exc:
            return False, f"Could not send email via API: {exc}"

    mail_username = (os.environ.get("MAIL_USERNAME") or "").strip()
    mail_password = (os.environ.get("MAIL_PASSWORD") or "").strip()
    mail_server = (os.environ.get("MAIL_SERVER") or "smtp.gmail.com").strip()
    mail_port = int(os.environ.get("MAIL_PORT") or "587")

    if not mail_username or not mail_password:
        return False, "Set BREVO_API_KEY in Render Environment to send emails."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from or mail_username
    msg["To"] = recipient_email
    msg.set_content(plain_fallback or subject)
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
    except Exception as exc:
        return False, f"Could not send email: {exc}"


def _send_reset_email(recipient_email, reset_url):
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
    return _send_brevo_html_email(
        recipient_email=recipient_email,
        subject="Reset Your Password - Alva's College Student Career Portal",
        html_body=html_body,
        plain_fallback=f"Reset your password (valid 30 mins): {reset_url}",
    )


def _send_register_otp_email(recipient_email, full_name, otp_code):
    greeting = full_name or "Student"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #0f172a; max-width: 520px; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px;">
        <h2 style="color: #1d4ed8; margin-bottom: 8px;">Email Verification OTP</h2>
        <p>Hello <strong>{greeting}</strong>,</p>
        <p>Use this 6-digit OTP to verify your email on <strong>Alva's College Student Career Portal</strong>:</p>
        <div style="margin: 18px 0; padding: 14px; text-align: center; background: #eff6ff; border: 1px dashed #2563eb; border-radius: 10px;">
            <span style="font-size: 28px; font-weight: 800; letter-spacing: 7px; color: #1d4ed8;">{otp_code}</span>
        </div>
        <p style="font-size: 13px; color: #475569;">This OTP is valid for 10 minutes. If you did not request this, ignore this email.</p>
    </div>
    """
    return _send_brevo_html_email(
        recipient_email=recipient_email,
        subject="Your Registration OTP - Alva's College Student Career Portal",
        html_body=html_body,
        plain_fallback=f"Your Alva's College Career Portal OTP is {otp_code} (valid 10 minutes).",
    )


def _send_welcome_email(recipient_email, full_name, college_name=None, register_number=None):
    details_rows = ""
    if college_name:
        details_rows += f"<div><strong>College:</strong> {college_name}</div>"
    if register_number:
        details_rows += f"<div><strong>Register Number:</strong> {register_number}</div>"

    details_box = f"""
    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px 16px; margin: 16px 0; font-size: 13px; color: #334155;">
        <div><strong>Email:</strong> {recipient_email}</div>
        {details_rows}
    </div>
    """

    html_body = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #0f172a; max-width: 540px; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px;">
        <h2 style="color: #1d4ed8; margin-bottom: 8px;">Welcome to Alva's College Student Career Portal</h2>
        <p>Hello <strong>{full_name}</strong>,</p>
        <p>Your account is now verified and active. Sign in anytime to explore AI-matched job opportunities and manage your placement profile.</p>
        {details_box}
        <p style="font-size: 12.5px; color: #64748b;">Skills Today. Better Tomorrow. &mdash; Alva's College, Moodubidire</p>
    </div>
    """
    _send_brevo_html_email(
        recipient_email=recipient_email,
        subject="Welcome to Alva's College Student Career Portal",
        html_body=html_body,
        plain_fallback=f"Welcome {full_name}! Your Alva's College Student Career Portal account is now active.",
    )


def _login_or_create_oauth_user(email, full_name, avatar_url=""):
    avatar_clean = (avatar_url or "").strip() or None
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, full_name, email, avatar_url, course_info FROM users WHERE email = ?",
            (email,)
        )
        user = cursor.fetchone()

        if not user:
            random_secret = secrets.token_urlsafe(24)
            cursor.execute(
                "INSERT INTO users (full_name, email, password, avatar_url, course_info) VALUES (?, ?, ?, ?, ?)",
                (full_name, email, _hash_password(random_secret), avatar_clean, DEFAULT_COURSE_INFO)
            )
            conn.commit()
            cursor.execute(
                "SELECT id, full_name, email, avatar_url, course_info FROM users WHERE email = ?",
                (email,)
            )
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
    session["course_info"] = (user.get("course_info") or "").strip() or DEFAULT_COURSE_INFO
    return True


@auth_bp.route("/send-register-otp", methods=["POST"])
def send_register_otp():
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip().lower()
    full_name = (data.get("full_name") or "").strip()

    if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"ok": False, "message": "Please enter a valid email address first."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email,))
        existing = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if existing:
        return jsonify({"ok": False, "message": "This email is already registered. Please sign in."}), 409

    now = int(time.time())
    last_sent = session.get("reg_otp_sent_at", 0)
    last_email = session.get("reg_otp_email", "")
    if last_email == email and (now - last_sent) < 30:
        wait_sec = 30 - (now - last_sent)
        return jsonify({"ok": False, "message": f"Please wait {wait_sec}s before resending OTP."}), 429

    otp_code = f"{random.randint(100000, 999999)}"
    session["reg_otp_email"] = email
    session["reg_otp_hash"] = _hash_password(f"{email}:{otp_code}")
    session["reg_otp_expires"] = now + 600
    session["reg_otp_sent_at"] = now
    session["reg_verified_email"] = None

    sent, err_msg = _send_register_otp_email(email, full_name, otp_code)
    if not sent:
        return jsonify({"ok": False, "message": err_msg or "Failed to send OTP email."}), 500

    is_campus = (
        email.endswith("@alvascollege.org")
        or email.endswith(".edu.in")
        or email.endswith(".ac.in")
    )
    return jsonify({
        "ok": True,
        "message": f"6-digit OTP sent to {email}. Check your Inbox or Spam folder.",
        "is_campus": is_campus,
    })


@auth_bp.route("/verify-register-otp", methods=["POST"])
def verify_register_otp():
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip().lower()
    otp_input = (data.get("otp") or "").strip()

    saved_email = session.get("reg_otp_email")
    saved_hash = session.get("reg_otp_hash")
    expires_at = session.get("reg_otp_expires", 0)

    if not saved_email or not saved_hash or saved_email != email:
        return jsonify({"ok": False, "message": "Click 'Verify Email' first to receive an OTP for this address."}), 400

    if int(time.time()) > expires_at:
        return jsonify({"ok": False, "message": "OTP has expired. Click 'Resend OTP' for a new code."}), 400

    if not otp_input or len(otp_input) != 6 or _hash_password(f"{email}:{otp_input}") != saved_hash:
        return jsonify({"ok": False, "message": "Fake or incorrect OTP! Enter the exact 6-digit code from your email."}), 400

    session["reg_verified_email"] = email
    return jsonify({"ok": True, "message": "Email verified! Set your password and complete registration."})


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = (request.form.get("full_name") or request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        otp_code = (request.form.get("otp") or "").strip()
        password = (request.form.get("password") or "").strip()
        confirm_password = (request.form.get("confirm_password") or "").strip()
        college_name = (request.form.get("college_name") or "").strip() or None
        register_number = (request.form.get("register_number") or "").strip().upper() or None
        course_info = (request.form.get("course_info") or "").strip() or (
            f"{college_name} Student" if college_name else DEFAULT_COURSE_INFO
        )

        if not full_name or not email or not password:
            return render_template("register.html", error="Full Name, Email, and Password are required.")

        if len(password) < 6:
            return render_template("register.html", error="Password must be at least 6 characters.")

        if confirm_password and password != confirm_password:
            return render_template("register.html", error="Passwords do not match.")

        # Strict server-side OTP verification
        verified_email = session.get("reg_verified_email")
        saved_email = session.get("reg_otp_email")
        saved_hash = session.get("reg_otp_hash")
        expires_at = session.get("reg_otp_expires", 0)

        otp_valid = (verified_email == email)
        if not otp_valid:
            if (
                saved_email == email
                and saved_hash
                and int(time.time()) <= expires_at
                and otp_code
                and _hash_password(f"{email}:{otp_code}") == saved_hash
            ):
                otp_valid = True

        if not otp_valid:
            return render_template(
                "register.html",
                error="Please verify your email with the real 6-digit OTP sent to your inbox before registering."
            )

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO users (full_name, email, password, course_info, college_name, register_number)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (full_name, email, _hash_password(password), course_info, college_name, register_number)
            )
            conn.commit()
            new_user_id = cursor.lastrowid
            if not new_user_id:
                cursor.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email,))
                row = cursor.fetchone()
                new_user_id = row["id"] if row else None
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

        for key in ("reg_otp_email", "reg_otp_hash", "reg_otp_expires", "reg_otp_sent_at", "reg_verified_email"):
            session.pop(key, None)

        _send_welcome_email(email, full_name, college_name=college_name, register_number=register_number)

        session["user_id"] = new_user_id
        session["full_name"] = full_name
        session["avatar_url"] = ""
        session["course_info"] = course_info
        return redirect(url_for("dashboard"))

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
                "SELECT id, full_name, email, avatar_url, course_info FROM users WHERE email = ? AND password = ?",
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
            session["course_info"] = (user.get("course_info") or "").strip() or DEFAULT_COURSE_INFO
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
    return google.authorize_redirect(redirect_uri, prompt="select_account")


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