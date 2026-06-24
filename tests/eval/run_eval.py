import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
"""
Custom evaluation script for the Insurance Claims Concierge Agent.
Runs the 5 eval cases directly through the ADK app and scores them
using Gemini as the LLM-as-judge — no Vertex AI / gcloud required.
"""

import asyncio  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

# Ensure GOOGLE_GENAI_USE_VERTEXAI is off BEFORE any ADK import
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"
if os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

import google.genai as genai  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402

# ── Load the agent app ──────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.agent import app as claims_app  # noqa: E402

# ── Eval dataset ────────────────────────────────────────────────────────────
EVAL_CASES = [
    {
        "id": "approved_cashless_claim",
        "prompt": "I need a cashless claim for policy POL999. I am admitted at Apollo Hospital for a knee surgery. The estimated cost is $2000.",
        "expected_outcome": "approved",
        "expect_traps": False,
    },
    {
        "id": "non_network_hospital_rejection",
        "prompt": "Please initiate a cashless claim for my policy POL123 at City Care Hospital for a general check-up costing $300.",
        "expected_outcome": "rejected_non_network",
        "expect_traps": False,
    },
    {
        "id": "excluded_treatment_rejection",
        "prompt": "I need to file a cashless claim under policy POL123 at Fortis Hospital for Dental Cleaning. It costs around $200.",
        "expected_outcome": "rejected_excluded",
        "expect_traps": False,
    },
    {
        "id": "claim_with_traps_copay",
        "prompt": "I want to admit myself at Max Hospital for an appendix operation. My policy is POL123 and the cost is $3000.",
        "expected_outcome": "human_gate",
        "expect_traps": True,
    },
    {
        "id": "lingo_explanation_request",
        "prompt": "What does co-payment mean? My claim form says I have a 10% co-pay and I don't understand it.",
        "expected_outcome": "explanation",
        "expect_traps": False,
    },
]

JUDGE_PROMPT = """You are an expert QA evaluator for an Insurance Claims Concierge AI Agent.

Evaluate the agent's response for the following scenario:

**User Prompt:** {prompt}
**Expected Outcome:** {expected_outcome}
**Traps Expected:** {expect_traps}
**Agent Final Response:** {response}

Score on these dimensions (1-5 each):

1. **Correctness** - Did the agent route/respond correctly for the expected outcome?
2. **Trap Detection** - If traps were expected, did the agent identify them? (5 if no traps expected and none reported)
3. **Plain Language** - Were insurance terms explained in simple, consumer-friendly English?
4. **Helpfulness** - Did the response give actionable guidance to the user?

Return ONLY valid JSON:
{{
  "correctness": <1-5>,
  "trap_detection": <1-5>,
  "plain_language": <1-5>,
  "helpfulness": <1-5>,
  "overall": <average of above, 1 decimal>,
  "verdict": "<one sentence summary>"
}}"""


async def run_single_case(runner: Runner, session_service: InMemorySessionService, case: dict) -> str:
    """Run one eval case through the agent and return the final response text."""
    from google.genai.types import Content, Part

    session = await session_service.create_session(
        app_name="app",
        user_id="eval_user",
    )

    final_response = ""
    async for event in runner.run_async(
        user_id="eval_user",
        session_id=session.id,
        new_message=Content(role="user", parts=[Part(text=case["prompt"])]),
    ):
        if hasattr(event, "content") and event.content:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    final_response = part.text  # keep last text response

    return final_response.strip()


def judge_response(client: genai.Client, case: dict, response: str) -> dict:
    """Use Gemini as LLM-as-judge to score the response."""
    prompt = JUDGE_PROMPT.format(
        prompt=case["prompt"],
        expected_outcome=case["expected_outcome"],
        expect_traps=case["expect_traps"],
        response=response if response else "(no response captured)",
    )
    result = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    try:
        return json.loads(result.text)
    except Exception:
        return {"error": "Failed to parse judge response", "raw": result.text}


async def main():
    print("\n" + "="*60)
    print("  INSURANCE CLAIMS CONCIERGE — EVALUATION REPORT")
    print("="*60)
    print(f"  Running {len(EVAL_CASES)} eval cases...\n")

    # Set up the runner
    session_service = InMemorySessionService()
    runner = Runner(
        app=claims_app,
        session_service=session_service,
    )

    # Set up Gemini judge client
    judge_client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))

    results = []
    for i, case in enumerate(EVAL_CASES, 1):
        print(f"[{i}/{len(EVAL_CASES)}] Running: {case['id']}")
        print(f"    Prompt: {case['prompt'][:70]}...")

        # Rate-limit pause: free tier = 5 RPM, each case = 2 LLM calls
        if i > 1:
            wait = 20
            print(f"    [WAIT] Pausing {wait}s to respect free-tier rate limit...")
            await asyncio.sleep(wait)

        # Run the agent
        try:
            response = await run_single_case(runner, session_service, case)
            print(f"    Response (preview): {response[:120]}...")
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                print("    [RATE_LIMIT] Hit quota - waiting 60s then retrying...")
                await asyncio.sleep(60)
                try:
                    response = await run_single_case(runner, session_service, case)
                    print(f"    Response (preview): {response[:120]}...")
                except Exception as e2:
                    response = f"ERROR after retry: {e2}"
                    print(f"    [ERR] Agent failed after retry: {e2}")
            else:
                response = f"ERROR: {e}"
                print(f"    [ERR] Agent error: {e}")

        # Judge the response
        try:
            scores = judge_response(judge_client, case, response)
            overall = scores.get("overall", "N/A")
            verdict = scores.get("verdict", "")
            print(f"    [OK] Score: {overall}/5 -- {verdict}")
        except Exception as e:
            scores = {"error": str(e)}
            print(f"    [ERR] Judge error: {e}")

        results.append({
            "case_id": case["id"],
            "prompt": case["prompt"],
            "expected_outcome": case["expected_outcome"],
            "agent_response": response,
            "scores": scores,
        })
        print()

    # Summary
    print("="*60)
    print("  SUMMARY")
    print("="*60)
    valid_scores = [r["scores"].get("overall") for r in results if isinstance(r["scores"].get("overall"), (int, float))]
    if valid_scores:
        avg = sum(valid_scores) / len(valid_scores)
        print(f"  Average Overall Score: {avg:.2f} / 5.0")
        print(f"  Cases Evaluated:       {len(results)}")
        print(f"  Cases Scored:          {len(valid_scores)}\n")

    for r in results:
        s = r["scores"]
        overall = s.get("overall", "ERR")
        icon = "[PASS]" if isinstance(overall, float) and overall >= 3.5 else "[WARN]"
        print(f"  {icon} {r['case_id']:<40} {overall}/5")

    # Save results
    out_dir = Path("artifacts/eval_results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"eval_results_{ts}.json"
    with open(out_file, "w") as f:
        json.dump({"timestamp": ts, "results": results, "average_score": avg if valid_scores else None}, f, indent=2)

    print(f"\n  [SAVED] Full results saved to: {out_file}")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
