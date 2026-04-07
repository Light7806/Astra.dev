"""
FastAPI server for the Dependency Hell CI/CD debugging environment.
Wraps the DependencyHellEnv simulator and exposes it via HTTP endpoints.
OpenEnv spec compliant.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
import uvicorn
from fastapi.responses import JSONResponse
import logging

from models import DevOpsAction, DevOpsObservation, DevOpsTask
from environment import DependencyHellEnv

# ============================================================
# LOGGING SETUP
# ============================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dependency-hell-api")

# ============================================================
# FASTAPI APP INITIALIZATION
# ============================================================
app = FastAPI(
    title="Dependency Hell - OpenEnv CI/CD Environment",
    description="An autonomous DevOps agent environment for debugging and fixing server crashes.",
    version="1.0.0"
)

# Add CORS middleware for HF Space + external clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# GLOBAL ENVIRONMENT INSTANCE
# ============================================================
# NOTE: In production, you'd want per-session environments.
# For this hackathon submission, a global instance is acceptable
# since judges will test serially, not concurrently.
env = DependencyHellEnv()

# ============================================================
# REQUEST/RESPONSE MODELS (Wrapper classes for API clarity)
# ============================================================

class ResetRequest(BaseModel):
    """Request body for the /reset endpoint."""
    task_id: str = Field(
        default="level_1_easy",
        description="The task to load (e.g., 'level_1_easy', 'level_5_hard')"
    )
    
    model_config = {"extra": "allow"}


class StepRequest(BaseModel):
    """Request body for the /step endpoint."""
    action: DevOpsAction = Field(
        ...,
        description="The action to execute in the environment"
    )


class StepResponse(BaseModel):
    """Response body from /step endpoint."""
    observation: DevOpsObservation
    reward: float = Field(
        ...,
        description="Reward signal for this step"
    )
    done: bool = Field(
        ...,
        description="Whether the episode has ended"
    )
    info: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (task_id, step count, total reward, etc.)"
    )


class TasksResponse(BaseModel):
    """Response body from /tasks endpoint."""
    tasks: List[DevOpsTask]
    action_schema: Dict[str, Any] = Field(
        ...,
        description="JSON schema for DevOpsAction"
    )
    observation_schema: Dict[str, Any] = Field(
        ...,
        description="JSON schema for DevOpsObservation"
    )


class HealthResponse(BaseModel):
    """Response body from /health endpoint."""
    status: str
    version: str
    environment: str


# ============================================================
# OPENENV-REQUIRED ENDPOINTS
# ============================================================

@app.post("/reset")
def reset_environment(request: Optional[ResetRequest] = None):
    """
    Reset the environment to a broken state and return initial observation.
    """
    try:
        task_id = request.task_id if request else "level_1_easy"
        logger.info(f"Resetting environment to task: {task_id}")
        obs = env.reset(task_id=task_id)
        logger.info(f"Environment reset successful. Files visible: {obs.visible_files}")
        return obs
    except ValueError as e:
        logger.error(f"Invalid task_id: {task_id}")
        raise HTTPException(status_code=400, detail=f"Invalid task_id: {str(e)}")
    except Exception as e:
        logger.error(f"Error resetting environment: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Environment reset failed: {str(e)}")


@app.post("/step")
def take_step(request: StepRequest):
    """
    Execute one action in the environment and return the result.
    
    Args:
        action: A DevOpsAction (read_file, overwrite_file, run_build, or revert_commit)
    
    Returns:
        StepResponse containing (observation, reward, done, info)
    
    Raises:
        HTTPException(400): If action is malformed
        HTTPException(500): If something goes wrong in the environment
    """
    try:
        logger.info(f"Executing action: {request.action.action_type}")
        obs, reward, done, info = env.step(request.action)
        logger.info(f"Step {info.get('step', '?')} complete. Reward: {reward:.3f}, Done: {done}")
        
        return StepResponse(
            observation=obs,
            reward=reward,
            done=done,
            info=info
        )
    except Exception as e:
        logger.error(f"Error during step: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Step execution failed: {str(e)}")


@app.get("/state")
def get_state():
    """
    Return the full internal state of the environment (for debugging).
    Shows all files, step counts, rewards, etc.
    
    Returns:
        Dictionary containing current_files, visible_files, step_count, total_reward, etc.
    """
    try:
        state = env.state()
        logger.info(f"State queried. Current files: {state.get('visible_files', [])}")
        return state
    except Exception as e:
        logger.error(f"Error retrieving state: {str(e)}")
        raise HTTPException(status_code=500, detail=f"State retrieval failed: {str(e)}")


# ============================================================
# INFORMATIONAL ENDPOINTS (For judges to inspect the environment)
# ============================================================

@app.get("/tasks")
def get_tasks():
    """
    Return all available tasks and the action/observation schemas.
    Judges use this to understand what the environment offers.
    
    Returns:
        TasksResponse with task list and JSON schemas
    """
    try:
        return TasksResponse(
            tasks=DependencyHellEnv.TASKS,
            action_schema=DevOpsAction.model_json_schema(),
            observation_schema=DevOpsObservation.model_json_schema()
        )
    except Exception as e:
        logger.error(f"Error retrieving tasks: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Tasks retrieval failed: {str(e)}")


@app.get("/health")
def health_check():
    """
    Health check endpoint. Judges hit this to verify the server is running.
    
    Returns:
        HealthResponse with status and version info
    """
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        environment="dependency-hell-ci-cd"
    )


# ============================================================
# OPENENV METADATA ENDPOINT
# ============================================================

@app.get("/metadata")
def get_metadata():
    """
    Return OpenEnv metadata about this environment.
    Used by openenv validate and HF Space validators.
    
    Returns:
        Metadata dictionary with env name, description, task count, etc.
    """
    return {
        "env_name": "dependency-hell",
        "description": "An autonomous DevOps agent environment for debugging and fixing server crashes.",
        "version": "1.0.0",
        "num_tasks": len(DependencyHellEnv.TASKS),
        "task_ids": [t.task_id for t in DependencyHellEnv.TASKS],
        "action_space_type": "discrete",
        "observation_space_type": "structured",
        "reward_range": (-1.0, 1.0),
        "max_episode_length": 15,
        "spec_compliance": "OpenEnv v1.0"
    }


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler with logging."""
    logger.error(f"HTTP Exception: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Catch-all exception handler."""
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )

# ============================================================
# STARTUP/SHUTDOWN EVENTS
# ============================================================

@app.on_event("startup")
async def startup_event():
    """Called when the server starts."""
    logger.info("🚀 Dependency Hell API starting up...")
    logger.info(f"Available tasks: {len(DependencyHellEnv.TASKS)}")
    logger.info("✅ Server ready. Hit POST /reset to start an episode.")


@app.on_event("shutdown")
async def shutdown_event():
    """Called when the server shuts down."""
    logger.info("🛑 Dependency Hell API shutting down.")


# ============================================================
# ROOT ENDPOINT (Welcome message)
# ============================================================

@app.get("/")
def root():
    """
    Root endpoint. Provides quick info about the API.
    """
    return {
        "name": "Dependency Hell - OpenEnv CI/CD Environment",
        "version": "1.0.0",
        "description": "An autonomous DevOps agent environment for debugging and fixing server crashes.",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "quick_start": {
            "1_list_tasks": "GET /tasks",
            "2_reset": "POST /reset with body {'task_id': 'level_1_easy'}",
            "3_step": "POST /step with body {'action': {...}}",
            "4_check_state": "GET /state",
            "5_health": "GET /health"
        }
    }
# ============================================================
# MAIN: RUN THE SERVER
# ============================================================

if __name__ == "__main__":
    logger.info("🎯 Booting Dependency Hell API...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
def main():
    uvicorn.run(app, host="0.0.0.0", port=7860)    