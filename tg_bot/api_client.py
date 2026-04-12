import httpx
import logging

logger = logging.getLogger(__name__)


class AreteAPI:
    def __init__(self, base_url: str, api_key: str = "") -> None:
        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key
        self._client = httpx.AsyncClient(base_url=base_url, timeout=30.0, headers=headers)

    async def create_user(self, data: dict) -> dict:
        resp = await self._client.post("/users", json=data)
        if resp.status_code >= 400:
            logger.error("create_user failed: %s %s", resp.status_code, resp.text)
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
        resp = await self._client.post("/chat", json=payload, timeout=120.0)
        resp.raise_for_status()
        return resp.json()

    async def get_plan(
        self,
        user_id: str,
        plan_type: str,
        prompt: str,
        force: bool = False,
    ) -> dict:
        """Get plan from cache or generate new."""
        params = {"prompt": prompt, "force": str(force).lower()}
        resp = await self._client.get(
            f"/plans/{user_id}/{plan_type}",
            params=params,
            timeout=300.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_my_day(self, user_id: str) -> dict:
        """Get today's workout + meal from cached plans."""
        resp = await self._client.get(
            f"/plans/{user_id}/my-day",
            timeout=120.0,
        )
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

    async def generate_schedule(self, user_id: str) -> dict:
        """Generate weekly schedule from cached plans."""
        resp = await self._client.post(
            f"/schedule/{user_id}/generate",
            timeout=90.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_today_session(self, user_id: str) -> dict:
        """Get today's session from training schedule."""
        resp = await self._client.get(
            f"/schedule/{user_id}/today",
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_week_schedule(self, user_id: str) -> dict:
        """Get this week's schedule."""
        resp = await self._client.get(
            f"/schedule/{user_id}/week",
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def complete_session(
        self,
        session_id: str,
        feedback: str | None = None,
        difficulty_rating: int | None = None,
    ) -> dict:
        """Mark session as completed."""
        payload: dict = {}
        if feedback:
            payload["feedback"] = feedback
        if difficulty_rating is not None:
            payload["difficulty_rating"] = difficulty_rating
        resp = await self._client.patch(
            f"/schedule/{session_id}/complete",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def skip_session(self, session_id: str, reason: str | None = None) -> dict:
        """Mark session as skipped."""
        payload: dict = {}
        if reason:
            payload["reason"] = reason
        resp = await self._client.patch(
            f"/schedule/{session_id}/skip",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def update_schedule(self, user_id: str, slots: list[dict]) -> list[dict]:
        """PUT /users/{user_id}/schedule"""
        resp = await self._client.put(f"/users/{user_id}/schedule", json={"slots": slots})
        resp.raise_for_status()
        return resp.json()

    async def get_schedule(self, user_id: str) -> list[dict]:
        """GET /users/{user_id}/schedule"""
        resp = await self._client.get(f"/users/{user_id}/schedule")
        resp.raise_for_status()
        return resp.json()

    async def log_exercise(self, user_id: str, data: dict) -> dict:
        """POST /exercise-log/{user_id}"""
        resp = await self._client.post(f"/exercise-log/{user_id}", json=data)
        resp.raise_for_status()
        return resp.json()

    async def get_exercise_history(self, user_id: str, exercise_name: str) -> dict:
        """GET /exercise-log/{user_id}/history/{exercise_name}"""
        resp = await self._client.get(f"/exercise-log/{user_id}/history/{exercise_name}")
        resp.raise_for_status()
        return resp.json()

    async def get_recent_exercises(self, user_id: str) -> list[dict]:
        """GET /exercise-log/{user_id}/recent"""
        resp = await self._client.get(f"/exercise-log/{user_id}/recent")
        resp.raise_for_status()
        return resp.json()

    async def chat_situation(self, user_id: str, situation: str, subcategory: str | None = None, conversation_id: str | None = None) -> dict:
        """POST /chat/situation"""
        payload: dict = {"user_id": user_id, "situation": situation}
        if subcategory:
            payload["subcategory"] = subcategory
        if conversation_id:
            payload["conversation_id"] = conversation_id
        resp = await self._client.post("/chat/situation", json=payload, timeout=120.0)
        resp.raise_for_status()
        return resp.json()

    async def chat_try(self, message: str) -> dict:
        """POST /chat/try — anonymous trial question (no user_id)"""
        resp = await self._client.post("/chat/try", json={"message": message}, timeout=120.0)
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
