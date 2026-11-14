from fastapi import FastAPI

app = FastAPI(title="Sales-research agent built with LangGraph")


@app.get("/health")
def health():
    return {"status": "ok"}
