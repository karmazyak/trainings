from aiogram.fsm.state import State, StatesGroup


class QuickOnboardingStates(StatesGroup):
    """5-tap onboarding: goal → fitness_level → gender → training_style → activity_level."""
    goal = State()
    fitness_level = State()
    gender = State()
    training_style = State()
    activity_level = State()


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
    """Edit profile: user picks a field, then enters/selects new value."""
    choosing_field = State()
    entering_value = State()  # for text fields (height, weight, allergies, etc.)
