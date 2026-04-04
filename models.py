from pydantic import BaseModel, Field
from typing import Literal, Optional, List

# ============================================================
# 1. ACTION MODEL — What the AI agent is allowed to do
# ============================================================
class DevOpsAction(BaseModel):
    """
    Represents a single action the agent can take in the environment.
    The agent must always choose one of the four action types.
    """
    action_type: Literal[
        "read_file",
        "overwrite_file",
        "run_build",
        "revert_commit"
    ] = Field(
        ...,
        description=(
            "The command to execute. "
            "'read_file' reads a file's contents. "
            "'overwrite_file' writes new content to a file. "
            "'run_build' triggers the build/test pipeline and grades the result. "
            "'revert_commit' resets all files back to their broken initial state."
        )
    )
    file_name: Optional[str] = Field(
        None,
        description="Target file (e.g. 'requirements.txt'). Required for read_file and overwrite_file."
    )
    content: Optional[str] = Field(
        None,
        description="The exact content to write into the file. Required for overwrite_file only."
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"action_type": "read_file", "file_name": "requirements.txt"},
                {"action_type": "overwrite_file", "file_name": "requirements.txt", "content": "flask==2.3.0\nrequests==2.28.0"},
                {"action_type": "run_build"},
                {"action_type": "revert_commit"}
            ]
        }
    }


# ============================================================
# 2. OBSERVATION MODEL — What the agent sees after each action
# ============================================================
class DevOpsObservation(BaseModel):
    """
    The full state snapshot returned to the agent after every step.
    This is everything the agent can see — nothing more, nothing less.
    """
    terminal_output: str = Field(
        ...,
        description="Console output from the last action — build logs, file contents, error messages, or success confirmations."
    )
    visible_files: List[str] = Field(
        ...,
        description="List of all file names currently present in the repository sandbox."
    )
    current_task: str = Field(
        ...,
        description="The task description the agent is currently trying to solve."
    )
    steps_remaining: int = Field(
        ...,
        description="How many steps the agent has left before the episode times out.",
        ge=0
    )
    tests_passed: int = Field(
        ...,
        description="Number of checks currently passing in the pipeline.",
        ge=0
    )
    total_tests: int = Field(
        ...,
        description="Total number of checks in the pipeline for this task.",
        ge=1
    )
    build_status: Literal["pending", "passing", "failing", "timeout"] = Field(
        ...,
        description="The current high-level status of the CI/CD pipeline."
    )


# ============================================================
# 3. REWARD MODEL — Structured reward signal per step
# ============================================================
class DevOpsReward(BaseModel):
    """
    A structured reward breakdown returned at every step.
    Provides interpretable signal rather than a raw float —
    so training logs are readable and partial credit is visible.
    """
    total: float = Field(
        ...,
        description="The net reward for this step. Sum of all components.",
        ge=-1.0,
        le=1.0
    )
    task_progress: float = Field(
        0.0,
        description="Reward for making measurable progress toward the goal (e.g. correct file edited)."
    )
    efficiency_penalty: float = Field(
        0.0,
        description="Negative reward for wasted actions (e.g. reading a file repeatedly, no-op steps)."
    )
    build_result: float = Field(
        0.0,
        description="Reward signal from the build pipeline. +1.0 for full pass, -0.5 for failure."
    )
    safety_penalty: float = Field(
        0.0,
        description="Penalty for destructive or unsafe actions (e.g. deleting production database)."
    )


# ============================================================
# 4. TASK MODEL — Defines each challenge in the environment
# ============================================================
class DevOpsTask(BaseModel):
    """
    Metadata for a single task in the environment.
    Used by the /tasks endpoint and the environment's reset logic.
    """
    task_id: str = Field(
        ...,
        description="Unique identifier for this task (e.g. 'level_1_easy')."
    )
    difficulty: Literal["easy", "medium", "hard"] = Field(
        ...,
        description="Difficulty tier. Easy tasks have one obvious fix. Hard tasks require careful multi-step reasoning."
    )
    description: str = Field(
        ...,
        description="The plain-English mission briefing shown to the agent at the start of the episode."
    )
    max_steps: int = Field(
        15,
        description="Maximum number of steps allowed for this task before timeout.",
        ge=5,
        le=30
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Category tags for this task (e.g. ['dependencies', 'security', 'config'])."
    )


# ============================================================
# 5. EPISODE RESULT MODEL — Final summary after episode ends
# ============================================================
class EpisodeResult(BaseModel):
    """
    Returned when done=True. Summarises the full episode outcome.
    Used by run_all.py to build the final evaluation report.
    """
    task_id: str
    success: bool = Field(
        ...,
        description="True if the agent triggered run_build and passed all checks."
    )
    final_score: float = Field(
        ...,
        description="Grader score between 0.0 and 1.0.",
        ge=0.0,
        le=1.0
    )
    total_steps: int = Field(
        ...,
        description="Total number of steps taken in this episode."
    )
    total_reward: float = Field(
        ...,
        description="Cumulative reward accumulated across the full episode."
    )
    termination_reason: Literal["success", "timeout", "critical_failure"] = Field(
        ...,
        description="Why the episode ended."
    )