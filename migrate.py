'''
This script migrates scripts from an old database to a new one and categorizes them using the Anthropic API. It performs the following steps:
1. Fetches all pages from the source Notion database.
2. Extracts the title and content of each page.
3. Uses the Anthropic API to analyze the content and extract metadata (date, themes, mood, hook).
4. Writes the enriched data to a new Notion database with the appropriate properties
Make sure to set the following environment variables in a .env file:
- ANTHROPIC_API_KEY: Your Anthropic API key
- NOTION_API_KEY: Your Notion API key
- NOTION_SOURCE_DATABASE_ID: The ID of the Notion database to migrate from
- NOTION_DEST_DATABASE_ID: The ID of the Notion database to migrate to
- NOTION_TITLE_FILTER: (Optional) Only migrate pages whose titles start with this string (case-insensitive)
'''
import os
import anthropic
import json
import re
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()

#env variables
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

TITLE_FILTER = os.getenv("NOTION_TITLE_FILTER", "").lower()
notion = Client(auth=os.getenv("NOTION_API_KEY"))
SOURCE_DB = os.getenv("NOTION_SOURCE_DATABASE_ID")

#obtains title property name (since it can be customized) and validates it exists
def get_title_property(pages: list) -> str:
    if not pages:
        raise ValueError("No pages found")
    for name, prop in pages[0]["properties"].items():
        if prop["type"] == "title":
            return name
    raise ValueError("No title property found")

#retrieves all the scripts from the source database, filtering by title if specified. Returns a list of dicts with page id and title. Assumes title is the first property of type "title" in the database schema. Skips pages without a title or that don't match the title filter.
def get_scripts():
    response = notion.databases.query(database_id=SOURCE_DB)
    pages = response["results"]
    
    title_prop = get_title_property(pages)
    entries = []
    
    for page in pages:
        title = page["properties"][title_prop]["title"]
        if not title:
            continue
        
        name = title[0]["plain_text"]
        
        if TITLE_FILTER and not name.lower().startswith(TITLE_FILTER):
            continue
        
        entries.append({
            "id": page["id"],
            "title": name
        })

    #sorts by title instead of last edited
    entries.sort(key=lambda x: int(x["title"].lower().replace("day", "").strip()))
    
    return entries

#retrieves the content of a Notion page given its ID. Concatenates text from paragraphs, headings, and list items into a single string. Only extracts plain text, ignoring formatting and other block types.
def get_page_content(page_id: str) -> str:
    blocks = notion.blocks.children.list(block_id=page_id)
    content = ""
    
    for block in blocks["results"]:
        block_type = block["type"]
        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"]:
            rich_text = block[block_type].get("rich_text", [])
            for text in rich_text:
                content += text["plain_text"]
            content += "\n"
    
    return content.strip()

#sets up new database with properties that we want to keep track of 
def setup_database_properties(database_id: str):
    notion.databases.update(
        database_id=database_id,
        properties={
            "Name": {"name": "Title"},  # rename existing title property
            "Date": {"date": {}},
            "Themes": {"multi_select": {"options": []}},
            "Mood": {"select": {"options": []}},
            "Hook": {"rich_text": {}},
            "Script": {"rich_text": {}}
        }
    )
    print("Properties added")

#Create new database if doesn't exist
def create_new_database(parent_page_id: str) -> str:
    response = notion.databases.create(
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"type": "text", "text": {"content": "Scripts"}}],
        properties={
            "Title": {"title": {}},
            "Date": {"date": {}},
            "Themes": {"multi_select": {"options": []}},
            "Mood": {"select": {"options": []}},
            "Hook": {"rich_text": {}},
            "Script": {"rich_text": {}}
        }
    )
    return response["id"]

#analyzes script content using the Anthropic API and extracts metadata. Sends a prompt to the API asking it to return a JSON object with date, themes, mood, and hook based on the script content. Cleans the response to extract the JSON and returns it as a dictionary.
def enrich_script(title: str, content: str) -> dict:
    response = anthropic_client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""Analyze this journal script and extract the following. Respond only in JSON with no extra text or markdown.

Title: {title}
Script: {content}

Return this exact structure:
{{
    "date": null,
    "themes": ["theme1", "theme2"],
    "mood": "one word mood",
    "hook": "one sentence summarizing the opening premise"
}}

For date: only fill it in if a specific date is mentioned in the script, otherwise null.
For themes: 2-3 short tags describing what the script is about.
For mood: single word capturing the emotional tone.
For hook: one sentence capturing what the script is really about."""
        }]
    )
    
    text = response.content[0].text
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(text)

#writes to new database with enriched metadata. Creates a new page in the destination database with the title, content, and extracted metadata (date, themes, mood, hook) as properties. Truncates the script content to 2000 characters to fit Notion's limits.
def write_to_new_database(database_id: str, title: str, content: str, enriched: dict):
    notion.pages.create(
        parent={"database_id": database_id},
        properties={
            "Title": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": enriched["date"]} if enriched["date"] else None},
            "Themes": {"multi_select": [{"name": t} for t in enriched["themes"]]},
            "Mood": {"select": {"name": enriched["mood"]}},
            "Hook": {"rich_text": [{"text": {"content": enriched["hook"]}}]},
            "Script": {"rich_text": [{"text": {"content": content[:2000]}}]}
        }
    )

if __name__ == "__main__":
    # dest_db = os.getenv("NOTION_DEST_DATABASE_ID")
    # setup_database_properties(dest_db)
    # scripts = get_scripts()
    # first = scripts[0]
    # content = get_page_content(first["id"])
    # enriched = enrich_script(first["title"], content)
    # write_to_new_database(dest_db, first["title"], content, enriched)
    # print(f"Wrote {first['title']}")