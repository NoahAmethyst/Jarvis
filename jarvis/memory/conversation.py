import hashlib
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from jarvis.config import POSTGRES_DSN
from jarvis.logging_config import format_log_tags

logger = logging.getLogger(__name__)


def _get_conn():
    return psycopg2.connect(POSTGRES_DSN)


def init_db():
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS llm_runtime_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    revision BIGINT NOT NULL,
                    models JSONB NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id)
            """)
        conn.commit()
    finally:
        conn.close()
    logger.info(
        "%s Conversation storage initialized",
        format_log_tags(("组件", "PostgreSQL"), ("状态", "就绪")),
    )


def load_history(user_id: str, limit: int = 20) -> list[BaseMessage]:
    """From the latest rows, replay complete question/final-answer pairs only."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT role, content, created_at FROM conversations
                   WHERE user_id = %s ORDER BY created_at DESC, id DESC LIMIT %s""",
                (user_id, limit),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    messages: list[BaseMessage] = []
    answer = None
    newer_row = None
    # Rows are newest first: the first assistant row before each human row
    # is the final reply under the legacy write order. Never backfill an
    # orphaned reply from outside the bounded window.
    for row in rows:
        role, content = row["role"], row["content"]
        if role == "ai":
            if answer is None:
                answer = content
        else:
            if role == "human":
                # New pairs share an insertion timestamp. A legacy answer
                # may have been appended later during a rolling deployment.
                if (newer_row is not None and newer_row["role"] == "ai"
                        and row["created_at"] is not None and row["created_at"] == newer_row["created_at"]):
                    answer = newer_row["content"]
                if content.strip() and answer is not None and answer.strip():
                    messages.extend((AIMessage(content=answer), HumanMessage(content=content)))
            answer = None
        newer_row = row
    return list(reversed(messages))


def save_turn(user_id: str, question: str, final_answer: str) -> None:
    """Insert the complete turn atomically using the existing table."""
    lock_key = int.from_bytes(
        hashlib.sha256(f"jarvis:conversation:{user_id}".encode()).digest()[:8], "big", signed=True,
    )
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            # Keep IDs ordered within a user's pair even if two insert
            # statements receive the same timestamp at database precision.
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
            cur.execute(
                """INSERT INTO conversations (user_id, role, content, created_at)
                   VALUES (%s, 'human', %s, statement_timestamp()),
                          (%s, 'ai', %s, statement_timestamp())""",
                (user_id, question, user_id, final_answer),
            )
        conn.commit()
    finally:
        conn.close()


def delete_history(user_id: str):
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE user_id = %s", (user_id,))
        conn.commit()
    finally:
        conn.close()


def get_history_records(user_id: str) -> list[dict]:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT role, content, created_at::text FROM conversations
                   WHERE user_id = %s ORDER BY created_at, id""",
                (user_id,),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
