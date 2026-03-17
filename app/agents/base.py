import logging

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.rag.retriever import retrieve_context, RetrievedChunk

logger = logging.getLogger(__name__)

client = AsyncOpenAI(
    api_key=settings.openrouter_api_key,
    base_url=settings.openrouter_base_url,
)


async def llm_call(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
) -> str:
    """Общий вызов LLM через OpenRouter."""
    response = await client.chat.completions.create(
        model=model or settings.llm_model,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content


async def llm_call_cheap(
    messages: list[dict],
    temperature: float = 0.3,
) -> str:
    """Вызов дешёвой модели (для предобработки, классификации, реренкинга)."""
    return await llm_call(messages, model=settings.llm_model_cheap, temperature=temperature)


class BaseAgent:
    system_prompt: str = ""
    domain_filter: list[str] | None = None

    async def get_response(
        self,
        user_message: str,
        db: AsyncSession,
        history: list[dict] | None = None,
        user_context: str = "",
        preferences: str = "",
        other_agent_plan: str | None = None,
    ) -> tuple[str, list[RetrievedChunk]]:
        """Получить ответ от агента. Возвращает (текст ответа, список источников)."""
        chunks = await retrieve_context(
            query=user_message,
            db=db,
            domain_filter=self.domain_filter,
        )

        # Формируем RAG-контекст с метаданными
        rag_parts = []
        for chunk in chunks:
            source_info = f"[Источник: {chunk.source}"
            if chunk.chapter:
                source_info += f", {chunk.chapter}"
            source_info += "]"
            rag_parts.append(f"{source_info}\n{chunk.content}")

        rag_context = "\n\n---\n\n".join(rag_parts) if rag_parts else ""

        system = self.system_prompt
        if user_context:
            system += f"\n\nДанные пользователя:\n{user_context}"
        if preferences:
            system += f"\n\nИзвестные предпочтения пользователя (СТРОГО учитывай):\n{preferences}"
        if other_agent_plan:
            system += f"\n\nПоследний план от другого специалиста (координируй с ним):\n{other_agent_plan}"
        if rag_context:
            system += f"\n\nКонтекст из базы знаний:\n{rag_context}"

        messages = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        response_text = await llm_call(messages)
        return response_text, chunks
