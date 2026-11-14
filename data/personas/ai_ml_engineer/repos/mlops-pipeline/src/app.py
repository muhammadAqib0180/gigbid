from fastapi import FastAPI

app = FastAPI(title="Automated model retraining pipeline")


@app.get("/health")
def health():
    return {"status": "ok"}
