import random
import re
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from google.adk.tools import ToolContext

# Define schemas for tool inputs and outputs
class DiceFormulaInput(BaseModel):
    formula: str = Field(..., description="The dice roll formula string, such as '1d10', '2d6', or '1d10+3'")

class CharacterUpdateInput(BaseModel):
    hp: Optional[int] = Field(None, description="New HP value to set directly, e.g. 25")
    credits: Optional[int] = Field(None, description="New credits value to set directly, e.g. 450")
    inventory_add: Optional[List[str]] = Field(None, description="List of items to add to inventory")
    inventory_remove: Optional[List[str]] = Field(None, description="List of items to remove from inventory")
    skills: Optional[Dict[str, int]] = Field(None, description="Skills to update, mapping skill name to new rank")
    stats: Optional[Dict[str, int]] = Field(None, description="Stats to update, mapping stat name to new value")

class JournalEntryInput(BaseModel):
    entry: str = Field(..., description="A short string summarizing the latest event or result (e.g. 'Bypassed lock.')")

class ToolResponse(BaseModel):
    status: str = Field(..., description="Status of the operation, 'success' or 'error'")
    message: Optional[str] = Field(None, description="Detailed message describing the result")
    data: Optional[Dict[str, Any]] = Field(None, description="Payload data resulting from the tool operation")


def roll_dice(args: DiceFormulaInput) -> dict:
    """Rolls dice based on a formula (e.g. '1d10', '2d6', '1d10+4', '2d6-1').

    Args:
        args: The dice roll input arguments containing the formula.

    Returns:
        A dictionary containing 'rolls' (list of individual die values), 
        'modifier' (the flat plus/minus value), and 'total' (the final sum).
    """
    formula = args.formula
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


def update_character_sheet(updates: CharacterUpdateInput, tool_context: ToolContext) -> dict:
    """Updates the character sheet with new values.

    Args:
        updates: The character update parameters.
        tool_context: The execution context for the tool (injected automatically).

    Returns:
        A dictionary containing the updated character sheet.
    """
    sheet = tool_context.state.get("character_sheet", {})
    if not sheet:
        return {"status": "error", "message": "No character sheet initialized."}
    
    if updates.hp is not None:
        sheet["hp"] = updates.hp
    if updates.credits is not None:
        sheet["credits"] = updates.credits
    if updates.inventory_add is not None:
        for item in updates.inventory_add:
            sheet["inventory"].append(str(item))
    if updates.inventory_remove is not None:
        for item in updates.inventory_remove:
            if str(item) in sheet["inventory"]:
                sheet["inventory"].remove(str(item))
    if updates.skills is not None:
        if "skills" not in sheet:
            sheet["skills"] = {}
        sheet["skills"].update(updates.skills)
    if updates.stats is not None:
        if "stats" not in sheet:
            sheet["stats"] = {}
        sheet["stats"].update(updates.stats)
                
    tool_context.state["character_sheet"] = sheet
    return {"status": "success", "character_sheet": sheet}


def add_journal_entry(entry_arg: JournalEntryInput, tool_context: ToolContext) -> dict:
    """Appends a new summary entry to the campaign journal log.

    Args:
        entry_arg: The journal entry content.
        tool_context: The execution context for the tool (injected automatically).

    Returns:
        A dictionary confirming the entry has been added.
    """
    sheet = tool_context.state.get("character_sheet", {})
    if "journal" not in sheet:
        sheet["journal"] = []
    sheet["journal"].append(entry_arg.entry)
    tool_context.state["character_sheet"] = sheet
    return {"status": "success", "journal": sheet["journal"]}
