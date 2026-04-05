import sqlite3
import os
from datetime import datetime
import anthropic
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "history.db"
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MESSAGE_THRESHOLD = 30

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            summary TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        compressed INTEGER DEFAULT 0,
        FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    conn.commit()
    conn.close()

def get_or_create_session() -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # get last session
    cursor.execute("SELECT id, summary FROM sessions ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()

    if not row:
        return create_session()

    session_id, summary = row

    # lazy summarization — if last session has no summary, generate it now
    if not summary:
        summarize_session(session_id)

    # always continue last session by default
    return session_id

def create_session() -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sessions (date, is_active) VALUES (?, ?)",
        (datetime.now().isoformat(), 1)
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id

def new_session() -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # mark all sessions inactive
    cursor.execute("UPDATE sessions SET is_active = 0")

    # create new session
    cursor.execute(
        "INSERT INTO sessions (date, is_active) VALUES (?, ?)",
        (datetime.now().isoformat(), 1)
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id

def summarize_session(session_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return

    messages_text = "\n".join([f"{row[0]}: {row[1]}" for row in rows])

    response = anthropic_client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"""Summarize this conversation in one short sentence capturing:
- what they worked on (specific day if mentioned)
- the emotional tone or theme discussed

Conversation:
{messages_text}

One sentence only, past tense, no preamble."""
        }]
    )

    summary = response.content[0].text.strip()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE sessions SET summary = ? WHERE id = ?",
        (summary, session_id)
    )
    conn.commit()
    conn.close()

def save_message(session_id: int, role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (session_id, role, content, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    if get_message_count(session_id) > MESSAGE_THRESHOLD:
        compress_old_messages(session_id)

def get_message_count(session_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def compress_old_messages(session_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, role, content FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT 20",
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return

    messages_text = "\n".join([f"{row[1]}: {row[2]}" for row in rows])

    response = anthropic_client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": f"""Summarize this conversation history into a concise paragraph capturing:
- emotional themes and what the person has been processing
- any important context about their content journey
- key things mentioned about their life or feelings

Conversation:
{messages_text}

Write in third person as context for a future conversation."""
        }]
    )

    summary = response.content[0].text

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO summaries (session_id, content, timestamp) VALUES (?, ?, ?)",
        (session_id, summary, datetime.now().isoformat())
    )
    ids = [row[0] for row in rows]
    cursor.execute(
        f"DELETE FROM messages WHERE id IN ({','.join('?' * len(ids))})", ids
    )
    conn.commit()
    conn.close()

def get_history(session_id: int) -> list:
    # get latest compression summary for this session
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT content FROM summaries WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,)
    )
    row = cursor.fetchone()
    summary = row[0] if row else None

    cursor.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,)
    )
    messages = [{"role": r[0], "content": r[1]} for r in cursor.fetchall()]
    conn.close()

    if not summary:
        return messages

    return [
        {"role": "user", "content": f"[Context from earlier in this conversation: {summary}]"},
        {"role": "assistant", "content": "I have that context, thank you."}
    ] + messages

def get_session_list() -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, date, summary FROM sessions ORDER BY id DESC"
    )
    rows = cursor.fetchall()
    conn.close()

    return [{
        "id": row[0],
        "date": row[1],
        "summary": row[2] or "no summary yet"
    } for row in rows]

def get_session_messages(session_id: int) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content, timestamp FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in rows]

def clear_history():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages")
    cursor.execute("DELETE FROM sessions")
    cursor.execute("DELETE FROM summaries")
    conn.commit()
    conn.close()