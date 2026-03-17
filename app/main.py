from fastapi import FastAPI

from app.routers import chat, documents, exercise, feedback, plans, users

app = FastAPI(
    title="Fitness AI Service",
    description="AI-тренер и диетолог с RAG на базе книг по ЗОЖ",
    version="0.2.0",
)

app.include_router(users.router)
app.include_router(chat.router)
app.include_router(plans.router)
app.include_router(documents.router)
app.include_router(exercise.router)
app.include_router(feedback.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
