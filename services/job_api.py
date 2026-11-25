import sqlite3
import requests
from config import Config


def _normalize_skills(raw):
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        return [x.strip() for x in raw.split(",") if x.strip()]
    return []


def _fetch_from_db_jobs():
    conn = sqlite3.connect(Config.DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
        if not cursor.fetchone():
            return []

        cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC, id DESC")
        rows = cursor.fetchall()
        jobs = []
        for r in rows:
            jobs.append({
                "id": f"campus_{r['id']}",
                "db_id": r["id"],
                "title": r["title"],
                "company": r["company"],
                "location": r["location"] or "Moodabidire / Bengaluru",
                "job_type": r["job_type"] or "Full Time",
                "package_lpa": r["package_lpa"] if "package_lpa" in r.keys() else "",
                "skills": _normalize_skills(r["skills"]),
                "apply_url": r["apply_url"] or "#",
                "description": r["description"] if "description" in r.keys() else "",
                "source": "Campus Drive"
            })
        return jobs
    except Exception as exc:
        print(f"DB jobs fetch error: {exc}")
        return []
    finally:
        cursor.close()
        conn.close()


def _fetch_from_custom_api(query="", location=""):
    api_url = (Config.JOB_API_URL or "").strip()
    if not api_url:
        return []

    headers = {"Accept": "application/json"}
    if Config.JOB_API_KEY:
        headers["Authorization"] = f"Bearer {Config.JOB_API_KEY}"

    try:
        resp = requests.get(
            api_url,
            params={"q": query or "developer", "location": location or "India"},
            headers=headers,
            timeout=8
        )
        if resp.status_code != 200:
            return []

        payload = resp.json()
        raw_items = payload.get("jobs") or payload.get("results") or payload.get("data") or []
        if not isinstance(raw_items, list):
            return []

        jobs = []
        for idx, item in enumerate(raw_items, start=1):
            if not isinstance(item, dict):
                continue
            jobs.append({
                "id": item.get("id", f"api_{idx}"),
                "title": item.get("title") or "Software Developer",
                "company": item.get("company") or item.get("company_name") or "Hiring Company",
                "location": item.get("location") or "India",
                "job_type": item.get("job_type") or "Full Time",
                "package_lpa": item.get("salary") or "",
                "skills": _normalize_skills(item.get("skills") or item.get("tags") or []),
                "apply_url": item.get("url") or item.get("apply_url") or "#",
                "description": "",
                "source": "Live API"
            })
        return jobs
    except Exception as exc:
        print(f"Custom API error: {exc}")
        return []


def _fetch_from_remotive(query="", location=""):
    term = " ".join(part for part in [query.strip(), location.strip()] if part).strip() or "software"
    try:
        resp = requests.get(
            "https://remotive.com/api/remote-jobs",
            params={"search": term, "limit": 25},
            timeout=8
        )
        if resp.status_code != 200:
            return []

        payload = resp.json()
        raw_items = payload.get("jobs") or []
        jobs = []
        for idx, item in enumerate(raw_items, start=1):
            if not isinstance(item, dict):
                continue
            tags = _normalize_skills(item.get("tags") or [])
            jobs.append({
                "id": item.get("id", f"remotive_{idx}"),
                "title": item.get("title") or "Software Engineer",
                "company": item.get("company_name") or "Hiring Company",
                "location": item.get("candidate_required_location") or "Remote",
                "job_type": str(item.get("job_type") or "full_time").replace("_", " ").title(),
                "package_lpa": item.get("salary") or "",
                "skills": tags[:6],
                "apply_url": item.get("url") or "#",
                "description": "",
                "source": "Remotive API"
            })
        return jobs
    except Exception as exc:
        print(f"Remotive API error: {exc}")
        return []


def fetch_jobs(query="", location=""):
    q = (query or "").strip()
    loc = (location or "").strip()

    jobs = []
    jobs.extend(_fetch_from_db_jobs())
    jobs.extend(_fetch_from_custom_api(q, loc))
    jobs.extend(_fetch_from_remotive(q, loc))

    q_lower = q.lower()
    loc_lower = loc.lower()

    filtered = []
    for job in jobs:
        title = str(job.get("title") or "")
        company = str(job.get("company") or "")
        job_loc = str(job.get("location") or "")
        skills = _normalize_skills(job.get("skills") or [])
        searchable = f"{title} {company} {job_loc} {' '.join(skills)}".lower()

        if q_lower and q_lower not in searchable:
            continue
        if loc_lower and loc_lower not in job_loc.lower():
            continue

        item = dict(job)
        item["skills"] = skills
        filtered.append(item)

    return filtered