from fastapi import FastAPI

app = FastAPI(title="Customer churn prediction for a telecom operator")


@app.get("/health")
def health():
    return {"status": "ok"}
