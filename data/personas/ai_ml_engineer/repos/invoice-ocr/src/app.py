from fastapi import FastAPI

app = FastAPI(title="Invoice field extraction pipeline")


@app.get("/health")
def health():
    return {"status": "ok"}
