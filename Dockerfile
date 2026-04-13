FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY timesheet_bot/ timesheet_bot/
COPY bot.py .

VOLUME ["/app/data"]

ENV DB_PATH=/app/data/timesheet.db

CMD ["python", "bot.py"]
