from fastapi import FastAPI

app = FastAPI(title="Inventory forecasting in Google Sheets")


@app.get("/health")
def health():
    return {"status": "ok"}
