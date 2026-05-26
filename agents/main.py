import os
import asyncio
import logging
import httpx
import socket
from typing import Optional, ClassVar, List, Dict, Any
from dataclasses import dataclass, asdict


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)
LOGGER = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)


@dataclass
class Config:
    """Konfiguracja agenta IoT ładowana ze zmiennych środowiskowych."""
    agent_name: str
    iot_server_url: str
    poll_interval: int
    registration_retries: int = 10
    request_timeout: int = 5

    @classmethod
    def from_env(cls) -> "Config":
        """Tworzy instancję konfiguracji na podstawie zmiennych środowiskowych."""
        return cls(
            agent_name=os.getenv("AGENT_NAME", socket.gethostname()),
            iot_server_url=os.getenv("IOT_SERVER_URL", "http://iot-server:7000"),
            poll_interval=int(os.getenv("POLL_INTERVAL", 2))
        )


@dataclass
class CommandTask:
    """Struktura danych reprezentująca zadanie odebrane z serwera IoT.""" 
    queue_id: int
    function_code: str
    parameters: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommandTask":
        """Inicjalizuje obiekt zadania na podstawie słownika."""
        return cls(
            queue_id=data["queue_id"],
            function_code=data.get("function_code", ""),
            parameters=data.get("parameters", {})
        )


@dataclass
class ExecutionResult:
    """Struktura przechowująca wynik wykonania skryptu przez agenta."""
    queue_id: int
    is_error: bool
    result: str

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje obiekt wyniku na słownik gotowy do wysyłki JSON."""
        return asdict(self)


class Agent:
    """Zarządza pracą agenta IoT, łącząc pętlę nasłuchu z bezpieczną egzekucją kodu."""

    __ALLOWED_BUILTINS: ClassVar[Dict[str, Any]] = {
        'ArithmeticError': ArithmeticError,
        'AssertionError': AssertionError,
        'AttributeError': AttributeError,
        'BaseException': BaseException,
        'Exception': Exception,
        'False': False,
        'IndexError': IndexError,
        'ImportError': ImportError,
        'KeyError': KeyError,
        'LookupError': LookupError,
        'None': None,
        'StopIteration': StopIteration,
        'True': True,
        'TypeError': TypeError,
        'ValueError': ValueError,
        '__build_class__': __build_class__,
        'abs': abs,
        'aiter': aiter,
        'all': all,
        'anext': anext,
        'any': any,
        'ascii': ascii,
        'bin': bin,
        'bool': bool,
        'bytearray': bytearray,
        'bytes': bytes,
        'callable': callable,
        'chr': chr,
        'complex': complex,
        'dict': dict,
        'dir': dir,
        'divmod': divmod,
        'enumerate': enumerate,
        'filter': filter,
        'float': float,
        'format': format,
        'frozenset': frozenset,
        'hasattr': hasattr,
        'hash': hash,
        'hex': hex,
        'id': id,
        'int': int,
        'isinstance': isinstance,
        'issubclass': issubclass,
        'iter': iter,
        'len': len,
        'list': list,
        'map': map,
        'max': max,
        'min': min,
        'next': next,
        'object': object,
        'oct': oct,
        'ord': ord,
        'pow': pow,
        'print': print,
        'range': range,
        'repr': repr,
        'reversed': reversed,
        'round': round,
        'set': set,
        'slice': slice,
        'sorted': sorted,
        'str': str,
        'sum': sum,
        'tuple': tuple,
        'type': type,
        'zip': zip,
    }

    __ALLOWED_MODULES: ClassVar[List[str]] = ['time', 'math']
    
    def __init__(self, config: Config):
        """Inicjalizuje agenta, ustawiając klienta HTTP oraz bezpieczne środowisko wykonawcze."""
        self.config = config
        self.device_id: Optional[int] = None
        self.client = httpx.AsyncClient(timeout=config.request_timeout)
        self.__exec_globals: Dict = self.build_exec_globals()
        self.task_queue: asyncio.Queue[CommandTask] = asyncio.Queue()

    @classmethod
    def build_exec_globals(cls) -> Dict:
        """Tworzy bazowy słownik zmiennych globalnych z ograniczonym dostępem do wbudowanych funkcji i modułów."""
        def __restricted_import__(name, globals=None, locals=None, fromlist=(), level=0):
            if name.split('.')[0] in cls.__ALLOWED_MODULES:
                return __import__(name, globals, locals, fromlist, level)
            raise ImportError(f"Import of '{name}' is forbidden.")
        
        exec_globals = {'__builtins__': cls.__ALLOWED_BUILTINS.copy()}
        exec_globals['__builtins__']['__import__'] = __restricted_import__
        return exec_globals
        
    async def register(self) -> bool:
        """Rejestruje agenta na serwerze IoT w celu uzyskania unikalnego identyfikatora device_id."""
        for attempt in range(1, self.config.registration_retries + 1):
            try:
                response = await self.client.post(
                    f"{self.config.iot_server_url}/agent/register",
                    json={"name": self.config.agent_name}
                )
                response.raise_for_status()
                self.device_id = response.json()["device_id"]
                return True
            except Exception:
                await asyncio.sleep(2 ** min(attempt - 1, 3))
        return False

    async def heartbeat_loop(self):
        """Cyklicznie odpytuje serwer IoT i przekazuje nowe zadania do kolejki wykonawczej."""
        if self.device_id is None:
            return
        
        while True:
            try:
                response = await self.client.get(
                    f"{self.config.iot_server_url}/agent/{self.device_id}/commands"
                )
                response.raise_for_status()
                response_data = response.json()
                
                if response_data.get('queue_id') is not None:
                    await self.task_queue.put(CommandTask.from_dict(response_data))
            except Exception as e:
                LOGGER.error(f"Błąd komunikacji z serwerem (heartbeat): {e}")
            finally:
                await asyncio.sleep(self.config.poll_interval)

    async def worker_loop(self):
        """Pobiera zadania z kolejki, uruchamia je i przesyła wyniki z powrotem na serwer."""
        while True:
            task = await self.task_queue.get()
            try:
                execution_result = await self.execute_command(task)
                await self.send_callback(execution_result)
            except Exception as e:
                LOGGER.critical(f"Krytyczna awaria pętli wykonawczej (Worker): {e}")
            finally:
                self.task_queue.task_done()

    async def execute_command(self, task: CommandTask) -> ExecutionResult:
        """Uruchamia otrzymany kod Pythona w odizolowanym i bezpiecznym środowisku (sandbox)."""
        result_payload = ExecutionResult(queue_id=task.queue_id, is_error=False, result="")
        try:
            local_env = {}
            # Kopia słownika chroni przed współdzieleniem stanu błędu / ucieczką pamięci
            scoped_globals = self.__exec_globals.copy()
            
            exec(task.function_code, scoped_globals, local_env)
            if "_sicc_command" not in local_env:
                raise Exception("Funkcja '_sicc_command' nie została zdefiniowana w kodzie")
            
            result_payload.result = str(local_env["_sicc_command"](**task.parameters))
        except Exception as e:
            result_payload.is_error = True
            result_payload.result = f"{type(e).__name__}: {e}"
        return result_payload

    async def send_callback(self, result: ExecutionResult):
        """Wysyła raport z wynikiem wykonania zadania z powrotem do serwera IoT."""
        try:
            await self.client.post(
                f"{self.config.iot_server_url}/agent/callback", 
                json=result.to_dict()
            )
        except Exception as e:
            LOGGER.error(f"Nie udało się wysłać statusu wykonania (Queue ID: {result.queue_id}): {e}")

    async def run(self):
        """Uruchamia proces rejestracji oraz współbieżne pętle nasłuchu i wykonawczą."""
        LOGGER.info(f"Uruchamianie agenta IoT: '{self.config.agent_name}'")
        if not await self.register():
            LOGGER.critical("Rejestracja odrzucona przez serwer. Wyłączanie agenta.")
            return
        
        LOGGER.info(f"Agent zarejestrowany pomyślnie. Przypisane ID: {self.device_id}")
        try:
            await asyncio.gather(
                self.heartbeat_loop(),
                self.worker_loop()
            )
        except asyncio.CancelledError:
            pass
        finally:
            await self.client.aclose()
            LOGGER.info("Agent został bezpiecznie wyłączony.")


async def main():
    """Główny punkt wejścia do aplikacji inicjalizujący asynchronicznego agenta."""
    config = Config.from_env()
    agent = Agent(config)
    await agent.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass