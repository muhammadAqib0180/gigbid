from fastapi import FastAPI

app = FastAPI(title="Dynamic pricing model for a travel site")


@app.get("/health")
def health():
    return {"status": "ok"}
