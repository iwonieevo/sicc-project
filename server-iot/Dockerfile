FROM python:3.11-slim

WORKDIR /app

COPY server-iot/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY server-iot/ .
COPY security ./security

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7000", "--reload"]
