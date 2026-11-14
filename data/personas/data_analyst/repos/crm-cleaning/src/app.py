from fastapi import FastAPI

app = FastAPI(title="CRM data cleaning and de-duplication")


@app.get("/health")
def health():
    return {"status": "ok"}
