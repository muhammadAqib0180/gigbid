from fastapi import FastAPI

app = FastAPI(title="Review sentiment analytics")


@app.get("/health")
def health():
    return {"status": "ok"}
