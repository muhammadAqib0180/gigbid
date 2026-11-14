from fastapi import FastAPI

app = FastAPI(title="GA4 migration and tracking plan")


@app.get("/health")
def health():
    return {"status": "ok"}
