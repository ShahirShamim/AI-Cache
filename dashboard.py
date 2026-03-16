import streamlit as st
import pandas as pd
from sqlalchemy import text as sql_text
from db import engine
import httpx
import os
import numpy as np

# --- Page Configuration ---
st.set_page_config(layout="wide", page_title="LLM Cache Dashboard")

# --- App State & Constants ---
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8000/v1/chat/completions")
TOKEN_COST_PER_1K_OUTPUT = 0.015

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- Main Layout ---
st.title("⚡️ LLM Semantic Caching Gateway")

analytics_col, chat_col = st.columns(2, gap="large")

# --- Analytics Column ---
with analytics_col:
    st.header("📈 Gateway Analytics")
    
    @st.cache_data(ttl=5)
    def fetch_data():
        try:
            with engine.connect() as conn:
                df = pd.read_sql(sql_text("SELECT * FROM logs"), conn)
            if not df.empty:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df = df.sort_values("timestamp", ascending=False)
            return df
        except Exception as e:
            st.warning(f"Could not connect to database: {e}")
            return pd.DataFrame()

    df = fetch_data()

    if df.empty:
        st.info("No data yet. Use the chat on the right to send some requests!")
    else:
        # --- 1. North Star Metrics ---
        st.subheader(" KPIs")
        total_requests = len(df)
        cache_hits = df["cache_hit"].sum()
        cache_hit_rate = (cache_hits / total_requests) * 100 if total_requests > 0 else 0
        simulated_tokens_saved = df.loc[df['cache_hit'] == True, 'tokens_used'].sum()
        estimated_cost_saved = (simulated_tokens_saved / 1000) * TOKEN_COST_PER_1K_OUTPUT
        today = pd.to_datetime('today').date()
        tokens_consumed_today = df.loc[(df['timestamp'].dt.date == today) & (df['cache_hit'] == False), 'tokens_used'].sum()

        c1, c2 = st.columns(2)
        c1.metric("Total Requests", total_requests, help="All requests processed by the gateway.")
        c2.metric("Cache Hit Rate", f"{cache_hit_rate:.2f}%", f"{cache_hits} hits", delta_color="normal")
        
        c3, c4 = st.columns(2)
        c3.metric("Est. Cost Saved (£)", f"£{estimated_cost_saved:.4f}", help="Based on saved tokens at the configured rate.")
        c4.metric("Tokens Consumed Today", f"{int(tokens_consumed_today):,}", help="Tokens used by cache misses today.")

        # --- 2. Performance & Yield ---
        st.subheader("⏱️ Performance & Yield")
        avg_latency_hit = df.loc[df['cache_hit'] == True, 'latency_ms'].mean() if cache_hits > 0 else 0
        avg_latency_miss = df.loc[df['cache_hit'] == False, 'latency_ms'].mean() if (total_requests - cache_hits) > 0 else 0
        avg_similarity_hit = df.loc[df['cache_hit'] == True, 'similarity_score'].mean() if cache_hits > 0 else 0
        
        c5, c6, c7 = st.columns(3)
        c5.metric("Avg Latency (Hit)", f"{avg_latency_hit:.0f} ms", f"{-(avg_latency_miss-avg_latency_hit):.0f} ms vs miss", delta_color="inverse")
        c6.metric("Avg Latency (Miss)", f"{avg_latency_miss:.0f} ms")
        c7.metric("Avg Similarity (Hits)", f"{avg_similarity_hit:.3f}", help="Average similarity score for all cache hits.")

        # --- 3. Audit & Guardrails ---
        with st.expander("🔍 Audit & Guardrails - Recent Cache Hits"):
            cache_hit_df = df.loc[df["cache_hit"] == True, ["timestamp", "query_text", "matched_prompt_text", "similarity_score"]].copy()
            cache_hit_df.rename(columns={
                "query_text": "New User Prompt",
                "matched_prompt_text": "Original Cached Prompt",
                "similarity_score": "Similarity Score"
            }, inplace=True)
            st.dataframe(cache_hit_df, height=300)

# --- Chat Column ---
with chat_col:
    st.header("💬 Live Chat Test")

    with st.expander("⚙️ Settings"):
        model_override = st.text_input("Model Override", "llama3.1:latest")
        similarity_threshold = st.slider(
            "Similarity Threshold", 
            min_value=0.70, max_value=1.0, value=0.92, step=0.01,
            help="Set the cutoff for a cache hit. Higher is stricter."
        )
    
    chat_container = st.container(height=600)
    with chat_container:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if "telemetry" in message:
                    st.caption(message["telemetry"])

    if prompt := st.chat_input("Ask me anything..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    message_placeholder = st.empty()
                    try:
                        payload = {
                            "model": model_override,
                            "messages": [{"role": "user", "content": prompt}],
                            "similarity_threshold": similarity_threshold
                        }
                        with httpx.Client() as client:
                            response = client.post(GATEWAY_URL, json=payload, timeout=60)
                            response.raise_for_status()
                            response_data = response.json()
                            full_response_content = response_data["choices"][0]["message"]["content"]
                            
                            cache_hit = response.headers.get("X-Cache-Hit", "false").lower() == "true"
                            latency_ms = float(response.headers.get("X-Latency-MS", "0"))
                            similarity_score = response.headers.get("X-Similarity-Score", "N/A")

                            if cache_hit:
                                telemetry_caption = f"✅ **CACHE HIT** | Latency: {latency_ms:.2f}ms | Similarity: {similarity_score}"
                            else:
                                telemetry_caption = f"❌ **CACHE MISS** | Latency: {latency_ms:.2f}ms"

                    except httpx.HTTPStatusError as e:
                        full_response_content = f"Error from gateway: {e.response.status_code} - {e.response.text}"
                        telemetry_caption = "Request Failed"
                    except Exception as e:
                        full_response_content = f"An unexpected error occurred: {str(e)}"
                        telemetry_caption = "Error"

                    message_placeholder.markdown(full_response_content)
                    st.caption(telemetry_caption)

        st.session_state.messages.append({
            "role": "assistant", 
            "content": full_response_content,
            "telemetry": telemetry_caption
        })
        st.rerun()

st.sidebar.button("Refresh Data")
st.sidebar.write("Dashboard auto-refreshes when data changes or new chats are sent.")

