import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'claims_db.json')

def load_db():
    if not os.path.exists(DB_PATH):
        # Fallback empty structure
        return {"network_hospitals": [], "policies": {}}
    with open(DB_PATH) as f:
        return json.load(f)

def check_hospital_network(hospital: str) -> str:
    """Agent Tool: Checks if a given hospital is in the insurer's cashless network.

    Args:
        hospital: The name of the hospital (e.g. 'Apollo Hospital').

    Returns:
        A string indicating whether the hospital is in the network or not.
    """
    db = load_db()
    hospitals = [h.lower() for h in db.get("network_hospitals", [])]
    if hospital.lower() in hospitals:
        return f"Success: {hospital} is in the cashless network."
    return f"Error: {hospital} is NOT in the cashless network."

def get_policy_coverage(policy_id: str, treatment: str) -> str:
    """Agent Tool: Retrieves the coverage details, exclusions, and limits for a treatment under a specific policy ID.

    Args:
        policy_id: The unique policy identifier (e.g. 'POL123').
        treatment: The name of the treatment (e.g. 'Wisdom Tooth Extraction', 'Dental Cleaning').

    Returns:
        A JSON string containing coverage status, co-payments, room rent limits, and remaining balance.
    """
    db = load_db()
    policies = db.get("policies", {})
    if policy_id not in policies:
        return json.dumps({"error": f"Policy {policy_id} not found."})

    policy = policies[policy_id]
    exclusions = [e.lower() for e in policy.get("exclusions", [])]

    if treatment.lower() in exclusions:
        return json.dumps({
            "policy_id": policy_id,
            "treatment": treatment,
            "covered": False,
            "reason": f"Treatment '{treatment}' is explicitly excluded in the policy exclusions.",
            "exclusions": policy.get("exclusions")
        })

    return json.dumps({
        "policy_id": policy_id,
        "treatment": treatment,
        "covered": True,
        "remaining_balance": policy.get("remaining_balance"),
        "co_pay_percentage": policy.get("co_pay") * 100 if policy.get("co_pay") is not None else 0,
        "room_rent_limit": policy.get("room_rent_limit")
    })

def explain_insurance_lingo(term: str) -> str:
    """Agent Tool: Translates complex insurance jargon into simple, consumer-friendly English.

    Args:
        term: The insurance term to explain (e.g. 'Co-pay', 'Deductible', 'Sub-limit').

    Returns:
        A clear, plain English definition of the term.
    """
    lingo_dict = {
        "co-pay": "Co-payment is a flat percentage (like 10% or 20%) of the total bill that you must pay out of your own pocket, while the insurer pays the rest.",
        "copayment": "Co-payment is a flat percentage (like 10% or 20%) of the total bill that you must pay out of your own pocket, while the insurer pays the rest.",
        "deductible": "A deductible is the initial fixed amount you must pay yourself before the insurance policy starts covering any expenses.",
        "sub-limit": "A sub-limit is a cap or ceiling on how much the policy will cover for a specific type of expense, such as room rent or ICU charges.",
        "sublimit": "A sub-limit is a cap or ceiling on how much the policy will cover for a specific type of expense, such as room rent or ICU charges.",
        "exclusions": "Exclusions are specific medical conditions, treatments, or services that the insurance policy does NOT cover under any circumstances.",
        "cashless": "Cashless claim means the insurer pays the hospital directly for your treatment, so you don't have to pay the bill yourself and wait for reimbursement (provided it's a network hospital)."
    }

    normalized = term.lower().strip()
    # Match partial terms or substring
    for key, val in lingo_dict.items():
        if key in normalized or normalized in key:
            return val

    return f"I don't have a direct definition for '{term}', but in insurance it generally refers to a specific policy term or clause. Please consult your policy documentation."
