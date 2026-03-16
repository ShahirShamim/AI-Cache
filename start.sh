#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# 1. Initialize the databases
echo "--- Initializing databases ---"
python db.py
echo "--- Databases initialized ---"

# 2. Start the FastAPI/uvicorn server in the background
echo "--- Starting FastAPI server ---"
uvicorn main:app --host 0.0.0.0 --port 8000 &
echo "--- FastAPI server started in background ---"

# 3. Start the Streamlit dashboard in the foreground
# This will keep the container running.
echo "--- Starting Streamlit dashboard ---"
streamlit run dashboard.py --server.address 0.0.0.0 --server.port 8501 --server.enableCORS false --server.enableXsrfProtection false
