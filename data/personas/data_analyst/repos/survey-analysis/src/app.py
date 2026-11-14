from fastapi import FastAPI

app = FastAPI(title="Customer survey analysis")


@app.get("/health")
def health():
    return {"status": "ok"}
