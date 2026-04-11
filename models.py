from pydantic import BaseModel, Field
from typing import Literal, Optional, List

class DevOpsAction(BaseModel):
    action_type: Literal[
        "read_file",
        "overwrite_file",
        "run_build",
        "revert_commit"
    ] = Field(..., description="The command to execute.")
    file_name: Optional[str] = Field(None, description="Target file.")
    content: Optional[str] = Field(None, description="New file content.")

class DevOpsObservation(BaseModel):
    terminal_output: str
    visible_files: List[str]
    current_task: str
    steps_remaining: int = Field(..., ge=0)
    tests_passed: int = Field(..., ge=0)
    total_tests: int = Field(..., ge=1)
    build_status: Literal["pending", "passing", "failing", "timeout"]

class DevOpsReward(BaseModel):
    total: float = Field(0.01, gt=-1.0, lt=1.0)
    task_progress: float = Field(0.01)
    efficiency_penalty: float = Field(0.01)
    build_result: float = Field(0.01)
    safety_penalty: float = Field(0.01)

class DevOpsTask(BaseModel):
    task_id: str
    difficulty: Literal["easy", "medium", "hard"]
    description: str
    max_steps: int = Field(15, ge=5, le=30)
    tags: List[str] = Field(default_factory=list)

class EpisodeResult(BaseModel):
    task_id: str
    success: bool
    final_score: float = Field(..., gt=0.0, lt=1.0)
    total_steps: int
    total_reward: float
    termination_reason: Literal["success", "timeout", "critical_failure"]