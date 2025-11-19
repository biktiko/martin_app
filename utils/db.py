import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sshtunnel import SSHTunnelForwarder

@st.cache_resource(show_spinner=False)
def get_pg_engine() -> Engine:
    ssh = st.secrets.get("ssh", None)
    pg = st.secrets["pg"]

    if ssh:
        # Check if forwarder is already in session state to avoid restarting it unnecessarily
        # Note: In a real production app, managing SSH tunnel lifecycle might need more care
        # but for Streamlit this pattern is common.
        
        # However, st.cache_resource handles the singleton nature of the engine.
        # We need to be careful not to start multiple tunnels if the engine is cached.
        # Ideally, the tunnel should be attached to the engine or managed globally.
        # For now, we'll follow the original logic but wrap it.
        
        forwarder = SSHTunnelForwarder(
            (ssh["host"], ssh.get("port", 22)),
            ssh_username=ssh["username"],
            ssh_password=ssh["password"],
            remote_bind_address=(ssh.get("remote_bind_host", "127.0.0.1"),
                                 int(ssh.get("remote_bind_port", 5432))),
            local_bind_address=("127.0.0.1", 0) 
        )
        forwarder.start()
        # Store forwarder in session state to prevent garbage collection closing it? 
        # Or just rely on the fact that this function returns the engine and the tunnel stays open?
        # The original code stored it in session_state.
        st.session_state["_ssh_forwarder"] = forwarder 
        host = "127.0.0.1"
        port = forwarder.local_bind_port
    else:
        host = st.secrets["pg"]["host"]
        port = int(st.secrets["pg"]["port"])

    url = (
        f"postgresql+psycopg2://{pg['user']}:{pg['password']}"
        f"@{host}:{port}/{pg['dbname']}"
    )
    engine = create_engine(url, pool_pre_ping=True)
    return engine

def load_from_db(sql: str) -> pd.DataFrame:
    eng = get_pg_engine()
    return pd.read_sql_query(sql, eng)

def check_db_connection():
    try:
        with get_pg_engine().connect() as conn:
            pong = conn.execute(text("SELECT current_database() AS db, current_user AS usr, now() AS ts")).mappings().first()
            st.success(f"PostgreSQL OK: db={pong['db']}, user={pong['usr']}, ts={pong['ts']}")
    except Exception as e:
        st.error(f"Ошибка подключения к PostgreSQL: {e}")
