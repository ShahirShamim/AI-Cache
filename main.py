from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
import httpx
import time
from sentence_transformers import SentenceTransformer
import torch
import os
import chromadb
import sqlalchemy
from sqlalchemy import text as sql_text
from db import log_request, engine, chroma_client, CACHE_COLLECTION_NAME, logs_table

# --- Configuration ---
OPENWEBUI_BASE_URL = os.getenv("OPENWEBUI_BASE_URL", "https://aichat.jmkn.org/api/chat/completions")
OPENWEBUI_API_KEY = os.getenv("OPENWEBUI_API_KEY", "YOUR_OPENWEBUI_API_KEY") # Replace with actual key or use .env
SIMILARITY_THRESHOLD = 0.92
TOKEN_COST_PER_1K = 0.015 # Based on OpenAI GPT-4o pricing
EMBEDDING_MODEL_NAME = "all-mpnet-base-v2"

app = FastAPI()

# Global variables for model and ChromaDB client
embedding_model: Optional[SentenceTransformer] = None
llm_cache_collection: Optional[chromadb.Collection] = None
http_client: Optional[httpx.AsyncClient] = None

@app.on_event("startup")
async def startup_event():
    global embedding_model, llm_cache_collection, http_client
    
    # Set up device for SentenceTransformer
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Loading Sentence Transformer model on device: {device}")
    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device=device)
    print("Sentence Transformer model loaded.")

    print("Connecting to ChromaDB collection...")
    # Ensure the collection is created with cosine space, as specified in db.py
    llm_cache_collection = chroma_client.get_or_create_collection(
        name=CACHE_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    print(f"ChromaDB collection '{CACHE_COLLECTION_NAME}' ready.")

    print("Initializing HTTP client...")
    http_client = httpx.AsyncClient(timeout=30.0)
    print("HTTP client initialized.")

@app.on_event("shutdown")
async def shutdown_event():
    global http_client
    if http_client:
        await http_client.aclose()
        print("HTTP client closed.")

# --- Pydantic Models for OpenAI-like API ---
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = "llama3.1:latest" # Default model as per plan.md
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 1.0
    stream: Optional[bool] = False # For MVP, stream is not supported
    similarity_threshold: Optional[float] = None # User-definable threshold

class ChatCompletionResponseChoiceDelta(BaseModel):
    content: str
    role: Optional[str] = "assistant"

class ChatCompletionResponseChoice(BaseModel):
    index: int
    message: ChatCompletionResponseChoiceDelta
    finish_reason: Optional[str] = None

class ChatCompletionResponseUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel):
    id: str = "chatcmpl-unknown"
    object: str = "chat.completion"
    created: int = int(time.time())
    model: str = "llama3.1:latest"
    choices: List[ChatCompletionResponseChoice]
    usage: ChatCompletionResponseUsage


# --- Helper Functions ---
def get_prompt_from_messages(messages: List[ChatMessage]) -> str:
    """Extracts the last user message as the prompt."""
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""

def estimate_tokens(text: str) -> int:
    """Estimates tokens using a simple char-to-token ratio (1 token ~ 4 chars)."""
    return len(text) // 4

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, http_request: Request):
    if not embedding_model or not llm_cache_collection or not http_client:
        raise HTTPException(status_code=500, detail="Service not initialized.")

    start_time = time.perf_counter()
    user_prompt = get_prompt_from_messages(request.messages)
    
    if not user_prompt:
        raise HTTPException(status_code=400, detail="No user prompt found in messages.")

    # 1. Generate embedding for the incoming prompt
    prompt_embedding = embedding_model.encode(user_prompt).tolist()

    cache_hit = False
    similarity_score = 0.0
    cached_response_content = None
    matched_prompt_text = None
    tokens_used = 0

    try:
        # 2. Query ChromaDB for the nearest neighbor
        results = llm_cache_collection.query(
            query_embeddings=[prompt_embedding],
            n_results=1,
            include=['distances', 'metadatas']
        )

        if results and results['distances'] and results['distances'][0]:
            distance = results['distances'][0][0]
            # ChromaDB cosine distance is 1 - similarity. So, similarity = 1 - distance.
            similarity_score = 1 - distance

            # 3. Check if similarity meets threshold
            # Use threshold from request if provided, otherwise use global default
            threshold_to_use = request.similarity_threshold if request.similarity_threshold is not None else SIMILARITY_THRESHOLD
            if similarity_score >= threshold_to_use:
                cache_hit = True
                cached_response_content = results['metadatas'][0][0]['response']
                matched_prompt_text = results['metadatas'][0][0]['prompt']
                tokens_used = estimate_tokens(cached_response_content) # Estimate tokens for cached response

    except Exception as e:
        print(f"Error querying ChromaDB: {e}")
        # Continue to LLM on ChromaDB error

    final_response_content = ""

    if cache_hit:
        final_response_content = cached_response_content
        print(f"Cache Hit! Similarity: {similarity_score:.4f}")
    else:
        print("Cache Miss. Forwarding to LLM...")
        # 4. Forward to LLM (OpenWebUI)
        headers = {"Authorization": f"Bearer {OPENWEBUI_API_KEY}"}
        try:
            # Need to send the exact request body that OpenWebUI expects
            # For this MVP, we assume request.model and messages are sufficient.
            # Stream is not supported in MVP.
            llm_response = await http_client.post(
                OPENWEBUI_BASE_URL, # Use the full URL directly
                json=request.dict(exclude_unset=True), # Send the original request payload
                headers=headers
            )
            llm_response.raise_for_status()
            llm_data = llm_response.json()

            # Extract content from LLM response
            if llm_data and llm_data.get("choices"):
                final_response_content = llm_data["choices"][0]["message"]["content"]
                # For cache misses, estimate tokens from the *newly generated* content
                tokens_used = estimate_tokens(final_response_content) 
            else:
                final_response_content = "Error: Could not get content from LLM."
                print(f"Unexpected LLM response format: {llm_data}")

            # 5. Asynchronously save new prompt embedding and response to ChromaDB
            # Store the user's prompt and the LLM's full response
            llm_cache_collection.add(
                embeddings=[prompt_embedding],
                metadatas=[{"prompt": user_prompt, "response": final_response_content}],
                ids=[str(hash(user_prompt))] # Simple unique ID for now
            )
            print("New prompt and response cached in ChromaDB.")

        except httpx.HTTPStatusError as e:
            print(f"HTTP error from LLM: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=f"LLM API error: {e.response.text}")
        except httpx.RequestError as e:
            print(f"Network error calling LLM: {e}")
            raise HTTPException(status_code=503, detail=f"LLM service unavailable: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during LLM call: {e}")
            raise HTTPException(status_code=500, detail=f"Internal server error during LLM call: {e}")

    end_time = time.perf_counter()
    latency_ms = (end_time - start_time) * 1000

    # 6. Log telemetry to SQLite
    try:
        log_request(
            query_text=user_prompt,
            matched_prompt_text=matched_prompt_text,
            cache_hit=cache_hit,
            similarity_score=similarity_score if cache_hit else None, # Only log score on hit
            latency_ms=latency_ms,
            tokens_used=tokens_used,
        )
    except Exception as e:
        print(f"Error logging request to SQLite: {e}")

    # 7. Construct and return the final response with custom headers
    response_body = {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": final_response_content},
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": estimate_tokens(user_prompt),
            "completion_tokens": tokens_used,
            "total_tokens": estimate_tokens(user_prompt) + tokens_used
        }
    }
    
    response_headers = {
        "X-Cache-Hit": str(cache_hit),
        "X-Latency-MS": str(round(latency_ms, 2)),
        "X-Similarity-Score": str(round(similarity_score, 4)) if cache_hit else "N/A",
        "Access-Control-Expose-Headers": "X-Cache-Hit, X-Latency-MS, X-Similarity-Score" # Expose custom headers
    }

    return JSONResponse(content=response_body, headers=response_headers)

# Basic health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Semantic Caching Gateway is running"}

# Endpoint to fetch logs (for dashboard development/debugging)
@app.get("/logs")
async def get_logs():
    conn = engine.connect()
    result = conn.execute(logs_table.select()).fetchall()
    conn.close()
    
    # Convert Row objects to dicts for JSON serialization
    logs_data = [dict(row._mapping) for row in result]
    return logs_data
