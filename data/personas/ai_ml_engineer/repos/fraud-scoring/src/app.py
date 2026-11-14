from fastapi import FastAPI

app = FastAPI(title="Real-time transaction fraud scoring")


@app.get("/health")
def health():
    return {"status": "ok"}
