import copy
import json
import re
from typing import Tuple, Optional
from models import DevOpsAction, DevOpsObservation, DevOpsTask, DevOpsReward, EpisodeResult

class DependencyHellEnv:
    TASKS = [
        DevOpsTask(
            task_id="level_1_easy",
            difficulty="easy",
            description="The build is failing. Fix the missing flask dependency in requirements.txt.",
            max_steps=15,
            tags=["dependencies", "beginner"]
        ),
        DevOpsTask(
            task_id="level_2_easy",
            difficulty="easy",
            description="The server crashed. Fix the Syntax Sabotage in config.json (missing comma after 'port' line).",
            max_steps=15,
            tags=["syntax", "json", "beginner"]
        ),
        DevOpsTask(
            task_id="level_3_medium",
            difficulty="medium",
            description="Security scanner blocked the build. Remove the leaked AWS key from app.py and use os.environ.get('SECRET_KEY') instead.",
            max_steps=15,
            tags=["security", "environment-variables"]
        ),
        DevOpsTask(
            task_id="level_4_medium",
            difficulty="medium",
            description="Environment variable missing! The app crashes because DATABASE_URL is not set. Add it to config.env.",
            max_steps=15,
            tags=["environment-variables", "configuration"]
        ),
        DevOpsTask(
            task_id="level_5_hard",
            difficulty="hard",
            description="BOSS FIGHT: Set debug to false in prod.yaml WITHOUT altering the prod_db_cluster connection string. One wrong move and you delete production.",
            max_steps=15,
            tags=["production", "careful-editing"]
        )
    ]

    def __init__(self):
        self.initial_files = {}
        self.current_files = {}
        self.current_task: Optional[DevOpsTask] = None
        self.step_count = 0
        self.max_steps = 15
        self.total_reward = 0.01
        self.episode_done = False
        self.read_history = set()
        self.last_action = None
        self.last_build_failed = False

    def reset(self, task_id: str = "level_1_easy") -> DevOpsObservation:
        self.step_count = 0
        self.total_reward = 0.01
        self.episode_done = False
        self.read_history = set()
        self.last_action = None
        self.last_build_failed = False

        self.current_task = next((t for t in self.TASKS if t.task_id == task_id), None)
        if not self.current_task:
            raise ValueError(f"Unknown task_id: {task_id}")

        self.max_steps = self.current_task.max_steps

        if task_id == "level_1_easy":
            self.initial_files = {
                "requirements.txt": "requests==2.28.0\nnumpy==1.24.0",
                "app.py": "import flask\nprint('App started!')"
            }
        elif task_id == "level_2_easy":
            self.initial_files = {
                "config.json": '{\n  "host": "localhost",\n  "port": 8080\n  "debug": true\n}',
                "app.py": "import json\njson.load(open('config.json'))"
            }
        elif task_id == "level_3_medium":
            self.initial_files = {
                "app.py": "import os\nSECRET_KEY = 'AKIAIOSFODNN7EXAMPLE'\ndef login():\n    return True"
            }
        elif task_id == "level_4_medium":
            self.initial_files = {
                "app.py": "import os\nDATABASE_URL = os.environ['DATABASE_URL']\nprint(f'Connecting to {DATABASE_URL}')",
                "config.env": "DEBUG=true\nSECRET_KEY=mysecret"
            }
        elif task_id == "level_5_hard":
            self.initial_files = {
                "prod.yaml": "server:\n  debug: true\n  port: 443\ndatabase:\n  url: 'postgres://admin:secret@prod-db-cluster.aws.com/main'"
            }

        self.current_files = copy.deepcopy(self.initial_files)
        return self._get_observation("Environment ready. Awaiting your first command...")

    def step(self, action: DevOpsAction) -> Tuple[DevOpsObservation, float, bool, dict]:
        self.step_count += 1
        self.last_action = action.action_type

        log_output = ""
        reward = 0.01
        done = False

        # ===== TIMEOUT CHECK =====
        if self.step_count >= self.max_steps:
            log_output = f"❌ TIMEOUT: Max {self.max_steps} steps reached. Episode terminated."
            reward = 0.01
            self.episode_done = True
            done = True
            return self._get_observation(log_output), reward, done, {
                "task_id": self.current_task.task_id,
                "termination_reason": "timeout"
            }

        # ===== ACTION: READ_FILE =====
        if action.action_type == "read_file":
            if not action.file_name:
                log_output = "❌ Error: file_name is required for read_file."
                reward = 0.01
            elif action.file_name not in self.current_files:
                log_output = f"❌ FileNotFoundError: '{action.file_name}' does not exist."
                reward = 0.01
            else:
                log_output = f"--- {action.file_name} ---\n{self.current_files[action.file_name]}"
                if action.file_name in self.read_history:
                    reward = 0.01
                else:
                    reward = 0.05
                    self.read_history.add(action.file_name)

        # ===== ACTION: OVERWRITE_FILE =====
        elif action.action_type == "overwrite_file":
            if not action.file_name or action.content is None:
                log_output = "❌ Error: file_name and content are both required for overwrite_file."
                reward = 0.01
            else:
                self.current_files[action.file_name] = action.content
                log_output = f"✓ Wrote {len(action.content)} characters to {action.file_name}"
                reward = 0.10

        # ===== ACTION: REVERT_COMMIT =====
        elif action.action_type == "revert_commit":
            self.current_files = copy.deepcopy(self.initial_files)
            log_output = "↶ git reset --hard HEAD (Reverted to broken initial state)"
            reward = 0.01

        # ===== ACTION: RUN_BUILD =====
        elif action.action_type == "run_build":
            grader_result = self._grade_task()
            log_output = grader_result["log"]
            reward = grader_result["reward"]
            done = grader_result["done"]

            if done:
                self.episode_done = True
            if grader_result["reward"] < 0.5:
                self.last_build_failed = True

        else:
            log_output = f"❌ Unknown action_type: {action.action_type}"
            reward = 0.01

        # ===== SAFETY CLAMP — always strictly between 0.01 and 0.99 =====
        reward = max(0.01, min(0.99, reward))

        self.total_reward += reward

        return self._get_observation(log_output), reward, done, {
            "task_id": self.current_task.task_id,
            "step": self.step_count,
            "total_reward": round(self.total_reward, 2)
        }

    def _grade_task(self) -> dict:
        task_id = self.current_task.task_id

        if task_id == "level_1_easy":
            req_text = self.current_files.get("requirements.txt", "").lower()
            if "flask" in req_text:
                return {
                    "log": "✅ BUILD PASS: flask dependency found. App will start.",
                    "reward": 0.99,
                    "done": True
                }
            else:
                return {
                    "log": "❌ BUILD FAIL: ModuleNotFoundError: No module named 'flask'",
                    "reward": 0.02,
                    "done": False
                }

        elif task_id == "level_2_easy":
            config_text = self.current_files.get("config.json", "")
            try:
                json.loads(config_text)
                return {
                    "log": "✅ BUILD PASS: config.json is valid JSON. Server booting...",
                    "reward": 0.99,
                    "done": True
                }
            except json.JSONDecodeError as e:
                return {
                    "log": f"❌ BUILD FAIL: JSONDecodeError at line {e.lineno}: {e.msg}",
                    "reward": 0.02,
                    "done": False
                }

        elif task_id == "level_3_medium":
            code = self.current_files.get("app.py", "")
            has_akia = "AKIA" in code or "AKIAIOSFODNN" in code
            uses_environ = "os.environ" in code

            if not has_akia and uses_environ:
                return {
                    "log": "✅ BUILD PASS: Secret key removed. Using environment variables.",
                    "reward": 0.99,
                    "done": True
                }
            elif has_akia:
                return {
                    "log": "❌ BUILD FAIL: Security Scan Blocked - Leaked AWS credential detected in app.py",
                    "reward": 0.02,
                    "done": False
                }
            else:
                return {
                    "log": "❌ BUILD FAIL: SECRET_KEY is hardcoded. Must use os.environ.get()",
                    "reward": 0.02,
                    "done": False
                }

        elif task_id == "level_4_medium":
            config_text = self.current_files.get("config.env", "")
            if re.search(r'DATABASE_URL\s*=\s*\S+', config_text):
                return {
                    "log": "✅ BUILD PASS: DATABASE_URL found in config.env. App will connect.",
                    "reward": 0.99,
                    "done": True
                }
            else:
                return {
                    "log": "❌ BUILD FAIL: KeyError: 'DATABASE_URL' environment variable not found",
                    "reward": 0.02,
                    "done": False
                }

        elif task_id == "level_5_hard":
            yaml_text = self.current_files.get("prod.yaml", "")

            if "prod-db-cluster" not in yaml_text or "database:" not in yaml_text:
                return {
                    "log": "💀 CRITICAL: PRODUCTION DATABASE DELETED. YOU ARE FIRED.",
                    "reward": 0.01,
                    "done": True
                }

            debug_false = re.search(r'debug\s*:\s*false', yaml_text, re.IGNORECASE)
            if debug_false:
                return {
                    "log": "✅ DEPLOY SUCCESS: Debug disabled. Database intact. Production is safe.",
                    "reward": 0.99,
                    "done": True
                }
            else:
                return {
                    "log": "❌ DEPLOY REJECTED: Debug mode is still active. Cannot deploy to production.",
                    "reward": 0.02,
                    "done": False
                }

        return {
            "log": "❌ Unknown task_id",
            "reward": 0.01,
            "done": False
        }

    def _get_observation(self, log: str) -> DevOpsObservation:
        tests_passed = 1 if self.episode_done else 0
        if self.episode_done:
            build_status = "passing"
        elif self.last_build_failed:
            build_status = "failing"
        else:
            build_status = "pending"

        return DevOpsObservation(
            terminal_output=log,
            visible_files=sorted(list(self.current_files.keys())),
            current_task=self.current_task.description,
            steps_remaining=max(0, self.max_steps - self.step_count),
            tests_passed=tests_passed,
            total_tests=1,
            build_status=build_status
        )

    def state(self) -> dict:
        return {
            "task_id": self.current_task.task_id if self.current_task else None,
            "step_count": self.step_count,
            "max_steps": self.max_steps,
            "total_reward": self.total_reward,
            "episode_done": self.episode_done,
            "current_files": self.current_files,
            "initial_files": self.initial_files,
            "visible_files": sorted(list(self.current_files.keys()))
        }

    def get_episode_result(self) -> Optional[EpisodeResult]:
        if not self.episode_done:
            return None

        grader_result = self._grade_task()
        success = grader_result["reward"] >= 0.99

        return EpisodeResult(
            task_id=self.current_task.task_id,
            success=success,
            final_score=0.99 if success else 0.01,
            total_steps=self.step_count,
            total_reward=self.total_reward,
            termination_reason="success" if success else "timeout" if self.step_count >= self.max_steps else "critical_failure"
        )