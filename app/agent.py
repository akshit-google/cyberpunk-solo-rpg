from typing import AsyncGenerator
from google.adk.agents import Agent, BaseAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.events import Event
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.callback_context import CallbackContext

from app.tools import roll_dice, get_character_sheet, update_character_sheet, add_journal_entry

# Initialize player character sheet in session state if not already done
async def init_state(callback_context: CallbackContext) -> None:
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
    return Agent(
        name="rules_agent",
        model=Gemini(model="gemini-flash-latest"),
        instruction=instruction,
        tools=[roll_dice, get_character_sheet, update_character_sheet, add_journal_entry],
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
    return Agent(
        name="narrator_agent",
        model=Gemini(model="gemini-flash-latest"),
        instruction=instruction,
    )


class GameCouncilAgent(BaseAgent):
    # Declare fields for Pydantic validation
    rules_agent: BaseAgent
    narrator_agent: BaseAgent

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # 1. Run the rules agent to process rolls, check sheet, log events.
        rules_report_text = ""
        async for event in self.rules_agent.run_async(ctx):
            if event.get_function_calls() or event.get_function_responses():
                yield event
            elif event.is_final_response():
                if event.content and event.content.parts:
                    rules_report_text += event.content.parts[0].text
        
        ctx.session.state["rules_report"] = rules_report_text or "No mechanical rolls or checks occurred."

        # 2. Run the narrator agent.
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
)

app = App(
    root_agent=root_agent,
    name="app",
)
