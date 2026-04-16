import requests
import time
import os

SERVER = os.getenv("IOT_SERVER_URL", "http://iot-server:7000")
DEVICE = os.getenv("AGENT_ID", -1)


while True:
    try:
        cmds = requests.get(f"{SERVER}/agent/{DEVICE}/commands").json()

        for c in cmds:
            try:
                exec(c["command"])
                result = "OK"
            except Exception as e:
                result = str(e)

            requests.post(
                f"{SERVER}/agent/commands/{c['command_id']}/done",
                json={"result": result}
            )

    except Exception as e:
        print("Błąd połączenia:", e)

    time.sleep(10)