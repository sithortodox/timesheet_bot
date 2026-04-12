FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# Данные хранятся в volume
VOLUME ["/app/data"]

ENV DATA_FILE=/app/data/timesheet_data.json

CMD ["python", "bot.py"]
