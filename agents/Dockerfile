FROM python:3.11-slim

WORKDIR /app

COPY agents/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY agents/ .
COPY security ./security

CMD ["python", "-u", "main.py"]
