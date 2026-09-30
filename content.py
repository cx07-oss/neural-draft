"""One authored simulation, one transfer case, and four immutable mechanics."""
FRONTS = ["Evidence", "Response", "People"]
EFFECTS = {
    "Investigate": "Gain 2 influence. +2 if your clue directly supports your chosen front.",
    "Contain": "Gain 2. Identify the live exposure for +1; gain another +1 if your rival contests this front.",
    "Challenge": "Gain 2. Challenge an unsupported claim for +1; gain another +1 against Investigate or Coordinate.",
    "Coordinate": "Gain 2. Choose a responder suited to your front to carry +1 to the next front (Evidence → Response → People → Evidence).",
}
EVIDENCE = [
    {"id": "request", "tag": "01 / VENDOR MESSAGE", "title": "A familiar thread", "preview": "MorrowSync support · 09:12", "text": "A reply in your existing support thread offers hotfix 4.8 before the 10:00 dispatch peak. It comes from the usual address and cites your real queue ticket. Support says the new signing partner is approved, but asks you to use an attached package while the portal catches up. The address and ticket are plausible; neither confirms who controls the account.", "term": "Trusted channel", "definition": "A contact route checked independently of the message, such as the vendor number in your internal directory."},
    {"id": "signature", "tag": "02 / PACKAGE RECORD", "title": "An unexplained handover", "preview": "Update verifier · 09:16", "text": "The package has a valid signature from Harbour Utilities Ltd, rather than the usual Morrow Systems. Last week's account note mentioned a packaging partner, but did not name it. The portal still lists 4.7. This might be a legitimate handover or a compromised update; the claim that this signer is approved has no independent confirmation.", "term": "Digital signature", "definition": "Links a file to a signer. A valid signature does not establish that the signer is the vendor you intended to trust."},
    {"id": "scope", "tag": "03 / OPERATIONS NOTE", "title": "The cost of waiting", "preview": "Leena Rao · 09:19", "text": "Two staging laptops downloaded the package; neither ran it. Dispatch retries are rising, though orders still flow. A vendor callback takes about 15 minutes; manual dispatch can bridge that delay with slower deliveries. Isolating staging stops package spread but delays today's release checks. A broad shutdown would interrupt live dispatch.", "term": "Blast radius", "definition": "How far a problem could spread. Targeting a narrow exposure can limit harm while retaining other options."},
]
ACTIONS = [
    {"id": "verify", "title": "Hold for an independent check", "text": "Preserve the package and call the directory contact. Accept a 15-minute delay and slower manual dispatch. Choose what to verify below.", "archetype": "Investigate"},
    {"id": "isolate", "title": "Quarantine staging first", "text": "Disconnect the two staging laptops and preserve their logs. Keep dispatch running, but lose today's release checks while the incident lead investigates.", "archetype": "Contain"},
    {"id": "coordinate", "title": "Rally a bounded response", "text": "Assign the dispatch lead to manual orders and the vendor liaison to signer confirmation. Hold installation until they agree; coordination costs staff and may delay the peak.", "archetype": "Coordinate"},
]
RUBRIC = [
    {"key": "verification", "title": "Verification", "levels": ["0 · No independent check or signer inspection", "1 · Inspect the signer or request a check", "2 · Inspect the signer and choose independent checking or vendor coordination"]},
    {"key": "risk", "title": "Risk recognition", "levels": ["0 · No relevant evidence inspected", "1 · Inspect the unusual request or signer", "2 · Inspect both the unusual request and signer"]},
    {"key": "response", "title": "Proportional response", "levels": ["0 · No bounded response", "1 · Choose a bounded response without checking its cost", "2 · Inspect operational costs, then choose a bounded response"]},
]
CASE = {
    "title": "The borrowed badge", "summary": "A contractor account exported an unusual batch of files from the Helix research workspace. Access is paused. Build an evidence-led response across three fronts.",
    "clues": [
        {"id": "audit", "title": "Export audit", "text": "The signed audit trail records a bulk export at 02:14 from a new device.", "front": "Evidence"},
        {"id": "token", "title": "A live session", "text": "One session token remains active; revoking it stops access without taking the workspace offline.", "front": "Response"},
        {"id": "owner", "title": "The workspace owner", "text": "The on-call owner can contact the contractor and notify affected research teams through the incident channel.", "front": "People"},
        {"id": "rumour", "title": "A channel rumour", "text": "An anonymous post says “everyone has been hacked”, with no source or supporting record.", "front": None},
    ],
}
RESPONSES = {"Investigate": "Gather information", "Challenge": "Test assumptions", "Contain": "Limit downside", "Coordinate": "Mobilise people and timing"}
CHOICES = {
    "Investigate": {"prompt": "Which clue supports your chosen front?", "options": [{"id": c["id"], "title": c["title"]} for c in CASE["clues"]]},
    "Contain": {"prompt": "Which exposure needs containing now?", "options": [
        {"id": "session", "title": "Revoke the active session token"},
        {"id": "shutdown", "title": "Take every research workspace offline"},
        {"id": "archive", "title": "Delete the audit archive"}]},
    "Challenge": {"prompt": "Which claim goes beyond the evidence?", "options": [
        {"id": "breach", "title": "The export proves every account was hacked"},
        {"id": "record", "title": "The audit records an export from a new device"},
        {"id": "access", "title": "A session token still allows access"}]},
    "Coordinate": {"prompt": "Who can act on your chosen front?", "options": [
        {"id": "analyst", "title": "Audit analyst — preserve and check the trail"},
        {"id": "operator", "title": "Access operator — revoke the live token"},
        {"id": "liaison", "title": "Workspace owner — contact people affected"}]},
}
PATTERNS = [
    {"id": "source", "kind": "Investigate", "label": "Verify source", "available": True},
    {"id": "claim", "kind": "Challenge", "label": "Test assumption", "available": True},
    {"id": "exposure", "kind": "Contain", "label": "Prioritise exposure", "available": True},
    {"id": "escalate", "kind": "Coordinate", "label": "Escalate effectively", "available": True},
    {"id": "trace", "kind": "Investigate", "label": "Trace origin", "available": False},
    {"id": "contradiction", "kind": "Challenge", "label": "Find contradiction", "available": False},
]
SKILLS = {"Investigate": "Verification under uncertainty", "Challenge": "Testing an assumption", "Contain": "Prioritising exposure", "Coordinate": "Coordinating a bounded response"}


def forged_record(action, inspected, focus="source"):
    """Describe selected actions, never claim the simulated plan was executed."""
    kind = "Challenge" if action == "verify" and focus == "claim" else next(a["archetype"] for a in ACTIONS if a["id"] == action)
    pattern = {"Investigate": "source", "Challenge": "claim", "Contain": "exposure", "Coordinate": "escalate"}[kind]
    plan = {"source": "chose to hold the update and verify its source through the directory contact", "claim": "chose to test the claim that the new signer is approved before installation", "exposure": "chose to quarantine staging while keeping dispatch running", "escalate": "chose to assign separate dispatch and vendor checks before allowing installation"}[pattern]
    titles = [e["title"] for e in EVIDENCE if e["id"] in inspected]
    text = f"Forged because you {plan}. " + ("You inspected: " + "; ".join(titles) + "." if titles else "No evidence items were opened.")
    required = {"source": {"signature"}, "claim": {"request", "signature"}, "exposure": {"scope"}, "escalate": {"signature", "scope"}}[pattern]
    return {"forged_because": text, "pattern": pattern if required.issubset(inspected) else None, "archetype": kind}


def strategy_observations(history, seat):
    """Observable choices and outcomes, not motives or claims of learning."""
    fronts = [h["plays"][seat]["front"] for h in history]
    matched = sum(h["effects"][seat]["context_match"] for h in history)
    observations = [
        {"text": f"You put pressure on {len(set(fronts))} of 3 fronts across {len(fronts)} rounds.", "rounds": [h["round"] for h in history], "skills": ["Risk allocation"]},
        {"text": f"{matched} of {len(history)} written decisions fully activated their skill effect.", "rounds": [h["round"] for h in history if h["effects"][seat]["context_match"]], "skills": ["Reasoning under uncertainty"]},
    ]
    for previous, current in zip(history, history[1:]):
        if previous["effects"][seat]["delta"][previous["plays"][seat]["front"]] < previous["effects"][1-seat]["delta"][previous["plays"][seat]["front"]] and current["plays"][seat]["front"] != previous["plays"][seat]["front"]:
            observations.append({"text": f"After your rival gained more on {previous['plays'][seat]['front']} in round {previous['round']}, you switched to {current['plays'][seat]['front']} in round {current['round']}.", "rounds": [previous["round"], current["round"]], "skills": ["Adaptation"]})
            break
    if len(observations) == 2:
        contests = [h["round"] for h in history if h["plays"][seat]["card"]["archetype"] == "Contain" and h["effects"][seat]["context_match"] and h["plays"][seat]["front"] == h["plays"][1-seat]["front"]]
        if contests:
            observations.append({"text": f"Your containment met a rival play in round {contests[0]}, earning the contested-front bonus.", "rounds": [contests[0]], "skills": ["Prediction"]})
    return observations
NAMES = {"Investigate": "Source Check", "Contain": "Safe Hold", "Challenge": "Reality Check", "Coordinate": "Team Link"}
FLAVOUR = {"Investigate": "Follow the signal. Earn the certainty.", "Contain": "A small boundary can protect a whole system.", "Challenge": "The next good decision begins with a question.", "Coordinate": "No one holds the whole map. Connect the people who do."}


def make_card(card_id, archetype, nickname, evolution="Initiate", demo=False):
    return {"id": card_id, "name": f"{nickname}'s {NAMES[archetype]}", "archetype": archetype,
            "effect": EFFECTS[archetype], "skill": SKILLS[archetype], "flavour": FLAVOUR[archetype],
            "evolution": evolution, "demo": demo}


def deck(card):
    starters = [("s1", "Trace", "Investigate"), ("s2", "Shield", "Contain"),
                ("s3", "Counterclaim", "Challenge"), ("s4", "Relay", "Coordinate"),
                ("s5", "Source Check", "Investigate")]
    return [{**card, "effect": EFFECTS[card["archetype"]]}] + [{"id": i, "name": n, "archetype": a, "effect": EFFECTS[a],
                     "skill": "Starter protocol", "flavour": FLAVOUR[a], "evolution": "Starter"} for i, n, a in starters]


def resolve_play(play, opponent):
    """Pure simultaneous mechanic: reads only the two committed plays."""
    front = play["front"]
    kind = play["card"]["archetype"]
    delta = {f: 0 for f in FRONTS}
    delta[front] = 2
    choice = play.get("choice", play.get("clue"))
    if kind == "Investigate":
        clue = next(c for c in CASE["clues"] if c["id"] == choice)
        earned = clue["front"] == front
        delta[front] += 2 if earned else 0
        why = f"{clue['title']} {'directly supports' if earned else 'does not directly support'} {front}: {'+2 clue bonus' if earned else 'no clue bonus'}."
    elif kind == "Contain":
        earned = choice == "session"
        contested = opponent["front"] == front
        delta[front] += (1 + int(contested)) if earned else 0
        why = ("You targeted the live session: +1. " + ("Your rival contested this front: +1." if contested else "No contested-front bonus.")) if earned else "The live session is the immediate exposure; this choice earns no containment bonus."
    elif kind == "Challenge":
        earned = choice == "breach"
        counter = opponent["card"]["archetype"] in ("Investigate", "Coordinate")
        delta[front] += (1 + int(counter)) if earned else 0
        why = ("The export does not prove every account was hacked: +1. " + (f"Rival used {opponent['card']['archetype']}: +1 counter bonus." if counter else "No counter bonus.")) if earned else "That claim is supported by the case; no challenge bonus."
    elif kind == "Coordinate":
        earned = {"analyst": "Evidence", "operator": "Response", "liaison": "People"}.get(choice) == front
        next_front = FRONTS[(FRONTS.index(front) + 1) % 3]
        delta[next_front] = int(earned)
        why = f"Your responder can act on {front}: +1 carried to {next_front}." if earned else f"Your responder's role does not address {front}: no relay bonus."
    else:
        raise ValueError("Unknown archetype")
    return {"delta": delta, "context_match": earned, "reason": f"+2 base influence on {front}. {why}"}


def winner(scores):
    leads = [sum(scores[p][f] > scores[1-p][f] for f in FRONTS) for p in (0, 1)]
    if max(leads) >= 2:
        return leads.index(max(leads)), "Leads at least two of the three fronts."
    if leads == [1, 1]:
        totals = [sum(s.values()) for s in scores]
        if totals[0] != totals[1]:
            return totals.index(max(totals)), "One front each, one tied: total influence breaks the split."
    return None, "Neither player leads two fronts, and the split has no winning tiebreak."
