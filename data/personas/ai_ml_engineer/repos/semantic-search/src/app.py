from fastapi import FastAPI

app = FastAPI(title="Semantic search for a research library")


@app.get("/health")
def health():
    return {"status": "ok"}
