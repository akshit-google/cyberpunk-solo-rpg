import random
import re
from google.adk.tools import ToolContext

def roll_dice(formula: str) -> dict:
    """Rolls dice based on a formula (e.g. '1d10', '2d6', '1d10+4', '2d6-1').

    Args:
        formula: The dice roll formula string, such as '1d10', '2d6', or '1d10+3'.

    Returns:
        A dictionary containing 'rolls' (list of individual die values), 
        'modifier' (the flat plus/minus value), and 'total' (the final sum).
    """
    # Normalize formula by removing spaces
    normalized = formula.replace(" ", "")
    match = re.match(r'^(\d+)d(\d+)(?:([+-])(\d+))?$', normalized)
    if not match:
        return {"status": "error", "message": f"Invalid dice formula: {formula}. Use format like '1d10', '2d6', '1d10+4'"}
    
    num_dice = int(match.group(1))
    sides = int(match.group(2))
    sign = match.group(3)
    mod_val = int(match.group(4)) if match.group(4) else 0
    
    rolls = [random.randint(1, sides) for _ in range(num_dice)]
    sum_rolls = sum(rolls)
    
    modifier = mod_val if sign == '+' else (-mod_val if sign == '-' else 0)
    total = sum_rolls + modifier
    
    return {
        "status": "success",
        "formula": formula,
        "rolls": rolls,
        "modifier": modifier,
        "total": total
    }


def get_character_sheet(tool_context: ToolContext) -> dict:
    """Fetches the current character sheet state (name, HP, credits, stats, skills, inventory).

    Returns:
        A dictionary containing the full character sheet.
    """
    return tool_context.state.get("character_sheet", {})


def update_character_sheet(updates: dict, tool_context: ToolContext) -> dict:
    """Updates the character sheet with new values.

    Args:
        updates: A dictionary of key-value pairs to update on the character sheet.
                 Example: {"hp": 25, "credits": 450, "inventory_add": "Cyberdeck", "inventory_remove": "Credkey"}

    Returns:
        A dictionary containing the updated character sheet.
    """
    sheet = tool_context.state.get("character_sheet", {})
    if not sheet:
        return {"status": "error", "message": "No character sheet initialized."}
    
    for key, value in updates.items():
        if key == "inventory_add":
            if isinstance(value, list):
                sheet["inventory"].extend([str(v) for v in value])
            else:
                sheet["inventory"].append(str(value))
        elif key == "inventory_remove":
            if isinstance(value, list):
                for item in value:
                    if str(item) in sheet["inventory"]:
                        sheet["inventory"].remove(str(item))
            else:
                if str(value) in sheet["inventory"]:
                    sheet["inventory"].remove(str(value))
        elif key in sheet:
            if isinstance(sheet[key], dict) and isinstance(value, dict):
                # Update nested dicts (like stats or skills)
                sheet[key].update(value)
            else:
                sheet[key] = value
                
    tool_context.state["character_sheet"] = sheet
    return {"status": "success", "character_sheet": sheet}


def add_journal_entry(entry: str, tool_context: ToolContext) -> dict:
    """Appends a new summary entry to the campaign journal log.

    Args:
        entry: A short string summarizing the latest event or result (e.g. 'Successfully hacked corporate lock. Obtained datapad.').

    Returns:
        A dictionary confirming the entry has been added.
    """
    sheet = tool_context.state.get("character_sheet", {})
    if "journal" not in sheet:
        sheet["journal"] = []
    sheet["journal"].append(entry)
    tool_context.state["character_sheet"] = sheet
    return {"status": "success", "journal": sheet["journal"]}
