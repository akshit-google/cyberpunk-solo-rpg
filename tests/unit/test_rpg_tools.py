from app.tools import roll_dice, get_character_sheet, update_character_sheet, add_journal_entry

class MockToolContext:
    def __init__(self, state=None):
        self.state = state if state is not None else {}


def test_roll_dice_valid() -> None:
    # Test flat rolls
    res = roll_dice("1d10")
    assert res["status"] == "success"
    assert len(res["rolls"]) == 1
    assert 1 <= res["rolls"][0] <= 10
    assert res["modifier"] == 0
    assert res["total"] == res["rolls"][0]

    # Test multiple dice
    res = roll_dice("3d6")
    assert res["status"] == "success"
    assert len(res["rolls"]) == 3
    assert all(1 <= d <= 6 for d in res["rolls"])
    assert res["modifier"] == 0
    assert res["total"] == sum(res["rolls"])

    # Test modifier addition
    res = roll_dice("1d10+4")
    assert res["status"] == "success"
    assert res["modifier"] == 4
    assert res["total"] == res["rolls"][0] + 4

    # Test modifier subtraction
    res = roll_dice("2d6-2")
    assert res["status"] == "success"
    assert res["modifier"] == -2
    assert res["total"] == sum(res["rolls"]) - 2


def test_roll_dice_invalid() -> None:
    res = roll_dice("invalid")
    assert res["status"] == "error"
    assert "Invalid dice formula" in res["message"]


def test_character_sheet_operations() -> None:
    # Set up starting state in context
    context = MockToolContext(state={
        "character_sheet": {
            "name": "Jax",
            "role": "Netrunner",
            "hp": 30,
            "max_hp": 30,
            "credits": 500,
            "stats": {"INT": 7, "REF": 6},
            "skills": {"interface": 4},
            "inventory": ["Neural Link"],
            "journal": ["Arrived in Neo-Chicago."]
        }
    })

    # Test get_character_sheet
    sheet = get_character_sheet(context)
    assert sheet["name"] == "Jax"
    assert sheet["credits"] == 500

    # Test update_character_sheet: flat update (credits and HP)
    update_res = update_character_sheet({"hp": 25, "credits": 450}, context)
    assert update_res["status"] == "success"
    assert context.state["character_sheet"]["hp"] == 25
    assert context.state["character_sheet"]["credits"] == 450

    # Test update_character_sheet: inventory add
    update_character_sheet({"inventory_add": "Cyberdeck"}, context)
    assert "Cyberdeck" in context.state["character_sheet"]["inventory"]

    # Test update_character_sheet: inventory remove
    update_character_sheet({"inventory_remove": "Neural Link"}, context)
    assert "Neural Link" not in context.state["character_sheet"]["inventory"]

    # Test update_character_sheet: nested update (skills)
    update_character_sheet({"skills": {"interface": 5, "handgun": 1}}, context)
    assert context.state["character_sheet"]["skills"]["interface"] == 5
    assert context.state["character_sheet"]["skills"]["handgun"] == 1

    # Test add_journal_entry
    journal_res = add_journal_entry("Bypassed corporate door.", context)
    assert journal_res["status"] == "success"
    assert "Bypassed corporate door." in context.state["character_sheet"]["journal"]
    assert len(context.state["character_sheet"]["journal"]) == 2
