import re
import logging
import asyncio
from typing import AsyncGenerator, Optional

from google.adk.agents import Agent, BaseAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.events import Event
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import FunctionTool
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.apps.app import EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer

from app.tools import (
    roll_dice, 
    get_character_sheet, 
    update_character_sheet, 
    add_journal_entry,
    DiceFormulaInput,
    CharacterUpdateInput,
    JournalEntryInput
)

# Set up local logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rpg_engine")


# --- 1. CALLBACKS: State Initialization & Async Memory Consolidation ---

async def init_state(callback_context: CallbackContext) -> None:
    """Initializes player character sheet in session state if not already done."""
    if "character_sheet" not in callback_context.state:
        callback_context.state["character_sheet"] = {
            "name": "Jax",
            "role": "Netrunner",
            "hp": 30,
            "max_hp": 30,
            "credits": 500,
            "stats": {
                "INT": 7,  # Intelligence
                "REF": 6,  # Reflexes
                "TECH": 8, # Technology
                "COOL": 5, # Cool
            },
            "skills": {
                "interface": 4,
                "handgun": 2,
                "stealth": 3,
                "athletics": 1,
            },
            "inventory": ["Neural Link", "Smart Pistol (10 ammo)", "Credkey"],
            "journal": ["Arrived in Neo-Chicago. Ready for the next gig."]
        }
    if "rules_report" not in callback_context.state:
        callback_context.state["rules_report"] = "No actions occurred yet."


async def run_memory_consolidation(callback_context: CallbackContext) -> None:
    """Performs background memory consolidation asynchronously."""
    try:
        await asyncio.sleep(0.5)  # Non-blocking simulation of background work
        sheet = callback_context.state.get("character_sheet", {})
        if sheet and "journal" in sheet:
            entries = sheet["journal"]
            logger.info(f"[ASYNC MEMORY CONSOLIDATION] Consolidating {len(entries)} journal entries in background.")
            # In a production app, we would write these to a persistent SQLite/Cloud SQL db or file here
    except Exception as e:
        logger.error(f"Error in background memory consolidation: {e}")


async def after_agent_consolidate(callback_context: CallbackContext) -> None:
    """Triggers background memory task without blocking the final user response."""
    asyncio.create_task(run_memory_consolidation(callback_context))
    return None


# --- 2. OBSERVABILITY: Intent vs Outcome Logging Callbacks ---

async def before_tool_log(tool, args, tool_context) -> None:
    """Explicitly logs the intent before executing a tool."""
    logger.info(f"[INTENT LOG] Intending to invoke tool '{tool.name}' with arguments: {args}")
    return None

async def after_tool_log(tool, args, tool_context, tool_response) -> None:
    """Explicitly logs the final outcome after a tool completes."""
    logger.info(f"[OUTCOME LOG] Tool '{tool.name}' completed execution. Response payload: {tool_response}")
    return None


# --- 3. HUMAN-IN-THE-LOOP: High-Stakes Confirmation Hook ---

def needs_approval(updates: CharacterUpdateInput, **kwargs) -> bool:
    """Evaluates whether an update requires explicit human-in-the-loop approval.
    
    Returns True for life-threatening damage (HP <= 0) or huge credit spending (credits <= 100).
    """
    if updates.hp is not None and updates.hp <= 0:
        logger.warning("[HITL TRIGGER] High-stakes action: Player is at risk of dying!")
        return True
    if updates.credits is not None and updates.credits <= 100:
        logger.warning("[HITL TRIGGER] High-stakes action: Large monetary spending!")
        return True
    return False

# Wrap update_character_sheet tool with approval hook
update_character_tool = FunctionTool(
    update_character_sheet, 
    require_confirmation=needs_approval
)


# --- 4. POLICY PLUGINS: PII Redaction Guardrails ---

class RPGPolicyPlugin(BasePlugin):
    """Custom runtime policy plugin enforcing PII redaction before invoking models."""
    async def before_model_callback(self, *, callback_context, llm_request):
        if llm_request.contents:
            for content in llm_request.contents:
                if content.parts:
                    for part in content.parts:
                        if part.text:
                            # Redact email addresses
                            email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
                            part.text = re.sub(email_pattern, "[REDACTED_EMAIL]", part.text)
                            # Redact phone numbers
                            phone_pattern = r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
                            part.text = re.sub(phone_pattern, "[REDACTED_PHONE]", part.text)
        return None


# --- 5. AGENT DEFINITIONS & STRATEGIC MODEL ROUTING ---

def create_rules_agent() -> Agent:
    instruction = """You are the mechanical Rules & Combat Engine (The Arbiter) of a Cyberpunk Solo RPG set in Neo-Chicago 2099.
Your job is to parse the user's action and determine if a skill check, combat round, item transaction, or state update is required.

Rules System:
1. Every skill check is rolled using a d10. The total is: d10 roll + Stat modifier + Skill modifier.
   Stats: INT, REF, TECH, COOL.
   Skills: interface, handgun, stealth, athletics.
2. Target difficulty thresholds: Easy = 10, Medium = 15, Hard = 20.
3. If an action requires a roll, fetch the character sheet first using `get_character_sheet`. Match the action to a stat and skill, roll using `roll_dice`, and evaluate success/failure.
4. If combat happens (e.g. shooting, dodging):
   - Attack roll: d10 + REF + handgun vs Evasion.
   - Damage roll: roll dice (e.g. 2d6 for smart pistol), subtract from HP.
   - Retaliation: Roll enemy attack against the player, calculate damage, update player HP using `update_character_sheet`.
5. If credits are earned/spent or items are found/used:
   - Call `update_character_sheet` to modify stats, credits, or inventory.
6. Always call `add_journal_entry` with a brief summary of the mechanical outcome (e.g. 'Jax hacked corporate ICE. Obtained project files. Credkey found.').

Your Output Format:
Output a structured, clear mechanical report summarizing what happened, what was rolled, success/failure status, and all state changes. 
Example:
[RULES REPORT]
Action: Hack corporate door.
Check: TECH + Interface vs Difficulty 15.
Roll: 1d10 (8) + TECH (8) + Interface (4) = 20 (Success).
State Changes: Added 'Project Files' to inventory.
Journal Log: Jax bypassed door lock to enter security room.
"""
    # Strategic Routing: Flash model for low-latency logic processing and fast tool-calling
    return Agent(
        name="rules_agent",
        model=Gemini(model="gemini-flash-latest"),
        instruction=instruction,
        tools=[roll_dice, get_character_sheet, update_character_tool, add_journal_entry],
        before_tool_callback=before_tool_log,
        after_tool_callback=after_tool_log,
    )


def create_narrator_agent() -> Agent:
    instruction = """You are the Narrator (Storyteller) of this Solo Cyberpunk RPG.
Your job is to read the user's action and the Rules Engine's mechanical report.
Describe the scene in a dark, atmospheric, rain-slicked cyberpunk tone (Neo-Chicago 2099).

Current Character Sheet state:
{character_sheet}

Latest mechanical rules resolution (use this to describe the outcome of their action):
{rules_report}

Guidelines:
1. Read the latest mechanical rules resolution (success, failure, damage taken, items gained).
2. Translate those mechanics into a cinematic, visceral narrative. If a roll succeeded, describe the character's expert execution. If it failed, describe a dramatic complication (sparks flying, alarms blaring, security bots activating).
3. Do NOT mention tool names, raw JSON, or words like 'tool_context' or 'rules_agent'. Keep it entirely immersive.
4. Refer to the character sheet state if you need to mention Jax's specific gear or status.
5. Always end your turn by asking the player: 'What do you do?' or giving them a few thematic choices.
"""
    # Strategic Routing: Pro model for high-quality, creative, multi-turn narrative generation
    return Agent(
        name="narrator_agent",
        model=Gemini(model="gemini-1.5-pro"),
        instruction=instruction,
    )


class GameCouncilAgent(BaseAgent):
    rules_agent: BaseAgent
    narrator_agent: BaseAgent

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # 1. Run the rules agent
        rules_report_text = ""
        async for event in self.rules_agent.run_async(ctx):
            if event.get_function_calls() or event.get_function_responses():
                yield event
            elif event.is_final_response():
                if event.content and event.content.parts:
                    rules_report_text += event.content.parts[0].text
        
        ctx.session.state["rules_report"] = rules_report_text or "No mechanical rolls or checks occurred."

        # 2. Run the narrator agent
        async for event in self.narrator_agent.run_async(ctx):
            yield event


# Instantiate sub-agents
rules_sub = create_rules_agent()
narrator_sub = create_narrator_agent()

# Instantiate composite root agent passing sub-agents into validation fields
root_agent = GameCouncilAgent(
    name="game_council",
    rules_agent=rules_sub,
    narrator_agent=narrator_sub,
    sub_agents=[rules_sub, narrator_sub],
    before_agent_callback=init_state,
    after_agent_callback=after_agent_consolidate,
)

app = App(
    root_agent=root_agent,
    name="app",
    # History Compaction/Context Bloat Management: periodic summary of intermediate conversation events
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=15,
        overlap_size=3,
        summarizer=LlmEventSummarizer(llm=Gemini(model="gemini-flash-latest")),
    ),
    plugins=[RPGPolicyPlugin()],
)
