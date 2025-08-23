FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt requirements-api.txt ./
RUN pip install -r requirements.txt -r requirements-api.txt

# Copy the application
COPY . .

# Install bash2gitlab in development mode
RUN pip install -e .

# Expose the API port
EXPOSE 8000

# Command to run the API server
CMD ["uvicorn", "bash2gitlab_api:app", "--host", "0.0.0.0", "--port", "8000"]
