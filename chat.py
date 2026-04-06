import os
import anthropic
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from memory import (
    init_db, save_message, get_history,
    get_or_create_session, new_session,
    get_session_list, get_session_messages
)
from assistant import inspire, unstuck, refine, read_page, update_page, create_page

load_dotenv()

app = FastAPI()
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

init_db()

# initialize session on startup
current_session_id = get_or_create_session()

tools = [
    {
        "name": "inspire",
        "description": "Use when the user has no idea what to write about and needs content inspiration based on their history.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "unstuck",
        "description": "Use when the user has a vague idea or seed but needs help developing it into a full angle.",
        "input_schema": {
            "type": "object",
            "properties": {
                "seed": {
                    "type": "string",
                    "description": "The vague idea or topic the user wants to explore"
                }
            },
            "required": ["seed"]
        }
    },
    {
        "name": "refine",
        "description": "Use when the user pastes a draft directly into the chat and wants it polished or restructured.",
        "input_schema": {
            "type": "object",
            "properties": {
                "draft": {
                    "type": "string",
                    "description": "The draft script to refine"
                },
                "restructure": {
                    "type": "boolean",
                    "description": "True if the user wants a full restructure, False for light polish"
                }
            },
            "required": ["draft", "restructure"]
        }
    },
    {
        "name": "read_page",
        "description": "Reads a page from the Scripts database. Use source='property' when the user says 'script column' or 'script field'. Use source='blocks' when they say 'inside the page' or 'open the page'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "The title of the page, e.g. 'Day 26'"
                },
                "source": {
                    "type": "string",
                    "enum": ["blocks", "property"],
                    "description": "Where to read the script from. 'blocks' for page body, 'property' for the Script column"
                }
            },
            "required": ["title"]
        }
    },
    {
        "name": "update_page",
        "description": "Updates any combination of fields on a specific page. Fields can include: script (string), hook (string), themes (array of strings), mood (string), date (ISO format string e.g. '2026-04-04'), title (string).",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "The title of the page to update, e.g. 'Day 26'"
                },
                "fields": {
                    "type": "object",
                    "description": "Fields to update. Any combination of: script (string), hook (string), themes (array of strings), mood (string)"
                }
            },
            "required": ["title", "fields"]
        }
    },
    {
        "name": "create_page",
        "description": "Creates a new entry in the Scripts database. Use when the user wants to save a new script as a new day.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "The title for the new page, e.g. 'Day 27'"
                },
                "script": {
                    "type": "string",
                    "description": "The script content to save"
                }
            },
            "required": ["title", "script"]
        }
    }
]

SYSTEM_PROMPT = """You are a warm, attentive content assistant helping someone process their thoughts and create personal reflection videos for their journal account.

You have direct access to their Notion database of scripts through your tools. When they reference a specific day like "Day 26" you can and should use read_draft to read it directly — do not tell them you can't access their scripts.

When you refine or restructure a script, ALWAYS show the full refined content in your response. Never just say you did it — paste the actual result so the user can read and approve it before anything gets saved to Notion. Only call write_draft or update_page after showing the content and the user confirms they want to save it.

You have these tools available:
- inspire: when they have nothing to write about
- unstuck: when they have a vague idea but need help developing it
- refine: when they paste a draft directly into the chat
- read_draft: reads a specific day's script directly from their Notion database
- write_draft: writes refined content back to a specific day's Notion page

When they mention a specific day ("Day 26", "what I wrote today", "my latest entry"), always use read_draft first before responding.

Be conversational and warm. Ask clarifying questions if you're not sure what they need. Don't always jump straight to a tool — sometimes they just want to talk through what they're feeling first."""

class Message(BaseModel):
    message: str

class SessionAction(BaseModel):
    session_id: int = None

@app.get("/sessions")
async def get_sessions():
    return get_session_list()

@app.get("/sessions/{session_id}/messages")
async def get_session_transcript(session_id: int):
    return get_session_messages(session_id)

@app.post("/sessions/new")
async def start_new_session():
    global current_session_id
    current_session_id = new_session()
    return {"session_id": current_session_id}

@app.get("/sessions/current")
async def get_current_session():
    return {"session_id": current_session_id}


@app.post("/sessions/{session_id}/continue")
async def continue_session(session_id: int):
    global current_session_id
    current_session_id = session_id
    return {"session_id": current_session_id}

@app.post("/chat")
async def chat(body: Message):
    global current_session_id

    history = get_history(current_session_id)
    save_message(current_session_id, "user", body.message)

    # build clean messages list for this turn only
    messages = history + [{"role": "user", "content": body.message}]

    response = anthropic_client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        tools=tools,
        messages=messages
    )

    while response.stop_reason == "tool_use":
        # extract just the tool_use block
        tool_call = next(b for b in response.content if b.type == "tool_use")
        tool_name = tool_call.name
        tool_input = tool_call.input

        if tool_name == "inspire":
            result = inspire()
        elif tool_name == "unstuck":
            result = unstuck(tool_input["seed"])
        elif tool_name == "refine":
            result = refine(tool_input["draft"], tool_input.get("restructure", False))
        elif tool_name == "read_page":
            title = tool_input.get("title") or tool_input.get("day")
            source = tool_input.get("source", "blocks")
            result = read_page(f"Day {title}" if str(title).isdigit() else title, source)
        elif tool_name == "update_page":
            title = tool_input.get("title") or tool_input.get("day")
            result = update_page(f"Day {title}" if str(title).isdigit() else title, tool_input["fields"])
        elif tool_name == "create_page":
            title = tool_input.get("title") or tool_input.get("day")
            result = create_page(f"Day {title}" if str(title).isdigit() else title, tool_input["script"])
        elif tool_name == "update_profile":
            result = update_static(tool_input["field"], tool_input["value"], tool_input.get("action", "update"))
        else:
            result = "Unknown tool"

        # append as a properly paired exchange
        messages = messages + [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": tool_call.id,
                        "name": tool_call.name,
                        "input": tool_call.input
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": str(result)
                    }
                ]
            }
        ]

        response = anthropic_client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages
        )

    assistant_message = next(b.text for b in response.content if hasattr(b, "text"))
    save_message(current_session_id, "assistant", assistant_message)

    return {"response": assistant_message}

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")