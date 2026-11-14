from fastapi import FastAPI

app = FastAPI(title="Contract clause extraction")


@app.get("/health")
def health():
    return {"status": "ok"}
