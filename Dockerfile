FROM python:3.9-slim

WORKDIR /app

# Copy backend and frontend
COPY backend/ /app/backend
COPY frontend/ /app/frontend

# Install backend dependencies
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Install trading bot dependencies
RUN pip install ccxt rich

# The command to run the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
