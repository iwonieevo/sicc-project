from fastapi import APIRouter, HTTPException
from app.routers.commands import commands
from pydantic import BaseModel
import requests

router = APIRouter()

# Model danych odbieranych od agenta
# result – wynik wykonania komendy w postaci stringa
class CommandResult(BaseModel):
    result: str

"""
# Dane do pobrania dla agenta
@router.get("/agent/{device_id}/next")
def get_next_command(device_id: int):

    for command in commands:
        if command["device_id"] == device_id and command["status"] == "pending":
            command["status"] = "processing"
            return command

    return {"message": "No commands"}
"""

# Endpoint odbierający wynik wykonania komendy od agenta
@router.post("/agent/commands/{command_id}/done")
def mark_done(command_id: int, data: CommandResult):

    for command in commands:                                            # Przeszukiwanie listy komend w celu znalezienia odpowiedniej
        if command["command_id"] == command_id:                         # Jeśli znaleziono właściwą komendę
            command["status"] = "done"                                  # Zmiana statusu na zakończony
            command["result"] = data.result                             # Zapisanie wyniku przesłanego przez agenta

            send_result_to_web_server(command)

            return command                                              # Zwrócenie zaktualizowanej komendy

    raise HTTPException(status_code=404, detail="Command not found")    # Obsługa błędu – brak komendy o podanym ID


def send_result_to_web_server(command):
    web_server_url = "http://127.0.0.1:7000/api/result"  

    payload = {
        "command_id": command["command_id"],
        "device_id": command["device_id"],
        "status": command["status"],
        "result": command["result"]
    }

    try:
        requests.post(web_server_url, json=payload)
    except Exception as e:
        print("Błąd wysyłania wyniku do aplikacji:", e)