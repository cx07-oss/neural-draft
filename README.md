# Neural-Draft

Neural-Draft is a competitive learning game where the decisions you make become the cards you play.

Instead of giving players a lesson and then testing them, Neural-Draft puts them in short situations where they have to decide what they would actually do. The player writes their own response, the system reviews their reasoning, and a card is created from the skill they demonstrated.

Players can then use those cards against another person in a four-round tactical game.

The aim is simple: **make the game enjoyable first, while useful skills are practised through play.**

---

## How it works

The main loop is:

**Case → Make a decision → Forge a card → Battle another player → Adapt → Try another case**

### 1. Enter a case

The player is given a short fictional situation, such as:

- a suspicious software update
- conflicting engineering sensor readings
- a delayed freight shipment
- a product launch problem
- conflicting scientific results

Each case contains incomplete information and competing priorities. There is usually no obvious multiple-choice answer.

The player can inspect evidence and then writes what they would do and why.

### 2. Forge a card

The response is reviewed for things such as:

- how the player used the available evidence
- whether they recognised important risks
- whether their response was proportionate
- how clearly they explained their decision

A successful response creates a card based on the type of reasoning shown.

There are four main approaches:

- **Investigate** — gather or verify information
- **Contain** — reduce immediate risk
- **Challenge** — question an assumption or claim
- **Coordinate** — organise people, timing or actions

The card also records why it was earned.

For example:

> **Forged because:** You independently verified the supplier before committing to the update.

A weak or unrelated response does not automatically create a card. The player receives a short hint and can try again.

### 3. Battle another player

Two players join the same room from separate browsers.

Each match lasts four rounds and has three fronts:

- **Evidence**
- **Response**
- **People**

Both players secretly choose a card and a front.

Some cards also ask the player to make a short tactical judgement before their special ability activates.

For example:

> Which clue makes this claim weakest, and why?

This means the player still has to think while using the card rather than simply pressing a button.

If the reasoning is weak, the card still contributes its normal influence, but its special ability may fail.

### 4. Review the match

At the end of the game, Neural-Draft shows:

- who won
- which rounds mattered most
- how the player changed their strategy
- which kinds of reasoning they used during the match

The result screen is not intended to give the player a school-style grade. It shows how they played and what kinds of decisions they practised.

---

## Why use AI?

Neural-Draft uses AI as a **reviewer**, not as a replacement for the player's thinking.

The player has to make the decision first.

AI can help with:

- creating new fictional cases
- interpreting written responses
- identifying the type of reasoning demonstrated
- writing personalised card names and descriptions
- checking short tactical responses during a battle

AI does **not** decide:

- how many points a card is worth
- what moves are legal
- the rules of the game
- who wins the match

Those rules are fixed in the Python server.

This is intentional. The player should be thinking for themselves rather than asking an AI system to make the decision for them.

---

## Card rarity

Cards can be:

- **Common**
- **Uncommon**
- **Rare**
- **Epic**

Rarity does not simply make a card stronger.

Instead, rarer cards represent more unusual or more complete approaches to a problem.

For example:

A straightforward response might say:

> I would verify the supplier before installing the update.

A more unusual response might combine:

- independent verification
- a reversible test
- maintaining business operations
- a clear rollback plan

That may unlock a rarer card with a more specialised ability.

Rare cards therefore offer different strategic options rather than simply giving the player more points.

---

## Running Neural-Draft

### Requirements

You need:

- Python
- Ollama
- Git

Neural-Draft uses `qwen3:8b` by default.

Check which Ollama models are installed:

```powershell
ollama list


