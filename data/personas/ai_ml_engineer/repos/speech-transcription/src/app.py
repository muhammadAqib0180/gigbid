from fastapi import FastAPI

app = FastAPI(title="Call transcription and summarisation")


@app.get("/health")
def health():
    return {"status": "ok"}
