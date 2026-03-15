FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV OUTPUT_DIR=/app/output
ENV DATABASE_PATH=/app/data/app.db
ENV REDIS_URL=redis://redis:6379/0

EXPOSE 5001

CMD ["gunicorn", "-w", "3", "-b", "0.0.0.0:5001", "app:app"]
