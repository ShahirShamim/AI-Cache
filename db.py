import chromadb
import sqlalchemy
from sqlalchemy import (
    create_engine,
    Table,
    Column,
    Integer,
    String,
    Boolean,
    Float,
    DateTime,
    MetaData,
)
import datetime
import os

# --- Configuration ---
DATA_DIR = "data"
METRICS_DB_PATH = os.path.join(DATA_DIR, "metrics.db")
CHROMA_DB_PATH = os.path.join(DATA_DIR, "chroma_cache")
CACHE_COLLECTION_NAME = "llm_cache"
METADATA_SCHEMA = {"hnsw:space": "cosine"}

# --- SQLite Setup ---
# Ensure the data directory exists before creating the engine
os.makedirs(DATA_DIR, exist_ok=True)
engine = create_engine(f"sqlite:///{METRICS_DB_PATH}")
metadata = MetaData()

logs_table = Table(
    "logs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime, default=datetime.datetime.utcnow),
    Column("query_text", String),
    Column("matched_prompt_text", String, nullable=True),
    Column("cache_hit", Boolean),
    Column("similarity_score", Float, nullable=True),
    Column("latency_ms", Float),
    Column("tokens_used", Integer),
)


# --- ChromaDB Setup ---
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

# Get or create the collection with cosine space for similarity
cache_collection = chroma_client.get_or_create_collection(
    name=CACHE_COLLECTION_NAME,
    metadata=METADATA_SCHEMA,
)


def init_db():
    """
    Initializes both SQLite and ChromaDB.
    Creates the 'logs' table in SQLite if it doesn't exist.
    Confirms the ChromaDB collection is ready.
    """
    print("Initializing databases...")
    os.makedirs(DATA_DIR, exist_ok=True)
    metadata.create_all(engine)
    print(f"SQLite database ready at '{METRICS_DB_PATH}'.")
    print(f"ChromaDB collection '{CACHE_COLLECTION_NAME}' is ready at '{CHROMA_DB_PATH}'.")

def log_request(
    query_text: str,
    cache_hit: bool,
    latency_ms: float,
    similarity_score: float = None,
    matched_prompt_text: str = None,
    tokens_used: int = 0,
):
    """Logs a request and its outcome to the SQLite database."""
    conn = engine.connect()
    ins = logs_table.insert().values(
        timestamp=datetime.datetime.utcnow(),
        query_text=query_text,
        matched_prompt_text=matched_prompt_text,
        cache_hit=cache_hit,
        similarity_score=similarity_score,
        latency_ms=latency_ms,
        tokens_used=tokens_used,
    )
    conn.execute(ins)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
