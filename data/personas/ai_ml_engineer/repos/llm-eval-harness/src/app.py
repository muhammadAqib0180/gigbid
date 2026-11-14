from fastapi import FastAPI

app = FastAPI(title="LLM evaluation harness")


@app.get("/health")
def health():
    return {"status": "ok"}
