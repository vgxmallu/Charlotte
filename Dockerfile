FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y git build-essential python3-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN pybabel compile -d locales -D messages

COPY . .

CMD ["python", "main.py"]
