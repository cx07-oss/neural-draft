"""Single-process hackathon app. SQLite owns collections; this process owns rooms."""
import asyncio
from contextlib import asynccontextmanager, contextmanager
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from typing import Literal
import uuid

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from assessment import assess
from content import ACTIONS, CASE, EFFECTS, EVIDENCE, FRONTS, RUBRIC, deck, make_card, resolve_play, winner

ROOT = Path(__file__).parent
DB = os.getenv("NEURAL_DB", str(ROOT / "neural.sqlite3"))


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


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title="Neural-Draft", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
rooms = {}
forge_locks = {}


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
        attempt = conn.execute("SELECT * FROM attempts WHERE player=? AND card IS NULL ORDER BY rowid DESC LIMIT 1", (token,)).fetchone()
    return {"nickname": player["nickname"], "cards": cards,
            "attempt": {"id": attempt["id"], "evidence": json.loads(attempt["evidence"]), "questions": json.loads(attempt["questions"])} if attempt else None}


class Identity(BaseModel):
    nickname: str = Field(min_length=1, max_length=18)
    demo: bool = False


@app.get("/")
@app.get("/demo")
async def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/config")
async def config():
    return {"evidence": EVIDENCE, "actions": ACTIONS, "rubric": RUBRIC, "case": CASE,
            "effects": EFFECTS, "ai": bool(os.getenv("OPENAI_API_KEY")) and os.getenv("NEURAL_OFFLINE") != "1"}


@app.post("/api/profile")
async def new_profile(body: Identity):
    name = body.nickname.strip()
    if not name or not all(c.isalnum() or c in " -_" for c in name):
        raise HTTPException(400, "Use 1–18 letters, numbers, spaces, hyphens or underscores.")
    token = secrets.token_urlsafe(32)
    with db() as conn:
        conn.execute("INSERT INTO players VALUES (?,?)", (token, name))
        if body.demo:
            card = make_card(str(uuid.uuid4()), "Investigate", name, "Demo issue", True)
            card["assessment"] = {"mode": "demo", "notice": "Quick-demo card. No skill assessment was performed.", "feedback": "Match a relevant clue to its front to activate your Investigate bonus.", "scores": {}}
            card["provenance"] = {"action": "demo", "reason": "Quick-demo issue", "inspected": []}
            conn.execute("INSERT INTO cards VALUES (?,?,?)", (card["id"], token, json.dumps(card)))
    return {"token": token, **profile(token)}


@app.get("/api/me")
async def me(x_player: str = Header(default="")):
    return profile(x_player)


@app.post("/api/forge/start")
async def forge_start(x_player: str = Header(default="")):
    p = profile(x_player)
    if not p["attempt"]:
        with db() as conn:
            conn.execute("INSERT INTO attempts (id,player) VALUES (?,?)", (str(uuid.uuid4()), x_player))
    return profile(x_player)["attempt"]


def get_attempt(attempt_id, token):
    identify(token)
    with db() as conn:
        row = conn.execute("SELECT * FROM attempts WHERE id=? AND player=?", (attempt_id, token)).fetchone()
    if not row:
        raise HTTPException(404, "Forge session not found. Start a new simulation.")
    return dict(row)


class Inspect(BaseModel):
    attempt: str
    evidence: Literal["request", "signature", "scope"]


@app.post("/api/forge/inspect")
async def inspect(body: Inspect, x_player: str = Header(default="")):
    attempt = get_attempt(body.attempt, x_player)
    if attempt["card"]:
        raise HTTPException(409, "This card has already been forged.")
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
    q = body.question.lower()
    if any(w in q for w in ("vendor", "verify", "contact", "sign", "trust")):
        answer = "Use the number in our internal directory, not the update email. I can ask the vendor to confirm both the release and expected signer. A valid signature alone isn't enough."
    elif any(w in q for w in ("run", "affect", "production", "scope", "laptop", "isolate")):
        answer = "Neither test laptop has run the file. Production is healthy. We can pause deployment, retain the evidence, and keep serving people while we check."
    elif any(w in q for w in ("urgent", "time", "deadline", "wait")):
        answer = "The deadline came from the same unverified message. We have no independent sign of a queue failure. Urgency is a reason to check carefully, not skip verification."
    else:
        answer = "I can help with the vendor's identity, the deadline, or which systems are affected. We have two test laptops, no execution yet, and a trusted vendor contact in the directory."
    history = json.loads(attempt["questions"])[-4:] + [{"question": body.question, "answer": answer}]
    with db() as conn:
        conn.execute("UPDATE attempts SET questions=? WHERE id=?", (json.dumps(history), body.attempt))
    return {"answer": answer, "questions": history, "mode": "authored"}


class Forge(BaseModel):
    attempt: str
    action: Literal["verify", "isolate", "install"]
    reason: str = Field(min_length=8, max_length=400)


@app.post("/api/forge")
async def forge(body: Forge, x_player: str = Header(default="")):
    async with forge_locks.setdefault(body.attempt, asyncio.Lock()):
        attempt = get_attempt(body.attempt, x_player)
        if attempt["card"]:
            with db() as conn:
                return json.loads(conn.execute("SELECT payload FROM cards WHERE id=?", (attempt["card"],)).fetchone()[0])
        inspected = json.loads(attempt["evidence"])
        review = await assess(body.action, inspected, body.reason)
        total = sum(review["scores"].values())
        evolution = "Luminous" if total >= 5 else "Focused" if total >= 3 else "Emerging"
        card = make_card(str(uuid.uuid4()), review["archetype"], identify(x_player)["nickname"], evolution)
        card["assessment"] = review
        card["provenance"] = {"action": body.action, "reason": body.reason, "inspected": inspected, "questions": json.loads(attempt["questions"])}
        with db() as conn:
            conn.execute("INSERT INTO cards VALUES (?,?,?)", (card["id"], x_player, json.dumps(card)))
            conn.execute("UPDATE attempts SET card=? WHERE id=?", (card["id"], body.attempt))
        return card


class RoomRequest(BaseModel):
    card_id: str


def chosen_deck(token, card_id):
    card = next((c for c in profile(token)["cards"] if c["id"] == card_id), None)
    if not card:
        raise HTTPException(400, "Select one of your forged cards first.")
    return deck(card)


def reset_match(room):
    room.update(round=1, phase="choose", scores=[{f: 0 for f in FRONTS} for _ in range(2)],
                plays={}, used=[[], []], history=[], ready=set(), rematch=set(), result=None)


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
            "sockets": {}, "created": time.time(), "lock": asyncio.Lock(), "match": 1}
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
            "locked": seat in room["plays"], "opponent_locked": rival in room["plays"],
            "own_play": room["plays"].get(seat), "opponent_online": rival in room["sockets"],
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
    insights = []
    for seat in (0, 1):
        investigation = [h for h in room["history"] if h["plays"][seat]["card"]["archetype"] == "Investigate"]
        missed = any(sum(h["effects"][seat]["delta"].values()) == 2 for h in investigation)
        insights.append("A clue bonus was missed. Match the evidence to the decision: audit → Evidence, live session → Response, owner → People." if missed else
                        "You grounded your investigation in relevant clues. Keep that habit: a clue is useful when it supports the decision at hand." if investigation else
                        "You shaped the response tactically. Next time, try Investigate and connect a concrete clue to the front it supports.")
    room["result"] = {"winner": win, "reason": reason, "decisive": [h["round"] for h in decisive], "insights": insights}


def handle_move(room, seat, msg):
    if msg.get("match") != room["match"] or msg.get("round") != room["round"]:
        raise ValueError("That move belongs to an older round. Your board has been refreshed.")
    kind = msg.get("type")
    if kind == "lock":
        if room["phase"] != "choose" or seat in room["plays"]:
            raise ValueError("Your move is already locked, or this round has finished.")
        if 1-seat not in room["sockets"]:
            raise ValueError("Your rival is disconnected. Wait for them to return.")
        card = next((c for c in room["decks"][seat] if c["id"] == msg.get("card_id")), None)
        if not card or card["id"] in room["used"][seat]:
            raise ValueError("Choose an unused card from your hand.")
        if msg.get("front") not in FRONTS:
            raise ValueError("Choose a front.")
        if card["archetype"] == "Investigate" and msg.get("clue") not in [c["id"] for c in CASE["clues"]]:
            raise ValueError("Choose a clue to support your investigation.")
        room["plays"][seat] = {"card": card, "front": msg["front"], "clue": msg.get("clue") if card["archetype"] == "Investigate" else None}
        room["used"][seat].append(card["id"])
        if len(room["plays"]) == 2:
            plays = [room["plays"][p] for p in (0, 1)]
            effects = [resolve_play(plays[p], plays[1-p]) for p in (0, 1)]
            for p in (0, 1):
                for f in FRONTS:
                    room["scores"][p][f] += effects[p]["delta"][f]
            room["history"].append({"round": room["round"], "plays": plays, "effects": effects, "scores": json.loads(json.dumps(room["scores"]))})
            room["phase"] = "result" if room["round"] == 4 else "reveal"
            if room["phase"] == "result":
                complete(room)
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
