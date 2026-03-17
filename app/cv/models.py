from pydantic import BaseModel


# COCO 17 keypoints
KEYPOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]

# Indices for quick access
KP = {name: i for i, name in enumerate(KEYPOINT_NAMES)}

# Joint angle definitions: (point_a, joint, point_b)
JOINT_ANGLES = {
    "left_elbow": (KP["left_shoulder"], KP["left_elbow"], KP["left_wrist"]),
    "right_elbow": (KP["right_shoulder"], KP["right_elbow"], KP["right_wrist"]),
    "left_knee": (KP["left_hip"], KP["left_knee"], KP["left_ankle"]),
    "right_knee": (KP["right_hip"], KP["right_knee"], KP["right_ankle"]),
    "left_hip": (KP["left_shoulder"], KP["left_hip"], KP["left_knee"]),
    "right_hip": (KP["right_shoulder"], KP["right_hip"], KP["right_knee"]),
    "left_shoulder": (KP["left_hip"], KP["left_shoulder"], KP["left_elbow"]),
    "right_shoulder": (KP["right_hip"], KP["right_shoulder"], KP["right_elbow"]),
}


class Keypoint(BaseModel):
    x: float
    y: float
    confidence: float


class FrameKeypoints(BaseModel):
    frame_index: int
    keypoints: list[Keypoint]


class JointAngleStats(BaseModel):
    joint_name: str
    min_angle: float
    max_angle: float
    mean_angle: float
    amplitude: float


class ExerciseReport(BaseModel):
    exercise_name: str
    total_frames: int
    reps_count: int
    joint_stats: list[JointAngleStats]
    symmetry_notes: list[str]
    report_text: str
