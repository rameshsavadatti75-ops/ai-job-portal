def calculate_job_matches(user_skills, jobs):
    user_set = {
        str(skill).strip().lower()
        for skill in (user_skills or [])
        if str(skill).strip()
    }

    ranked = []
    for job in (jobs or []):
        req_skills = [
            str(s).strip()
            for s in (job.get("skills") or [])
            if str(s).strip()
        ]

        if not req_skills:
            matched = []
            missing = []
            score = 50 if user_set else 0
        else:
            matched = [s for s in req_skills if s.lower() in user_set]
            missing = [s for s in req_skills if s.lower() not in user_set]
            score = int(round((len(matched) / len(req_skills)) * 100))

        item = dict(job)
        item["skills"] = req_skills
        item["matched_skills"] = matched
        item["missing_skills"] = missing
        item["match_score"] = score
        ranked.append(item)

    ranked.sort(key=lambda j: (j["match_score"], len(j["matched_skills"])), reverse=True)
    return ranked


def calculate_resume_strength(skills_list, has_resume):
    if not has_resume:
        return 20, [
            "Upload PDF or DOCX resume",
            "Extract core technical skills",
            "Unlock AI job match scoring",
            "Track placement applications"
        ]

    count = len(skills_list or [])
    score = min(98, 45 + (count * 7))
    tips = [
        "Resume parsed successfully",
        f"{count} skills identified" if count else "Add more skill keywords",
        "Structured for role matching",
        "Ready for job applications"
    ]
    return score, tips