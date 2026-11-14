from fastapi import FastAPI

app = FastAPI(title="Custom CRM with task automation")


@app.get("/health")
def health():
    return {"status": "ok"}
