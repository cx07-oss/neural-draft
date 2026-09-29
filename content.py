"""One authored simulation, one transfer case, and four immutable mechanics."""
FRONTS = ["Evidence", "Response", "People"]
EFFECTS = {
    "Investigate": "Gain 2 influence. +2 if your clue directly supports your chosen front.",
    "Contain": "Gain 2 influence. +2 if your rival also plays on this front.",
    "Challenge": "Gain 2 influence. +2 if your rival plays Investigate or Coordinate, on any front.",
    "Coordinate": "Gain 2 influence here and 1 on the next front: Evidence → Response → People → Evidence.",
}
EVIDENCE = [
    {"id": "request", "tag": "01 / VENDOR MESSAGE", "title": "An urgent favour", "preview": "MorrowSync support · 09:12", "text": "“Our 4.8 hotfix prevents a queue failure. Install this attached updater before 10:00. The portal is being repaired; please temporarily disable endpoint protection if installation is blocked.” The sender is updates@morrow-sync.help, a domain you have never used.", "term": "Endpoint protection", "definition": "Software that monitors a device for suspicious activity. Disabling it removes a safety layer exactly when an unverified program would run."},
    {"id": "signature", "tag": "02 / PACKAGE RECORD", "title": "A signature out of place", "preview": "Update verifier · 09:16", "text": "The updater is signed by “Harbour Utilities Ltd”. The last approved MorrowSync package was signed by “Morrow Systems”. The vendor portal still lists version 4.7. A valid signature identifies a signer; it does not prove this is the expected vendor.", "term": "Digital signature", "definition": "A cryptographic link between a file and its signer. Check the expected signer and release through an independent, trusted channel."},
    {"id": "scope", "tag": "03 / OPERATIONS NOTE", "title": "The blast radius", "preview": "Leena Rao · 09:19", "text": "Two test laptops downloaded the file but have not run it. Production is healthy. We can pause deployment and preserve the file and logs. The approved vendor contact is in our internal directory, independent of the message.", "term": "Blast radius", "definition": "The systems or people that could be affected. A narrow, reversible response can reduce risk without shutting down healthy services."},
]
ACTIONS = [
    {"id": "verify", "title": "Pause. Verify. Preserve.", "text": "Hold the update, preserve the file and logs, and call the vendor using the internal directory.", "archetype": "Investigate"},
    {"id": "isolate", "title": "Isolate the test laptops", "text": "Disconnect both test laptops, keep production running, and ask the incident lead to investigate.", "archetype": "Contain"},
    {"id": "install", "title": "Trust the urgent update", "text": "Disable protection on the test laptops and run the updater to meet the deadline.", "archetype": "Challenge"},
]
RUBRIC = [
    {"key": "verification", "title": "Verification", "levels": ["0 · No independent check", "1 · Inspect the signer or request an investigation", "2 · Inspect the signer and choose independent vendor verification"]},
    {"key": "risk", "title": "Risk recognition", "levels": ["0 · No relevant evidence inspected", "1 · Inspect the unusual request or signer", "2 · Inspect both the unusual request and signer"]},
    {"key": "response", "title": "Proportional response", "levels": ["0 · Run an unverified updater with protection disabled", "1 · Pause or isolate without checking scope", "2 · Inspect scope, then pause or isolate while keeping production running"]},
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
NAMES = {"Investigate": "Signal Cartographer", "Contain": "Quiet Firewall", "Challenge": "Assumption Breaker", "Coordinate": "Relay Architect"}
FLAVOUR = {"Investigate": "Follow the signal. Earn the certainty.", "Contain": "A small boundary can protect a whole system.", "Challenge": "The next good decision begins with a question.", "Coordinate": "No one holds the whole map. Connect the people who do."}


def make_card(card_id, archetype, nickname, evolution="Initiate", demo=False):
    return {"id": card_id, "name": f"{nickname}'s {NAMES[archetype]}", "archetype": archetype,
            "effect": EFFECTS[archetype], "skill": "Cyber incident judgement", "flavour": FLAVOUR[archetype],
            "evolution": evolution, "demo": demo}


def deck(card):
    starters = [("s1", "Trace Lens", "Investigate"), ("s2", "Circuit Shelter", "Contain"),
                ("s3", "Counterpoint", "Challenge"), ("s4", "Human Relay", "Coordinate"),
                ("s5", "Source Check", "Investigate")]
    return [card] + [{"id": i, "name": n, "archetype": a, "effect": EFFECTS[a],
                     "skill": "Starter protocol", "flavour": FLAVOUR[a], "evolution": "Starter"} for i, n, a in starters]


def resolve_play(play, opponent):
    """Pure simultaneous mechanic: reads only the two committed plays."""
    front = play["front"]
    kind = play["card"]["archetype"]
    delta = {f: 0 for f in FRONTS}
    delta[front] = 2
    if kind == "Investigate":
        clue = next(c for c in CASE["clues"] if c["id"] == play["clue"])
        earned = clue["front"] == front
        delta[front] += 2 if earned else 0
        why = f"{clue['title']} {'directly supports' if earned else 'does not directly support'} {front}: {'+2 clue bonus' if earned else 'no clue bonus'}."
    elif kind == "Contain":
        earned = opponent["front"] == front
        delta[front] += 2 if earned else 0
        why = "Your rival contested this front: +2 containment bonus." if earned else "Your rival played elsewhere: no containment bonus."
    elif kind == "Challenge":
        earned = opponent["card"]["archetype"] in ("Investigate", "Coordinate")
        delta[front] += 2 if earned else 0
        why = f"Rival used {opponent['card']['archetype']}: " + ("+2 challenge bonus." if earned else "no challenge bonus.")
    else:
        next_front = FRONTS[(FRONTS.index(front) + 1) % 3]
        delta[next_front] = 1
        why = f"Coordination carries +1 influence to {next_front}."
    return {"delta": delta, "reason": f"+2 base influence on {front}. {why}"}


def winner(scores):
    leads = [sum(scores[p][f] > scores[1-p][f] for f in FRONTS) for p in (0, 1)]
    if max(leads) >= 2:
        return leads.index(max(leads)), "Leads at least two of the three fronts."
    if leads == [1, 1]:
        totals = [sum(s.values()) for s in scores]
        if totals[0] != totals[1]:
            return totals.index(max(totals)), "One front each, one tied: total influence breaks the split."
    return None, "Neither player leads two fronts, and the split has no winning tiebreak."
