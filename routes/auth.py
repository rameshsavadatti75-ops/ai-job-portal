import os
import random
import re
import time
import urllib.request
import json
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from database import get_db_connection

auth_bp = Blueprint("auth", __name__)


def _get_serializer():
    secret = os.environ.get("SECRET_KEY", "alvas-career-portal-secret-key")
    return URLSafeTimedSerializer(secret)


def send_brevo_email(to_email: str, to_name: str, subject: str, html_content: str) -> tuple[bool, str]:
    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    mail_from = os.environ.get("MAIL_FROM", "").strip()

    if not api_key or not mail_from:
        return False, "Email service is not configured on the server."

    payload = {
        "sender": {
            "name": "Alva's College Career Portal",
            "email": mail_from
        },
        "to": [
            {
                "email": to_email,
                "name": to_name or to_email.split("@")[0]
            }
        ],
        "subject": subject,
        "htmlContent": html_content
    }

    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if 200 <= resp.status < 300:
                return True, "Sent"
            return False, f"Email provider returned status {resp.status}"
    except Exception as exc:
        return False, str(exc)


@auth_bp.route("/send-register-otp", methods=["POST"])
def send_register_otp():
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip().lower()
    full_name = (data.get("full_name") or "").strip()

    if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"ok": False, "message": "Please enter a valid email address first."}), 400

    # Check if email is already registered
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE LOWER(email) = %s", (email,))
            if cur.fetchone():
                return jsonify({"ok": False, "message": "This email is already registered. Please sign in instead."}), 409
    finally:
        conn.close()

    # Rate-limit resend (30 seconds cooldown)
    last_sent = session.get("reg_otp_sent_at", 0)
    last_email = session.get("reg_otp_email", "")
    now = int(time.time())
    if last_email == email and (now - last_sent) < 30:
        wait_sec = 30 - (now - last_sent)
        return jsonify({"ok": False, "message": f"Please wait {wait_sec}s before requesting another OTP."}), 429

    otp_code = f"{random.randint(100000, 999999)}"
    session["reg_otp_email"] = email
    session["reg_otp_hash"] = generate_password_hash(otp_code)
    session["reg_otp_expires"] = now + 600  # 10 minutes
    session["reg_otp_sent_at"] = now
    session["reg_verified_email"] = None

    html_body = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:520px;margin:0 auto;padding:24px;border:1px solid #e2e8f0;border-radius:14px;background:#ffffff;">
        <h2 style="color:#0d3b8e;margin:0 0 8px;">Alva's College Student Career Portal</h2>
        <p style="color:#475569;font-size:14px;margin:0 0 18px;">Hello {full_name or 'Student'}, use the one-time verification code below to verify your email address and complete registration:</p>
        <div style="background:#eff6ff;border:1px dashed #2563eb;border-radius:10px;padding:16px;text-align:center;margin:16px 0;">
            <span style="font-size:30px;font-weight:800;letter-spacing:8px;color:#1d4ed8;">{otp_code}</span>
        </div>
        <p style="color:#64748b;font-size:12.5px;margin:14px 0 0;">This OTP expires in <strong>10 minutes</strong>. Do not share this code with anyone.</p>
    </div>
    """

    ok, err_msg = send_brevo_email(
        to_email=email,
        to_name=full_name,
        subject="Your Verification OTP - Alva's College Student Career Portal",
        html_content=html_body
    )

    if not ok:
        return jsonify({"ok": False, "message": f"Could not send OTP email: {err_msg}"}), 500

    is_campus = email.endswith("@alvascollege.org") or email.endswith(".edu.in") or email.endswith(".ac.in")
    return jsonify({
        "ok": True,
        "message": f"6-digit OTP sent to {email}. Check your Inbox or Spam folder.",
        "is_campus": is_campus
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
        return jsonify({"ok": False, "message": "Please click 'Verify Email' to receive an OTP for this email first."}), 400

    if int(time.time()) > expires_at:
        return jsonify({"ok": False, "message": "OTP has expired. Click 'Resend OTP' to get a new code."}), 400

    if not otp_input or len(otp_input) != 6 or not check_password_hash(saved_hash, otp_input):
        return jsonify({"ok": False, "message": "Invalid OTP entered. Please check your email and enter the exact 6-digit code."}), 400

    session["reg_verified_email"] = email
    return jsonify({"ok": True, "message": "Email verified successfully! You can now complete your registration."})


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, full_name, email, password_hash, course_info, avatar_url FROM users WHERE LOWER(email) = %s",
                (email,)
            )
            user = cur.fetchone()
    finally:
        conn.close()

    if not user or not user["password_hash"] or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid email address or password.")

    session["user_id"] = user["id"]
    session["user_name"] = user["full_name"]
    session["user_email"] = user["email"]
    session["course_info"] = user.get("course_info") or "Alva's College Student"
    session["avatar_url"] = user.get("avatar_url")
    return redirect(url_for("dashboard"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    full_name = (request.form.get("full_name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    otp_code = (request.form.get("otp") or "").strip()
    password = request.form.get("password") or ""
    confirm_password = request.form.get("confirm_password") or ""
    college_name = (request.form.get("college_name") or "").strip() or None
    register_number = (request.form.get("register_number") or "").strip().upper() or None

    if not full_name or not email or not password:
        return render_template("register.html", error="Full Name, Email, and Password are required.")

    if len(password) < 6:
        return render_template("register.html", error="Password must be at least 6 characters long.")

    if confirm_password and password != confirm_password:
        return render_template("register.html", error="Passwords do not match.")

    # Strict server-side OTP check (prevents bypassing frontend JS with fake OTP)
    verified_email = session.get("reg_verified_email")
    saved_email = session.get("reg_otp_email")
    saved_hash = session.get("reg_otp_hash")
    expires_at = session.get("reg_otp_expires", 0)

    is_verified = (verified_email == email)
    if not is_verified:
        if saved_email == email and saved_hash and int(time.time()) <= expires_at and check_password_hash(saved_hash, otp_code):
            is_verified = True

    if not is_verified:
        return render_template("register.html", error="Email OTP verification failed or expired. Please verify your real email OTP before creating an account.")

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE LOWER(email) = %s", (email,))
            if cur.fetchone():
                return render_template("register.html", error="An account with this email already exists. Please sign in.")

            default_course = f"{college_name} Student" if college_name else "Alva's College Student"
            cur.execute(
                """
                INSERT INTO users (full_name, email, password_hash, course_info, college_name, register_number)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (full_name, email, generate_password_hash(password), default_course, college_name, register_number)
            )
            new_user = cur.fetchone()
        conn.commit()
    finally:
        conn.close()

    # Clear OTP session keys
    for key in ("reg_otp_email", "reg_otp_hash", "reg_otp_expires", "reg_otp_sent_at", "reg_verified_email"):
        session.pop(key, None)

    # Send instant welcome email
    welcome_html = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:540px;margin:0 auto;padding:24px;border:1px solid #e2e8f0;border-radius:14px;background:#ffffff;">
        <h2 style="color:#0d3b8e;margin:0 0 10px;">Welcome to Alva's College Student Career Portal!</h2>
        <p style="color:#334155;font-size:14px;line-height:1.6;">Hi <strong>{full_name}</strong>,</p>
        <p style="color:#475569;font-size:14px;line-height:1.6;">Your student career account has been verified and activated. You can now upload your resume, view AI skill match scores, and apply to opportunities across Karnataka and India.</p>
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:12px 16px;margin:16px 0;font-size:13px;color:#334155;">
            <div><strong>Registered Email:</strong> {email}</div>
            {f'<div><strong>College:</strong> {college_name}</div>' if college_name else ''}
            {f'<div><strong>Register Number:</strong> {register_number}</div>' if register_number else ''}
        </div>
        <p style="color:#64748b;font-size:12px;margin-top:16px;">Skills Today. Better Tomorrow. &mdash; Alva's College, Moodubidire</p>
    </div>
    """
    send_brevo_email(
        to_email=email,
        to_name=full_name,
        subject="Welcome to Alva's College Student Career Portal",
        html_content=welcome_html
    )

    session["user_id"] = new_user["id"]
    session["user_name"] = full_name
    session["user_email"] = email
    session["course_info"] = f"{college_name} Student" if college_name else "Alva's College Student"
    return redirect(url_for("dashboard"))


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    email = (request.form.get("email") or "").strip().lower()
    if not email:
        return render_template("login.html", error="Please enter your registered email address.")

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, full_name FROM users WHERE LOWER(email) = %s", (email,))
            user = cur.fetchone()
    finally:
        conn.close()

    if user:
        token = _get_serializer().dumps(email, salt="password-reset-salt")
        reset_link = url_for("auth.reset_password", token=token, _external=True)
        html_body = f"""
        <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:520px;margin:0 auto;padding:24px;border:1px solid #e2e8f0;border-radius:14px;">
            <h2 style="color:#0d3b8e;">Reset Your Password</h2>
            <p style="color:#475569;font-size:14px;">Hi {user['full_name']}, click the button below to set a new password (valid for 30 minutes):</p>
            <p style="margin:20px 0;"><a href="{reset_link}" style="background:#1d63dc;color:#ffffff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;">Set New Password</a></p>
        </div>
        """
        send_brevo_email(email, user["full_name"], "Reset Your Password - Alva's College Student Career Portal", html_body)

    return render_template("login.html", info=f"Password reset link sent to {email}. Check your inbox (and spam folder); it expires in 30 minutes.")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = _get_serializer().loads(token, salt="password-reset-salt", max_age=1800)
    except (SignatureExpired, BadSignature):
        return render_template("login.html", error="Reset link is invalid or has expired. Please request a new one.")

    if request.method == "GET":
        return render_template("reset_password.html", email=email, token=token)

    new_password = request.form.get("password") or ""
    confirm_password = request.form.get("confirm_password") or ""
    if len(new_password) < 6 or new_password != confirm_password:
        return render_template("reset_password.html", email=email, token=token, error="Passwords must match and be at least 6 characters.")

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET password_hash = %s WHERE LOWER(email) = %s", (generate_password_hash(new_password), email))
        conn.commit()
    finally:
        conn.close()

    return render_template("login.html", info="Password updated successfully! Please sign in with your new password.")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))