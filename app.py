"""Single-process hackathon app. SQLite owns collections; this process owns rooms."""
import asyncio
from contextlib import asynccontextmanager, contextmanager
import json
import logging
import os
from pathlib import Path
import secrets
from datetime import datetime, timezone
import sqlite3
import time
from typing import Literal
import uuid

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict

from abilities import ABILITIES, decorate, resolve_pair
from reasoning import ai_available, assess_written, assess_battle, award, generate_scenario
from providers import provider_status, warm_gameplay_model
from scenarios import DOMAINS, SEEDS, Scenario, public_case
from content import ACTIONS, CASE, CHOICES, EFFECTS, EVIDENCE, FRONTS, PATTERNS, RESPONSES, RUBRIC, deck, forged_record, make_card, resolve_play, strategy_observations, winner

ROOT = Path(__file__).parent
DB = os.getenv("NEURAL_DB", str(ROOT / "neural.sqlite3"))
LOG = logging.getLogger("uvicorn.error")


@contextmanager
def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS players (token TEXT PRIMARY KEY, nickname TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, player TEXT NOT NULL, evidence TEXT NOT NULL DEFAULT '[]', questions TEXT NOT NULL DEFAULT '[]', card TEXT);
        CREATE TABLE IF NOT EXISTS cards (id TEXT PRIMARY KEY, player TEXT NOT NULL, payload TEXT NOT NULL);
        """)

        # Additive schema evolution; preserve existing cards and private profiles.
        columns = {r[1] for r in conn.execute("PRAGMA table_info(attempts)")}
        for name, definition in {"scenario_id": "TEXT", "response": "TEXT NOT NULL DEFAULT ''", "assessment_json": "TEXT", "retry_count": "INTEGER NOT NULL DEFAULT 0", "status": "TEXT NOT NULL DEFAULT 'active'"}.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE attempts ADD COLUMN {name} {definition}")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS scenarios (id TEXT PRIMARY KEY, generated_json TEXT NOT NULL, domain TEXT NOT NULL, created_at TEXT NOT NULL, source TEXT NOT NULL, validated INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS forge_submissions (attempt TEXT NOT NULL, submission INTEGER NOT NULL, response TEXT NOT NULL, assessment_json TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(attempt,submission));
        CREATE TABLE IF NOT EXISTS battle_reasoning (room_id TEXT NOT NULL, match_no INTEGER NOT NULL, round_no INTEGER NOT NULL, player TEXT NOT NULL, card_id TEXT NOT NULL, prompt TEXT NOT NULL, response TEXT NOT NULL, result TEXT NOT NULL, ability_id TEXT NOT NULL, PRIMARY KEY(room_id,match_no,round_no,player));
        """)
        for scenario in SEEDS:
            conn.execute("INSERT OR IGNORE INTO scenarios VALUES (?,?,?,?,?,1)", (scenario["scenario_id"], json.dumps(scenario), scenario["domain"], datetime.now(timezone.utc).isoformat(), "authored cache"))
        for row in conn.execute("SELECT id,evidence FROM attempts WHERE scenario_id IS NULL").fetchall():
            seen = [{"request":"E1","signature":"E2","scope":"E3"}.get(e,e) for e in json.loads(row["evidence"])]
            conn.execute("UPDATE attempts SET scenario_id='seed-vendor', evidence=? WHERE id=?", (json.dumps(seen),row["id"]))


def load_case(case_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM scenarios WHERE id=? AND validated=1", (case_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Case unavailable. Open a new case.")
    return Scenario.model_validate_json(row["generated_json"]).model_dump(), row["source"]


def attempt_view(attempt):
    case, source = load_case(attempt["scenario_id"])
    review = json.loads(attempt["assessment_json"]) if attempt["assessment_json"] else None
    return {"id": attempt["id"], "evidence": json.loads(attempt["evidence"]), "questions": json.loads(attempt["questions"]), "scenario": public_case(case, source), "response": attempt["response"], "assessment": review, "retry_count": attempt["retry_count"], "can_retry": attempt["retry_count"] < 2, "status": attempt["status"]}


@asynccontextmanager
async def lifespan(app):
    init_db()
    warm_task = asyncio.create_task(warm_gameplay_model())
    yield
    if not warm_task.done():
        warm_task.cancel()
    await asyncio.gather(warm_task, return_exceptions=True)
    tasks = list(room_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="Neural-Draft", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
rooms = {}
forge_locks = {}
room_tasks = set()


def identify(token):
    with db() as conn:
        row = conn.execute("SELECT * FROM players WHERE token=?", (token,)).fetchone()
    if not row:
        raise HTTPException(401, "This local profile could not be found. Start with a nickname again.")
    return dict(row)


def profile(token):
    player = identify(token)
    with db() as conn:
        cards = [json.loads(r[0]) for r in conn.execute("SELECT payload FROM cards WHERE player=? ORDER BY rowid DESC", (token,))]
        attempt = conn.execute("SELECT * FROM attempts WHERE player=? AND card IS NULL AND status='active' ORDER BY rowid DESC LIMIT 1", (token,)).fetchone()
    cards = [decorate(card) for card in cards]
    return {"nickname": player["nickname"], "cards": cards,
            "attempt": attempt_view(attempt) if attempt else None}


class Identity(BaseModel):
    nickname: str = Field(min_length=1, max_length=18)
    demo: bool = False


@app.get("/")
@app.get("/demo")
async def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/config")
async def config():
    status = await provider_status()
    public_case = {**CASE, "clues": [{k: v for k, v in c.items() if k != "front"} for c in CASE["clues"]]}
    return {"evidence": EVIDENCE, "actions": ACTIONS, "rubric": RUBRIC, "case": public_case,
            "choices": CHOICES, "responses": RESPONSES, "patterns": [
                {"id": "investigate", "kind": "Investigate", "label": "Independent verification", "available": True},
                {"id": "contain", "kind": "Contain", "label": "Bounded exposure", "available": True},
                {"id": "challenge", "kind": "Challenge", "label": "Testing an assumption", "available": True},
                {"id": "coordinate", "kind": "Coordinate", "label": "Shared action", "available": True},
                {"id": "special_rare", "kind": "Rare", "label": "Classified signature I", "available": True},
                {"id": "special_epic", "kind": "Epic", "label": "Classified signature II", "available": True}],
            "effects": EFFECTS, "abilities": ABILITIES, "domains": DOMAINS, "ai": status["available"], "ai_status": status}


@app.post("/api/profile")
async def new_profile(body: Identity):
    name = body.nickname.strip()
    if not name or not all(c.isalnum() or c in " -_" for c in name):
        raise HTTPException(400, "Use 1–18 letters, numbers, spaces, hyphens or underscores.")
    token = secrets.token_urlsafe(32)
    with db() as conn:
        conn.execute("INSERT INTO players VALUES (?,?)", (token, name))
        if body.demo:
            card = decorate(make_card(str(uuid.uuid4()), "Investigate", name, "Demo issue", True))
            card["assessment"] = {"mode": "demo", "notice": "Quick-demo card. No skill assessment was performed.", "feedback": "Write which clue supports your front and why to activate Verify.", "scores": {}}
            card["provenance"] = {"action": "demo", "reason": "Quick-demo issue", "inspected": []}
            conn.execute("INSERT INTO cards VALUES (?,?,?)", (card["id"], token, json.dumps(card)))
    return {"token": token, **profile(token)}


@app.get("/api/me")
async def me(x_player: str = Header(default="")):
    return profile(x_player)


class StartCase(BaseModel):
    domain: Literal["random", "cybersecurity", "engineering", "product", "logistics", "scientific", "coordination"] = "random"
    new: bool = False
    generate: bool = False
    known_good: bool = False


@app.post("/api/forge/start")
async def forge_start(body: StartCase = StartCase(), x_player: str = Header(default="")):
    async with forge_locks.setdefault("start:"+x_player, asyncio.Lock()):
        p = profile(x_player)
        if p["attempt"] and not body.new:
            return p["attempt"]
        domain = secrets.choice(DOMAINS) if body.domain == "random" else body.domain
        generated = await generate_scenario(domain) if body.generate and not body.known_good else None
        with db() as conn:
            if generated:
                generated["scenario_id"] = "gen-" + uuid.uuid4().hex
                conn.execute("INSERT INTO scenarios VALUES (?,?,?,?,?,1)", (generated["scenario_id"], json.dumps(generated), domain, datetime.now(timezone.utc).isoformat(), "AI generated · cached"))
                case_id = generated["scenario_id"]
            elif body.known_good:
                case_id = "seed-vendor"
            else:
                rows = conn.execute("SELECT id FROM scenarios WHERE validated=1" + (" AND domain=?" if body.domain != "random" else ""), (domain,) if body.domain != "random" else ()).fetchall()
                previous = p["attempt"]["scenario"]["scenario_id"] if p["attempt"] else None
                choices = [r["id"] for r in rows if r["id"] != previous] or [r["id"] for r in rows]
                case_id = secrets.choice(choices)
                LOG.info("[AI] Scenario loaded from cache - %s", case_id)
            conn.execute("UPDATE attempts SET status='abandoned' WHERE player=? AND card IS NULL AND status='active'", (x_player,))
            attempt_id = str(uuid.uuid4())
            conn.execute("INSERT INTO attempts (id,player,scenario_id) VALUES (?,?,?)", (attempt_id,x_player,case_id))
        result = attempt_view(get_attempt(attempt_id,x_player))
        if body.generate and not generated:
            result["message"] = "Live case generation unavailable — a cached case is ready."
        return result


def get_attempt(attempt_id, token):
    identify(token)
    with db() as conn:
        row = conn.execute("SELECT * FROM attempts WHERE id=? AND player=?", (attempt_id, token)).fetchone()
    if not row:
        raise HTTPException(404, "Forge session not found. Start a new simulation.")
    return dict(row)


class Inspect(BaseModel):
    attempt: str
    evidence: str = Field(max_length=10)


@app.post("/api/forge/inspect")
async def inspect(body: Inspect, x_player: str = Header(default="")):
    attempt = get_attempt(body.attempt, x_player)
    if attempt["card"]:
        raise HTTPException(409, "This card has already been forged.")
    case, _ = load_case(attempt["scenario_id"])
    if body.evidence not in {e["id"] for e in case["evidence"]}:
        raise HTTPException(400, "Evidence is not part of this case.")
    seen = sorted(set(json.loads(attempt["evidence"])) | {body.evidence})
    with db() as conn:
        conn.execute("UPDATE attempts SET evidence=? WHERE id=?", (json.dumps(seen), body.attempt))
    return {"evidence": seen}


class Ask(BaseModel):
    attempt: str
    question: str = Field(min_length=2, max_length=240)


@app.post("/api/forge/ask")
async def ask(body: Ask, x_player: str = Header(default="")):
    attempt = get_attempt(body.attempt, x_player)
    if attempt["card"]:
        raise HTTPException(409, "This card has already been forged.")
    case, _ = load_case(attempt["scenario_id"])
    q = body.question.lower()
    evidence = max(case["evidence"], key=lambda e: sum(t.lower() in q for t in e["tags"]))
    answer = case["characters"][0]["initial_message"] + " From our records: " + evidence["text"]
    history = json.loads(attempt["questions"])[-4:] + [{"question": body.question, "answer": answer}]
    with db() as conn:
        conn.execute("UPDATE attempts SET questions=? WHERE id=?", (json.dumps(history), body.attempt))
    return {"answer": answer, "questions": history, "mode": "authored"}


class Forge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt: str
    response: str = Field(default="", max_length=1200)


@app.post("/api/forge")
async def forge(body: Forge, x_player: str = Header(default="")):
    async with forge_locks.setdefault(body.attempt, asyncio.Lock()):
        attempt = get_attempt(body.attempt, x_player)
        if attempt["card"]:
            card = next(c for c in profile(x_player)["cards"] if c["id"] == attempt["card"])
            return {"card": card, "assessment": card["assessment"], "can_retry": False}
        if attempt["status"] != "active":
            raise HTTPException(409, "This forge has closed. Open a new case.")
        if attempt["assessment_json"] and attempt["response"] == body.response.strip():
            return {"card": None, "assessment": json.loads(attempt["assessment_json"]), "can_retry": attempt["retry_count"] < 2, "retry_count": attempt["retry_count"]}
        if attempt["retry_count"] >= 2:
            raise HTTPException(409, "Both attempts are used. A new case is waiting.")
        case, source = load_case(attempt["scenario_id"])
        inspected = json.loads(attempt["evidence"])
        text = body.response.strip()
        review = await assess_written(text, case, inspected)
        reward = award(review, case)
        now = datetime.now(timezone.utc).isoformat()
        card = None
        if reward:
            card = make_card(str(uuid.uuid4()), review["archetype"], identify(x_player)["nickname"], "Luminous" if reward["rarity"] in ("RARE","EPIC") else "Focused" if reward["rarity"] == "UNCOMMON" else "Emerging")
            card.update(reward)
            card.update(name=reward["name"], skill=review["demonstrated_skill"], flavour=review["flavour"], forged_because=review["forged_because"], assessment=review, domain=case["domain"], source_scenario=case["title"], forged_at=now, pattern=review["special_unlock"] or review["archetype"].lower())
            card["provenance"] = {"version": 3, "scenario_id": case["scenario_id"], "source": source, "reason": text, "inspected": inspected, "evidence_snapshot": [e for e in case["evidence"] if e["id"] in inspected], "questions": json.loads(attempt["questions"]), "signals": review["signals"]}
            card = decorate(card)
        tries = attempt["retry_count"] + 1
        with db() as conn:
            conn.execute("INSERT INTO forge_submissions VALUES (?,?,?,?,?)", (body.attempt, tries, text, json.dumps(review), now))
            conn.execute("UPDATE attempts SET response=?,assessment_json=?,retry_count=?,card=?,status=? WHERE id=?", (text,json.dumps(review),tries,card["id"] if card else None,"minted" if card else "active",body.attempt))
            if card:
                conn.execute("INSERT INTO cards VALUES (?,?,?)", (card["id"],x_player,json.dumps(card)))
        return {"card": card, "assessment": review, "can_retry": not card and tries < 2, "retry_count": tries}


class RoomRequest(BaseModel):
    card_id: str


def chosen_deck(token, card_id):
    card = next((c for c in profile(token)["cards"] if c["id"] == card_id), None)
    if not card:
        raise HTTPException(400, "Select one of your forged cards first.")
    return [decorate(c) for c in deck(card)]


def reset_match(room):
    room.update(round=1, phase="choose", scores=[{f: 0 for f in FRONTS} for _ in range(2)],
                plays={}, pending={}, used=[[], []], history=[], ready=set(), rematch=set(), result=None)


@app.post("/api/rooms")
async def create_room(body: RoomRequest, x_player: str = Header(default="")):
    cards = chosen_deck(x_player, body.card_id)
    # Stale rooms are ephemeral; collections remain in SQLite.
    for code, room in list(rooms.items()):
        if time.time() - room["created"] > 21600 and not room["sockets"]:
            rooms.pop(code, None)
    code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(5))
    while code in rooms:
        code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(5))
    room = {"code": code, "players": [x_player], "names": [identify(x_player)["nickname"]], "decks": [cards],
            "sockets": {}, "created": time.time(), "lock": asyncio.Lock(), "match": 1, "id": uuid.uuid4().hex}
    reset_match(room)
    room["phase"] = "lobby"
    rooms[code] = room
    return {"code": code}


@app.post("/api/rooms/{code}/join")
async def join_room(code: str, body: RoomRequest, x_player: str = Header(default="")):
    cards = chosen_deck(x_player, body.card_id)
    room = rooms.get(code.upper())
    if not room:
        raise HTTPException(404, "Room not found. Check the code, or create a new room after a server restart.")
    async with room["lock"]:
        if x_player not in room["players"]:
            if len(room["players"]) == 2:
                raise HTTPException(409, "This room already has two players.")
            room["players"].append(x_player)
            room["names"].append(identify(x_player)["nickname"])
            room["decks"].append(cards)
            room["phase"] = "choose"
        await broadcast(room)
    return {"code": room["code"]}


def snapshot(room, seat):
    rival = 1 - seat
    return {"type": "state", "code": room["code"], "seat": seat, "names": room["names"],
            "round": room["round"], "match": room["match"], "phase": room["phase"],
            "scores": room["scores"], "deck": room["decks"][seat], "used": room["used"][seat],
            "locked": seat in room["plays"] or seat in room["pending"], "opponent_locked": rival in room["plays"] or rival in room["pending"], "evaluating": seat in room["pending"],
            "own_play": room["plays"].get(seat) or room["pending"].get(seat), "opponent_online": rival in room["sockets"],
            "history": room["history"], "ready": seat in room["ready"], "opponent_ready": rival in room["ready"],
            "rematch": seat in room["rematch"], "opponent_rematch": rival in room["rematch"], "result": room["result"]}


async def broadcast(room):
    for seat, ws in list(room["sockets"].items()):
        try:
            await ws.send_json(snapshot(room, seat))
        except (RuntimeError, WebSocketDisconnect, OSError):
            if room["sockets"].get(seat) is ws:
                room["sockets"].pop(seat, None)


def complete(room):
    win, reason = winner(room["scores"])
    # Most consequential rounds by absolute influence swing; all remain in log.
    decisive = sorted(room["history"], key=lambda h: abs(sum(h["effects"][0]["delta"].values()) - sum(h["effects"][1]["delta"].values())), reverse=True)[:2]
    insights = [strategy_observations(room["history"], seat) for seat in (0, 1)]
    room["result"] = {"winner": win, "reason": reason, "decisive": [h["round"] for h in decisive], "insights": insights}


def handle_move(room, seat, msg):
    if msg.get("match") != room["match"] or msg.get("round") != room["round"]:
        raise ValueError("That move belongs to an older round. Your board has been refreshed.")
    kind = msg.get("type")
    if kind == "lock":
        raise ValueError("Use the sealed written-move evaluator.")
    elif kind == "ready":
        if room["phase"] != "reveal":
            raise ValueError("Wait for the round to reveal.")
        room["ready"].add(seat)
        if len(room["ready"]) == 2:
            room["round"] += 1
            room.update(phase="choose", plays={}, ready=set())
    elif kind == "rematch":
        if room["phase"] != "result":
            raise ValueError("Finish the match first.")
        room["rematch"].add(seat)
        if len(room["rematch"]) == 2:
            room["match"] += 1
            reset_match(room)
    else:
        raise ValueError("Unknown move.")


def validate_lock(room, seat, msg):
    if msg.get("match") != room["match"] or msg.get("round") != room["round"]:
        raise ValueError("That move belongs to an older round.")
    if room["phase"] != "choose" or seat in room["plays"] or seat in room["pending"]:
        raise ValueError("Your move is already sealed.")
    if 1-seat not in room["sockets"]:
        raise ValueError("Your rival is disconnected. Wait for them to return.")
    card = next((c for c in room["decks"][seat] if c["id"] == msg.get("card_id")),None)
    if not card or card["id"] in room["used"][seat]:
        raise ValueError("Choose an unused card from your hand.")
    if msg.get("front") not in FRONTS:
        raise ValueError("Choose a front.")
    text = msg.get("response", "")
    if not isinstance(text,str) or len(text) > 400:
        raise ValueError("Keep your tactical decision to 400 characters.")
    return {"card": card, "front": msg["front"], "response": text.strip()}


async def evaluate_sealed(room, seat, play, match, round_no):
    evaluation = await assess_battle(play["response"],play["card"]["ability_id"],play["front"])
    async with room["lock"]:
        if room["match"] != match or room["round"] != round_no or room["pending"].get(seat) is not play:
            return
        with db() as conn:
            conn.execute("INSERT OR REPLACE INTO battle_reasoning VALUES (?,?,?,?,?,?,?,?,?)", (room["id"],match,round_no,room["players"][seat],play["card"]["id"],play["card"]["prompt"],play["response"],json.dumps(evaluation),play["card"]["ability_id"]))
        room["pending"].pop(seat)
        room["plays"][seat] = {**play,"evaluation": evaluation}
        if len(room["plays"]) == 2:
            plays = [room["plays"][p] for p in (0,1)]
            effects = resolve_pair(plays,room["scores"])
            for p in (0,1):
                for f in FRONTS:
                    room["scores"][p][f] += effects[p]["delta"][f]
            room["history"].append({"round":round_no,"plays":plays,"effects":effects,"scores":json.loads(json.dumps(room["scores"]))})
            room["phase"] = "result" if round_no == 4 else "reveal"
            if room["phase"] == "result":
                complete(room)
        await broadcast(room)


def track_task(task):
    room_tasks.add(task)
    task.add_done_callback(room_tasks.discard)


@app.websocket("/ws/{code}")
async def websocket(ws: WebSocket, code: str):
    await ws.accept()
    room = rooms.get(code.upper())
    seat = None
    try:
        auth = await asyncio.wait_for(ws.receive_json(), timeout=8)
        token = auth.get("token", "") if isinstance(auth, dict) else ""
        if not room or token not in room["players"]:
            await ws.send_json({"type": "error", "fatal": True, "message": "Room unavailable. Return to your collection and create or join a room."})
            await ws.close(code=1008)
            return
        seat = room["players"].index(token)
        async with room["lock"]:
            old = room["sockets"].get(seat)
            room["sockets"][seat] = ws
            if old and old is not ws:
                await old.close(code=4001, reason="Opened in another tab")
            await broadcast(room)
        while True:
            msg = await ws.receive_json()
            if not isinstance(msg, dict):
                await ws.send_json({"type": "error", "message": "Invalid message."})
                continue
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
                continue
            async with room["lock"]:
                if room["sockets"].get(seat) is not ws:
                    break
                try:
                    if msg.get("type") == "lock":
                        play = validate_lock(room,seat,msg)
                        room["pending"][seat] = play
                        room["used"][seat].append(play["card"]["id"])
                        track_task(asyncio.create_task(evaluate_sealed(room,seat,play,room["match"],room["round"])))
                    else:
                        handle_move(room, seat, msg)
                except ValueError as exc:
                    await ws.send_json({"type": "error", "message": str(exc)})
                await broadcast(room)
    except (WebSocketDisconnect, asyncio.TimeoutError, json.JSONDecodeError, RuntimeError):
        pass
    finally:
        if room and seat is not None:
            async with room["lock"]:
                if room["sockets"].get(seat) is ws:
                    room["sockets"].pop(seat, None)
                    await broadcast(room)
