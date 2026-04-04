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

if __name__ == "__main__":
    summaries = get_script_summaries()
    for s in summaries:
        print(s)