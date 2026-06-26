# ruff: noqa
import os
import json
from typing import Any, Literal
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load local environment variables from .env
load_dotenv()

from google.adk.agents.context import Context
from google.adk.apps import App
from google.adk.events import Event, RequestInput
from google.adk.workflow import Edge, Workflow, node
from google.adk.agents import LlmAgent
from google.adk.models import Gemini

# Configure ADK to use AI Studio API key (not Vertex AI)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"
# Ensure both env var names are set (different ADK versions prefer one or the other)
if os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

# Import local tools
from app.tools import check_hospital_network, get_policy_coverage, explain_insurance_lingo

# Define the extraction schema
class ClaimExtraction(BaseModel):
    policy_id: str = Field(description="The policy ID (e.g. POL123), empty if not found.")
    hospital: str = Field(description="The hospital name (e.g. Apollo Hospital), empty if not found.")
    treatment: str = Field(description="The medical treatment or procedure (e.g. Dental Cleaning, Wisdom Tooth Extraction).")
    estimated_cost: float = Field(description="The estimated cost of the treatment, default 0.0.")

# Extraction LLM Agent
extraction_agent = LlmAgent(
    name="extraction",
    model=Gemini(model="gemini-3.5-flash"),
    instruction="""You are an expert medical claims classifier. You MUST parse the user's natural language request and extract ALL available information. Do NOT ask for more information — extract whatever is provided.
    Extract:
    1. The policy ID (e.g., POL123). If not found, use empty string.
    2. The hospital name (e.g., Apollo Hospital). If not found, use empty string.
    3. The treatment or procedure name (e.g., Wisdom Tooth Extraction). If not found, use empty string.
    4. The estimated cost of the treatment. If not found, use 0.0.
    IMPORTANT: Always output structured data matching the schema. Never refuse to extract.
    """,
    output_key="extraction",
    output_schema=ClaimExtraction,
)

# Define the risk analysis schema
class RiskAnalysis(BaseModel):
    traps: list[str] = Field(description="List of traps found (e.g. '10% co-payment', 'Room rent limit is $150/day'). Empty if none.")
    explanations: list[str] = Field(description="Plain English translation of jargon terms found (e.g. 'Co-pay means...', 'Sub-limit means...').")
    summary: str = Field(description="Summary of the claim evaluation and potential issues.")

# Risk Analysis LLM Agent
risk_agent = LlmAgent(
    name="risk_analysis",
    model=Gemini(model="gemini-3.5-flash"),
    instruction="""You are a senior claims risk auditor. You are given verified tool outputs containing hospital network status and policy coverage details. You MUST analyze the data that is provided to you — do NOT say you lack information.

    Using the PROVIDED data, do the following:
    1. Identify any co-payments (e.g., '10% co-pay') and add them to the 'traps' list.
    2. Identify any room rent sub-limits (e.g., 'room rent capped at $150/day') and add them to the 'traps' list.
    3. Identify any exclusions mentioned and add them to the 'traps' list.
    4. Provide plain English explanations for insurance jargon found (like co-pay, sub-limit, deductible, network).
    5. Provide a brief summary of the claim evaluation based on the data provided.

    CRITICAL: If the coverage data shows a co-pay percentage > 0, you MUST list it as a trap.
    If the coverage data shows a room_rent_limit, you MUST list it as a trap.
    If the network status says NOT in network, mention that clearly.
    Format your findings matching the output schema.
    """,
    output_key="risk_data",
    output_schema=RiskAnalysis,
)

# Decision Schema for Human-in-the-Loop
class DecisionInput(BaseModel):
    decision: Literal['proceed', 'cancel'] = Field(description="User decision: 'proceed' to file cashless claim despite warnings, 'cancel' to abort.")
    user_notes: str = Field(description="Any notes or comments from the user.")

@node
def save_request(node_input: str):
    """Saves the user request in state."""
    yield Event(data=node_input, state={'user_query': node_input})

@node
def verify_eligibility(ctx: Context, node_input: Any):
    """Calls tools to verify coverage and hospital network status."""
    extraction = ctx.state.get("extraction", {})
    policy_id = extraction.get("policy_id", "")
    hospital = extraction.get("hospital", "")
    treatment = extraction.get("treatment", "")
    cost = extraction.get("estimated_cost", 0.0)
    
    # Execute tools
    network_res = check_hospital_network(hospital)
    coverage_res = get_policy_coverage(policy_id, treatment)
    
    yield Event(
        data=node_input,
        state={
            "policy_id": policy_id,
            "hospital": hospital,
            "treatment": treatment,
            "estimated_cost": cost,
            "network_status": network_res,
            "coverage_details": coverage_res
        }
    )

@node
def prepare_risk_input(ctx: Context, node_input: Any):
    """Formats the prompt for the risk analysis agent using tool outputs."""
    user_query = ctx.state.get("user_query", "")
    network_status = ctx.state.get("network_status", "")
    coverage_details_str = ctx.state.get("coverage_details", "{}")
    
    # Pre-parse some flags to force the LLM to see them
    try:
        cov = json.loads(coverage_details_str)
        warnings = []
        if cov.get("co_pay_percentage", 0) > 0:
            warnings.append(f"CRITICAL WARNING: Policy has a {cov['co_pay_percentage']}% co-pay!")
        if cov.get("room_rent_limit", 0) > 0:
            warnings.append(f"CRITICAL WARNING: Policy has a room rent limit of ${cov['room_rent_limit']}!")
        
        warnings_text = "\n".join(warnings) if warnings else "No obvious numerical traps detected."
    except Exception:
        warnings_text = ""
    
    prompt = f"""Analyze this insurance claim for hidden traps and risks.

=== USER REQUEST ===
{user_query}

=== HOSPITAL NETWORK STATUS (from tool) ===
{network_status}

=== POLICY COVERAGE DETAILS (from tool, JSON) ===
{coverage_details_str}

=== SYSTEM PRE-ANALYSIS WARNINGS ===
{warnings_text}

Based on the above verified data and warnings, identify all traps (co-pays, sub-limits, exclusions) and explain insurance terms in plain English. YOU MUST INCLUDE THE WARNINGS IN YOUR TRAPS LIST."""
    yield Event(data=prompt)

@node
def route_claim(ctx: Context, node_input: Any):
    """Routes the claim to auto-approval, human-gate, or rejection."""
    network_status = ctx.state.get("network_status", "")
    coverage_details_str = ctx.state.get("coverage_details", "{}")
    
    try:
        cov = json.loads(coverage_details_str)
    except Exception:
        cov = {}
        
    risk_data = ctx.state.get("risk_data", {})
    traps = risk_data.get("traps", []) if isinstance(risk_data, dict) else getattr(risk_data, "traps", [])
    
    # Check network
    if "NOT in the cashless network" in network_status:
        yield Event(data="Non-Network Hospital", route="reject_non_network")
        return
        
    # Check coverage exclusion
    if cov.get("covered") is False:
        yield Event(data="Treatment Excluded", route="reject_excluded")
        return
        
    # Check if there are traps requiring human review
    if traps:
        yield Event(data="Traps Detected", route="gate")
        return
        
    yield Event(data="Approved", route="approve")

@node
def human_approval(ctx: Context, node_input: Any):
    """Asks for human confirmation if traps are detected."""
    decision_data = ctx.resume_inputs.get("decision_input")
    if decision_data is None:
        yield RequestInput(
            interrupt_id="decision_input",
            message="Wait! We found potential traps in this claim. Do you want to proceed?",
            response_schema=DecisionInput
        )
        return
    
    # Save the input to state
    yield Event(data=node_input, state={"human_decision": decision_data})

@node
def route_after_human(ctx: Context, node_input: Any):
    """Routes the workflow based on the human decision."""
    decision_data = ctx.state.get("human_decision", {})
    # Handle both Pydantic model and dict
    decision = decision_data.get("decision", "cancel") if isinstance(decision_data, dict) else getattr(decision_data, "decision", "cancel")
    
    if decision == "proceed":
        yield Event(data="Approved by User", route="approve")
    else:
        yield Event(data="Cancelled by User", route="cancel")

@node
def generate_claims_form(ctx: Context, node_input: Any):
    """Generates the cashless claim request form."""
    extraction = ctx.state.get("extraction", {})
    risk_data = ctx.state.get("risk_data", {})
    
    form = f"""### CASHLESS CLAIM REQUEST FORM
    
    **Policy ID:** {ctx.state.get('policy_id')}
    **Hospital:** {ctx.state.get('hospital')}
    **Treatment:** {ctx.state.get('treatment')}
    **Estimated Cost:** ${ctx.state.get('estimated_cost')}
    
    **Warnings/Traps Identified:**
    {', '.join(risk_data.get('traps', ['None']))}
    
    **Status:** Cashless claim initiated successfully.
    """
    yield Event(data=form)

@node
def reject_non_network(ctx: Context, node_input: Any):
    """Rejects the cashless request because the hospital is out of network."""
    hospital = ctx.state.get("hospital", "Selected hospital")
    message = f"Rejection: Cashless claims are only available at network hospitals. {hospital} is NOT in the network. Please seek reimbursement or visit a network hospital (e.g. Apollo Hospital)."
    yield Event(data=message)

@node
def reject_excluded(ctx: Context, node_input: Any):
    """Rejects the cashless request because the treatment is excluded."""
    treatment = ctx.state.get("treatment", "Selected treatment")
    coverage_details_str = ctx.state.get("coverage_details", "{}")
    try:
        cov = json.loads(coverage_details_str)
        reason = cov.get("reason", "Excluded treatment.")
    except Exception:
        reason = "Excluded treatment."
    message = f"Rejection: {reason}"
    yield Event(data=message)

@node
def cancel_claim(ctx: Context, node_input: Any):
    """Confirms the cancellation of the claim request."""
    yield Event(data="Claim cancelled by the user.")

# Wire the graph workflow
root_agent = Workflow(
    name="claims_concierge_workflow",
    edges=[
        ('START', save_request, extraction_agent, verify_eligibility, prepare_risk_input, risk_agent, route_claim),
        (route_claim, {
            "gate": human_approval,
            "approve": generate_claims_form,
            "reject_non_network": reject_non_network,
            "reject_excluded": reject_excluded
        }),
        (human_approval, route_after_human),
        (route_after_human, {
            "approve": generate_claims_form,
            "cancel": cancel_claim
        })
    ]
)

app = App(
    root_agent=root_agent,
    name="app",
)
