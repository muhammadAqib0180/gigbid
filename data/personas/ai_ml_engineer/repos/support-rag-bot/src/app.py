from fastapi import FastAPI

app = FastAPI(title="Retrieval-augmented support assistant")


@app.get("/health")
def health():
    return {"status": "ok"}
