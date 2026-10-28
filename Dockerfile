FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LENDING_DB=/data/lending.db

WORKDIR /app

# Install dependencies first so Docker can cache this layer.
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application files. Files in .dockerignore are excluded.
COPY . .

# Persist SQLite data in a volume rather than inside the image.
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# Initialise the SQLite schema, then start the REST API.
CMD ["sh", "-c", "python -c 'from lending import init_db; init_db()' && exec uvicorn lending:app --host 0.0.0.0 --port 8000"]