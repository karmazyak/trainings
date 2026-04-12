from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    """v2 onboarding: try_question → goal → fitness_level → week_template → custom days."""
    try_question = State()
    goal = State()
    fitness_level = State()
    week_template = State()
    custom_week_day = State()  # which day we're configuring (1-7)


class SkillStates(StatesGroup):
    """States for skill flows."""
    asking_trainer = State()
    asking_dietologist = State()
    asking_question = State()  # unified question with auto-routing
    # Progressive profiling
    collecting_height = State()
    collecting_weight = State()


class VideoAnalysisStates(StatesGroup):
    waiting_exercise_name = State()


class FeedbackStates(StatesGroup):
    collecting_comment = State()


class FitnessTestStates(StatesGroup):
    """Baseline fitness assessment: pushups → plank → squats."""
    pushups = State()
    plank = State()
    squats = State()


class SessionFeedbackStates(StatesGroup):
    """Post-workout feedback flow."""
    collecting_feedback = State()


class LogExerciseStates(StatesGroup):
    """Exercise logging after workout or manual."""
    choosing_action = State()  # same/up/edit for current exercise
    manual_input = State()  # entering "85 × 5 × 4"
    manual_exercise_name = State()  # entering exercise name for manual log


class SituationStates(StatesGroup):
    """Situational nutrition help."""
    custom_situation = State()
    shop_custom = State()


class EditProfileStates(StatesGroup):
    """Edit profile: user picks a field, then enters/selects new value."""
    choosing_field = State()
    entering_value = State()
