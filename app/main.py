from fastapi import FastAPI

app = FastAPI(
    title="Exchange Rate API Backend",
    description="Semestral project - Backend for exchange rate application",
    version="1.0.0"
)

@app.get("/health")
async def health_check():
    return {"status": "ok"}