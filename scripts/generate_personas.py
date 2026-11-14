"""Generate the three SYNTHETIC persona corpora under data/personas/.

Per persona:
  profile.json          rates, floor, connects budget (synthetic)
  cv.pdf                PDF CV (exercises the PDF loader)
  case_studies/*.md     one per project, client-facing prose; implied skills described, not named
  repos/<slug>/         README (technical; lists only explicit stack) + code whose imports reveal implied skills
  reviews.json          client reviews (synthetic clients)
  proposals.jsonl       ~150 past proposals with outcome won / replied / ignored
  _gold_projects.json   ground-truth registry used ONLY for dev-set gold labels (never ingested)

Past-proposal job titles are real Upwork titles from the Kaggle 60k dataset (Apache-2.0) when it is
available locally; everything else is synthetic. Deterministic: seed 4016.

    python -m scripts.generate_personas
"""

from __future__ import annotations

import csv
import json
import math
import random
import re
import shutil
import sys
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.skills import canon, extract_skills  # noqa: E402
from scripts.persona_specs import IMPLIED_PHRASES, PERSONAS  # noqa: E402

OUT = ROOT / "data" / "personas"
KAGGLE_60K = ROOT / "data" / "raw" / "kaggle" / "upwork-freelance-jobs-60k" / "Final_Upwork_Dataset.csv"
SEED = 4016

# --------------------------------------------------------------------------- code snippets
SNIPPETS: dict[str, tuple[str, str]] = {
    # skill: (filename, code)
    "Celery": ("tasks.py", 'from celery import Celery\n\napp = Celery("{slug}", broker="redis://redis:6379/0")\n\n\n@app.task(bind=True, max_retries=3, default_retry_delay=30)\ndef process_item(self, item_id: str) -> dict:\n    try:\n        return run_pipeline(item_id)\n    except TransientError as exc:\n        raise self.retry(exc=exc)\n'),
    "Redis": ("cache.py", 'import redis\n\nr = redis.Redis.from_url(REDIS_URL)\n\n\ndef cached(key: str, ttl: int = 300):\n    hit = r.get(key)\n    if hit:\n        return json.loads(hit)\n    value = compute(key)\n    r.setex(key, ttl, json.dumps(value))\n    return value\n'),
    "Airflow": ("dags/daily_pipeline.py", 'from airflow import DAG\nfrom airflow.operators.python import PythonOperator\n\nwith DAG("{slug}_daily", schedule="0 5 * * *", catchup=False, default_args={{"retries": 2}}) as dag:\n    extract = PythonOperator(task_id="extract", python_callable=extract_sources)\n    load = PythonOperator(task_id="load", python_callable=load_warehouse)\n    extract >> load\n'),
    "Docker": ("Dockerfile", 'FROM python:3.11-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\nCMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]\n'),
    "Kubernetes": ("k8s/deployment.yaml", 'apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: {slug}\nspec:\n  replicas: 2\n---\napiVersion: autoscaling/v2\nkind: HorizontalPodAutoscaler\nmetadata:\n  name: {slug}\nspec:\n  minReplicas: 2\n  maxReplicas: 10\n'),
    "MLflow": ("train.py", 'import mlflow\n\nwith mlflow.start_run(run_name="{slug}"):\n    model = train(X_train, y_train)\n    mlflow.log_metric("val_score", evaluate(model, X_val, y_val))\n    mlflow.sklearn.log_model(model, "model")\n'),
    "SHAP": ("explain.py", 'import shap\n\nexplainer = shap.TreeExplainer(model)\nshap_values = explainer.shap_values(X_customer)\ntop_reasons = rank_features(shap_values)\n'),
    "Pinecone": ("vector_store.py", 'from pinecone import Pinecone\n\npc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])\nindex = pc.Index("{slug}")\nindex.upsert(vectors=[(c.id, embed(c.text), c.meta) for c in chunks])\n'),
    "ONNX": ("export.py", 'import torch\n\ntorch.onnx.export(model, dummy_input, "model.onnx", opset_version=17)\nsession = onnxruntime.InferenceSession("model.onnx")\n'),
    "edge deployment": ("jetson/run.sh", '#!/bin/sh\n# runs on an NVIDIA Jetson next to the camera\npython3 infer.py --engine model.trt --camera /dev/video0 --fps 30\n'),
    "A/B testing": ("experiment.py", 'from scipy import stats\n\ndef ab_result(conv_a, n_a, conv_b, n_b):\n    table = [[conv_a, n_a - conv_a], [conv_b, n_b - conv_b]]\n    return stats.chi2_contingency(table)\n'),
    "Kafka": ("consumer.py", 'from confluent_kafka import Consumer\n\nconsumer = Consumer({{"group.id": "{slug}-scorer", "bootstrap.servers": BROKERS}})\nconsumer.subscribe(["transactions"])\n'),
    "LoRA fine-tuning": ("finetune.py", 'from peft import LoraConfig, get_peft_model\n\nconfig = LoraConfig(r=8, lora_alpha=16, target_modules=["q_proj", "v_proj"])\nmodel = get_peft_model(base_model, config)\n'),
    "PostgreSQL": ("db.py", 'import psycopg\n\nwith psycopg.connect(DATABASE_URL) as conn:\n    conn.execute("CREATE TABLE IF NOT EXISTS audit (id serial primary key, payload jsonb)")\n'),
    "AWS S3": ("storage.py", 'import boto3\n\ns3 = boto3.client("s3")\ns3.upload_file(local_path, BUCKET, key)\n'),
    "InfluxDB": ("ingest.py", 'from influxdb_client import InfluxDBClient\n\nwrite_api = InfluxDBClient(url=URL, token=TOKEN).write_api()\nwrite_api.write(bucket="sensors", record=points)\n'),
    "GitHub Actions": (".github/workflows/eval.yml", 'name: eval\non: [pull_request]\njobs:\n  eval:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: pytest evals/ --threshold 0.8\n'),
    "webhooks": ("webhooks.ts", 'export async function POST(req: Request) {{\n  const event = stripe.webhooks.constructEvent(await req.text(), sig, secret);\n  if (event.type === "invoice.payment_failed") await startDunning(event.data.object);\n}}\n'),
    "WebSockets": ("socket.ts", 'import {{ WebSocketServer }} from "ws";\n\nconst wss = new WebSocketServer({{ port: 8080 }});\nwss.on("connection", (ws) => ws.on("message", (m) => broadcast(m)));\n'),
    "Vercel": ("vercel.json", '{{ "framework": "nextjs", "github": {{ "autoJobCancelation": true }} }}\n'),
    "OAuth": ("auth.ts", 'export const authOptions = {{ providers: [GoogleProvider({{ clientId, clientSecret }})] }};\n'),
    "role-based access control": ("permissions.ts", 'export const can = (role: Role, action: Action) => POLICY[role].includes(action);\n'),
    "ISR caching": ("app/[slug]/page.tsx", 'export const revalidate = 300;\nexport default async function Page({{ params }}) {{ return <Article post={{await getPost(params.slug)}} />; }}\n'),
    "service workers": ("sw.js", 'self.addEventListener("fetch", (e) => e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request))));\n'),
    "JWT auth": ("auth.ts", 'const token = jwt.sign({{ sub: partnerId }}, SECRET, {{ expiresIn: "15m" }});\n'),
    "row-level security": ("policies.sql", 'alter table entries enable row level security;\ncreate policy "own rows" on entries for select using (auth.uid() = user_id);\n'),
    "video transcoding": ("transcode.py", 'subprocess.run(["ffmpeg", "-i", src, "-c:v", "libx264", "-f", "hls", out], check=True)\n'),
    "idempotency keys": ("payouts.ts", 'await stripe.transfers.create({{ amount, destination }}, {{ idempotencyKey: `payout-${{sessionId}}` }});\n'),
    "Google Analytics": ("analytics.js", 'gtag("event", "sign_up", {{ variant: VARIANT }});\n'),
    "DataLoader caching": ("loaders.ts", 'export const recipeLoader = new DataLoader((ids) => prisma.recipe.findMany({{ where: {{ id: {{ in: ids }} }} }}));\n'),
    "SAML": ("saml.ts", 'const saml = new SAML({{ entryPoint: IDP_SSO_URL, issuer: "{slug}", cert: IDP_CERT }});\n'),
    "data modelling": ("model/schema.md", '# Star schema\n- fact_sales (date_key, store_key, product_key, revenue, units)\n- dim_store, dim_product, dim_date\n'),
    "data testing": ("models/schema.yml", 'version: 2\nmodels:\n  - name: fct_revenue\n    columns:\n      - name: invoice_id\n        tests: [unique, not_null]\n'),
    "BigQuery": ("load.py", 'from google.cloud import bigquery\n\nclient = bigquery.Client()\nclient.load_table_from_dataframe(df, "analytics.events").result()\n'),
    "power analysis": ("power.py", 'from statsmodels.stats.power import NormalIndPower\n\nn = NormalIndPower().solve_power(effect_size=0.05, alpha=0.05, power=0.8)\n'),
    "text analysis": ("themes.R", 'library(tidytext)\ncomments %>% unnest_tokens(word, text) %>% count(theme, word, sort = TRUE)\n'),
    "BigQuery export": ("ga4_export.sql", 'SELECT event_name, COUNT(*) FROM `project.analytics_123.events_*` GROUP BY 1;\n'),
    "indexing": ("migrations/add_indexes.sql", 'CREATE INDEX CONCURRENTLY idx_txn_account_date ON transactions (account_id, booked_at);\n'),
    "cron jobs": ("reminders.ts", '@Cron("0 9 * * *")\nasync sendReminders() {{ await this.sms.sendDueReminders(); }}\n'),
}
LANG_FILES = {
    "python": ("app.py", 'from fastapi import FastAPI\n\napp = FastAPI(title="{title}")\n\n\n@app.get("/health")\ndef health():\n    return {{"status": "ok"}}\n'),
    "ts": ("src/index.ts", 'import express from "express";\n\nconst app = express();\napp.get("/health", (_req, res) => res.json({{ ok: true }}));\napp.listen(3000);\n'),
    "sql": ("models/report.sql", 'select date_trunc(\'week\', order_date) as week, sum(revenue) as revenue\nfrom {{{{ ref("fct_orders") }}}}\ngroup by 1\n'),
}

OPEN_PERSONAL = [
    "Your post about {title_l} caught my eye because {hook}.",
    "I read your brief for {title_l}; {hook}.",
    "{hook_c}, which is close to what you describe in \"{title}\".",
    "For your {title_l} project, the key risk I see is getting {skill} right, and {hook}.",
]
OPEN_GENERIC = [
    "Dear Hiring Manager, I am writing to apply for this job.",
    "I am excited to apply for this project and I am the perfect fit.",
    "Hello, I hope this message finds you well. I have read your job description.",
    "Hi there! I am a hard-working professional with many years of experience.",
]
CLOSINGS = [
    "Could you share a sample of the data so I can confirm the approach?",
    "Happy to walk you through the repo on a short call.",
    "What does success look like for you in the first two weeks?",
    "I can start this week; would a short call on Thursday work?",
    "Let me know if you have any questions.",
]
REVIEW_TEMPLATES = [
    "{name} {verb} our {thing} and {result}. Clear communication and solid documentation.",
    "Excellent work on the {thing}. {result_c}. Would hire again.",
    "{name} understood the problem quickly. {result_c}. Delivered on time.",
    "Great experience. The {thing} is in production and {result}.",
]


def _problem(text: str) -> str:
    first = text.split()[0].lower()
    if first in {"a", "an", "the"} or text.split()[0][0].isupper():
        return text[0].upper() + text[1:] + "."
    return "The client's " + text + "."


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def _first(name: str) -> str:
    return name.split()[0]


def _latin1(s: str) -> str:
    return s.replace("—", "-").replace("–", "-").replace("’", "'").encode("latin-1", "replace").decode("latin-1")


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def load_titles(keywords: list[str], limit: int, rng: random.Random) -> list[dict]:
    """Real job titles + skills from the Kaggle 60k dataset matching the persona domain."""
    rows: list[dict] = []
    if not KAGGLE_60K.exists():
        return rows
    csv.field_size_limit(10**9)
    kw = [k.lower() for k in keywords]
    with open(KAGGLE_60K, encoding="utf-8-sig", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            title = (row.get("Job Title") or "").strip()
            skills = [row.get(f"Category_{i}", "").strip() for i in range(1, 10)]
            skills = [s for s in skills if s]
            blob = (title + " " + " ".join(skills)).lower()
            if title and any(re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", blob) for k in kw):
                rows.append({"title": title, "skills": [canon(s) for s in skills]})
    rng.shuffle(rows)
    seen, out = set(), []
    for r in rows:
        if r["title"].lower() in seen:
            continue
        seen.add(r["title"].lower())
        out.append(r)
        if len(out) >= limit:
            break
    return out


def case_study_md(p: dict, persona: dict) -> str:
    implied_txt = " ".join(IMPLIED_PHRASES.get(s, s) for s in p["implied"])
    named = ", ".join(p["skills"][:-1]) + (" and " + p["skills"][-1] if len(p["skills"]) > 1 else p["skills"][0])
    results = "\n".join(f"- {r[0].upper() + r[1:]}." for r in p["results"])
    return (
        f"---\nid: case-{p['slug']}\ntype: case_study\nproject: {p['slug']}\nclient_industry: {p['industry']}\n"
        f"date: {p['year']}-{p['month']:02d}\nskills: [{', '.join(p['skills'])}]\nsynthetic: true\n---\n\n"
        f"# {p['title']}\n\n"
        f"**Client:** a {p['industry']} company (anonymised, synthetic)  \n**Year:** {p['year']}\n\n"
        f"## The problem\n\nThe client's {p['problem']}.\n\n"
        f"## What I did\n\nI {p['approach']}. The work used {named}. {implied_txt}\n\n"
        f"## Results\n\n{results}\n\n"
        f"## What I would do differently\n\nI would agree the evaluation metric with the client in week one; "
        f"most of the rework came from changing what \"good\" meant halfway through.\n"
    )


def readme_md(p: dict) -> str:
    stack = "\n".join(f"- {s}" for s in p["skills"])
    return (
        f"# {p['slug']}\n\n{p['title']} (synthetic portfolio repository).\n\n"
        f"## Stack\n\n{stack}\n\n## Setup\n\n```bash\nmake install\nmake test\n```\n\n"
        f"## Architecture\n\nThe service {p['approach'].split(',')[0]}. See `src/` for the pipeline entry points.\n"
    )


def code_files(p: dict, rng: random.Random) -> dict[str, str]:
    files: dict[str, str] = {}
    langs = {s.lower() for s in p["skills"]}
    if langs & {"typescript", "javascript", "node.js", "react", "next.js", "nestjs", "express"}:
        fn, code = LANG_FILES["ts"]
    elif langs & {"sql", "dbt", "power bi", "tableau", "excel"}:
        fn, code = LANG_FILES["sql"]
    else:
        fn, code = LANG_FILES["python"]
    files[fn] = code.format(title=p["title"], slug=p["slug"])
    for s in p["implied"] + [s for s in p["skills"] if s in SNIPPETS]:
        if s in SNIPPETS and SNIPPETS[s][0] not in files:
            fn, code = SNIPPETS[s]
            files[fn] = code.format(slug=p["slug"], title=p["title"])
    deps = sorted({s for s in p["skills"] + p["implied"] if s[0].isalpha()})
    files["requirements.txt" if fn.endswith(".py") else "DEPENDENCIES.md"] = "\n".join(
        d.lower().replace(" ", "-") for d in deps
    ) + "\n"
    return files


def proposal_text(p_cited: list[dict], job: dict, persona: dict, personal: bool, specific: bool, rng: random.Random) -> str:
    title = job["title"]
    main = p_cited[0]
    hook = f"I recently {main['approach'].split(',')[0]} for {_article(main['industry'])} {main['industry']} client"
    if personal:
        skill = (job["skills"] or main["skills"])[0]
        opening = rng.choice(OPEN_PERSONAL).format(
            title=title, title_l=title.lower(), hook=hook, hook_c=hook[0].upper() + hook[1:], skill=skill)
    else:
        opening = rng.choice(OPEN_GENERIC)
    body = []
    for proj in p_cited:
        sent = f"On {_article(proj['title'])} {proj['title'].lower()} project for {_article(proj['industry'])} {proj['industry']} client I {proj['approach']}"
        if specific:
            sent += f"; {proj['results'][0]}"
        body.append(sent + ".")
    middle = (
        f"For this job I would start with a short audit, agree the success metric with you, then deliver in weekly increments using "
        f"{', '.join((job['skills'] or main['skills'])[:3])}."
    )
    return "\n\n".join([opening, " ".join(body), middle, rng.choice(CLOSINGS), f"Best,\n{_first(persona['display_name'])}"])


def outcome_for(rel: float, personal: bool, specific: bool, words: int, rng: random.Random) -> str:
    logit = -1.7 + 2.4 * rel + 0.8 * personal + 0.6 * specific - 0.9 * (not personal) - 0.004 * max(0, words - 220)
    p_reply = 1 / (1 + math.exp(-logit))
    if rng.random() < p_reply:
        return "won" if rng.random() < 0.30 + 0.35 * rel else "replied"
    return "ignored"


def write_cv_pdf(path: Path, persona: dict, projects: list[dict]) -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _latin1(persona["display_name"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, _latin1(persona["headline"]), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.multi_cell(0, 6, new_x="LMARGIN", new_y="NEXT", text=_latin1("SYNTHETIC PERSONA FOR AI-4016. " + persona["summary"]))
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Skills", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    skills = sorted({s for p in projects for s in p["skills"]})
    pdf.multi_cell(0, 6, new_x="LMARGIN", new_y="NEXT", text=_latin1(", ".join(skills)))
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Experience", new_x="LMARGIN", new_y="NEXT")
    for i, (role, org, period) in enumerate(persona["roles"]):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, _latin1(f"{role} - {org} ({period})"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for p in projects[i * 4 : i * 4 + 4]:
            pdf.multi_cell(0, 5, new_x="LMARGIN", new_y="NEXT", text=_latin1(f"- {p['title']}: {p['results'][0]}."))
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Education", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, new_x="LMARGIN", new_y="NEXT", text=_latin1(persona["education"]))
    pdf.output(str(path))


def build_persona(pid: str, persona: dict, rng: random.Random) -> dict:
    out = OUT / pid
    if out.exists():
        shutil.rmtree(out)
    (out / "case_studies").mkdir(parents=True)
    (out / "repos").mkdir()
    projects = []
    for slug, title, industry, year, skills, implied, problem, approach, results in persona["projects"]:
        projects.append({
            "slug": slug, "title": title, "industry": industry, "year": year, "month": rng.randint(1, 12),
            "skills": [canon(s) for s in skills], "implied": [canon(s) if s in IMPLIED_PHRASES and canon(s) == s else s for s in implied],
            "problem": problem, "approach": approach, "results": results,
        })
    for p in projects:
        (out / "case_studies" / f"{p['slug']}.md").write_text(case_study_md(p, persona), encoding="utf-8")
        repo = out / "repos" / p["slug"]
        repo.mkdir()
        (repo / "README.md").write_text(readme_md(p), encoding="utf-8")
        for fn, code in code_files(p, rng).items():
            f = repo / "src" / fn if not fn.startswith((".github", "k8s", "Dockerfile", "requirements", "DEPENDENCIES", "dags", "models", "migrations", "jetson")) else repo / fn
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(code, encoding="utf-8")
    write_cv_pdf(out / "cv.pdf", persona, projects)

    # reviews
    reviews = []
    for i, p in enumerate(rng.sample(projects, k=min(12, len(projects)))):
        res = p["results"][0]
        reviews.append({
            "id": f"review-{p['slug']}", "project": p["slug"], "client_industry": p["industry"],
            "date": f"{p['year']}-{min(12, p['month'] + 1):02d}", "stars": rng.choice([5, 5, 5, 4.8, 4.5, 4]),
            "text": rng.choice(REVIEW_TEMPLATES).format(
                name=_first(persona["display_name"]), verb=rng.choice(["rebuilt", "delivered", "designed"]),
                thing=p["title"].lower(), result=res, result_c=res[0].upper() + res[1:]),
            "synthetic": True,
        })
    (out / "reviews.json").write_text(json.dumps(reviews, indent=2), encoding="utf-8")

    # past proposals with outcomes
    titles = load_titles(persona["domain_keywords"], 400, rng)
    if len(titles) < 150:
        titles += [{"title": f"{p['title']} for a {p['industry']} business", "skills": p["skills"]} for p in projects] * 10
    proposals = []
    for i in range(150):
        job = titles[i]
        jskills = set(job["skills"])
        scored = sorted(projects, key=lambda p: -len(jskills & set(p["skills"] + p["implied"])))
        good = rng.random() < 0.6
        cited = scored[:2] if good else rng.sample(projects, 2)
        cited = cited[: rng.choice([1, 2])]
        rel = 0.0
        if jskills:
            rel = len(jskills & {s for p in cited for s in p["skills"] + p["implied"]}) / len(jskills)
        personal = rng.random() < (0.7 if good else 0.35)
        specific = rng.random() < (0.75 if good else 0.4)
        text = proposal_text(cited, job, persona, personal, specific, rng)
        outcome = outcome_for(rel, personal, specific, len(text.split()), rng)
        year = rng.choice([2022, 2023, 2024, 2025, 2026])
        proposals.append({
            "id": f"prop-{pid[:4]}-{i:03d}", "job_title": job["title"], "job_skills": sorted(jskills),
            "date": f"{year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}", "projects_cited": [p["slug"] for p in cited],
            "personalised_opening": personal, "includes_metric": specific, "outcome": outcome, "text": text,
            "job_title_source": "kaggle:ahmedmyalo/upwork-freelance-jobs-60k" if titles and i < len(titles) else "synthetic",
            "synthetic": True,
        })
    with open(out / "proposals.jsonl", "w", encoding="utf-8") as fh:
        for p in proposals:
            fh.write(json.dumps(p) + "\n")

    profile = {
        "persona_id": pid, "display_name": persona["display_name"], "headline": persona["headline"],
        "summary": persona["summary"], "hourly_rate_usd": persona["hourly_rate_usd"],
        "min_hourly_usd": persona["min_hourly_usd"], "min_fixed_usd": persona["min_fixed_usd"],
        "weekly_connects": persona["weekly_connects"], "domain_keywords": persona["domain_keywords"],
        "skills": sorted({s for p in projects for s in p["skills"]}), "synthetic": True,
    }
    (out / "profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
    gold = [{k: p[k] for k in ("slug", "title", "industry", "year", "skills", "implied", "problem", "approach", "results")} for p in projects]
    (out / "_gold_projects.json").write_text(json.dumps(gold, indent=2), encoding="utf-8")
    counts = {o: sum(1 for p in proposals if p["outcome"] == o) for o in ("won", "replied", "ignored")}
    return {"persona": pid, "projects": len(projects), "reviews": len(reviews), "proposals": counts}


def main() -> None:
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    summary = [build_persona(pid, persona, rng) for pid, persona in PERSONAS.items()]
    print(json.dumps(summary, indent=2))
    # sanity: implied skills must not be named in case studies
    for pid in PERSONAS:
        for f in (OUT / pid / "case_studies").glob("*.md"):
            body = f.read_text(encoding="utf-8").split("---", 2)[2]
            _ = extract_skills(body)


if __name__ == "__main__":
    main()
