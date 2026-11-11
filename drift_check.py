"""
Drift detection — reads query_log.jsonl and flags degradation.

Checks:
  1. Critic fail rate  — if >30% of last 20 queries failed critic
  2. Cost spike        — if avg cost is 2x the baseline
  3. Slow responses    — if avg response time >30s
  4. Tool miss rate    — if too many queries returned no tools

Run standalone: python drift_check.py
Called by:      daily_alert.py
"""

import json
import os
from datetime import datetime, timedelta

QUERY_LOG        = "query_log.jsonl"
WINDOW           = 20     # last N queries to analyze
CRITIC_FAIL_THRESHOLD  = 0.30   # alert if >30% fail critic
COST_SPIKE_MULTIPLIER  = 2.0    # alert if cost is 2x baseline
SLOW_RESPONSE_SECS     = 30.0   # alert if avg response >30s
TOOL_MISS_THRESHOLD    = 0.40   # alert if >40% queries hit no tools


def load_recent_queries(n: int = WINDOW) -> list:
    if not os.path.exists(QUERY_LOG):
        return []
    entries = []
    with open(QUERY_LOG) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
    return entries[-n:]


def run_drift_check() -> dict:
    entries = load_recent_queries(WINDOW)
    all_entries = load_recent_queries(10000)

    result = {
        "total_queries":    len(all_entries),
        "window":           len(entries),
        "alerts":           [],
        "metrics":          {},
        "status":           "OK",
    }

    if len(entries) < 5:
        result["alerts"].append("Not enough data yet — need at least 5 queries to detect drift.")
        return result

    # ── Metric 1: Critic fail rate ────────────────────────────────────────────
    fail_count  = sum(1 for e in entries if not e.get("critic_passed", True))
    fail_rate   = fail_count / len(entries)
    result["metrics"]["critic_fail_rate"] = round(fail_rate, 2)

    if fail_rate > CRITIC_FAIL_THRESHOLD:
        result["alerts"].append(
            f"CRITIC FAIL RATE: {fail_rate*100:.0f}% of last {len(entries)} queries failed quality check (threshold: {CRITIC_FAIL_THRESHOLD*100:.0f}%)"
        )

    # ── Metric 2: Cost spike ──────────────────────────────────────────────────
    costs       = [e.get("cost_usd", 0) for e in entries if e.get("cost_usd", 0) > 0]
    avg_cost    = sum(costs) / len(costs) if costs else 0

    if len(all_entries) > WINDOW:
        baseline_entries = all_entries[:-WINDOW]
        baseline_costs   = [e.get("cost_usd", 0) for e in baseline_entries if e.get("cost_usd", 0) > 0]
        baseline_avg     = sum(baseline_costs) / len(baseline_costs) if baseline_costs else 0
        if baseline_avg > 0 and avg_cost > baseline_avg * COST_SPIKE_MULTIPLIER:
            result["alerts"].append(
                f"COST SPIKE: Avg cost ${avg_cost:.4f} is {avg_cost/baseline_avg:.1f}x baseline (${baseline_avg:.4f})"
            )

    result["metrics"]["avg_cost_usd"]  = round(avg_cost, 6)
    result["metrics"]["total_cost_usd"] = round(sum(e.get("cost_usd", 0) for e in all_entries), 4)

    # ── Metric 3: Slow responses ──────────────────────────────────────────────
    times    = [e.get("elapsed_s", 0) for e in entries if e.get("elapsed_s", 0) > 0]
    avg_time = sum(times) / len(times) if times else 0
    result["metrics"]["avg_response_s"] = round(avg_time, 1)

    if avg_time > SLOW_RESPONSE_SECS:
        result["alerts"].append(
            f"SLOW RESPONSES: Avg response time {avg_time:.1f}s exceeds {SLOW_RESPONSE_SECS}s threshold"
        )

    # ── Metric 4: Tool miss rate ──────────────────────────────────────────────
    no_tools    = sum(1 for e in entries if not e.get("tools"))
    miss_rate   = no_tools / len(entries)
    result["metrics"]["tool_miss_rate"] = round(miss_rate, 2)

    if miss_rate > TOOL_MISS_THRESHOLD:
        result["alerts"].append(
            f"TOOL MISS RATE: {miss_rate*100:.0f}% of queries called no tools (threshold: {TOOL_MISS_THRESHOLD*100:.0f}%)"
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    result["status"] = "DRIFT DETECTED" if result["alerts"] else "OK"

    # ── Most common tools ─────────────────────────────────────────────────────
    from collections import Counter
    tool_counts = Counter()
    for e in all_entries:
        for t in e.get("tools", []):
            tool_counts[t.split("{")[0]] += 1
    result["metrics"]["top_tools"] = dict(tool_counts.most_common(5))

    return result


def format_drift_report(result: dict) -> str:
    lines = [
        f"*Drift Report — Last {result['window']} queries (Total: {result['total_queries']})*",
        f"Status: {'⚠️ ' + result['status'] if result['status'] != 'OK' else '✅ OK'}",
        "",
        f"Critic fail rate : {result['metrics'].get('critic_fail_rate', 0)*100:.0f}%",
        f"Avg cost/query   : ${result['metrics'].get('avg_cost_usd', 0):.4f}",
        f"Total cost       : ${result['metrics'].get('total_cost_usd', 0):.4f}",
        f"Avg response time: {result['metrics'].get('avg_response_s', 0):.1f}s",
        f"Tool miss rate   : {result['metrics'].get('tool_miss_rate', 0)*100:.0f}%",
    ]

    if result["metrics"].get("top_tools"):
        lines.append("")
        lines.append("Top tools used:")
        for tool, count in result["metrics"]["top_tools"].items():
            lines.append(f"  {tool}: {count}x")

    if result["alerts"]:
        lines.append("")
        lines.append("ALERTS:")
        for alert in result["alerts"]:
            lines.append(f"  ⚠️  {alert}")

    return "\n".join(lines)


if __name__ == "__main__":
    result = run_drift_check()
    print(format_drift_report(result))
