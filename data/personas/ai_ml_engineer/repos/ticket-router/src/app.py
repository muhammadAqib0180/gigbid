from fastapi import FastAPI

app = FastAPI(title="Support ticket routing classifier")


@app.get("/health")
def health():
    return {"status": "ok"}
