from flask import Blueprint, render_template, request, redirect, url_for, session
from database import get_db_connection
from services.job_api import fetch_jobs
from services.matching import calculate_job_matches

jobs_bp = Blueprint("jobs", __name__)


def _load_latest_user_skills(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT parsed_skills FROM resumes WHERE user_id = ? ORDER BY uploaded_at DESC, id DESC LIMIT 1",
            (user_id,)
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not row or not row["parsed_skills"]:
        return []
    return [s.strip() for s in str(row["parsed_skills"]).split(",") if s.strip()]


def _get_user_action_keys(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT job_key, action_type FROM job_actions WHERE user_id = ?",
            (user_id,)
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    applied = {r["job_key"] for r in rows if r["action_type"] == "applied"}
    saved = {r["job_key"] for r in rows if r["action_type"] == "saved"}
    return applied, saved


def _attach_flags(jobs, applied_keys, saved_keys):
    out = []
    for job in jobs:
        item = dict(job)
        key = f"{str(item.get('title', '')).strip().lower()}|{str(item.get('company', '')).strip().lower()}"
        item["job_key"] = key
        item["is_applied"] = key in applied_keys
        item["is_saved"] = key in saved_keys
        out.append(item)
    return out


@jobs_bp.route("/jobs")
def find_jobs():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    user_id = session["user_id"]
    query = request.args.get("q", "").strip()
    location = request.args.get("location", "").strip()

    skills = _load_latest_user_skills(user_id)
    ranked = calculate_job_matches(skills, fetch_jobs(query=query, location=location))
    applied_keys, saved_keys = _get_user_action_keys(user_id)

    return render_template(
        "jobs.html",
        full_name=session.get("full_name", "Student"),
        jobs=_attach_flags(ranked, applied_keys, saved_keys),
        user_skills=skills,
        query=query,
        location=location,
        page_title="Find Jobs"
    )


@jobs_bp.route("/recommended-jobs")
def recommended_jobs():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    user_id = session["user_id"]
    skills = _load_latest_user_skills(user_id)
    all_ranked = calculate_job_matches(skills, fetch_jobs())
    strong = [j for j in all_ranked if j["match_score"] >= 40]
    ranked = strong if strong else all_ranked
    applied_keys, saved_keys = _get_user_action_keys(user_id)

    return render_template(
        "jobs.html",
        full_name=session.get("full_name", "Student"),
        jobs=_attach_flags(ranked, applied_keys, saved_keys),
        user_skills=skills,
        query="",
        location="",
        page_title="Recommended Jobs"
    )


@jobs_bp.route("/applied-jobs")
def applied_jobs():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    user_id = session["user_id"]
    skills = _load_latest_user_skills(user_id)
    applied_keys, saved_keys = _get_user_action_keys(user_id)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT * FROM job_actions WHERE user_id = ? AND action_type = 'applied' ORDER BY created_at DESC, id DESC",
            (user_id,)
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    jobs = []
    for r in rows:
        jobs.append({
            "job_key": r["job_key"],
            "title": r["title"],
            "company": r["company"],
            "location": r["location"] or "India",
            "job_type": r["job_type"] or "Full Time",
            "package_lpa": "",
            "skills": [s.strip() for s in str(r["skills"] or "").split(",") if s.strip()],
            "apply_url": r["apply_url"] or "#",
            "match_score": r["match_score"] or 0,
            "missing_skills": [],
            "source": "Tracked Application",
            "is_applied": True,
            "is_saved": r["job_key"] in saved_keys
        })

    return render_template(
        "jobs.html",
        full_name=session.get("full_name", "Student"),
        jobs=jobs,
        user_skills=skills,
        query="",
        location="",
        page_title="Applied Jobs"
    )


@jobs_bp.route("/saved-jobs")
def saved_jobs():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    user_id = session["user_id"]
    skills = _load_latest_user_skills(user_id)
    applied_keys, saved_keys = _get_user_action_keys(user_id)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT * FROM job_actions WHERE user_id = ? AND action_type = 'saved' ORDER BY created_at DESC, id DESC",
            (user_id,)
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    jobs = []
    for r in rows:
        jobs.append({
            "job_key": r["job_key"],
            "title": r["title"],
            "company": r["company"],
            "location": r["location"] or "India",
            "job_type": r["job_type"] or "Full Time",
            "package_lpa": "",
            "skills": [s.strip() for s in str(r["skills"] or "").split(",") if s.strip()],
            "apply_url": r["apply_url"] or "#",
            "match_score": r["match_score"] or 0,
            "missing_skills": [],
            "source": "Saved Role",
            "is_applied": r["job_key"] in applied_keys,
            "is_saved": True
        })

    return render_template(
        "jobs.html",
        full_name=session.get("full_name", "Student"),
        jobs=jobs,
        user_skills=skills,
        query="",
        location="",
        page_title="Saved Jobs"
    )


@jobs_bp.route("/post-job", methods=["GET", "POST"])
def post_job():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    user_id = session["user_id"]
    error = None
    success = None

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        company = (request.form.get("company") or "").strip()
        location = (request.form.get("location") or "").strip()
        job_type = (request.form.get("job_type") or "Full Time").strip()
        package_lpa = (request.form.get("package_lpa") or "").strip()
        skills = (request.form.get("skills") or "").strip()
        apply_url = (request.form.get("apply_url") or "#").strip()
        description = (request.form.get("description") or "").strip()

        if not title or not company or not location or not skills:
            error = "Job Title, Company, Location, and Required Skills are required."
        else:
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO jobs (posted_by, title, company, location, job_type, package_lpa, skills, apply_url, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, title, company, location, job_type, package_lpa, skills, apply_url, description)
                )
                conn.commit()
                success = f"Published '{title}' at {company} to live campus job listings!"
            finally:
                cursor.close()
                conn.close()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC, id DESC")
        posted_jobs = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    return render_template(
        "post_job.html",
        full_name=session.get("full_name", "Student"),
        posted_jobs=posted_jobs,
        error=error,
        success=success
    )


@jobs_bp.route("/jobs/delete/<int:job_id>", methods=["POST"])
def delete_job(job_id):
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("jobs.post_job"))


@jobs_bp.route("/jobs/action", methods=["POST"])
def record_job_action():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    user_id = session["user_id"]
    action_type = (request.form.get("action_type") or "").strip()
    title = (request.form.get("title") or "").strip()
    company = (request.form.get("company") or "").strip()
    location = (request.form.get("location") or "India").strip()
    job_type = (request.form.get("job_type") or "Full Time").strip()
    skills = (request.form.get("skills") or "").strip()
    apply_url = (request.form.get("apply_url") or "#").strip()
    match_score = int(request.form.get("match_score") or 0)
    next_url = request.form.get("next_url") or url_for("jobs.find_jobs")

    if title and company:
        job_key = f"{title.lower()}|{company.lower()}"
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            if action_type == "unsave":
                cursor.execute(
                    "DELETE FROM job_actions WHERE user_id = ? AND job_key = ? AND action_type = 'saved'",
                    (user_id, job_key)
                )
            elif action_type in {"applied", "saved"}:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO job_actions
                    (user_id, job_key, title, company, location, job_type, skills, apply_url, match_score, action_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, job_key, title, company, location, job_type, skills, apply_url, match_score, action_type)
                )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    return redirect(next_url)