import os
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, session
from config import Config
from database import get_db_connection
from services.resume_parser import extract_text_from_file
from services.skill_extractor import extract_skills

resume_bp = Blueprint("resume", __name__)


def _allowed_file(filename):
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in Config.ALLOWED_EXTENSIONS


def _load_latest_resume(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT resume_filepath, parsed_skills, uploaded_at FROM resumes WHERE user_id = ? ORDER BY uploaded_at DESC, id DESC LIMIT 1",
            (user_id,)
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


@resume_bp.route("/upload", methods=["GET", "POST"])
def upload_resume():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    user_id = session["user_id"]
    error = None
    success = None

    if request.method == "POST":
        file = request.files.get("resume_file") or request.files.get("resume")

        if not file or not file.filename:
            error = "Please select a PDF or DOCX resume file to upload."
        elif not _allowed_file(file.filename):
            error = "Unsupported file format. Please upload a .pdf or .docx file."
        else:
            os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
            safe_name = secure_filename(file.filename)
            stored_name = f"user_{user_id}_{safe_name}"
            filepath = os.path.join(Config.UPLOAD_FOLDER, stored_name)
            file.save(filepath)

            extracted_text = extract_text_from_file(filepath)
            if not extracted_text.strip():
                error = "File saved, but no readable text could be extracted. Make sure your PDF/DOCX is not a scanned image."
            else:
                skills = extract_skills(extracted_text)
                skills_csv = ", ".join(skills)

                conn = get_db_connection()
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        "INSERT INTO resumes (user_id, resume_filepath, parsed_skills) VALUES (?, ?, ?)",
                        (user_id, filepath, skills_csv)
                    )
                    conn.commit()
                finally:
                    cursor.close()
                    conn.close()

                if skills:
                    success = f"Resume parsed! Extracted {len(skills)} skills: {skills_csv}"
                else:
                    success = "Resume parsed and saved, but no catalog skills were detected yet. Check that your skill keywords appear in the resume text."

    latest = _load_latest_resume(user_id)
    latest_filename = os.path.basename(latest["resume_filepath"]) if latest and latest["resume_filepath"] else None
    latest_skills = [s.strip() for s in str(latest["parsed_skills"] or "").split(",") if s.strip()] if latest else []

    return render_template(
        "upload_resume.html",
        full_name=session.get("full_name", "Student"),
        error=error,
        success=success,
        latest_filename=latest_filename,
        latest_skills=latest_skills
    )