"""Skill vocabulary: canonical names, aliases (Kaggle/Upwork spellings) and broad-skill expansion.

Used by requirement extraction (Fit Matcher), GigSim client preferences, and dev-set gold labels.
"""

from __future__ import annotations

import re
from functools import lru_cache

CANONICAL = [
    # languages / core
    "Python", "JavaScript", "TypeScript", "SQL", "R", "HTML", "CSS", "VBA", "DAX",
    # ML / AI
    "machine learning", "deep learning", "scikit-learn", "XGBoost", "LightGBM", "PyTorch", "TensorFlow",
    "pandas", "NumPy", "model evaluation", "feature engineering", "time series forecasting", "time series",
    "forecasting", "anomaly detection", "recommendation systems", "implicit feedback", "computer vision",
    "OpenCV", "YOLO", "OCR", "NLP", "spaCy", "Hugging Face Transformers", "sentence-transformers",
    "fine-tuning", "transfer learning", "LoRA fine-tuning", "LLM", "LangChain", "LangGraph", "RAG",
    "OpenAI API", "tool calling", "LLM evaluation", "RAGAS", "LLM summarisation", "Whisper", "FAISS",
    "Pinecone", "MLflow", "SHAP", "ONNX", "Bayesian optimisation", "A/B testing", "statistics",
    "regression", "logistic regression", "chatbot", "AI agents", "edge deployment",
    # web
    "React", "Next.js", "Vue", "Node.js", "Express", "NestJS", "Django", "FastAPI", "Flask", "REST APIs",
    "GraphQL", "Apollo", "Prisma", "PostgreSQL", "MongoDB", "MySQL", "Redis", "Celery", "Kafka",
    "WebSockets", "Stripe", "Stripe Connect", "webhooks", "idempotency keys", "OAuth 2.0", "OAuth",
    "Auth0", "SAML", "JWT auth", "Shopify", "WordPress", "headless CMS", "SEO", "Tailwind CSS", "PWA",
    "IndexedDB", "Firebase", "Supabase", "OpenAPI", "Playwright", "Jest", "GitHub Actions", "CI/CD",
    "Docker", "Kubernetes", "AWS", "AWS ECS", "AWS S3", "Terraform", "Vercel", "landing pages",
    "web development", "full stack development", "front-end development", "back-end development",
    "API integration", "Streamlit", "pytest",
    # data
    "data analysis", "data visualization", "Power BI", "Tableau", "Looker Studio", "Excel", "Google Sheets",
    "Apps Script", "Power Query", "dbt", "Snowflake", "BigQuery", "Fivetran", "Airflow", "ETL",
    "Google Analytics 4", "Google Tag Manager", "cohort analysis", "KPI reporting", "survey analysis",
    "financial modelling", "data cleaning", "fuzzy matching", "Metabase", "query optimisation",
    "geospatial analysis", "GeoPandas", "data modelling", "dashboards", "InfluxDB",
]

ALIASES = {
    "microsoft power bi": "Power BI", "power bi": "Power BI", "powerbi": "Power BI",
    "microsoft excel": "Excel", "excel": "Excel", "excel vba": "VBA", "excel formula": "Excel",
    "google data studio": "Looker Studio", "looker studio": "Looker Studio", "data studio": "Looker Studio",
    "google sheets": "Google Sheets", "google apps script": "Apps Script",
    "data visualization": "data visualization", "visualization": "data visualization", "data visualisation": "data visualization",
    "data analysis": "data analysis", "data analytics": "data analysis", "analytics": "data analysis",
    "machine learning": "machine learning", "ml": "machine learning", "deep learning": "deep learning",
    "artificial intelligence": "machine learning", "ai": "machine learning", "data science": "machine learning",
    "natural language processing": "NLP", "nlp": "NLP", "computer vision": "computer vision",
    "chatbot": "chatbot", "chatbot development": "chatbot", "ai chatbot": "chatbot",
    "large language model": "LLM", "llm": "LLM", "llms": "LLM", "generative ai": "LLM", "gpt": "OpenAI API",
    "chatgpt": "OpenAI API", "openai": "OpenAI API", "openai api": "OpenAI API", "gpt api": "OpenAI API",
    "langchain": "LangChain", "langgraph": "LangGraph", "retrieval augmented generation": "RAG", "rag": "RAG",
    "ai agent development": "AI agents", "ai agents": "AI agents", "agentic ai": "AI agents",
    "tensorflow": "TensorFlow", "pytorch": "PyTorch", "scikit-learn": "scikit-learn", "sklearn": "scikit-learn",
    "hugging face": "Hugging Face Transformers", "transformers": "Hugging Face Transformers",
    "javascript": "JavaScript", "js": "JavaScript", "typescript": "TypeScript", "react": "React",
    "reactjs": "React", "react.js": "React", "next.js": "Next.js", "nextjs": "Next.js", "vue.js": "Vue",
    "vuejs": "Vue", "vue": "Vue", "node.js": "Node.js", "nodejs": "Node.js", "node": "Node.js",
    "express": "Express", "expressjs": "Express", "nestjs": "NestJS", "django": "Django", "flask": "Flask",
    "fastapi": "FastAPI", "rest api": "REST APIs", "restful api": "REST APIs", "api": "REST APIs",
    "api development": "REST APIs", "api integration": "API integration", "graphql": "GraphQL",
    "postgresql": "PostgreSQL", "postgres": "PostgreSQL", "mongodb": "MongoDB", "mysql": "MySQL",
    "redis": "Redis", "celery": "Celery", "stripe": "Stripe", "shopify": "Shopify",
    "shopify development": "Shopify", "wordpress": "WordPress", "wordpress development": "WordPress",
    "search engine optimization": "SEO", "seo": "SEO", "tailwind css": "Tailwind CSS", "tailwind": "Tailwind CSS",
    "html5": "HTML", "html": "HTML", "css": "CSS", "css 3": "CSS", "firebase": "Firebase", "supabase": "Supabase",
    "docker": "Docker", "kubernetes": "Kubernetes", "amazon web services": "AWS", "aws": "AWS",
    "web development": "web development", "web application": "web development", "website development": "web development",
    "full-stack development": "full stack development", "full stack development": "full stack development",
    "front-end development": "front-end development", "frontend": "front-end development",
    "back-end development": "back-end development", "backend": "back-end development",
    "sql": "SQL", "python": "Python", "r": "R", "pandas": "pandas", "numpy": "NumPy",
    "tableau": "Tableau", "dbt": "dbt", "snowflake": "Snowflake", "bigquery": "BigQuery",
    "google bigquery": "BigQuery", "airflow": "Airflow", "apache airflow": "Airflow", "etl": "ETL",
    "etl pipeline": "ETL", "google analytics": "Google Analytics 4", "google analytics 4": "Google Analytics 4",
    "ga4": "Google Analytics 4", "google tag manager": "Google Tag Manager", "statistics": "statistics",
    "statistical analysis": "statistics", "a/b testing": "A/B testing", "forecasting": "forecasting",
    "time series analysis": "time series", "dashboard": "dashboards", "dashboards": "dashboards",
    "data cleaning": "data cleaning", "data mining": "data analysis", "data modeling": "data modelling",
    "financial modeling": "financial modelling", "metabase": "Metabase", "playwright": "Playwright",
    "jest": "Jest", "github actions": "GitHub Actions", "ci/cd": "CI/CD", "terraform": "Terraform",
    "oauth": "OAuth", "auth0": "Auth0", "websocket": "WebSockets", "websockets": "WebSockets",
    "opencv": "OpenCV", "yolo": "YOLO", "ocr": "OCR", "spacy": "spaCy", "pinecone": "Pinecone",
    "faiss": "FAISS", "mlflow": "MLflow", "xgboost": "XGBoost", "lightgbm": "LightGBM", "streamlit": "Streamlit",
    "whisper": "Whisper", "kafka": "Kafka", "prisma": "Prisma", "vercel": "Vercel",
}

BROAD = {
    "machine learning": ["scikit-learn", "XGBoost", "LightGBM", "PyTorch", "TensorFlow", "model evaluation", "feature engineering"],
    "deep learning": ["PyTorch", "TensorFlow", "computer vision", "Hugging Face Transformers", "fine-tuning"],
    "LLM": ["LangChain", "LangGraph", "RAG", "OpenAI API", "LLM evaluation", "LLM summarisation"],
    "chatbot": ["RAG", "LangChain", "OpenAI API", "LangGraph"],
    "AI agents": ["LangGraph", "LangChain", "tool calling", "OpenAI API"],
    "NLP": ["spaCy", "Hugging Face Transformers", "sentence-transformers", "LLM summarisation"],
    "data analysis": ["SQL", "pandas", "Excel", "statistics", "cohort analysis"],
    "data visualization": ["Power BI", "Tableau", "Looker Studio", "Metabase", "Streamlit", "dashboards"],
    "dashboards": ["Power BI", "Tableau", "Looker Studio", "Metabase", "Streamlit"],
    "web development": ["React", "Next.js", "Node.js", "Django", "TypeScript"],
    "full stack development": ["React", "Next.js", "Node.js", "Django", "PostgreSQL"],
    "front-end development": ["React", "Next.js", "Vue", "Tailwind CSS", "TypeScript"],
    "back-end development": ["Node.js", "Django", "FastAPI", "PostgreSQL", "REST APIs"],
    "REST APIs": ["REST APIs", "FastAPI", "Express", "Node.js", "OpenAPI"],
    "forecasting": ["time series forecasting", "LightGBM", "forecasting"],
    "AWS": ["AWS ECS", "AWS S3", "Terraform"],
}

_CANON_BY_KEY = {c.lower(): c for c in CANONICAL}


def _key(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def canon(skill: str) -> str:
    k = _key(skill)
    if k in ALIASES:
        return ALIASES[k]
    if k in _CANON_BY_KEY:
        return _CANON_BY_KEY[k]
    return skill.strip()


def expand(skill: str) -> list[str]:
    c = canon(skill)
    return [c] + BROAD.get(c, [])


@lru_cache(maxsize=1)
def _mention_patterns() -> list[tuple[str, re.Pattern[str]]]:
    terms: dict[str, str] = {}
    for c in CANONICAL:
        terms[c.lower()] = c
    for alias, c in ALIASES.items():
        if len(alias) >= 3 or alias in {"r", "ai", "ml", "js"}:
            terms[alias] = c
    pats = []
    for term, c in sorted(terms.items(), key=lambda kv: -len(kv[0])):
        if term in {"r", "ai", "ml", "js", "api", "node", "express", "excel", "react", "vue"}:
            # short / ambiguous: require word boundaries and original casing hint
            rx = re.compile(rf"(?<![\w.]){re.escape(term)}(?![\w])", re.IGNORECASE)
        else:
            rx = re.compile(rf"(?<![\w]){re.escape(term)}(?![\w])", re.IGNORECASE)
        pats.append((c, rx))
    return pats


def extract_skills(text: str) -> list[str]:
    """Canonical skills mentioned in free text, most specific first, de-duplicated."""
    found: list[str] = []
    low = text or ""
    for c, rx in _mention_patterns():
        if c in found:
            continue
        if c == "R":
            if re.search(r"(?<![\w])R(?![\w+#])(?=\s|,|/|\))", low) and re.search(r"\b(R (language|programming|studio|script)|in R\b|using R\b|RStudio)", low):
                found.append(c)
            continue
        if c == "machine learning" and not re.search(r"\b(machine learning|ml|ai|artificial intelligence|data science)\b", low, re.I):
            continue
        if rx.search(low):
            found.append(c)
    return found
