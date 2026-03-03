FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY deepsolver/ ./deepsolver/
COPY storage/ ./storage/
COPY api/ ./api/
COPY utils/ ./utils/

# Copy data files
COPY solver_hand_order.txt .

# Cloud Run uses PORT env variable
ENV PORT=8080

# Environment variables (DEEPSOLVER_API_TOKEN, CORS_ORIGINS) are set via Cloud Run

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
