
# Implementation Plan: Semantic Caching Gateway

## Objective
Build a local Semantic Caching Gateway and an Analytics Dashboard to optimize LLM requests by caching responses based on semantic similarity. This gateway will act as a drop-in replacement for standard LLM APIs, intercepting requests, checking a local vector database for similar past queries, and falling back to an OpenWebUI instance if no match is found.

## Models & Backend
- **LLM Backend:** The gateway will forward cache misses to an OpenWebUI API endpoint (`https://aichat.jmkn.org/api/chat/completions`) using a Bearer token. This backend should be configured to run `llama3.1` or `llama3`.
- **Embedding Engine:** The gateway will use the `sentence-transformers` library with the `all-MiniLM-L6-v2` model. This model runs locally within the Python process to generate embeddings instantly without network overhead.

## Architecture & Tech Stack
- **API Gateway:** FastAPI
- **Embedding Engine:** `sentence-transformers`
- **Vector Database:** ChromaDB (local persistence)
- **Telemetry Database:** SQLite (`metrics.db`)
- **Frontend Dashboard:** Streamlit
- **HTTP Client:** `httpx` (for asynchronous API calls to the LLM backend)

## Implementation Steps

### 1. Project Setup
- Initialize a Python virtual environment.
- Create `requirements.txt` with dependencies: `fastapi`, `uvicorn`, `sentence-transformers`, `chromadb`, `httpx`, `streamlit`, `pandas`, `plotly`, `sqlalchemy`.

### 2. Database & Storage Initialization (`db.py`)
- **Telemetry DB (SQLite):**
  - Setup `metrics.db` with a `logs` table to capture every request.
  - Schema:
    - `id` (INTEGER PRIMARY KEY)
    - `timestamp` (DATETIME)
    - `query_text` (TEXT) - The new prompt received by the gateway.
    - `matched_prompt_text` (TEXT, nullable) - The original prompt from the cache that was matched. NULL if cache miss.
    - `cache_hit` (BOOLEAN)
    - `similarity_score` (FLOAT)
    - `latency_ms` (FLOAT)
    - `tokens_used` (INTEGER)
- **Vector DB (ChromaDB):**
  - Initialize a persistent ChromaDB client.
  - Create a collection named `llm_cache`. **Crucially, this collection must be configured to use the `cosine` space for similarity.**
  - Each entry in the collection will store the prompt's embedding along with the following metadata: `{'response': 'The LLM text response', 'prompt': 'The original prompt text'}`.

### 3. FastAPI Gateway (`main.py`)
- Create a `/v1/chat/completions` endpoint that mirrors the OpenAI request structure.
- **Execution Flow:**
  1. Record start time and extract the user's prompt from the request payload.
  2. Generate an embedding for the prompt using `all-MiniLM-L6-v2`.
  3. Query the `llm_cache` collection in ChromaDB for the single nearest neighbor. The query will return a distance metric.
  4. **Semantic Check:** Convert the distance to a similarity score (`similarity = 1 - distance`).
  5. **Branch A: Cache Hit (if `similarity > 0.92`)**
     - Retrieve the cached response and the original prompt text from the matched document's metadata.
     - Set `cache_hit = True`.
     - Log telemetry to SQLite, including the `query_text` (new prompt), `matched_prompt_text` (from cache), and `similarity_score`.
     - Return the cached response. Latency should be under 50ms.
  6. **Branch B: Cache Miss (if `similarity <= 0.92`)**
     - Forward the request to the OpenWebUI API using `httpx`.
     - Await the response from the LLM.
     - Asynchronously, save the *new* prompt embedding and its corresponding response into ChromaDB.
     - Set `cache_hit = False`.
     - Estimate `tokens_used` for the generated response (`len(text) / 4`).
     - Log telemetry to SQLite. The `matched_prompt_text` will be NULL.
     - Return the LLM-generated response. Latency will be >2000ms.
  7. For both branches, calculate and log the total `latency_ms`.

### 4. Streamlit Analytics Dashboard (`dashboard.py`)
- Build a single-page web app on `localhost:8501` to visualize the gateway's value.
- The dashboard will auto-refresh and pull data directly from `metrics.db`.
- **Section 1: North Star Metrics (KPIs)**
  - Total Requests Processed
  - Cache Hit Rate (%)
  - Simulated Tokens Saved
  - Estimated Cost Saved ($) (use `$0.015 / 1k tokens` as the baseline)
- **Section 2: Performance & Yield**
  - Bar chart: Average Latency (Cache Miss) vs. Average Latency (Cache Hit).
  - Line graph: Daily token consumption (Tokens Used vs. Tokens Saved).
- **Section 3: Audit & Guardrails**
  - A table/dataframe of recent cache hits with columns: `Original Cached Prompt` (`matched_prompt_text`), `New User Prompt` (`query_text`), and `Similarity Score`. This allows for "vibe checking" the semantic threshold.

### 5. Verification & Testing
- **Test 1:** Send an initial prompt. **Expect:** Cache Miss, slow response, one new entry in ChromaDB, one new `cache_hit=False` log in SQLite.
- **Test 2:** Send the exact same prompt. **Expect:** Cache Hit, similarity of `1.0`, very fast response, one new `cache_hit=True` log.
- **Test 3:** Send a semantically similar but differently worded prompt. **Expect:** Cache Hit, `similarity > 0.92`, fast response, one new `cache_hit=True` log.
- **Test 4:** Send a completely unrelated prompt. **Expect:** Cache Miss.
- **Test 5:** Launch the Streamlit app and verify all KPIs and tables populate correctly based on the test requests.