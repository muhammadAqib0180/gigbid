from fastapi import FastAPI

app = FastAPI(title="Visual defect detection on a production line")


@app.get("/health")
def health():
    return {"status": "ok"}
