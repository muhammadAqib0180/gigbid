from fastapi import FastAPI

app = FastAPI(title="Product recommendations for an online store")


@app.get("/health")
def health():
    return {"status": "ok"}
