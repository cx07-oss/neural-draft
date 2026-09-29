"""Optional live protocol check: python tests/live_smoke.py [http://127.0.0.1:8000].

Creates two named test profiles on the target server. This is not a browser test.
"""
import asyncio
import json
import sys

import httpx
import websockets


async def main(base):
    async with httpx.AsyncClient(base_url=base) as client:
        async def post(path, data, token=""):
            r = await client.post("/api" + path, json=data, headers={"X-Player": token})
            r.raise_for_status()
            return r.json()

        a = await post("/profile", {"nickname": "WireCheckA"})
        b = await post("/profile", {"nickname": "WireCheckB", "demo": True})
        attempt = await post("/forge/start", {}, a["token"])
        for clue in ("request", "signature", "scope"):
            await post("/forge/inspect", {"attempt": attempt["id"], "evidence": clue}, a["token"])
        card = await post("/forge", {"attempt": attempt["id"], "action": "verify", "focus": "claim", "reason": "Test the approval claim before introducing the new signer."}, a["token"])
        assert card["archetype"] == "Challenge" and card["pattern"] == "claim"
        code = (await post("/rooms", {"card_id": card["id"]}, a["token"]))["code"]
        await post("/rooms/" + code + "/join", {"card_id": b["cards"][0]["id"]}, b["token"])

        async def until(ws, predicate):
            while True:
                data = json.loads(await asyncio.wait_for(ws.recv(), 5))
                assert data["type"] != "error", data
                if predicate(data):
                    return data

        url = base.replace("http", "ws", 1) + "/ws/" + code
        wa = await websockets.connect(url)
        wb = None
        try:
            await wa.send(json.dumps({"token": a["token"]}))
            await until(wa, lambda s: s["type"] == "state")
            wb = await websockets.connect(url)
            await wb.send(json.dumps({"token": b["token"]}))
            await until(wa, lambda s: s.get("opponent_online"))
            await until(wb, lambda s: s["type"] == "state")
            plays_a = [(card["id"], "Evidence", "breach"), ("s1", "Response", "token"), ("s2", "People", "session"), ("s4", "Evidence", "analyst")]
            plays_b = [(b["cards"][0]["id"], "Evidence", "audit"), ("s3", "People", "record"), ("s2", "People", "session"), ("s4", "Response", "operator")]
            for n in range(1, 5):
                def move(p):
                    return json.dumps(dict(type="lock", match=1, round=n, card_id=p[0], front=p[1], choice=p[2]))
                await wa.send(move(plays_a[n-1]))
                locked = await until(wa, lambda s: s.get("locked") and s.get("round") == n)
                hidden = await until(wb, lambda s: s.get("opponent_locked") and s.get("round") == n)
                assert len(hidden["history"]) == n-1
                if n == 2:
                    await wa.close()
                    await until(wb, lambda s: not s.get("opponent_online"))
                    wa = await websockets.connect(url)
                    await wa.send(json.dumps({"token": a["token"]}))
                    restored = await until(wa, lambda s: s.get("locked"))
                    assert restored["own_play"] == locked["own_play"]
                    await until(wb, lambda s: s.get("opponent_online"))
                await wb.send(move(plays_b[n-1]))
                sa = await until(wa, lambda s: s.get("phase") in ("reveal", "result") and len(s.get("history", [])) == n)
                sb = await until(wb, lambda s: s.get("phase") in ("reveal", "result") and len(s.get("history", [])) == n)
                assert sa["scores"] == sb["scores"]
                if n < 4:
                    for ws in (wa, wb):
                        await ws.send(json.dumps(dict(type="ready", match=1, round=n)))
                    for ws in (wa, wb):
                        await until(ws, lambda s: s.get("round") == n+1)
            assert all(h["effects"][0]["context_match"] for h in sa["history"])
            assert not sa["history"][1]["effects"][1]["context_match"]
            assert len(sa["result"]["insights"][0]) == 3
            for ws in (wa, wb):
                await ws.send(json.dumps(dict(type="rematch", match=1, round=4)))
            for ws in (wa, wb):
                reset = await until(ws, lambda s: s.get("match") == 2)
                assert reset["round"] == 1 and reset["used"] == []
            print("PASS: forge, four contextual effects, wrong-choice denial, hidden locks, four rounds, locked reconnect, insights, rematch.")
            print("Forge mode:", card["assessment"]["mode"], "Final scores:", sa["scores"])
        finally:
            await wa.close()
            if wb:
                await wb.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"))
