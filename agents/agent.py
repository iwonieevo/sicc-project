import requests, time

SERVER = "http://127.0.0.1:7000"  # zmień adres na 7000
DEVICE = 0                        # zmień ID

#SERVER = "http://host.docker.internal:8000"  # możliwe że trzeba tak jeśli uruchamiami w Dockerze na Windows/Mac



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