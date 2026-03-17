import httpx
import logging

logger = logging.getLogger(__name__)


class AreteAPI:
    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=60.0)

    async def create_user(self, data: dict) -> dict:
        resp = await self._client.post("/users", json=data)
        resp.raise_for_status()
        return resp.json()

    async def get_user(self, user_id: str) -> dict:
        resp = await self._client.get(f"/users/{user_id}")
        resp.raise_for_status()
        return resp.json()

    async def update_user(self, user_id: str, data: dict) -> dict:
        resp = await self._client.patch(f"/users/{user_id}", json=data)
        resp.raise_for_status()
        return resp.json()

    async def chat(
        self,
        user_id: str,
        message: str,
        agent: str = "auto",
        conversation_id: str | None = None,
    ) -> dict:
        payload: dict = {
            "user_id": user_id,
            "agent": agent,
            "message": message,
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        resp = await self._client.post("/chat", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def analyze_exercise(
        self,
        user_id: str,
        exercise_name: str,
        video_bytes: bytes,
        filename: str = "exercise.mp4",
    ) -> dict:
        resp = await self._client.post(
            "/exercise/analyze",
            data={"user_id": user_id, "exercise_name": exercise_name},
            files={"video": (filename, video_bytes, "video/mp4")},
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def submit_feedback(
        self,
        user_id: str,
        message_id: str,
        rating: int,
        comment: str | None = None,
    ) -> dict:
        payload: dict = {
            "user_id": user_id,
            "message_id": message_id,
            "rating": rating,
        }
        if comment:
            payload["comment"] = comment
        resp = await self._client.post("/feedback", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
