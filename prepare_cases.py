"""Prepare validated AI cases before judging; never needed to play offline."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
import secrets
import time
import uuid

import app
from reasoning import generate_scenario
from scenarios import DOMAINS


async def prepare(domain, count, timeout):
    os.environ["SCENARIO_AI_TIMEOUT"] = str(timeout)
    app.init_db()
    saved = 0
    for _ in range(count):
        selected_domain = domain or secrets.choice(DOMAINS)
        start = time.monotonic()
        case = await generate_scenario(selected_domain)
        if case:
            case["scenario_id"] = "gen-" + uuid.uuid4().hex
            with app.db() as conn:
                conn.execute("INSERT INTO scenarios VALUES (?,?,?,?,?,1)", (case["scenario_id"], json.dumps(case), case["domain"], datetime.now(timezone.utc).isoformat(), "AI generated · cached"))
            saved += 1
            print(f"Cached: {case['title']} ({time.monotonic()-start:.1f}s)", flush=True)
        else:
            print(f"No valid {selected_domain} case after {time.monotonic()-start:.1f}s; existing validated cache remains available.", flush=True)
    return saved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", choices=DOMAINS, help="Optional; omitted runs across the controlled domains")
    parser.add_argument("--count", type=int, choices=range(1,13), default=10)
    parser.add_argument("--timeout", type=int, choices=range(1,601), default=300)
    args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(prepare(args.domain,args.count,args.timeout)) else 1)
