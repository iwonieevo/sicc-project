import os
import requests
import asyncio
import logging
import socket
from typing import Optional
from dataclasses import dataclass

logging.getLogger().handlers.clear()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Agent configuration loaded from environment variables."""
    agent_name: str
    iot_server_url: str
    poll_interval: int
    registration_retries: int = 10
    request_timeout: int = 5

    @classmethod
    def from_env(cls) -> "Config":
        agent_name = os.getenv("AGENT_NAME", socket.gethostname())
        iot_server_url = os.getenv("IOT_SERVER_URL", "http://iot-server:7000")
        poll_interval = int(os.getenv("POLL_INTERVAL", 2))
        
        return cls(
            agent_name=agent_name,
            iot_server_url=iot_server_url,
            poll_interval=poll_interval
        )


class Agent:
    """
    IoT edge agent that polls server for commands and executes them.
    
    Lifecycle:
    1. Register with IoT server to obtain device_id
    2. Poll /agent/{device_id}/commands endpoint for pending commands
    3. Execute received Python code in restricted environment
    4. Send results back via /agent/callback endpoint
    5. Repeat until interrupted
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.device_id: Optional[int] = None
        self.session = requests.Session()
        logger.info(f"Initialized agent '{config.agent_name}'")
    
    async def register(self) -> bool:
        """
        Register agent with IoT server using exponential backoff retry.
        
        Returns:
            bool: True if registration succeeded, False otherwise
        """
        logger.info(f"Registering with IoT server at {self.config.iot_server_url}")
        
        for attempt in range(1, self.config.registration_retries + 1):
            try:
                response = self.session.post(
                    f"{self.config.iot_server_url}/agent/register",
                    json={"name": self.config.agent_name},
                    timeout=self.config.request_timeout
                )
                response.raise_for_status()
                
                data = response.json()
                self.device_id = data["device_id"]
                status = data["status"]
                logger.info(f"Registered successfully: device_id={self.device_id}, status={status}")
                return True
                
            except requests.RequestException as e:
                backoff = 2 ** min(attempt - 1, 3)
                logger.warning(f"Registration attempt {attempt}/{self.config.registration_retries} failed: {e}. Retrying in {backoff}s...")
                await asyncio.sleep(backoff)
        
        logger.error("Failed to register after all attempts")
        return False
    
    async def poll_commands(self) -> Optional[dict]:
        """
        Poll server for next pending command.
        
        Returns:
            Optional[dict]: Command payload containing queue_id, function_code, 
                           and parameters, or None if no commands available
        """
        if self.device_id is None:
            logger.error("Cannot poll: device_id not set")
            return None
        
        try:
            response = self.session.get(
                f"{self.config.iot_server_url}/agent/{self.device_id}/commands",
                timeout=self.config.request_timeout
            )
            response.raise_for_status()
            
            if not response.text or response.text == "{}":
                return None
            
            data = response.json()
            
            # Check if response contains command data
            if not data or "queue_id" not in data:
                return None
            
            logger.info(f"Received command: queue_id={data['queue_id']}")
            return data
            
        except requests.RequestException as e:
            logger.warning(f"Poll failed: {e}")
            return None
    
    async def execute_command(self, payload: dict) -> dict:
        """
        Execute command payload in restricted environment.
        
        Expects payload['function_code'] to contain Python code defining
        a function named '_sicc_command'. The function is executed with
        provided parameters.
        
        Args:
            payload: Command payload with queue_id, function_code, parameters
            
        Returns:
            dict: Result payload with queue_id, is_error, result fields
        """
        queue_id = payload.get("queue_id")
        function_code = str(payload.get("function_code"))
        parameters = payload.get("parameters", {})
        
        logger.info(f"Executing queue_id={queue_id}")
        result_payload = {
            "queue_id": queue_id,
            "is_error": True,
            "result": None
        }
        
        try:
            safe_builtins = {
                'print': print,
                'len': len,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'list': list,
                'dict': dict,
                'tuple': tuple,
                'range': range,
                'abs': abs,
                'min': min,
                'max': max,
                'sum': sum,
                'round': round,
                'sorted': sorted,
                'enumerate': enumerate,
                'zip': zip,
                'map': map,
                'filter': filter,
                'type': type,
                'isinstance': isinstance,
                'Exception': Exception,
                'ValueError': ValueError,
                'TypeError': TypeError,
                'KeyError': KeyError,
                'IndexError': IndexError,
            }
            local_env = {}
            exec(function_code, {"__builtins__": safe_builtins}, local_env)
            
            if "_sicc_command" not in local_env:
                raise Exception("Function '_sicc_command' not defined")
            
            result = str(local_env["_sicc_command"](**parameters))
            logger.info(f"Execution successful: queue_id={queue_id}")
            
            result_payload["is_error"] = False
            result_payload["result"] = result
        
        except Exception as e:
            msg = f"Execution failed: {type(e).__name__}: {e}"
            logger.error(msg)
            result_payload["is_error"] = True
            result_payload["result"] = msg
        
        return result_payload
    
    async def send_callback(self, result: dict) -> bool:
        """
        Send execution result back to server.
        
        Args:
            result: Result payload from execute_command
            
        Returns:
            bool: True if callback succeeded, False otherwise
        """
        try:
            response = self.session.post(
                f"{self.config.iot_server_url}/agent/callback",
                json=result,
                timeout=self.config.request_timeout
            )
            response.raise_for_status()
            logger.info(f"Callback sent: queue_id={result['queue_id']}")
            return True
        except requests.RequestException as e:
            logger.error(f"Callback failed: {e}")
            return False
    
    async def run(self):
        """
        Main agent loop: register, then poll-execute-callback indefinitely.
        """
        if not await self.register():
            logger.error("Startup failed")
            return
        
        logger.info(f"Starting polling loop (interval={self.config.poll_interval}s)")
        
        try:
            while True:
                command = await self.poll_commands()
                if command:
                    result = await self.execute_command(command)
                    await self.send_callback(result)
                
                await asyncio.sleep(self.config.poll_interval)
        except KeyboardInterrupt:
            logger.info("Shutdown requested")
        except Exception as e:
            logger.error(f"Fatal error in polling loop: {e}", exc_info=True)


async def main():
    config = Config.from_env()
    agent = Agent(config)
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())