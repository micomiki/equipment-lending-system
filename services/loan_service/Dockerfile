
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY clients/ ./clients/
COPY services/ ./services/

EXPOSE 8002

CMD ["uvicorn", "services.loan_service.main:app", "--host", "0.0.0.0", "--port", "8002"]
