from fastapi import FastAPI

app = FastAPI(title="Demand forecasting for a grocery chain")


@app.get("/health")
def health():
    return {"status": "ok"}
