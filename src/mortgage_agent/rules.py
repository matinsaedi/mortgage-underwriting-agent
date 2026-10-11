"""Underwriting rules: turn an applicant into a decision."""

from typing import Literal
from pydantic import BaseModel
from mortgage_agent.schemas import Applicant, ExpectedOutcome
from mortgage_agent.calculators import dti, add_years, funds_to_close, usable_assets, unsourced_deposits, unlettered_gifts, excluded_gifts

class Finding(BaseModel):
    """One problem a rule found in the application"""
    rule_id: str
    severity: Literal["decline", "condition"]
    reason: str


def decide(findings: list[Finding]) -> ExpectedOutcome:
    """Turn findings into a decision. 
    
    - Any deal-breaker -> decline, and list only the deal-breakers as reasons.
    - Only fixable issues -> approve with conditions, and list all of them.
    - No findings -> approve.
    """
    declines = [f for f in findings if f.severity == "decline"]
    if declines:
        decision, drivers = "decline", declines
    elif findings:
        decision, drivers = "approve with conditions", findings
    else:
        decision, drivers = "approve", []
    return ExpectedOutcome(
        decision=decision, 
        reasons=[f.reason for f in drivers],
        rule_ids=[f.rule_id for f in drivers]
    )



MIN_CREDIT_SCORE = 620

def check_credit_score(applicant: Applicant) -> Finding | None:
    """Minimum credit score for fixed-rate loans (B3-5.1-01)"""
    score = applicant.credit.score
    if score < MIN_CREDIT_SCORE:
        return Finding(
            rule_id="B3-5.1-01",
            severity="decline",
            reason=f"Credit score {score} is below the {MIN_CREDIT_SCORE} minimum.",
        )
    return None



MANUAL_DTI_BASE = 36
MANUAL_DTI_MAX = 45
DU_DTI_MAX = 50

def check_dti(applicant: Applicant) -> Finding | None:
    """Maximum debt-to-income ratio (B3-6-02)"""
    ratio = dti(applicant)
    method = applicant.loan.underwriting
    if method == "DU":
        limit = DU_DTI_MAX
    else:
        if MANUAL_DTI_BASE < ratio <= MANUAL_DTI_MAX:
            raise ValueError(
                f"Manual DTI {ratio:.1f}% is in the 36-45% band, "
                "which needs the Eligibility Matrix (not in B3)."
            )
        limit = MANUAL_DTI_MAX

    if ratio > limit:
        return Finding(
            rule_id="B3-6-02",
            severity="decline",
            reason=f"DTI {ratio:.1f}% exceeds the {limit}% maximum for {method} underwriting.",
        )
    return None




BANKRUPTCY_WAIT_YEARS = {7: 4, 13: 2}

def check_bankruptcy(applicant: Applicant) -> Finding | None:
    """Waiting period from bankruptcy discharge to closing (B3-5.3-07)"""
    c = applicant.credit
    if c.bankruptcy_chapter is None or c.bankruptcy_discharge_date is None:
        return None
    years = BANKRUPTCY_WAIT_YEARS[c.bankruptcy_chapter]
    eligible_on = add_years(c.bankruptcy_discharge_date, years)
    if applicant.closing_date < eligible_on:
        return Finding(
            rule_id="B3-5.3-07",
            severity="decline",
            reason=(
                f"Chapter {c.bankruptcy_chapter} bankruptcy discharged {c.bankruptcy_discharge_date}; "
                f"the {years}-year wait ends {eligible_on}, after the {applicant.closing_date} closing."
            )
        )
    return None


FORECLOSURE_WAIT_YEARS = 7

def check_foreclosure(applicant: Applicant) -> Finding | None:
    """Waiting period from foreclosure completion to closing (B3-5.3-07)"""
    c = applicant.credit
    if c.foreclosure_date is None:
        return None
    eligible_on = add_years(c.foreclosure_date, FORECLOSURE_WAIT_YEARS)
    if applicant.closing_date < eligible_on:
        return Finding(
            rule_id="B3-5.3-07",
            severity="decline",
            reason=(
                f"Foreclosure completed {c.foreclosure_date}; the {FORECLOSURE_WAIT_YEARS}-year wait "
                f"ends {eligible_on}, after the {applicant.closing_date} closing."
            )
        )
    return None


def required_reserves_months(applicant: Applicant) -> int:
    """Minimum months of PITIA reserves for DU loans (B3-4.1-01)"""
    loan = applicant.loan
    if loan.occupancy == "second home":
        return 2
    if loan.occupancy == "investment property" or loan.property_type == "2-4 unit":
        return 6
    return 0


def check_funds(applicant: Applicant) -> Finding | None:
    """Enough verified money to close and keep the required reserves (B3-4.1-01, B3-4.2-02)"""
    months = required_reserves_months(applicant)
    needed = funds_to_close(applicant) + months * applicant.loan.monthly_housing_payment
    verified = usable_assets(applicant) 
    deposits = unsourced_deposits(applicant)
    gifts = unlettered_gifts(applicant)
    excluded = excluded_gifts(applicant)

    if verified >= needed:
        return None

    available = verified + deposits + gifts
    if available >= needed:
        fixes = []
        if deposits > 0:
            fixes.append(f"document the source of ${deposits:,.0f} in large deposits")
        if gifts > 0:
            fixes.append(f"obtain a signed gift letter for ${gifts:,.0f} in gifts")
        return Finding(
            rule_id="B3-4.2-02" if deposits > 0 else "B3-4.3-04",
            severity="condition",
            reason=f"Verified funds of ${verified:,.0f} are short of the ${needed:,.0f} needed; "
            + " and ".join(fixes) + ".",
        )

    if excluded > 0 and available + excluded >= needed:
        return Finding(
            rule_id="B3-4.3-04",
            severity="decline",
            reason=(
                f"Funds of ${available:,.0f} are short of the ${needed:,.0f} needed; "
                f"${excluded:,.0f} in gifts can't be used because the donor or property type isn't allowed."
            ),
        )
    
    return Finding(
        rule_id="B3-4.1-01",
        severity="decline",
        reason=(
            f"Funds of ${verified + deposits + gifts:,.0f} are short of the ${needed:,.0f} needed "
            f"to close and hold {months} months of reserves."
        ),
    )
    