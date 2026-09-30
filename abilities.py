"""The complete, server-owned ability library. No AI-authored numbers or rules."""
from content import FRONTS

ABILITIES = {
    "INVESTIGATE_VERIFY": {"kind": "Investigate", "name": "Verify", "effect": "Base 2. Success: +2 here. Partial: +1 here.", "prompt": "Which case clue supports this front, and what would you verify?"},
    "CONTAIN_ISOLATE": {"kind": "Contain", "name": "Isolate", "effect": "Base 2. Success: +1 here, another +1 if contested. Partial: +1 here.", "prompt": "What live exposure would you contain first, and why is that proportionate?"},
    "CHALLENGE_COUNTERCLAIM": {"kind": "Challenge", "name": "Counterclaim", "effect": "Base 2. Success: +1 here, another +1 against Investigate or Coordinate. Partial: +1 here.", "prompt": "Which claim goes beyond the case evidence, and why?"},
    "COORDINATE_RALLY": {"kind": "Coordinate", "name": "Rally", "effect": "Base 2. Success: +1 here and +1 next front. Partial: +1 next front.", "prompt": "Who should act on this front, and what should they do?"},
    "INVESTIGATE_CROSSCHECK": {"kind": "Investigate", "name": "Cross-Reference", "effect": "Base 2. Success: +1 here and +1 on your weakest other front. Partial: +1 here.", "prompt": "Connect two independent case records: what do they establish, and what remains uncertain?"},
    "CONTAIN_STABILISE": {"kind": "Contain", "name": "Stabilise", "effect": "Base 2. Success: +2 here if contested; otherwise +1 here and +1 next. Partial: +1 here.", "prompt": "How would you stop the live exposure while keeping unaffected work running?"},
    "CHALLENGE_FALSE_PREMISE": {"kind": "Challenge", "name": "False Premise", "effect": "Base 2. Success: +1 here and cancel at most 1 rival bonus influence. Partial: +1 here. Never cancels base.", "prompt": "Identify the unsupported leap, cite the case, and propose a check that could disprove it."},
    "COORDINATE_DUAL_CHANNEL": {"kind": "Coordinate", "name": "Dual Channel", "effect": "Base 2. Success: +1 on each other front. Partial: +1 next front.", "prompt": "Assign two distinct responders and a handoff that keeps access control and communication aligned."},
}
DEFAULT = {v["kind"]: k for k, v in list(ABILITIES.items())[:4]}
SPECIAL = {v["kind"]: k for k, v in list(ABILITIES.items())[4:]}
RARITIES = ("COMMON", "UNCOMMON", "RARE", "EPIC")


def decorate(card):
    """Old collections remain playable under current mechanics; provenance is untouched."""
    ability_id = card.get("ability_id", DEFAULT[card["archetype"]])
    ability = ABILITIES[ability_id]
    if ability["kind"] != card["archetype"]:
        raise ValueError("Ability/archetype mismatch")
    return {**card, "ability_id": ability_id, "ability_name": ability["name"], "effect": ability["effect"], "prompt": ability["prompt"], "rarity": card.get("rarity", "COMMON")}


def resolve_pair(plays, scores):
    results = []
    for seat, play in enumerate(plays):
        front = play["front"]
        other = plays[1-seat]
        ability = play["card"]["ability_id"]
        evaluation = play["evaluation"]
        outcome = evaluation["effect_result"]
        delta = dict.fromkeys(FRONTS, 0)
        delta[front] = 2
        next_front = FRONTS[(FRONTS.index(front)+1) % 3]
        if outcome == "partial":
            delta[next_front if ability.startswith("COORDINATE") else front] += 1
        elif outcome == "success":
            if ability == "INVESTIGATE_VERIFY":
                delta[front] += 2
            elif ability == "CONTAIN_ISOLATE":
                delta[front] += 1 + int(other["front"] == front)
            elif ability == "CHALLENGE_COUNTERCLAIM":
                delta[front] += 1 + int(other["card"]["archetype"] in ("Investigate", "Coordinate"))
            elif ability == "COORDINATE_RALLY":
                delta[front] += 1
                delta[next_front] += 1
            elif ability == "INVESTIGATE_CROSSCHECK":
                weakest = min((f for f in FRONTS if f != front), key=lambda f: scores[seat][f])
                delta[front] += 1
                delta[weakest] += 1
            elif ability == "CONTAIN_STABILISE":
                delta[front] += 1
                delta[front if other["front"] == front else next_front] += 1
            elif ability == "CHALLENGE_FALSE_PREMISE":
                delta[front] += 1
            elif ability == "COORDINATE_DUAL_CHANNEL":
                for f in FRONTS:
                    if f != front:
                        delta[f] += 1
        results.append({"delta": delta, "context_match": outcome == "success", "outcome": outcome,
                        "reason": f"Base 2 on {front}. {outcome.title()}: {evaluation['feedback']}", "cancelled": 0})
    # Simultaneous suppression reads the original bonuses, preserving every base 2.
    originals = [r["delta"].copy() for r in results]
    for seat, play in enumerate(plays):
        if play["card"]["ability_id"] == "CHALLENGE_FALSE_PREMISE" and play["evaluation"]["effect_result"] == "success":
            rival = 1-seat
            target = next((f for f in FRONTS if originals[rival][f] > (2 if plays[rival]["front"] == f else 0)), None)
            if target:
                results[rival]["delta"][target] -= 1
                results[rival]["cancelled"] = 1
                results[seat]["reason"] += f" Cancelled 1 rival bonus on {target}."
                results[rival]["reason"] += f" Rival cancelled 1 bonus on {target}; base remains."
            else:
                results[seat]["reason"] += " No rival bonus to cancel."
    return results
