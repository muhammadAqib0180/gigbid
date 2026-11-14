from fastapi import FastAPI

app = FastAPI(title="Containerised deployment on AWS")


@app.get("/health")
def health():
    return {"status": "ok"}
