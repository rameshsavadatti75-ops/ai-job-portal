import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, session
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from database import init_db, get_db_connection
from routes.auth import auth_bp, init_oauth
from routes.resume import resume_bp
from routes.jobs import jobs_bp
from routes.profile import profile_bp
from services.job_api import fetch_jobs
from services.matching import calculate_job_matches, calculate_resume_strength

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

init_oauth(app)

app.register_blueprint(auth_bp)
app.register_blueprint(resume_bp)
app.register_blueprint(jobs_bp)
app.register_blueprint(profile_bp)

os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
with app.app_context():
    init_db()


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("auth.login"))


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    user_id = session["user_id"]
    full_name = session.get("full_name", "Student")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT resume_filepath, parsed_skills, uploaded_at FROM resumes WHERE user_id = ? ORDER BY uploaded_at DESC, id DESC LIMIT 1",
            (user_id,)
        )
        resume_record = cursor.fetchone()

        cursor.execute(
            "SELECT action_type, COUNT(*) AS total FROM job_actions WHERE user_id = ? GROUP BY action_type",
            (user_id,)
        )
        counts = {row["action_type"]: row["total"] for row in cursor.fetchall()}
    finally:
        cursor.close()
        conn.close()

    resume_filename = None
    upload_date = None
    skills_list = []

    if resume_record:
        filepath = resume_record["resume_filepath"]
        resume_filename = os.path.basename(filepath) if filepath else None

        raw_date = resume_record["uploaded_at"]
        if raw_date:
            try:
                upload_date = datetime.fromisoformat(str(raw_date)).strftime("%d %b %Y")
            except ValueError:
                upload_date = str(raw_date)
        else:
            upload_date = "Recent"

        raw_skills = resume_record["parsed_skills"]
        if raw_skills:
            skills_list = [s.strip() for s in str(raw_skills).split(",") if s.strip()]

    ranked_jobs = calculate_job_matches(skills_list, fetch_jobs())
    top_jobs = ranked_jobs[:3]
    best_match = ranked_jobs[0]["match_score"] if ranked_jobs else 0
    strength_score, strength_tips = calculate_resume_strength(skills_list, bool(resume_filename))

    return render_template(
        "dashboard.html",
        full_name=full_name,
        resume_filename=resume_filename,
        upload_date=upload_date,
        skills_list=skills_list,
        recommended_count=len(ranked_jobs),
        applied_count=counts.get("applied", 0),
        saved_count=counts.get("saved", 0),
        best_match_score=best_match,
        strength_score=strength_score,
        strength_tips=strength_tips,
        top_jobs=top_jobs
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "1") == "1")