from fastapi import FastAPI

app = FastAPI(title="Horae", description="Natural language calendar event creation")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
