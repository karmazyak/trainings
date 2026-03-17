import math
from collections import defaultdict

import numpy as np

from app.cv.models import (
    ExerciseReport,
    FrameKeypoints,
    JointAngleStats,
    JOINT_ANGLES,
)


def _calc_angle(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    """Calculate angle at point b formed by points a-b-c, in degrees."""
    ba = (a[0] - b[0], a[1] - b[1])
    bc = (c[0] - b[0], c[1] - b[1])

    dot = ba[0] * bc[0] + ba[1] * bc[1]
    mag_ba = math.sqrt(ba[0] ** 2 + ba[1] ** 2)
    mag_bc = math.sqrt(bc[0] ** 2 + bc[1] ** 2)

    if mag_ba * mag_bc == 0:
        return 0.0

    cos_angle = max(-1.0, min(1.0, dot / (mag_ba * mag_bc)))
    return math.degrees(math.acos(cos_angle))


def _compute_joint_angles(frame: FrameKeypoints, min_confidence: float = 0.3) -> dict[str, float]:
    """Compute all joint angles for a single frame."""
    angles = {}
    kps = frame.keypoints

    for joint_name, (idx_a, idx_b, idx_c) in JOINT_ANGLES.items():
        if idx_a >= len(kps) or idx_b >= len(kps) or idx_c >= len(kps):
            continue

        pa, pb, pc = kps[idx_a], kps[idx_b], kps[idx_c]
        if pa.confidence < min_confidence or pb.confidence < min_confidence or pc.confidence < min_confidence:
            continue

        angle = _calc_angle((pa.x, pa.y), (pb.x, pb.y), (pc.x, pc.y))
        angles[joint_name] = angle

    return angles


def _count_reps(angle_series: list[float], threshold_fraction: float = 0.4) -> int:
    """Count repetitions by detecting cycles in angle series."""
    if len(angle_series) < 5:
        return 0

    arr = np.array(angle_series)
    min_val, max_val = arr.min(), arr.max()
    amplitude = max_val - min_val

    if amplitude < 15:  # too little movement
        return 0

    threshold = min_val + amplitude * threshold_fraction
    above = arr > threshold

    # Count transitions from below to above threshold
    reps = 0
    was_below = False
    for val in above:
        if not val:
            was_below = True
        elif was_below:
            reps += 1
            was_below = False

    return reps


SYMMETRY_PAIRS = [
    ("left_knee", "right_knee"),
    ("left_elbow", "right_elbow"),
    ("left_hip", "right_hip"),
    ("left_shoulder", "right_shoulder"),
]

JOINT_NAMES_RU = {
    "left_knee": "левое колено",
    "right_knee": "правое колено",
    "left_elbow": "левый локоть",
    "right_elbow": "правый локоть",
    "left_hip": "левое бедро",
    "right_hip": "правое бедро",
    "left_shoulder": "левое плечо",
    "right_shoulder": "правое плечо",
}


def analyze_exercise(
    frames: list[FrameKeypoints],
    exercise_name: str,
) -> ExerciseReport:
    """Analyze exercise from extracted keypoints."""
    # Collect angle time series per joint
    angle_series: dict[str, list[float]] = defaultdict(list)

    for frame in frames:
        angles = _compute_joint_angles(frame)
        for joint_name, angle in angles.items():
            angle_series[joint_name].append(angle)

    # Compute stats per joint
    joint_stats = []
    for joint_name, series in angle_series.items():
        if not series:
            continue
        arr = np.array(series)
        joint_stats.append(JointAngleStats(
            joint_name=joint_name,
            min_angle=round(float(arr.min()), 1),
            max_angle=round(float(arr.max()), 1),
            mean_angle=round(float(arr.mean()), 1),
            amplitude=round(float(arr.max() - arr.min()), 1),
        ))

    # Count reps using the joint with largest amplitude
    reps_count = 0
    if joint_stats:
        primary_joint = max(joint_stats, key=lambda s: s.amplitude)
        reps_count = _count_reps(angle_series[primary_joint.joint_name])

    # Symmetry analysis
    symmetry_notes = []
    for left, right in SYMMETRY_PAIRS:
        if left in angle_series and right in angle_series:
            left_arr = np.array(angle_series[left])
            right_arr = np.array(angle_series[right])
            min_len = min(len(left_arr), len(right_arr))
            if min_len > 0:
                diff = abs(float(left_arr[:min_len].mean() - right_arr[:min_len].mean()))
                if diff > 8:
                    left_ru = JOINT_NAMES_RU.get(left, left)
                    right_ru = JOINT_NAMES_RU.get(right, right)
                    symmetry_notes.append(
                        f"Асимметрия {left_ru}/{right_ru}: разница средних углов {diff:.1f}°"
                    )

    # Build text report
    report_lines = [f"Упражнение: {exercise_name}"]
    report_lines.append(f"Обработано кадров: {len(frames)}")
    report_lines.append(f"Повторений: {reps_count}")
    report_lines.append("")
    report_lines.append("Углы суставов (мин / макс / среднее / амплитуда):")
    for s in joint_stats:
        name_ru = JOINT_NAMES_RU.get(s.joint_name, s.joint_name)
        report_lines.append(f"  {name_ru}: {s.min_angle}° / {s.max_angle}° / {s.mean_angle}° / {s.amplitude}°")

    if symmetry_notes:
        report_lines.append("")
        report_lines.append("Замечания по симметрии:")
        for note in symmetry_notes:
            report_lines.append(f"  - {note}")

    report_text = "\n".join(report_lines)

    return ExerciseReport(
        exercise_name=exercise_name,
        total_frames=len(frames),
        reps_count=reps_count,
        joint_stats=joint_stats,
        symmetry_notes=symmetry_notes,
        report_text=report_text,
    )
