from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
import uvicorn
import logging

from models import DevOpsAction, DevOpsObservation, DevOpsTask
from environment import DependencyHellEnv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dependency-hell-api")

app = FastAPI(
    title="Dependency Hell - OpenEnv CI/CD Environment",
    description="An autonomous DevOps agent environment for debugging and fixing server crashes.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

env = DependencyHellEnv()

class ResetRequest(BaseModel):
    task_id: str = Field(default="level_1_easy")
    model_config = {"extra": "allow"}

class StepRequest(BaseModel):
    action: DevOpsAction

class StepResponse(BaseModel):
    observation: DevOpsObservation
    reward: float
    done: bool
    info: Dict[str, Any] = Field(default_factory=dict)

class TasksResponse(BaseModel):
    tasks: List[DevOpsTask]
    action_schema: Dict[str, Any]
    observation_schema: Dict[str, Any]

class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str

@app.post("/reset")
def reset_environment(request: Optional[ResetRequest] = None):
    try:
        task_id = request.task_id if request else "level_1_easy"
        obs = env.reset(task_id=task_id)
        return obs
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid task_id: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Environment reset failed: {str(e)}")

@app.post("/step")
def take_step(request: StepRequest):
    try:
        obs, reward, done, info = env.step(request.action)
        score = max(0.01, min(0.99, reward))
        info["score"] = score
        return StepResponse(observation=obs, reward=reward, done=done, info=info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Step execution failed: {str(e)}")

@app.get("/state")
def get_state():
    try:
        return env.state()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"State retrieval failed: {str(e)}")

@app.get("/tasks")
def get_tasks():
    try:
        return TasksResponse(
            tasks=DependencyHellEnv.TASKS,
            action_schema=DevOpsAction.model_json_schema(),
            observation_schema=DevOpsObservation.model_json_schema()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tasks retrieval failed: {str(e)}")

@app.get("/health")
def health_check():
    return HealthResponse(status="healthy", version="1.0.0", environment="dependency-hell-ci-cd")

@app.get("/metadata")
def get_metadata():
    return {
        "env_name": "dependency-hell",
        "description": "An autonomous DevOps agent environment for debugging and fixing server crashes.",
        "version": "1.0.0",
        "num_tasks": len(DependencyHellEnv.TASKS),
        "task_ids": [t.task_id for t in DependencyHellEnv.TASKS],
        "action_space_type": "discrete",
        "observation_space_type": "structured",
        "reward_range": (0.01, 0.99),
        "max_episode_length": 15,
        "spec_compliance": "OpenEnv v1.0"
    }

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={"error": "Internal server error"})

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Dependency Hell API starting up...")
    logger.info(f"Available tasks: {len(DependencyHellEnv.TASKS)}")
    logger.info("✅ Server ready. Hit POST /reset to start an episode.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Dependency Hell API shutting down.")

@app.get("/")
def root():
    return {
        "name": "Dependency Hell - OpenEnv CI/CD Environment",
        "version": "1.0.0",
        "description": "An autonomous DevOps agent environment for debugging and fixing server crashes.",
        "docs": "/docs",
        "quick_start": {
            "1_list_tasks": "GET /tasks",
            "2_reset": "POST /reset with body {'task_id': 'level_1_easy'}",
            "3_step": "POST /step with body {'action': {...}}",
            "4_check_state": "GET /state",
            "5_health": "GET /health"
        }
    }

def main():
    uvicorn.run(app, host="0.0.0.0", port=7860)

if __name__ == "__main__":
    main()