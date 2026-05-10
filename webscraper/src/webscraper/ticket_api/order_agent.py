"""Order Tracker agent — Phase 3.

Uses the Claude API with tool use to inspect incomplete orders and write
field suggestions to orders_suggested via the Phase 2 tool layer.

Usage:
    python -m webscraper.ticket_api.order_agent --order-id JCH-69B031DF
    python -m webscraper.ticket_api.order_agent --incomplete          # process all orders missing key fields
    python -m webscraper.ticket_api.order_agent --summary             # show completeness summary only

Required env vars:
    ANTHROPIC_API_KEY      — Claude API key
    TICKET_API_URL         — base URL of the FastAPI server (default: http://127.0.0.1:8788)
    INGEST_API_KEY         — API key for the /suggest and /flag endpoints

The agent ONLY calls suggest and flag. It never calls confirm.
confirm is a human-only action taken through the UI.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import anthropic
import requests

# ── Config ────────────────────────────────────────────────────────────────────

API_BASE = os.getenv("TICKET_API_URL", "http://127.0.0.1:8788").rstrip("/")
INGEST_KEY = os.getenv("INGEST_API_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192
BATCH_SIZE = 5  # orders processed per --incomplete run

_HEADERS: dict[str, str] = {}
if INGEST_KEY:
    _HEADERS["X-Ingest-Key"] = INGEST_KEY


# ── HTTP helpers ───────────────────────────────────────────────────────────────


def _get(path: str) -> dict[str, Any]:
    r = requests.get(f"{API_BASE}{path}", headers=_HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    r = requests.post(f"{API_BASE}{path}", json=body, headers=_HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


# ── Tool implementations ───────────────────────────────────────────────────────


def tool_get_order(order_id: str) -> dict[str, Any]:
    return _get(f"/api/orders/{order_id}")


def tool_get_order_dispatch(order_id: str) -> dict[str, Any]:
    return _get(f"/api/orders/{order_id}/dispatch")


def tool_get_order_account(order_id: str) -> dict[str, Any]:
    return _get(f"/api/orders/{order_id}/account")


def tool_get_incomplete_orders(field: str | None = None) -> dict[str, Any]:
    path = "/api/orders/incomplete"
    if field:
        path += f"?field={field}"
    return _get(path)


def tool_get_completeness_summary() -> dict[str, Any]:
    return _get("/api/orders/incomplete/summary")


def tool_suggest_field(order_id: str, field: str, value: str,
                        confidence: float, reason: str) -> dict[str, Any]:
    return _post(f"/api/orders/{order_id}/suggest", {
        "field": field,
        "value": value,
        "confidence": confidence,
        "source": f"agent:{reason}",
    })


def tool_flag_field(order_id: str, field: str, reason: str) -> dict[str, Any]:
    return _post(f"/api/orders/{order_id}/flag", {
        "field": field,
        "reason": reason,
    })


# ── Tool dispatch ──────────────────────────────────────────────────────────────


TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_order",
        "description": "Get the full order record for a single order ID, including any pending suggestions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The order ID, e.g. JCH-69B031DF"}
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "get_order_dispatch",
        "description": "Get dispatch-specific fields (dispatch_date, assigned tech, location, task, install_type) and correlated VPBX record for an order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"}
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "get_order_account",
        "description": "Get account/configuration fields (pbx_ip, seats, phone_model, pon, on_net_ott) and correlated VPBX and handles records for an order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"}
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "get_incomplete_orders",
        "description": "Get orders that are missing data. Optionally filter by a specific field name. Returns a list of order records.",
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "description": "Optional: one of customer_name, customer_abbrev, dispatch_date, install_type, assigned, engineer, seats, pbx_ip, phone_model, location, pon, on_net_ott",
                }
            },
        },
    },
    {
        "name": "get_completeness_summary",
        "description": "Get a summary of how many orders are missing each key field.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "suggest_field",
        "description": (
            "Write a suggested value for a field to the orders_suggested staging table. "
            "This NEVER modifies the production orders table. "
            "Use this when you can infer a value with reasonable confidence from available data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "field": {
                    "type": "string",
                    "description": "Field to suggest: customer_name, customer_abbrev, dispatch_date, install_type, task, assigned, engineer, detail_url, seats, pbx_ip, phone_model, location, pon, on_net_ott",
                },
                "value": {"type": "string", "description": "The suggested value"},
                "confidence": {
                    "type": "number",
                    "description": "0.0–1.0. Use ≥0.9 for direct lookups, 0.7–0.9 for inferred, <0.7 for uncertain",
                },
                "reason": {
                    "type": "string",
                    "description": "Short explanation of how you derived this value, e.g. 'vpbx_records ip match' or 'pon prefix indicates SIP trunk'",
                },
            },
            "required": ["order_id", "field", "value", "confidence", "reason"],
        },
    },
    {
        "name": "flag_field",
        "description": (
            "Flag a field as needing human review. Use this when a field is empty and you cannot "
            "determine the correct value from available data, or when the data looks inconsistent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "field": {"type": "string"},
                "reason": {"type": "string", "description": "Why this field needs human attention"},
            },
            "required": ["order_id", "field", "reason"],
        },
    },
]


def dispatch_tool(name: str, inputs: dict[str, Any]) -> Any:
    if name == "get_order":
        return tool_get_order(inputs["order_id"])
    if name == "get_order_dispatch":
        return tool_get_order_dispatch(inputs["order_id"])
    if name == "get_order_account":
        return tool_get_order_account(inputs["order_id"])
    if name == "get_incomplete_orders":
        return tool_get_incomplete_orders(inputs.get("field"))
    if name == "get_completeness_summary":
        return tool_get_completeness_summary()
    if name == "suggest_field":
        return tool_suggest_field(
            inputs["order_id"], inputs["field"], inputs["value"],
            inputs["confidence"], inputs["reason"],
        )
    if name == "flag_field":
        return tool_flag_field(inputs["order_id"], inputs["field"], inputs["reason"])
    raise ValueError(f"Unknown tool: {name!r}")


# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an Order Tracker assistant for a Hosted PBX Engineer at 123NET.

## Your role
You help fill in and validate order records in the 123NET Order Tracker system. You inspect
incomplete orders, correlate data from multiple sources, and write suggestions to a staging
table for human review. You never modify production data directly.

## The engineer
- Username: tjohnson
- Role: Engineer (NOT Project Manager — the system historically mislabeled this field "pm")
- Deploys Hosted PBX systems for business customers throughout Michigan

## Order types at 123NET
- **Hosted PBX (HPBX)**: Full voice system deployment — phones, PBX config, MikroTik router,
  switch, sometimes ATAs and Algo paging units
- **SIP Trunk**: Connect customer's existing PBX to 123.net's SIP network
- **EVC (Ethernet Virtual Circuit)**: 123.net provides the internet circuit (this is On-Net)
- **OTT (Over The Top)**: Customer has their own ISP; 123.net service rides over it

## Key field definitions

**pon** — Provisioning Order Number. Two formats:
- `EVC-XXXXXX` or `EVC-XXXXXXA` — Ethernet Virtual Circuit. Always On-Net.
- `SIPTG-XXXX` — SIP Trunk Group. Usually OTT unless paired with an EVC order.

**on_net_ott** — Whether 123.net provides the internet circuit:
- On-Net: 123.net provides internet (EVC PON present)
- OTT: Customer has their own ISP (no EVC PON, or SIPTG only)
- If an order has both an EVC and SIPTG PON, it's On-Net.

**install_type** — Type of deployment:
- Hosted PBX, SIP Trunk, EVC, Expansion, Reconnect, etc.

**assigned** — The field tech assigned for the dispatch date. Comes from the dispatch calendar.

**pbx_ip** — The public IP address of the customer's PBX or router.
- May be findable in vpbx_records.ip if the account already exists.
- May also be in the account's handles record.

**seats** — Number of phone extensions/seats. Related to phone_model and qty.

**phone_model** — Phone model and quantity, e.g. "Yealink T54W x 8".

**location** — Physical site address. Should include street, city, state, zip.

## Confidence guidelines
- **0.95**: Direct field match from another authoritative record (e.g. vpbx_records.ip → pbx_ip)
- **0.85**: Strong inference (e.g. EVC PON present → On-Net)
- **0.70**: Reasonable inference with some uncertainty
- **< 0.70**: Flag instead of suggest

## Rules
1. NEVER call confirm — that is human-only via the UI
2. NEVER invent data — only suggest values you can trace to a specific source
3. If a field is empty and you have no reliable source, call flag_field
4. Always include a clear reason when suggesting or flagging
5. Prioritize orders with upcoming dispatch dates
6. A suggestion for pbx_ip should only come from vpbx_records or a reliable IP in the order data
7. on_net_ott can usually be inferred from pon — an EVC PON means On-Net

## Workflow for a single order
1. Call get_order to see current state and any pending suggestions
2. Call get_order_dispatch to see dispatch/tech assignment details
3. Call get_order_account to see account/VPBX correlation data
4. For each empty key field, either suggest a value or flag it
5. Report what you found and what actions you took

## Workflow for bulk processing
1. Call get_completeness_summary to understand the landscape
2. Call get_incomplete_orders with the most critical missing field
3. Work through the returned orders, applying the single-order workflow to each
4. Prioritize: dispatch_date missing > assigned missing > pbx_ip missing > pon missing
"""


# ── Agent loop ─────────────────────────────────────────────────────────────────


def run_agent(task: str, verbose: bool = True) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]

    if verbose:
        print(f"\n[agent] Task: {task}\n")

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,  # type: ignore[arg-type]
            messages=messages,  # type: ignore[arg-type]
        )

        # Collect assistant turn
        messages.append({"role": "assistant", "content": response.content})  # type: ignore[arg-type]

        if response.stop_reason == "end_turn":
            # Extract final text
            text_blocks = [b.text for b in response.content if hasattr(b, "text")]
            final = "\n".join(text_blocks)
            if verbose:
                print(f"\n[agent] Done.\n{final}")
            return final

        if response.stop_reason != "tool_use":
            if verbose:
                print(f"\n[agent] Stopped: stop_reason={response.stop_reason!r} (likely hit max_tokens)")
            break

        # Process all tool calls in this turn
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if verbose:
                print(f"  → {block.name}({json.dumps(block.input, separators=(',', ':'))})")
            try:
                result = dispatch_tool(block.name, block.input)  # type: ignore[arg-type]
                result_str = json.dumps(result, default=str)
            except Exception as exc:
                result_str = json.dumps({"error": str(exc)})
            if verbose:
                preview = result_str[:200] + "..." if len(result_str) > 200 else result_str
                print(f"     ← {preview}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_str,
            })

        messages.append({"role": "user", "content": tool_results})  # type: ignore[arg-type]

    return "[agent] Stopped unexpectedly"


# ── CLI ────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="123NET Order Tracker agent")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--order-id", help="Analyze and fill a single order")
    group.add_argument("--incomplete", action="store_true",
                       help="Process all orders missing key fields")
    group.add_argument("--summary", action="store_true",
                       help="Show completeness summary and exit")
    group.add_argument("--query", help="Free-text question about orders")
    parser.add_argument("--quiet", action="store_true", help="Suppress tool call trace")
    parser.add_argument("--batch", type=int, default=BATCH_SIZE,
                        help=f"Max orders to process per --incomplete run (default {BATCH_SIZE})")
    args = parser.parse_args()

    if not ANTHROPIC_KEY:
        print("ERROR: ANTHROPIC_API_KEY env var is not set.", file=sys.stderr)
        sys.exit(1)

    verbose = not args.quiet

    if args.summary:
        run_agent("Call get_completeness_summary and report the results clearly, "
                  "highlighting which fields have the most gaps.", verbose=verbose)
    elif args.order_id:
        run_agent(
            f"Analyze order {args.order_id}. Inspect its current state, correlate dispatch "
            f"and account data, then suggest values for any empty fields you can determine "
            f"with confidence, and flag any fields that need human attention.",
            verbose=verbose,
        )
    elif args.incomplete:
        run_agent(
            f"Call get_completeness_summary first to understand the landscape. "
            f"Then call get_incomplete_orders for the most critical missing field. "
            f"Pick the {args.batch} orders with the most urgent upcoming dispatch dates "
            f"and work through each one: call get_order_dispatch and get_order_account, "
            f"then suggest values or flag fields you cannot determine. "
            f"After finishing those {args.batch} orders, stop and report what you did.",
            verbose=verbose,
        )
    elif args.query:
        run_agent(args.query, verbose=verbose)


if __name__ == "__main__":
    main()
