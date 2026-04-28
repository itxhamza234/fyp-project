# advisor_prompt.py

def build_voice_advisor_prompt(ai_tone=None, ai_rules=None) -> str:
    # WAPDA ke liye advisor aur assistant same hain
    from assistant_prompt import build_voice_assistant_prompt
    return build_voice_assistant_prompt(ai_tone, ai_rules)