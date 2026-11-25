import requests
from config import Config
from database import get_db_connection


KARNATAKA_KEYWORDS = {
    "karnataka", "bengaluru", "bangalore", "mangaluru", "mangalore",
    "mysuru", "mysore", "moodabidire", "moodbidri", "udupi", "manipal",
    "hubballi", "hubli", "dharwad", "belagavi", "belgaum", "shivamogga",
    "tumakuru", "davangere", "ballari", "kalaburagi"
}

INDIA_KEYWORDS = {
    "india", "bharat", "remote india", "india remote", "pune", "hyderabad",
    "chennai", "mumbai", "delhi", "ncr", "bengaluru", "bangalore",
    "mangaluru", "mysuru", "kolkata", "ahmedabad", "noida", "gurugram",
    "gurgaon", "kochi", "coimbatore", "jaipur", "indore", "bhubaneswar"
} + KARNATAKA_KEYWORDS


CURATED_INDIA_KARNATAKA_JOBS = [
    {
        "id": "ka_01",
        "title": "Junior Python & Flask Developer",
        "company": "NammaTech Systems",
        "location": "Bengaluru, Karnataka",
        "job_type": "Full Time",
        "package_lpa": "5.5 - 8 LPA",
        "skills": ["Python", "Flask", "SQL", "HTML", "CSS", "Git"],
        "apply_url": "https://www.linkedin.com/jobs/search/?keywords=Python%20Flask%20Bengaluru",
        "description": "Build backend web services and REST APIs in Bengaluru.",
        "source": "Karnataka Career Feed"
    },
    {
        "id": "ka_02",
        "title": "Full Stack Web Developer Intern",
        "company": "Coastal Cloud Labs",
        "location": "Mangaluru, Karnataka",
        "job_type": "Internship",
        "package_lpa": "₹18k - ₹25k / mo",
        "skills": ["PHP", "MySQL", "JavaScript", "HTML", "CSS"],
        "apply_url": "https://www.linkedin.com/jobs/search/?keywords=Web%20Developer%20Intern%20Mangaluru",
        "description": "Hands-on web development internship near coastal Karnataka tech hubs.",
        "source": "Karnataka Career Feed"
    },
    {
        "id": "ka_03",
        "title": "Data Analyst & R / SQL Associate",
        "company": "Mysuru Analytics Works",
        "location": "Mysuru, Karnataka",
        "job_type": "Full Time",
        "package_lpa": "4.8 - 7 LPA",
        "skills": ["SQL", "R", "Python", "Data Analytics", "Excel"],
        "apply_url": "https://www.linkedin.com/jobs/search/?keywords=Data%20Analyst%20Mysuru",
        "description": "Analyze business datasets and create clear analytical dashboards.",
        "source": "Karnataka Career Feed"
    },
    {
        "id": "ka_04",
        "title": "Software Engineer Trainee (Fresher)",
        "company": "Hubballi Digital Solutions",
        "location": "Hubballi-Dharwad, Karnataka",
        "job_type": "Full Time",
        "package_lpa": "4.2 - 6 LPA",
        "skills": ["Python", "Java", "SQL", "Git", "Problem Solving"],
        "apply_url": "https://www.linkedin.com/jobs/search/?keywords=Software%20Engineer%20Hubballi",
        "description": "Fresher engineering role in North Karnataka with structured mentorship.",
        "source": "Karnataka Career Feed"
    },
    {
        "id": "ka_05",
        "title": "Frontend & UI Engineer",
        "company": "Sahyadri Softwares",
        "location": "Udupi / Manipal, Karnataka",
        "job_type": "Full Time",
        "package_lpa": "5 - 7.5 LPA",
        "skills": ["JavaScript", "HTML", "CSS", "React", "UI/UX"],
        "apply_url": "https://www.linkedin.com/jobs/search/?keywords=Frontend%20Developer%20Udupi",
        "description": "Craft responsive web interfaces for SaaS and edtech products.",
        "source": "Karnataka Career Feed"
    },
    {
        "id": "in_01",
        "title": "Software Development Engineer (Fresher)",
        "company": "Deccan Enterprise Tech",
        "location": "Pune, Maharashtra, India",
        "job_type": "Full Time",
        "package_lpa": "6 - 9 LPA",
        "skills": ["Python", "SQL", "REST APIs", "Git", "Docker"],
        "apply_url": "https://www.linkedin.com/jobs/search/?keywords=Software%20Engineer%20Pune%20India",
        "description": "Work on scalable enterprise applications across Indian offices.",
        "source": "India Career Feed"
    },
    {
        "id": "in_02",
        "title": "AI / ML & Python Associate",
        "company": "Hyderabad Cloud AI",
        "location": "Hyderabad, Telangana, India",
        "job_type": "Full Time",
        "package_lpa": "6.5 - 10 LPA",
        "skills": ["Python", "Machine Learning", "SQL", "Pandas", "NLP"],
        "apply_url": "https://www.linkedin.com/jobs/search/?keywords=Python%20AI%20Hyderabad%20India",
        "description": "Build data pipelines and ML-assisted workflows for enterprise clients.",
        "source": "India Career Feed"
    },
    {
        "id": "in_03",
        "title": "Backend Developer (Remote - India)",
        "company": "BharathSaaS Technologies",
        "location": "Remote (India)",
        "job_type": "Remote",
        "package_lpa": "5.5 - 8.5 LPA",
        "skills": ["Python", "PostgreSQL", "Flask", "API Design", "Git"],
        "apply_url": "https://www.linkedin.com/jobs/search/?keywords=Python%20Backend%20India%20Remote",
        "description": "Remote role open to candidates based in India.",
        "source": "India Career Feed"
    }
]


def _normalize_skills(raw):
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        return [x.strip() for x in raw.split(",") if x.strip()]
    return []


def classify_region(location_str):
    loc = (location_str or "").lower()
    if any(k in loc for k in KARNATAKA_KEYWORDS):
        return "karnataka", 1, "Karnataka", "#dcfce7", "#15803d"
    if any(k in loc for k in INDIA_KEYWORDS):
        return "india", 2, "India", "#fef3c7", "#b45309"
    return "global", 3, "Global / Other", "#f1f5f9", "#475569"


def _fetch_from_db_jobs():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC, id DESC")
        rows = cursor.fetchall()
        jobs = []
        for r in rows:
            jobs.append({
                "id": f"campus_{r['id']}",
                "db_id": r["id"],
                "title": r["title"],
                "company": r["company"],
                "location": r["location"] or "Moodabidire / Bengaluru, Karnataka",
                "job_type": r.get("job_type") or "Full Time",
                "package_lpa": r.get("package_lpa") or "",
                "skills": _normalize_skills(r.get("skills") or ""),
                "apply_url": r.get("apply_url") or "#",
                "description": r.get("description") or "",
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
            params={"q": query or "developer", "location": location or "Karnataka India"},
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
                "location": item.get("location") or "Bengaluru, Karnataka",
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


def _fetch_from_arbeitnow(query=""):
    try:
        resp = requests.get("https://www.arbeitnow.com/api/job-board-api", timeout=8)
        if resp.status_code != 200:
            return []
        payload = resp.json()
        raw_items = payload.get("data") or []
        q_low = (query or "").strip().lower()
        jobs = []
        for idx, item in enumerate(raw_items[:40], start=1):
            if not isinstance(item, dict):
                continue
            title = item.get("title") or "Software Role"
            company = item.get("company_name") or "Hiring Company"
            loc = item.get("location") or "Remote"
            tags = _normalize_skills(item.get("tags") or [])
            blob = f"{title} {company} {loc} {' '.join(tags)}".lower()
            if q_low and q_low not in blob:
                continue
            job_types = item.get("job_types") or []
            jtype = "Remote" if item.get("remote") else (job_types[0] if job_types else "Full Time")
            jobs.append({
                "id": f"arbeit_{item.get('slug') or idx}",
                "title": title,
                "company": company,
                "location": loc,
                "job_type": str(jtype).replace("_", " ").title(),
                "package_lpa": "",
                "skills": tags[:6],
                "apply_url": item.get("url") or "#",
                "description": "",
                "source": "Arbeitnow"
            })
        return jobs[:15]
    except Exception as exc:
        print(f"Arbeitnow API error: {exc}")
        return []


def _fetch_from_remotive(query="", location=""):
    term = " ".join(part for part in [query.strip(), location.strip()] if part).strip() or "software"
    try:
        resp = requests.get(
            "https://remotive.com/api/remote-jobs",
            params={"search": term, "limit": 20},
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
                "location": item.get("candidate_required_location") or "Remote (Global)",
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
    jobs.extend(CURATED_INDIA_KARNATAKA_JOBS)
    jobs.extend(_fetch_from_custom_api(q, loc))
    jobs.extend(_fetch_from_arbeitnow(q))
    jobs.extend(_fetch_from_remotive(q, loc))

    q_lower = q.lower()
    loc_lower = loc.lower()

    filtered = []
    seen_keys = set()
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

        dedup_key = f"{title.strip().lower()}|{company.strip().lower()}|{job_loc.strip().lower()}"
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        region_code, region_tier, region_label, badge_bg, badge_fg = classify_region(job_loc)
        item = dict(job)
        item["skills"] = skills
        item["region_code"] = region_code
        item["region_tier"] = region_tier
        item["region_label"] = region_label
        item["badge_bg"] = badge_bg
        item["badge_fg"] = badge_fg
        filtered.append(item)

    return filtered