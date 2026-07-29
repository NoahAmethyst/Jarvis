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
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT role, content FROM conversations
                   WHERE user_id = %s ORDER BY created_at DESC LIMIT %s""",
                (user_id, limit),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    messages: list[BaseMessage] = []
    for row in reversed(rows):
        if row["role"] == "human":
            messages.append(HumanMessage(content=row["content"]))
        else:
            messages.append(AIMessage(content=row["content"]))
    return messages


def save_message(user_id: str, role: str, content: str):
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO conversations (user_id, role, content) VALUES (%s, %s, %s)",
                (user_id, role, content),
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
                   WHERE user_id = %s ORDER BY created_at""",
                (user_id,),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
