import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.trainer import trainer_agent
from app.cv.exercise_analyzer import analyze_exercise
from app.cv.pose_estimator import extract_keypoints
from app.database import get_db
from app.models import ExerciseAnalysis, User
from app.routers.chat import format_user_context
from app.schemas import ExerciseAnalyzeResponse

router = APIRouter(prefix="/exercise", tags=["exercise"])

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm"}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB


@router.post("/analyze", response_model=ExerciseAnalyzeResponse)
async def analyze_exercise_video(
    video: UploadFile = File(...),
    user_id: UUID = Form(...),
    exercise_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    suffix = Path(video.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video format. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Save uploaded video to temp file
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await video.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="File too large (max 100MB)")
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        # 1. Extract skeleton keypoints via YOLO-Pose
        frames = extract_keypoints(tmp_path)

        if not frames:
            raise HTTPException(status_code=422, detail="No person detected in the video")

        # 2. Analyze exercise biomechanics
        report = analyze_exercise(frames, exercise_name)

        # 3. Get trainer feedback via LLM
        trainer_message = (
            f"Пользователь загрузил видео упражнения. Проанализируй результат и дай рекомендации по технике.\n\n"
            f"{report.report_text}"
        )
        user_context = format_user_context(user)

        trainer_feedback, _ = await trainer_agent.get_response(
            user_message=trainer_message,
            db=db,
            user_context=user_context,
        )

        # 4. Save to DB
        keypoints_data = [
            {
                "frame_index": f.frame_index,
                "keypoints": [{"x": kp.x, "y": kp.y, "confidence": kp.confidence} for kp in f.keypoints],
            }
            for f in frames
        ]

        analysis = ExerciseAnalysis(
            user_id=user_id,
            exercise_name=exercise_name,
            video_filename=video.filename,
            reps_count=report.reps_count,
            analysis_report=report.report_text,
            trainer_feedback=trainer_feedback,
            keypoints_json=keypoints_data,
        )
        db.add(analysis)
        await db.commit()
        await db.refresh(analysis)

        return ExerciseAnalyzeResponse(
            analysis_id=analysis.id,
            exercise_name=exercise_name,
            reps_count=report.reps_count,
            analysis_report=report.report_text,
            trainer_feedback=trainer_feedback,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
