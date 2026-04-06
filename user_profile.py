import json
import os
from datetime import datetime

PROFILE_PATH = "profile.json"

def load_profile() -> dict:
    if not os.path.exists(PROFILE_PATH):
        return get_default_profile()
    with open(PROFILE_PATH, "r") as f:
        return json.load(f)

def save_profile(profile: dict):
    with open(PROFILE_PATH, "w") as f:
        json.dump(profile, f, indent=2)

def get_default_profile() -> dict:
    return {
        "static": {
            "voice": "conversational, like talking to a close friend",
            "delivery": "thoughtful, sentences feel considered not stream of consciousness",
            "tone": "vulnerable but composed, not dramatic",
            "sentence_style": "",
            "never": ["overly formal language", "flowery expressions", "generic journal phrases"],
            "common_patterns": []
        },
        "dynamic": {
            "emotional_arc": "",
            "recent_themes": [],
            "energy": "",
            "last_updated": ""
        }
    }

def update_static(field: str, value, action: str = "update"):
    profile = load_profile()
    
    if field not in profile["static"]:
        return f"Field '{field}' not found in static profile"
    
    current = profile["static"][field]
    
    if isinstance(current, list):
        if action == "add":
            if value not in current:
                current.append(value)
        elif action == "remove":
            current = [x for x in current if x != value]
        profile["static"][field] = current
    else:
        profile["static"][field] = value
    
    save_profile(profile)
    return f"Updated static profile — {field}"

def update_dynamic(updates: dict):
    profile = load_profile()
    profile["dynamic"].update(updates)
    profile["dynamic"]["last_updated"] = datetime.now().isoformat()
    save_profile(profile)