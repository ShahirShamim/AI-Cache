# Project: Semantic Caching Gateway

## Project Overview

This project is a Python-based Semantic Caching Gateway designed to optimize Large Language Model (LLM) costs and reduce latency. It acts as a local, drop-in replacement for OpenAI-compatible APIs.

The gateway intercepts outgoing LLM requests, generates a vector embedding for the user's prompt, and queries a local vector database (ChromaDB) to find semantically similar prompts that have been answered before.

-   If a similar prompt is found above a confidence threshold (0.92), the cached response is returned instantly.
-   If no similar prompt is found (a "cache miss"), the request is forwarded to a designated LLM backend (e.g., a local Ollama instance exposed via OpenWebUI). The new response is then cached for future use.

All requests and their outcomes (cache hit/miss, latency, etc.) are logged to a local SQLite database, which powers a Streamlit-based analytics dashboard for observing performance and cost savings.

**Key Technologies:**
-   **API Gateway:** FastAPI
-   **Vector Database:** ChromaDB
-   **Embedding Model:** `sentence-transformers` (`all-MiniLM-L6-v2`)
-   **Metrics Database:** SQLite
-   **Analytics Dashboard:** Streamlit
-   **HTTP Client:** `httpx`

## Building and Running

**1. Initial Setup:**

First, create a Python virtual environment and install the required dependencies from `requirements.txt`.

```bash
# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**2. Initialize Databases:**

Before running the main application, the databases need to be initialized.

```bash
# TODO: Confirm the exact command to run
# This will likely be a command like:
python -c "from db import init_db; init_db()"
```

**3. Run the Gateway:**

The API gateway is a FastAPI application run with `uvicorn`.

```bash
# Run the FastAPI server, with live-reloading
uvicorn main:app --reload
```
The API will be available at `http://127.0.0.1:8000`.

**4. Run the Analytics Dashboard:**

The dashboard is a Streamlit application.

```bash
# Run the Streamlit dashboard
streamlit run dashboard.py
```
The dashboard will be available at `http://localhost:8501`.

## Development Conventions

-   **File Structure:** The project is organized into three main files, reflecting a separation of concerns:
    -   `main.py`: Contains the core FastAPI application logic for the API gateway.
    -   `db.py`: Handles the setup and initialization for both the SQLite (`metrics.db`) and ChromaDB databases.
    -   `dashboard.py`: Contains the Streamlit application for data visualization.
-   **Asynchronous Code:** The FastAPI gateway uses `async` and `await` for non-blocking I/O, particularly when forwarding requests to the LLM backend using the `httpx` library.
-   **Testing:** Verification is performed by sending a sequence of prompts to the running gateway and observing the console output and dashboard for expected behavior (cache hits, misses, latency differences). Refer to the `plan.md` for a detailed verification plan.