"""
inference.py — Dependency Hell Baseline Agent
==============================================
Runs an OpenAI-compatible LLM agent against the Dependency Hell environment.
Emits structured stdout logs in the required [START] / [STEP] / [END] format.
"""

import json
import os
import sys
from typing import Optional
import requests
from openai import OpenAI

# ============================================================
# CONFIGURATION — All read from environment variables
# ============================================================
API_KEY      = os.environ.get("HF_TOKEN")
API_BASE_URL = os.environ.get("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME   = os.environ.get("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
ENV_BASE_URL = os.environ.get("ENV_BASE_URL", "https://abhi-x-light-dependency-hell.hf.space")
BENCHMARK    = "dependency-hell"
MAX_STEPS    = 15  # Bumped to 15 to match the environment task limits
# ============================================================
# STRUCTURED STDOUT LOGGING — Exact required format
# ============================================================

def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val  = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, rewards: list, score: float = 0.0) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


# ============================================================
# OPENAI TOOL DEFINITION
# ============================================================
devops_tools = [
    {
        "type": "function",
        "function": {
            "name": "take_action",
            "description": (
                "Execute a DevOps command on the CI/CD server. "
                "Start by reading files to understand the problem. "
                "Then overwrite the broken file with your fix. "
                "Finally call run_build to verify. You MUST call run_build to complete the task."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action_type": {
                        "type": "string",
                        "enum": ["read_file", "overwrite_file", "run_build", "revert_commit"],
                        "description": "The command to execute."
                    },
                    "file_name": {
                        "type": "string",
                        "description": "Target file. Required for read_file and overwrite_file."
                    },
                    "content": {
                        "type": "string",
                        "description": "New file content. Required for overwrite_file."
                    }
                },
                "required": ["action_type"]
            }
        }
    }
]


# ============================================================
# SINGLE TASK AGENT LOOP
# ============================================================
def run_single_task(client: OpenAI, task_id: str, task_description: str) -> dict:
    rewards     = []
    steps_taken = 0
    success     = False

    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)

    try:
        # --- Reset environment ---
        reset_resp = requests.post(
            f"{ENV_BASE_URL}/reset",
            json={"task_id": task_id},
            timeout=30
        )
        reset_resp.raise_for_status()
        obs = reset_resp.json()

        # --- Build conversation ---
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an elite DevOps AI agent. Fix broken CI/CD pipelines.\n\n"
                    "STRATEGY:\n"
                    "1. READ files first to understand what is broken.\n"
                    "2. Identify the exact problem.\n"
                    "3. OVERWRITE the broken file with the precise fix.\n"
                    "4. Call RUN_BUILD to verify.\n\n"
                    "RULES:\n"
                    "- You MUST call run_build to complete the task.\n"
                    "- Do not read the same file twice.\n"
                    "- Only change what is broken — nothing else.\n"
                    "- For security tasks: remove hardcoded secrets, use os.environ.get().\n"
                    "- For production tasks: NEVER delete database connection strings.\n"
                    "- For env variable tasks: add missing variables to config files.\n"
                )
            },
            {
                "role": "user",
                "content": (
                    f"Task: {task_description}\n\n"
                    f"Initial state:\n{json.dumps(obs, indent=2)}"
                )
            }
        ]

        for step in range(1, MAX_STEPS + 1):
            # --- Ask the model what to do ---
            completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=devops_tools,
                tool_choice="required",
                temperature=0.1,
                max_tokens=1000,
            )

            message = completion.choices[0].message

            if not message.tool_calls:
                log_step(step=step, action="no_tool_call", reward=0, done=False, error="model returned no tool call")
                rewards.append(0)
                steps_taken = step
                break

            tool_call   = message.tool_calls[0]
            action_args = json.loads(tool_call.function.arguments)
            action_str  = action_args.get("action_type", "unknown")
            if action_args.get("file_name"):
                action_str += f"({action_args['file_name']})"

            # --- Execute action in environment ---
            error_msg = None
            reward    = 0
            done      = False

            try:
                env_resp = requests.post(
                    f"{ENV_BASE_URL}/step",
                    json={"action": action_args},
                    timeout=30
                )
                env_resp.raise_for_status()
                result = env_resp.json()

                obs    = result.get("observation", {})
                reward = float(result.get("reward", 0.0))
                done   = bool(result.get("done", False))

            except Exception as e:
                error_msg = str(e)
                done      = False

            rewards.append(reward)
            steps_taken = step

            log_step(step=step, action=action_str, reward=reward, done=done, error=error_msg)

            # --- Update conversation with result ---
            messages.append(message)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps({
                    "terminal_output":  obs.get("terminal_output", ""),
                    "visible_files":    obs.get("visible_files", []),
                    "steps_remaining":  obs.get("steps_remaining", 0),
                    "build_status":     obs.get("build_status", "pending"),
                    "reward":           reward,
                    "done":             done
                })
            })

            if done:
                break

        # --- Determine success ---
        success = len(rewards) > 0 and rewards[-1] >= 0.99

    except Exception as e:
        log_step(
            step=steps_taken + 1,
            action="exception",
            reward=0,
            done=True,
            error=str(e)
        )
        rewards.append(0.0)
        steps_taken += 1

    finally:
        # UPDATED: Score is strictly within (0, 1) to pass hackathon validator
        score = 0.99 if success else 0.01
        log_end(success=success, steps=steps_taken, rewards=rewards, score=score)

    return {
        "task_id":      task_id,
        "success":      success,
        # UPDATED: Score is strictly within (0, 1)
        "final_score":  0.99 if success else 0.01,
        "total_steps":  steps_taken,
        "total_reward": round(sum(rewards), 2)
    }


# ============================================================
# MAIN — RUN ALL TASKS
# ============================================================
def main():
    if not API_KEY:
        # Ensure fail log also complies with the (0, 1) rule
        print("[END] success=false steps=0 score=0.010 rewards=", flush=True)
        print("ERROR: Please set HF_TOKEN environment variable.", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=API_KEY, base_url=API_BASE_URL)

    # --- Fetch tasks from environment server ---
    try:
        tasks_resp = requests.get(f"{ENV_BASE_URL}/tasks", timeout=30)
        tasks_resp.raise_for_status()
        tasks = tasks_resp.json().get("tasks", [])
    except Exception as e:
        print(f"ERROR: Could not reach environment server at {ENV_BASE_URL}: {e}", file=sys.stderr)
        print("Make sure the server is running: python app.py", file=sys.stderr)
        sys.exit(1)

    results = []

    for task in tasks:
        task_id          = task["task_id"]
        task_description = task["description"]

        try:
            result = run_single_task(client, task_id, task_description)
        except Exception as e:
            result = {
                "task_id":      task_id,
                "success":      False,
                # UPDATED: Score is strictly within (0, 1)
                "final_score":  0.01,
                "total_steps":  0,
                "total_reward": 0.0
            }

        results.append(result)

    # --- Summary to stderr so it doesn't pollute stdout log format ---
    passed = sum(1 for r in results if r["success"])
    avg    = sum(r["final_score"] for r in results) / len(results) if results else 0.0
    print(f"\n--- BASELINE SUMMARY ---", file=sys.stderr)
    print(f"Tasks passed : {passed} / {len(results)}", file=sys.stderr)
    print(f"Average score: {avg:.2f}", file=sys.stderr)
    for r in results:
        status = "PASS" if r["success"] else "FAIL"
        print(
            f"  {r['task_id']} | {status} | score={r['final_score']:.2f} | steps={r['total_steps']} | reward={r['total_reward']:+.2f}",
            file=sys.stderr
        )


if __name__ == "__main__":
    main()