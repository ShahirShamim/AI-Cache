# ⚡️ LLM Semantic Caching Gateway

This project implements a smart caching gateway for Large Language Models (LLMs). It acts as a drop-in replacement for OpenAI-compatible APIs, intercepting requests and returning cached responses for semantically similar prompts. This significantly reduces costs, lowers latency, and ensures consistent answers for frequent queries.

The entire application, including the gateway, databases, and an analytics dashboard, is containerized with Docker for easy local deployment.

## Why Cache LLM Outputs?

-   **Cost Savings:** By serving a cached response instead of hitting a paid LLM endpoint, you avoid paying for token generation on redundant questions.
-   **Lower Latency:** A cache hit returns a response in milliseconds (~50ms) instead of seconds (~2-5s), leading to a much faster user experience.
-   **Consistent Responses:** Guarantees that frequent or important queries always receive the same high-quality, validated response.

---

## How It Works

The gateway intercepts every incoming request and follows a "cache-or-call" logic based on the semantic meaning of the user's prompt.

```mermaid
graph LR
    %% Node Definitions
    User([fa:fa-user User/Client])
    Gateway{{"⚡ Semantic Gateway"}}
    Embed(Generate Embedding)
    VectorDB[(ChromaDB)]
    LLM[fa:fa-robot Downstream LLM]
    
    %% Style Classes
    classDef cacheHit fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef cacheMiss fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    classDef success fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px;
    classDef failure fill:#ffcdd2,stroke:#c62828,stroke-width:2px;

    %% Main Flow
    User -->|POST /v1/chat| Gateway
    
    subgraph Logic ["Logic & Search"]
        Gateway --> Embed
        Embed --> VectorDB
    end

    %% Decision Path
    VectorDB -- "Similarity > 0.9" --> Hit[fa:fa-bolt Cache Hit]
    VectorDB -- "Similarity < 0.9" --> Miss[fa:fa-clock Cache Miss]

    %% Response Paths
    Hit -->|Fast Response| User
    
    subgraph External ["Remote API"]
        Miss --> LLM
        LLM --> Save[Update Vector DB]
        Save -.-> VectorDB
    end
    
    LLM -->|Slow Response| User

    %% Applying Styles
    class Hit success;
    class Miss failure;
    class Gateway cacheHit;
    class LLM cacheMiss;
```

---

## Tech Stack & Services

-   **API Gateway:** **FastAPI** provides the high-performance, asynchronous web server.
-   **Embedding Engine:** **Sentence-Transformers** (`all-mpnet-base-v2` model) runs locally to generate vector embeddings from user prompts. It will leverage a GPU if one is passed into the container.
-   **Vector Database:** **ChromaDB** stores the embeddings and the corresponding responses, enabling fast similarity searches.
-   **Metrics Database:** **SQLite** stores telemetry for every request (latency, cache status, etc.) to power the dashboard.
-   **Frontend Dashboard:** **Streamlit** is used to create an interactive, real-time analytics dashboard and chat interface.
-   **Containerization:** **Docker** and **Docker Compose** are used to build, run, and manage the entire application stack.
-   **Downstream LLM:** The gateway is configured to forward cache misses to any OpenAI-compatible API, such as a local **Ollama** instance exposed via **OpenWebUI**.

---

## Local Hosting & Usage

This application is designed to be run locally with Docker.

### Prerequisites

-   Docker
-   Docker Compose
-   NVIDIA Container Toolkit (for optional GPU support)

### Running the Application

1.  **Configure API Key:**
    The API key for your downstream LLM service (e.g., OpenWebUI) must be placed in the `.env` file. Rename or copy `.env.example` to `.env` and add your key:
    ```
    OPENWEBUI_API_KEY=your_api_key_here
    ```

2.  **Build and Run with Docker Compose:**
    Open a terminal in the project root and run:
    ```bash
    docker compose up --build -d
    ```
    This command will:
    -   Build the Docker image, downloading the embedding model in the process.
    -   Start the container in the background.
    -   Create a persistent volume (`app_data`) to store the cache and metrics databases.

3.  **Access the Dashboard:**
    Once the container is running, open your web browser and navigate to:
    **[http://localhost:8501](http://localhost:8501)**

---

## Dashboard Features

The Streamlit dashboard provides a comprehensive view of the caching gateway's performance and allows for interactive testing.

-   **📈 Gateway Analytics:** A real-time view of all key performance indicators (KPIs), latency metrics, and cost savings.
-   **💬 Live Chat Test:** An interactive chat window to send requests to the gateway and see the caching mechanism in action. You can override the model name and the similarity threshold for fine-grained testing.
-   **🔍 Audit & Guardrails:** A table of recent cache hits, allowing you to "vibe check" the quality of the matches and tune the similarity threshold accordingly.
