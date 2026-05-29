import logging
import os
import signal
import socket
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, ClassVar, Dict, List, Optional

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

LOGGER = logging.getLogger(__name__)


@dataclass
class Config:
    """IoT agent configuration loaded from environment variables."""

    agent_name: str
    iot_server_url: str
    poll_interval: int
    registration_retries: int = 10
    request_timeout: int = 5

    @classmethod
    def from_env(cls) -> "Config":
        """Creates a Config instance from environment variables, falling back to defaults."""
        return cls(
            agent_name=os.getenv("AGENT_NAME", socket.gethostname()),
            iot_server_url=os.getenv("IOT_SERVER_URL", "http://iot-server:7000"),
            poll_interval=int(os.getenv("POLL_INTERVAL", 2)),
        )


@dataclass
class CommandTask:
    """Represents a task received from the IoT server."""

    queue_id: int
    function_code: str
    parameters: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommandTask":
        """Constructs a CommandTask from a dictionary, validating required fields.

        Raises ValueError if queue_id is missing or not an integer, or if function_code
        is missing or not a string.
        """
        queue_id = data.get("queue_id")
        if not isinstance(queue_id, int) or isinstance(queue_id, bool):
            raise ValueError(f"'queue_id' must be an integer, got: {type(queue_id).__name__}")

        function_code = data.get("function_code")
        if not isinstance(function_code, str):
            raise ValueError(f"'function_code' must be a string, got: {type(function_code).__name__}")

        return cls(
            queue_id=queue_id,
            function_code=function_code,
            parameters=data.get("parameters", {}),
        )


@dataclass
class ExecutionResult:
    """Holds the result of a command execution, including success status and output."""

    queue_id: int
    is_error: bool
    result: str

    def to_dict(self) -> Dict[str, Any]:
        """Returns the execution result as a dictionary suitable for JSON serialization."""
        return asdict(self)


class Agent:
    """Manages the IoT agent lifecycle using dedicated OS threads for parallel execution."""

    __ALLOWED_BUILTINS: ClassVar[Dict[str, Any]] = {
        "ArithmeticError": ArithmeticError,
        "AssertionError": AssertionError,
        "AttributeError": AttributeError,
        "BaseException": BaseException,
        "Exception": Exception,
        "False": False,
        "IndexError": IndexError,
        "ImportError": ImportError,
        "KeyError": KeyError,
        "LookupError": LookupError,
        "None": None,
        "StopIteration": StopIteration,
        "True": True,
        "TypeError": TypeError,
        "ValueError": ValueError,
        "__build_class__": __build_class__,
        "abs": abs,
        "aiter": aiter,
        "all": all,
        "anext": anext,
        "any": any,
        "ascii": ascii,
        "bin": bin,
        "bool": bool,
        "bytearray": bytearray,
        "bytes": bytes,
        "callable": callable,
        "chr": chr,
        "complex": complex,
        "dict": dict,
        "dir": dir,
        "divmod": divmod,
        "enumerate": enumerate,
        "filter": filter,
        "float": float,
        "format": format,
        "frozenset": frozenset,
        "hasattr": hasattr,
        "hash": hash,
        "hex": hex,
        "id": id,
        "int": int,
        "isinstance": isinstance,
        "issubclass": issubclass,
        "iter": iter,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "next": next,
        "object": object,
        "oct": oct,
        "ord": ord,
        "pow": pow,
        "print": print,
        "range": range,
        "repr": repr,
        "reversed": reversed,
        "round": round,
        "set": set,
        "slice": slice,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "type": type,
        "zip": zip,
    }

    __ALLOWED_MODULES: ClassVar[List[str]] = ["time", "math"]

    def __init__(self, config: Config):
        """Initializes the agent with an HTTP client and a sandboxed execution environment."""
        self.config = config
        self.device_id: Optional[int] = None
        self.client = httpx.Client(timeout=config.request_timeout)
        self.__exec_globals: Dict = self.build_exec_globals()
        self.current_task: Optional[CommandTask] = None
        self.task_lock = threading.Lock()
        self.task_event = threading.Event()

    @classmethod
    def build_exec_globals(cls) -> Dict:
        """Builds a globals dictionary with restricted builtins and a module import guard limited to allowed modules."""

        def __restricted_import__(name, globals=None, locals=None, fromlist=(), level=0):
            if name.split(".")[0] in cls.__ALLOWED_MODULES:
                return __import__(name, globals, locals, fromlist, level)
            raise ImportError(f"Import of '{name}' is forbidden.")

        exec_globals = {"__builtins__": cls.__ALLOWED_BUILTINS.copy()}
        exec_globals["__builtins__"]["__import__"] = __restricted_import__
        return exec_globals

    def register(self) -> bool:
        """Registers the agent synchronously with exponential backoff."""
        for attempt in range(1, self.config.registration_retries + 1):
            try:
                response = self.client.post(
                    f"{self.config.iot_server_url}/agent/register",
                    json={"name": self.config.agent_name},
                )
                response.raise_for_status()
                self.device_id = response.json()["device_id"]
                return True
            except Exception as e:
                LOGGER.warning(f"Registration attempt {attempt} failed: {e}")
                time.sleep(2 ** min(attempt - 1, 3))
        return False

    def heartbeat_loop(self):
        """Dedicated thread loop for polling the server and identifying jobs."""
        LOGGER.info("Heartbeat thread started.")
        while True:
            try:
                response = self.client.get(f"{self.config.iot_server_url}/agent/{self.device_id}/commands")
                response.raise_for_status()
                response_data = response.json()

                queue_id = response_data.get("queue_id")
                if queue_id is not None:
                    with self.task_lock:
                        if self.current_task and self.current_task.queue_id == queue_id:
                            LOGGER.debug(f"Polled job {queue_id} is already executing.")
                            continue

                        if self.current_task is None:
                            LOGGER.info(f"Received job {queue_id}. Triggering worker.")
                            self.current_task = CommandTask.from_dict(response_data)
                            self.task_event.set()
                        else:
                            LOGGER.warning(f"Server offered job {queue_id}, but agent is busy.")
            except Exception as e:
                LOGGER.error(f"Heartbeat communication error: {e}")
            finally:
                time.sleep(self.config.poll_interval)

    def worker_loop(self):
        """Dedicated thread loop for executing tasks sequentially."""
        LOGGER.info("Worker thread started.")
        while True:
            self.task_event.wait()
            self.task_event.clear()

            with self.task_lock:
                task = self.current_task

            if task is None:
                continue

            try:
                execution_result = self.execute_command(task)
                if execution_result.is_error:
                    LOGGER.warning(f"Task failed (Queue ID: {task.queue_id}): {execution_result.result}")
                else:
                    LOGGER.info(f"Task completed successfully (Queue ID: {task.queue_id})")
                self.send_callback(execution_result)
            except Exception as e:
                LOGGER.error(f"Unexpected worker error on Queue ID {task.queue_id}: {e}")
            finally:
                with self.task_lock:
                    self.current_task = None

    def execute_command(self, task: CommandTask) -> ExecutionResult:
        """Executes Python code raw inside the worker thread context."""
        result_payload = ExecutionResult(queue_id=task.queue_id, is_error=False, result="")
        LOGGER.info(f"Executing task (Queue ID: {task.queue_id})")
        try:
            local_env = {}
            scoped_globals = self.__exec_globals.copy()

            exec(task.function_code, scoped_globals, local_env)
            if "_sicc_command" not in local_env:
                raise Exception("Function '_sicc_command' was not defined.")

            result_payload.result = str(local_env["_sicc_command"](**task.parameters))
        except Exception as e:
            result_payload.is_error = True
            result_payload.result = f"{type(e).__name__}: {e}"
        return result_payload

    def send_callback(self, result: ExecutionResult):
        """Sends command callback to the IoT server"""
        try:
            self.client.post(f"{self.config.iot_server_url}/agent/callback", json=result.to_dict())
        except Exception as e:
            LOGGER.error(f"Failed to send callback for Queue ID {result.queue_id}: {e}")

    def run(self):
        """Main agent loop"""
        LOGGER.info(f"Starting Threaded IoT agent: '{self.config.agent_name}'")
        if not self.register():
            LOGGER.critical("Registration failed. Shutting down.")
            return

        LOGGER.info(f"Agent registered successfully. Assigned ID: {self.device_id}")

        shutdown_event = threading.Event()

        def handle_shutdown_signal(signum, frame):
            """Handling of Docker's shutdown signals"""
            LOGGER.info(f"Received signal {signum}. Initiating clean shutdown...")
            shutdown_event.set()

        signal.signal(signal.SIGTERM, handle_shutdown_signal)
        signal.signal(signal.SIGINT, handle_shutdown_signal)

        heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        worker_thread = threading.Thread(target=self.worker_loop, daemon=True)

        heartbeat_thread.start()
        worker_thread.start()

        shutdown_event.wait()

        LOGGER.info("Closing active connections...")
        self.client.close()
        LOGGER.info("Agent shut down cleanly.")


if __name__ == "__main__":
    config = Config.from_env()
    agent = Agent(config)
    agent.run()
