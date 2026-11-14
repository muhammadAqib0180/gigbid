from fastapi import FastAPI

app = FastAPI(title="ETL pipeline for advertising platforms")


@app.get("/health")
def health():
    return {"status": "ok"}
