from fastapi import FastAPI

app = FastAPI(title="Sensor anomaly detection for pumping stations")


@app.get("/health")
def health():
    return {"status": "ok"}
