# Use an official Python runtime as a parent image
# For GPU support, the host machine must have NVIDIA drivers installed.
# The 'torch' library installed via pip includes CUDA runtime libraries,
# and docker-compose.yml handles exposing the GPU device to the container.
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies that might be needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# This will also download the sentence-transformers model into the image
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Make the startup script executable
RUN chmod +x ./start.sh

# Expose the ports the app runs on
EXPOSE 8000
EXPOSE 8501

# Define the command to run the application
ENTRYPOINT ["./start.sh"]
