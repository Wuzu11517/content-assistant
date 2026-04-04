import os
import anthropic
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()

notion = Client(auth=os.getenv("NOTION_API_KEY"))
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
SCRIPTS_DB = os.getenv("NOTION_DEST_DATABASE_ID")

def get_script_summaries() -> list:
    response = notion.databases.query(database_id=SCRIPTS_DB)
    summaries = []

    for page in response["results"]:
        props = page["properties"]
        title = props["Title"]["title"][0]["plain_text"] if props["Title"]["title"] else ""
        hook = props["Hook"]["rich_text"][0]["plain_text"] if props["Hook"]["rich_text"] else ""
        mood = props["Mood"]["select"]["name"] if props["Mood"]["select"] else ""
        themes = [t["name"] for t in props["Themes"]["multi_select"]]

        summaries.append({
            "id": page["id"],
            "title": title,
            "hook": hook,
            "mood": mood,
            "themes": themes
        })

    return summaries

def get_full_script(page_id: str) -> str:
    props = notion.pages.retrieve(page_id=page_id)["properties"]
    return props["Script"]["rich_text"][0]["plain_text"] if props["Script"]["rich_text"] else ""

def inspire():
    summaries = get_script_summaries()
    
    all_themes = [t for s in summaries for t in s["themes"]]
    summary_text = "\n".join([
        f"{s['title']}: {s['hook']} (mood: {s['mood']}, themes: {', '.join(s['themes'])})"
        for s in summaries
    ])
    
    response = anthropic_client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"""You are a content assistant helping someone who makes personal reflection videos.

Here is everything they have written so far:
{summary_text}

Based on their history:
- Identify themes they haven't explored yet or haven't gone deep enough on
- Suggest 4 content directions they could go next
- Each suggestion should feel like a natural next chapter given what they've already shared

Format each suggestion as:
Topic: [topic]
Angle: [specific angle or question to explore]
Why now: [why this feels like the right next step based on their history]
"""
        }]
    )
    
    return response.content[0].text

def unstuck(seed: str):
    summaries = get_script_summaries()
    
    summary_text = "\n".join([
        f"{s['title']}: {s['hook']} (mood: {s['mood']}, themes: {', '.join(s['themes'])})"
        for s in summaries
    ])
    
    response = anthropic_client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"""You are a content assistant helping someone who makes personal reflection videos.

Here is everything they have written so far:
{summary_text}

They want to make something about: "{seed}"

Based on their voice and history:
- Develop this seed into a clear content angle
- Write a strong opening hook (1-2 sentences to open the video)
- Give them a loose structure to follow (3-4 bullet points, not a full script)
- Keep it feeling personal and authentic to how they already write
"""
        }]
    )
    
    return response.content[0].text

def refine(draft: str, restructure: bool = False):
    summaries = get_script_summaries()
    
    # find 3 most relevant scripts by matching themes in the draft
    response = anthropic_client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": f"""Given this draft: "{draft}"
            
And these scripts with their themes:
{chr(10).join([f"{s['title']}: {', '.join(s['themes'])}" for s in summaries])}

Return only the titles of the 3 most thematically similar scripts, comma separated, nothing else."""
        }]
    )
    
    similar_titles = [t.strip() for t in response.content[0].text.split(",")]
    similar_scripts = [
        get_full_script(s["id"]) 
        for s in summaries 
        if s["title"] in similar_titles
    ]
    
    voice_context = "\n\n---\n\n".join(similar_scripts)
    
    mode_instruction = """Restructure and reframe this idea if it isn't coming through clearly. 
    You can change the structure significantly but keep the core idea and their voice.""" if restructure else \
    """Polish this draft lightly — tighten sentences, improve word choice, cut rambling. 
    Keep their structure and voice intact. Don't over-edit."""
    
    response = anthropic_client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"""You are a content assistant helping someone refine their personal reflection video scripts.

Here are examples of their writing style and voice:
{voice_context}

Their draft:
{draft}

{mode_instruction}

Return only the refined script, nothing else."""
        }]
    )
    
    return response.content[0].text

if __name__ == "__main__":