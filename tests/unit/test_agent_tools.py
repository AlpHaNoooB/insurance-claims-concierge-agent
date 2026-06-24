from app.tools import (
    check_hospital_network,
    explain_insurance_lingo,
    get_policy_coverage,
)


def test_check_hospital_network_success():
    """Verify that a network hospital is correctly approved."""
    res = check_hospital_network("Apollo Hospital")
    assert "Success" in res
    assert "in the cashless network" in res

def test_check_hospital_network_fail():
    """Verify that a non-network hospital is correctly rejected."""
    res = check_hospital_network("Apollo Clinics")
    assert "Error" in res
    assert "NOT in the cashless network" in res

def test_get_policy_coverage_covered():
    """Verify policy coverage details are retrieved correctly for covered treatments."""
    res_str = get_policy_coverage("POL123", "Wisdom Tooth Extraction")
    import json
    res = json.loads(res_str)
    assert res["covered"] is True
    assert res["co_pay_percentage"] == 10.0
    assert res["room_rent_limit"] == 150.0

def test_get_policy_coverage_excluded():
    """Verify policy exclusions are flagged correctly."""
    res_str = get_policy_coverage("POL123", "Dental Cleaning")
    import json
    res = json.loads(res_str)
    assert res["covered"] is False
    assert "excluded" in res["reason"]

def test_get_policy_coverage_not_found():
    """Verify non-existent policies return an error."""
    res_str = get_policy_coverage("INVALID_POL", "Wisdom Tooth Extraction")
    import json
    res = json.loads(res_str)
    assert "error" in res

def test_explain_insurance_lingo():
    """Verify that insurance jargon is translated to plain English."""
    res_copay = explain_insurance_lingo("co-pay")
    res_sublimit = explain_insurance_lingo("sub-limit")

    assert "Co-payment is a flat percentage" in res_copay
    assert "A sub-limit is a cap or ceiling" in res_sublimit
