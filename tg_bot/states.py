from aiogram.fsm.state import State, StatesGroup


class QuickOnboardingStates(StatesGroup):
    """3-tap onboarding: goal → fitness_level → gender."""
    goal = State()
    fitness_level = State()
    gender = State()


class SkillStates(StatesGroup):
    """States for skill flows."""
    asking_trainer = State()
    asking_dietologist = State()
    # Progressive profiling (just-in-time data collection)
    collecting_height = State()
    collecting_weight = State()


class VideoAnalysisStates(StatesGroup):
    waiting_exercise_name = State()


class FeedbackStates(StatesGroup):
    collecting_comment = State()


class EditProfileStates(StatesGroup):
    choosing_field = State()
    entering_value = State()
