import re

try:
    import spacy
    try:
        _NLP = spacy.load("en_core_web_sm")
    except Exception:
        _NLP = None
except Exception:
    _NLP = None

SKILL_CATALOG = {
    "python": "Python",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "c": "C",
    "c++": "C++",
    "c#": "C#",
    "php": "PHP",
    "r": "R",
    "sql": "SQL",
    "mysql": "MySQL",
    "sqlite": "SQLite",
    "postgresql": "PostgreSQL",
    "mongodb": "MongoDB",
    "html": "HTML",
    "html5": "HTML",
    "css": "CSS",
    "css3": "CSS",
    "bootstrap": "Bootstrap",
    "tailwind": "Tailwind CSS",
    "react": "React",
    "angular": "Angular",
    "vue": "Vue.js",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "flask": "Flask",
    "django": "Django",
    "fastapi": "FastAPI",
    "rest api": "REST API",
    "git": "Git",
    "github": "GitHub",
    "docker": "Docker",
    "aws": "AWS",
    "cloud computing": "Cloud Computing",
    "data analysis": "Data Analysis",
    "data analytics": "Data Analytics",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "excel": "Excel",
    "power bi": "Power BI",
    "tableau": "Tableau",
    "machine learning": "Machine Learning",
    "nlp": "NLP",
    "spacy": "spaCy",
    "problem solving": "Problem Solving",
    "communication": "Communication",
    "teamwork": "Teamwork",
    "team work": "Teamwork",
    "leadership": "Leadership",
}


def extract_skills(text):
    if not text or not str(text).strip():
        return []

    cleaned = re.sub(r"\s+", " ", str(text).lower())
    found = []
    seen = set()

    for token, label in SKILL_CATALOG.items():
        pattern = r"(?<![a-z0-9+#])" + re.escape(token) + r"(?![a-z0-9+#])"
        if re.search(pattern, cleaned) and label.lower() not in seen:
            seen.add(label.lower())
            found.append(label)

    if _NLP is not None:
        doc = _NLP(str(text)[:25000])
        for chunk in doc.noun_chunks:
            candidate = chunk.text.strip().lower()
            if candidate in SKILL_CATALOG:
                label = SKILL_CATALOG[candidate]
                if label.lower() not in seen:
                    seen.add(label.lower())
                    found.append(label)

    return found