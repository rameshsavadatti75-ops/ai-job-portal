import hashlib
from flask import Blueprint, render_template, request, redirect, url_for, session
from database import get_db_connection

profile_bp = Blueprint("profile", __name__)


def _load_profile_data(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, full_name, email, created_at FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()

        cursor.execute(
            "SELECT resume_filepath, parsed_skills, uploaded_at FROM resumes WHERE user_id = ? ORDER BY uploaded_at DESC, id DESC LIMIT 1",
            (user_id,)
        )
        resume = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    skills = []
    if resume and resume["parsed_skills"]:
        skills = [s.strip() for s in str(resume["parsed_skills"]).split(",") if s.strip()]
    return user, resume, skills


@profile_bp.route("/profile")
def view_profile():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    user, resume, skills = _load_profile_data(session["user_id"])
    return render_template(
        "portal_pages.html",
        page_type="profile",
        page_title="Student Profile",
        full_name=session.get("full_name", "Student"),
        user=user,
        resume=resume,
        skills=skills,
        message=None
    )


@profile_bp.route("/career-resources")
def career_resources():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    return render_template(
        "portal_pages.html",
        page_type="resources",
        page_title="Career Resources",
        full_name=session.get("full_name", "Student"),
        user=None,
        resume=None,
        skills=[],
        message=None
    )


@profile_bp.route("/settings", methods=["GET", "POST"])
def settings():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    user_id = session["user_id"]
    message = None

    if request.method == "POST":
        new_name = (request.form.get("full_name") or "").strip()
        new_password = (request.form.get("new_password") or "").strip()

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            if new_name:
                cursor.execute("UPDATE users SET full_name = ? WHERE id = ?", (new_name, user_id))
                session["full_name"] = new_name
            if new_password:
                hashed = hashlib.sha256(new_password.encode("utf-8")).hexdigest()
                cursor.execute("UPDATE users SET password = ? WHERE id = ?", (hashed, user_id))
            conn.commit()
            message = "Settings saved successfully."
        finally:
            cursor.close()
            conn.close()

    user, resume, skills = _load_profile_data(user_id)
    return render_template(
        "portal_pages.html",
        page_type="settings",
        page_title="Settings",
        full_name=session.get("full_name", "Student"),
        user=user,
        resume=resume,
        skills=skills,
        message=message
    )


@profile_bp.route("/help-support")
def help_support():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    return render_template(
        "portal_pages.html",
        page_type="help",
        page_title="Help & Support",
        full_name=session.get("full_name", "Student"),
        user=None,
        resume=None,
        skills=[],
        message=None
    )