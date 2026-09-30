"""Optional live protocol check: python tests/live_smoke.py [http://127.0.0.1:8000].

Creates two named test profiles on the target server. This is not a browser test.
"""
import asyncio
import json
import sys

import httpx
import websockets


async def main(base):
    async with httpx.AsyncClient(base_url=base, timeout=60) as client:
        async def post(path, data, token=""):
            r = await client.post("/api" + path, json=data, headers={"X-Player": token})
            r.raise_for_status()
            return r.json()

        profiles=[]
        decisions=["I would independently verify the vendor signature in a reversible sandbox before rollout because delay is safer than risking dispatch.", "I would assign the vendor liaison a signer check and keep manual dispatch running in a reversible pilot; then report back in a handoff before installation because the team needs a stop decision."]
        for name,decision in zip(("WireCheckA","WireCheckB"),decisions):
            profile=await post("/profile",{"nickname":name})
            attempt=await post("/forge/start",{"known_good":True},profile["token"])
            for clue in ("E1","E2","E3"):
                await post("/forge/inspect",{"attempt":attempt["id"],"evidence":clue},profile["token"])
            result=await post("/forge",{"attempt":attempt["id"],"response":decision},profile["token"])
            assert result["card"],result
            profile["card"]=result["card"]
            profiles.append(profile)
        a,b=profiles
        card=a["card"]
        assert card["ability_id"] in ("INVESTIGATE_VERIFY","INVESTIGATE_CROSSCHECK")
        code=(await post("/rooms",{"card_id":card["id"]},a["token"]))["code"]
        await post("/rooms/"+code+"/join",{"card_id":b["card"]["id"]},b["token"])

        async def until(ws, predicate):
            while True:
                data = json.loads(await asyncio.wait_for(ws.recv(), 12))
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
            plays_a = [(card["id"], "Evidence", "Compare the audit export and live session token because they establish activity but do not prove who used the account; verify the contractor."), ("s1", "Response", "The live session token matters because revoking it stops continuing access."), ("s2", "People", "Revoke the active session token because it permits continuing access without disrupting unaffected work."), ("s4", "Evidence", "Assign the audit analyst to preserve records before checking the export trail.")]
            plays_b = [(b["card"]["id"], "People", "Assign the access operator to revoke the token while the workspace owner contacts the contractor, then report the handoff before reopening access."), ("s3", "People", "I challenge the bad guy."), ("s2", "People", "Revoke the live session token because it allows further exports."), ("s4", "Response", "Ask the access operator to revoke the live token before more files leave the workspace.")]
            for n in range(1, 5):
                def move(p):
                    return json.dumps(dict(type="lock", match=1, round=n, card_id=p[0], front=p[1], response=p[2]))
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
                    assert all(restored["own_play"][k] == locked["own_play"][k] for k in ("card","front","response"))
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
            assert any(h["effects"][0]["context_match"] for h in sa["history"])
            assert not sa["history"][1]["effects"][1]["context_match"]
            assert 2 <= len(sa["result"]["insights"][0]) <= 3
            assert sum(sa["history"][1]["effects"][1]["delta"].values()) == 2
            for ws in (wa, wb):
                await ws.send(json.dumps(dict(type="rematch", match=1, round=4)))
            for ws in (wa, wb):
                reset = await until(ws, lambda s: s.get("match") == 2)
                assert reset["round"] == 1 and reset["used"] == []
            print("PASS: forge, four contextual effects, failed reasoning keeps base, hidden locks, four rounds, locked reconnect, insights, rematch.")
            print("Forge modes:", [p["card"]["assessment"]["mode"] for p in profiles], "Rarities:", [p["card"]["rarity"] for p in profiles], "Battle modes:", sorted({p["evaluation"]["mode"] for h in sa["history"] for p in h["plays"]}), "Final scores:", sa["scores"])
        finally:
            await wa.close()
            if wb:
                await wb.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"))
