from fastapi import FastAPI

app = FastAPI(title="Medical image classification prototype")


@app.get("/health")
def health():
    return {"status": "ok"}
