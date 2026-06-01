import logging
import os
import signal
import socket
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, ClassVar, Dict, List, Optional

import httpx

from security import (
    ROLE_AGENT_IOT,
    CryptoError,
    Direction,
    HandshakeStart,
    SecureEnvelope,
    SecureSession,
    SecureSessionStore,
    complete_client_handshake,
    create_handshake_start,
    decrypt_envelope,
    ed25519_public_key_from_private_key,
    encrypt_envelope,
    load_secure_transport_settings,
    public_key_id,
)
from security.encoding import b64decode, b64encode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

LOGGER = logging.getLogger(__name__)


@dataclass
class Config:
    """IoT agent configuration loaded from environment variables."""

    agent_name: str
    iot_server_url: str
    iot_server_identity: str
    iot_server_key_id: str | None
    enrollment_token: str | None
    poll_interval: int
    registration_retries: int = 10
    request_timeout: int = 5

    @classmethod
    def from_env(cls) -> "Config":
        """Creates a Config instance from environment variables, falling back to defaults."""
        iot_server_identity = os.getenv("SICC_IOT_SERVER_IDENTITY")
        if not iot_server_identity:
            raise ValueError("SICC_IOT_SERVER_IDENTITY is required")

        return cls(
            agent_name=os.getenv("AGENT_NAME", socket.gethostname()),
            iot_server_url=os.getenv("IOT_SERVER_URL", "http://iot-server:7000"),
            iot_server_identity=iot_server_identity,
            iot_server_key_id=os.getenv("SICC_IOT_SERVER_KEY_ID") or None,
            enrollment_token=os.getenv("AGENT_ENROLLMENT_TOKEN") or None,
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
            raise ValueError(
                f"'queue_id' must be an integer, got: {type(queue_id).__name__}"
            )

        function_code = data.get("function_code")
        if not isinstance(function_code, str):
            raise ValueError(
                f"'function_code' must be a string, got: {type(function_code).__name__}"
            )

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


class SecureAgentTransport:
    """Agent-side encrypted transport for agent-IoT requests."""

    def __init__(self, config: Config):
        self.config = config
        self.settings, self.public_key = self._load_settings(config.agent_name)
        if self.settings.enabled and self.settings.identity != config.agent_name:
            raise ValueError(
                "SICC_SERVICE_IDENTITY must match AGENT_NAME when SECURE_MODE=true"
            )
        self.client = httpx.Client(timeout=config.request_timeout)
        self.session_store = SecureSessionStore()
        self.session_creation_lock = threading.RLock()

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    def close(self) -> None:
        self.client.close()

    def registration_payload(self) -> dict[str, Any]:
        payload = {"name": self.config.agent_name}
        if self.config.enrollment_token is not None:
            payload["enrollment_token"] = self.config.enrollment_token

        if self.settings.enabled:
            if self.public_key is None or self.settings.key_id is None:
                raise ValueError("agent signing key is not configured")

            payload.update(
                {
                    "public_key_id": self.settings.key_id,
                    "public_key": b64encode(self.public_key),
                }
            )

        return payload

    def request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        try:
            return self._request(method, path, json_data=json_data, params=params)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                self._discard_sessions()
                raise
            LOGGER.info("Agent-IoT secure session missing remotely; handshaking again")
            self._discard_sessions()
            return self._request(method, path, json_data=json_data, params=params)
        except (httpx.HTTPError, CryptoError, ValueError):
            self._discard_sessions()
            raise

    def _request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        session = self._get_or_create_session()
        with session.lock:
            seq = session.replay.state_for(
                Direction.CLIENT_TO_SERVER
            ).allocate_send_seq()
            request_envelope = encrypt_envelope(
                {
                    "method": method,
                    "path": path,
                    "json": json_data,
                    "params": params,
                },
                session.keys,
                session.transcript.protocol_version,
                session.transcript.session_id,
                Direction.CLIENT_TO_SERVER,
                seq=seq,
            )

            response = self.client.post(
                self._iot_url("/secure/agent-iot/request"),
                json=request_envelope.to_dict(),
            )
            response.raise_for_status()

            response_envelope = SecureEnvelope.from_dict(response.json())
            session.replay.state_for(Direction.SERVER_TO_CLIENT).accept_recv_seq(
                response_envelope.seq
            )
            response_body = decrypt_envelope(
                response_envelope,
                session.keys,
                session.transcript.protocol_version,
                Direction.SERVER_TO_CLIENT,
                max_skew_ms=self.settings.max_skew_ms,
            )

        status_code = response_body.get("status_code")
        if not isinstance(status_code, int) or isinstance(status_code, bool):
            raise ValueError("secure response missing status_code")

        return status_code, response_body.get("body")

    def _get_or_create_session(self) -> SecureSession:
        session = self.session_store.first()
        if session is not None:
            return session

        with self.session_creation_lock:
            session = self.session_store.first()
            if session is not None:
                return session
            return self._initiate_handshake()

    def _initiate_handshake(self) -> SecureSession:
        server_key_id = self._select_iot_server_key_id()
        start, client_ephemeral = create_handshake_start(
            self.settings,
            role=ROLE_AGENT_IOT,
            server_identity=self.config.iot_server_identity,
            server_key_id=server_key_id,
        )

        start_response = self.client.post(
            self._iot_url("/secure/agent-iot/handshake/start"),
            json=self._start_to_payload(start),
        )
        start_response.raise_for_status()
        data = start_response.json()
        self._validate_start_response(start, data)

        client_handshake = complete_client_handshake(
            self.settings,
            start,
            client_ephemeral,
            server_ephemeral_pubkey=self._decode_b64_field(
                data["server_ephemeral_pubkey"]
            ),
            server_signature=self._decode_b64_field(data["server_signature"]),
        )

        finish_response = self.client.post(
            self._iot_url("/secure/agent-iot/handshake/finish"),
            json={
                "session_id": client_handshake.transcript.session_id,
                "client_signature": b64encode(client_handshake.client_signature),
            },
        )
        finish_response.raise_for_status()

        session = SecureSession(
            transcript=client_handshake.transcript,
            keys=client_handshake.keys,
        )
        self.session_store.put(session)
        LOGGER.info(
            "Established agent-IoT secure session %s", session.transcript.session_id
        )
        return session

    def _select_iot_server_key_id(self) -> str:
        if self.config.iot_server_key_id:
            return self.config.iot_server_key_id
        raise ValueError("SICC_IOT_SERVER_KEY_ID is required when SECURE_MODE=true")

    def _discard_sessions(self) -> None:
        with self.session_creation_lock:
            self.session_store.clear()

    def _iot_url(self, path: str) -> str:
        return f"{self.config.iot_server_url.rstrip('/')}{path}"

    def _start_to_payload(self, start: HandshakeStart) -> dict[str, Any]:
        return {
            "role": start.role,
            "session_id": start.session_id,
            "client_identity": start.client_identity,
            "server_identity": start.server_identity,
            "client_key_id": start.client_key_id,
            "server_key_id": start.server_key_id,
            "client_ephemeral_pubkey": b64encode(start.client_ephemeral_pubkey),
            "timestamp_ms": start.timestamp_ms,
        }

    def _validate_start_response(
        self, start: HandshakeStart, data: dict[str, Any]
    ) -> None:
        expected = {
            "role": start.role,
            "session_id": start.session_id,
            "client_identity": start.client_identity,
            "server_identity": start.server_identity,
            "client_key_id": start.client_key_id,
            "server_key_id": start.server_key_id,
            "client_ephemeral_pubkey": b64encode(start.client_ephemeral_pubkey),
            "timestamp_ms": start.timestamp_ms,
            "protocol_version": self.settings.protocol_version,
            "algorithm_suite": self.settings.algorithm_suite,
        }
        for field, value in expected.items():
            if data.get(field) != value:
                raise ValueError(f"handshake response field mismatch: {field}")

    def _decode_b64_field(self, value: str) -> bytes:
        try:
            return b64decode(value)
        except Exception as exc:
            raise ValueError("invalid handshake base64 field") from exc

    def _load_settings(self, agent_name: str):
        source = dict(os.environ)
        if not source.get("SICC_SERVICE_IDENTITY"):
            source["SICC_SERVICE_IDENTITY"] = agent_name

        public_key = None
        if _parse_bool(source.get("SECURE_MODE", "false")):
            private_key_b64 = source.get("SICC_SERVICE_PRIVATE_KEY_B64")
            if private_key_b64:
                private_key = b64decode(private_key_b64)
                public_key = ed25519_public_key_from_private_key(private_key)
            else:
                raise ValueError(
                    "SICC_SERVICE_PRIVATE_KEY_B64 is required when SECURE_MODE=true"
                )

            derived_key_id = public_key_id(public_key)
            if not source.get("SICC_SERVICE_KEY_ID"):
                source["SICC_SERVICE_KEY_ID"] = derived_key_id
            elif source["SICC_SERVICE_KEY_ID"] != derived_key_id:
                raise ValueError(
                    "SICC_SERVICE_KEY_ID does not match SICC_SERVICE_PRIVATE_KEY_B64"
                )

        settings = load_secure_transport_settings(
            default_identity=agent_name,
            env=source,
        )
        return settings, public_key


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("SECURE_MODE must be a boolean")


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
        self.secure_transport = SecureAgentTransport(config)
        self.__exec_globals: Dict = self.build_exec_globals()
        self.current_task: Optional[CommandTask] = None
        self.task_lock = threading.Lock()
        self.task_event = threading.Event()

    @classmethod
    def build_exec_globals(cls) -> Dict:
        """Builds a globals dictionary with restricted builtins and a module import guard limited to allowed modules."""

        def __restricted_import__(
            name, globals=None, locals=None, fromlist=(), level=0
        ):
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
                    json=self.secure_transport.registration_payload(),
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
                if self.secure_transport.enabled:
                    status_code, response_data = self.secure_transport.request(
                        "GET",
                        f"/agent/{self.device_id}/commands",
                    )
                    if status_code >= 400:
                        raise RuntimeError(
                            f"poll failed with status {status_code}: {response_data}"
                        )
                else:
                    response = self.client.get(
                        f"{self.config.iot_server_url}/agent/{self.device_id}/commands"
                    )
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
                            LOGGER.warning(
                                f"Server offered job {queue_id}, but agent is busy."
                            )
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
                    LOGGER.warning(
                        f"Task failed (Queue ID: {task.queue_id}): {execution_result.result}"
                    )
                else:
                    LOGGER.info(
                        f"Task completed successfully (Queue ID: {task.queue_id})"
                    )
                self.send_callback(execution_result)
            except Exception as e:
                LOGGER.error(
                    f"Unexpected worker error on Queue ID {task.queue_id}: {e}"
                )
            finally:
                with self.task_lock:
                    self.current_task = None

    def execute_command(self, task: CommandTask) -> ExecutionResult:
        """Executes Python code raw inside the worker thread context."""
        result_payload = ExecutionResult(
            queue_id=task.queue_id, is_error=False, result=""
        )
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
            if self.secure_transport.enabled:
                status_code, body = self.secure_transport.request(
                    "POST",
                    "/agent/callback",
                    json_data=result.to_dict(),
                )
                if status_code >= 400:
                    raise RuntimeError(
                        f"callback failed with status {status_code}: {body}"
                    )
            else:
                self.client.post(
                    f"{self.config.iot_server_url}/agent/callback",
                    json=result.to_dict(),
                )
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
        self.secure_transport.close()
        LOGGER.info("Agent shut down cleanly.")


if __name__ == "__main__":
    config = Config.from_env()
    agent = Agent(config)
    agent.run()
