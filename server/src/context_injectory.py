import json

MAX_CONTEXT_SIZE = 15 * 1024  # 15KB


def build_smart_business_context(structured_data: dict) -> str:
    if not structured_data:
        return ""

    full_json_str = json.dumps(structured_data, ensure_ascii=False)
    size_bytes = len(full_json_str.encode("utf-8"))

    if size_bytes < MAX_CONTEXT_SIZE:
        print(f"[CONTEXT MODE] Full inject | Size={size_bytes}")
        return f"""
Official Business Data:
{full_json_str}
"""

    core = {}
    for key in ["services", "contact", "pricing", "locations"]:
        if key in structured_data:
            core[key] = structured_data[key]

    print(f"[CONTEXT MODE] Core inject | Size={size_bytes}")

    return f"""
Official Business Core Data:
{json.dumps(core, ensure_ascii=False)}

For detailed business information not present here,
you MUST call the business data tool.
"""