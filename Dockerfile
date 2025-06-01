FROM python:3.9-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create directory for user data
RUN mkdir -p /opt/render/project/user_data

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command (will be overridden by Render)
CMD ["uvicorn", "document_upload:app", "--host", "0.0.0.0", "--port", "10000"] 