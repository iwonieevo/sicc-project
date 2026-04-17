from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests
import os

router = APIRouter()

# Przechowuje komendy wysłane do urządzeń
commands = []

class CommandRequest(BaseModel):
    # Model danych przyjmowanych od backendu aplikacji
    # device_id – identyfikator urządzenia
    # command – komenda w postaci stringa (np. kod do wykonania)

    device_id: str  # zmiana na str z int
    command: str

@router.post("/commands")
def create_command(data: CommandRequest):
    # Endpoint służący do tworzenia nowej komendy dla urządzenia
    # Odbiera dane od backendu aplikacji

    new_command = {
        "command_id": len(commands),  # unikalny identyfikator komendy
        "device_id": data.device_id,  # urządzenie docelowe
        "command": data.command,      # treść komendy
        "status": "pending",          # status początkowy
        "result": None                # wynik wykonania
    }

    commands.append(new_command)      # Dodanie komendy do listy przechowywanej w pamięci serwera

    send_to_agent(new_command)        # Wysłanie komendy do agenta

    return new_command                # Zwrócenie utworzonej komendy do backendu aplikacji

# Endpoint zwracający wszystkie komendy wraz z ich statusem i wynikami
@router.get("/commands")
def get_commands():
    return commands

# Funkcja odpowiedzialna za wysłanie komendy do agenta przez HTTP
def send_to_agent(command):
    AGENT_PORT = os.getenv("AGENT_PORT", "9000")
    agent_url = f"http://agent-{command['device_id']}:{AGENT_PORT}/execute"  # Dynamic agent URL

    payload = {                                  # Dane wysyłane do agenta
        "command_id": command["command_id"],     # Numer rozkazu
        "command": command["command"]            # Treść
    }

    response = requests.post(agent_url, json=payload)
    response.raise_for_status()  # Ensure the request succeeds