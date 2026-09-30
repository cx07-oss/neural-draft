"""Validated fictional cases. Six authored seeds are always available offline."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from abilities import ABILITIES

Domain = Literal["cybersecurity", "engineering", "product", "logistics", "scientific", "coordination"]
Archetype = Literal["Investigate", "Contain", "Challenge", "Coordinate"]
Signal = Literal["verification", "containment", "challenge", "coordination", "tradeoff", "reversible", "continuity", "test", "handoff"]
AbilityID = Literal["INVESTIGATE_VERIFY", "CONTAIN_ISOLATE", "CHALLENGE_COUNTERCLAIM", "COORDINATE_RALLY", "INVESTIGATE_CROSSCHECK", "CONTAIN_STABILISE", "CHALLENGE_FALSE_PREMISE", "COORDINATE_DUAL_CHANNEL"]
DOMAINS = list(Domain.__args__)
ShortText = Annotated[str, Field(min_length=2, max_length=240)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Character(Strict):
    name: str = Field(min_length=2, max_length=50)
    role: str = Field(min_length=2, max_length=70)
    initial_message: str = Field(min_length=20, max_length=350)


class Evidence(Strict):
    id: str = Field(pattern=r"^E[1-5]$")
    title: str = Field(min_length=3, max_length=80)
    text: str = Field(min_length=20, max_length=650)
    reliability: Literal["high", "medium", "low"]
    tags: list[Annotated[str, Field(min_length=2, max_length=30)]] = Field(min_length=1, max_length=5)


class Rubric(Strict):
    important_considerations: list[ShortText] = Field(min_length=2, max_length=5)
    dangerous_assumptions: list[ShortText] = Field(min_length=1, max_length=4)
    good_reasoning_signals: list[ShortText] = Field(min_length=2, max_length=5)
    failure_signals: list[ShortText] = Field(min_length=1, max_length=4)


class Special(Strict):
    id: Literal["special_rare", "special_epic"]
    rarity: Literal["RARE", "EPIC"]
    name_seed: str = Field(min_length=3, max_length=40)
    required_reasoning: list[Signal] = Field(min_length=3, max_length=6)
    ability_template: AbilityID

    @model_validator(mode="after")
    def conditions(self):
        if self.id != "special_" + self.rarity.lower():
            raise ValueError("Special ID and rarity must agree")
        if len(set(self.required_reasoning)) != len(self.required_reasoning):
            raise ValueError("Duplicate conditions")
        if self.rarity == "EPIC" and len(self.required_reasoning) < 4:
            raise ValueError("Epic needs four distinctive signals")
        if self.ability_template not in list(ABILITIES)[4:]:
            raise ValueError("Special requires an approved variant")
        return self


class Scenario(Strict):
    scenario_id: str = Field(pattern=r"^[a-z0-9_-]{3,60}$")
    title: str = Field(min_length=5, max_length=90)
    domain: Domain
    difficulty: Literal["STANDARD", "COMPLEX"]
    brief: str = Field(min_length=40, max_length=650)
    stakes: str = Field(min_length=15, max_length=250)
    time_pressure: str = Field(min_length=10, max_length=150)
    characters: list[Character] = Field(min_length=1, max_length=2)
    evidence: list[Evidence] = Field(min_length=3, max_length=5)
    hidden_rubric: Rubric
    possible_archetypes: list[Archetype] = Field(min_length=2, max_length=4)
    special_card_conditions: list[Special] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({e.id for e in self.evidence}) != len(self.evidence):
            raise ValueError("Evidence IDs must be unique")
        if len({s.id for s in self.special_card_conditions}) != len(self.special_card_conditions):
            raise ValueError("Special IDs must be unique")
        for s in self.special_card_conditions:
            if ABILITIES[s.ability_template]["kind"] not in self.possible_archetypes:
                raise ValueError("Special archetype unavailable")
        return self


def public_case(case, source):
    return {k: v for k, v in case.items() if k not in ("hidden_rubric", "special_card_conditions")} | {"source": source}


def seed(i, title, domain, brief, stakes, pressure, name, role, message, evidence):
    return Scenario.model_validate({
        "scenario_id": i, "title": title, "domain": domain, "difficulty": "STANDARD", "brief": brief,
        "stakes": stakes, "time_pressure": pressure, "characters": [{"name": name, "role": role, "initial_message": message}],
        "evidence": [{"id": f"E{n+1}", "title": t, "text": text, "reliability": reliability, "tags": tags} for n, (t, text, reliability, tags) in enumerate(evidence)],
        "hidden_rubric": {"important_considerations": [stakes, "Separate established facts from assumptions; keep a reversible option."], "dangerous_assumptions": ["Urgency proves that the proposed action is correct."], "good_reasoning_signals": ["Propose an independent check tied to case evidence.", "Name a limited action, its cost and a condition for revising it."], "failure_signals": ["Unrelated text, outcome demands, or blind action without a case-grounded reason."]},
        "possible_archetypes": ["Investigate", "Contain", "Challenge", "Coordinate"],
        "special_card_conditions": [
            {"id": "special_rare", "rarity": "RARE", "name_seed": "Ghost Protocol", "required_reasoning": ["verification", "reversible", "tradeoff"], "ability_template": "INVESTIGATE_CROSSCHECK"},
            {"id": "special_epic", "rarity": "EPIC", "name_seed": "Zero-Hour Diplomat", "required_reasoning": ["coordination", "reversible", "continuity", "handoff"], "ability_template": "COORDINATE_DUAL_CHANNEL"},
        ],
    }).model_dump()


SEEDS = [
    seed("seed-vendor", "The update that couldn't wait", "cybersecurity",
         "A familiar vendor offers hotfix 4.8 before the dispatch peak. The message names your real support ticket, but the package signer has changed. Orders still flow, with rising retries. You own the next move: protect dispatch without treating uncertainty as proof of an attack.",
         "A delay slows deliveries; an unverified package could expose dispatch. Quarantining everything would stop live orders.", "The dispatch peak starts in 25 minutes.", "Leena Rao", "Operations lead", "I can arrange a directory callback or a manual dispatch bridge. Both cost time and staff. Tell me what to prioritise.", [
             ("Familiar thread", "The usual vendor address replies in your existing ticket. It says the signing partner is approved and asks you to use an attachment while the portal catches up.", "medium", ["vendor", "update", "dispatch"]),
             ("Unexpected signer", "The signature is valid for Harbour Utilities, not Morrow Systems. Last week's note mentioned an unnamed packaging partner. The portal still lists 4.7.", "high", ["signature", "signer", "portal"]),
             ("Room to manoeuvre", "Two staging laptops downloaded the package but have not run it. A trusted directory callback takes 15 minutes. Manual dispatch can bridge that delay at reduced speed.", "high", ["staging", "directory", "manual"])]),
    seed("seed-cooling", "The sensor that cried wolf", "engineering",
         "A render farm's temperature dashboard spikes just before a studio delivery. An operator wants to stop every render. A second sensor disagrees and the first was recalibrated this morning. Decide how to protect equipment without unnecessarily losing the delivery window.",
         "Ignoring real heat could damage equipment; a full stop discards hours of rendering.", "The delivery window closes in 40 minutes.", "Imani Chen", "Render operations lead", "I can pause one rack and get a second reading. The producer needs an updated delivery estimate.", [
             ("Conflicting readings", "Rack 4 reports 86 degrees from the recalibrated sensor; the independent intake probe reads 29. Neighbouring racks are stable.", "high", ["sensor", "rack", "temperature"]),
             ("Calibration change", "The calibration ticket changed the conversion coefficient this morning. No independent measurement was attached to the ticket.", "medium", ["calibration", "coefficient", "reading"]),
             ("A reversible pause", "Rack 4 can checkpoint and pause without losing progress. Stopping all racks loses the delivery slot. A technician can measure locally in eight minutes.", "high", ["checkpoint", "technician", "delivery"])]),
    seed("seed-launch", "One customer, two promises", "product",
         "Your small startup promised a reporting feature to an anchor customer. A new onboarding experiment looks promising, but would use the same engineer. The investor demo is tomorrow. Decide what to ship and how to test the assumption behind that decision.",
         "A broken promise risks trust; an untested launch could waste the only engineer's time.", "You have one engineering day before the demo.", "Mara Sol", "Product lead", "I can negotiate a smaller report or run the onboarding trial with support. Neither option gives us every promised feature.", [
             ("Small experiment", "Onboarding conversion rose from 3 of 20 to 7 of 20 users during a referral campaign. The cohorts came from different sources.", "medium", ["conversion", "cohort", "onboarding"]),
             ("Customer's actual need", "The customer needs an export before Friday's review. They asked for automated dashboards later; the sales note combines both requests.", "high", ["customer", "export", "dashboard"]),
             ("Capacity and fallback", "A manual export takes two hours of support time. A reversible onboarding pilot takes half a day and can be rolled back. One engineer is available.", "high", ["engineer", "manual", "pilot"])]),
    seed("seed-freight", "The missing scan", "logistics",
         "A display shipment for a trade show has no arrival scan at a regional depot. The carrier says it is moving; the venue wants a replacement sent now. You can reserve a van, reroute a partial replacement, or investigate first. Each minute reduces your options.",
         "A duplicate shipment wastes the budget; waiting too long leaves the booth empty.", "The last same-day van leaves in 35 minutes.", "Eli Park", "Dispatch coordinator", "I can hold a van for ten minutes. The depot supervisor has a separate inventory list and the venue can accept a partial display.", [
             ("Tracking gap", "The parcel was scanned out of the hub at 06:20 but never into the depot. Three other parcels on the same truck also lack arrival scans.", "medium", ["scan", "depot", "truck"]),
             ("Independent inventory", "The depot supervisor logged a display-sized crate on a paper manifest. Its serial number is partly obscured; a photo can be obtained in ten minutes.", "high", ["manifest", "serial", "photo"]),
             ("Partial options", "A local supplier can deliver a small display today. Reserving the van is refundable for ten minutes; dispatching the full replacement is not.", "high", ["van", "replacement", "supplier"])]),
    seed("seed-lab", "The breakthrough with a shadow", "scientific",
         "Your fictional materials lab sees a dramatic improvement in a coating test. A partner wants an announcement today. The treatment samples and controls were measured on different machines. Decide what the team can responsibly claim and what test should come next.",
         "Premature claims risk the partnership; an open-ended retest could lose a demonstration slot.", "The partner's demonstration script locks in two hours.", "Nadia Vale", "Lab coordinator", "We have time for a small blinded retest, not a full study. I can keep the partner's demo conditional if we agree what it can show.", [
             ("Uneven comparison", "All six treated samples were measured on machine B; controls used machine A. Machine B was serviced yesterday.", "high", ["sample", "machine", "control"]),
             ("Calibration record", "Machine B's service note says sensitivity may shift until recalibrated. No shared reference sample was run on both machines.", "high", ["calibration", "reference", "sensitivity"]),
             ("Small decisive test", "Two spare samples and one reference are available. They can be measured blind on both machines in 40 minutes. The partner can show a process demo without a performance claim.", "high", ["blind", "reference", "demo"])]),
    seed("seed-handoff", "Two teams, one release window", "coordination",
         "Design and infrastructure disagree about releasing a new workspace view. Design reports a successful pilot; infrastructure sees a spike in retry traffic. Each team measures a different group. Decide who should do what before the release window closes.",
         "A broad rollout could overload the service; cancelling wastes a committed customer preview.", "The release window closes in 30 minutes.", "Tomas Reed", "Release coordinator", "I can keep a small preview group while both leads compare records. We need one owner for the stop decision and a clear handoff.", [
             ("Successful pilot", "Design tested twenty internal users on cached workspaces. None opened a large imported workspace.", "medium", ["pilot", "workspace", "cached"]),
             ("Retry spike", "Infrastructure's retries came from three large imports during a maintenance job. The request traces do not yet identify the new view as the cause.", "high", ["retry", "trace", "import"]),
             ("Shared release control", "A feature flag can limit the preview and roll it back. Design owns customer communication; infrastructure owns tracing and the flag. Neither has been assigned the final stop call.", "high", ["flag", "owner", "handoff"])]),
]

# Hidden opportunities vary with the case; they never change the ability rules.
for case in SEEDS:
    if case["domain"] in ("engineering", "logistics"):
        case["special_card_conditions"][0].update(name_seed="Continuity Shield", required_reasoning=["containment", "reversible", "continuity"], ability_template="CONTAIN_STABILISE")
    elif case["domain"] in ("product", "scientific"):
        case["special_card_conditions"][0].update(name_seed="False Premise", required_reasoning=["challenge", "verification", "test"], ability_template="CHALLENGE_FALSE_PREMISE")
    Scenario.model_validate(case)
