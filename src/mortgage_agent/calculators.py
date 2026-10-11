"""Exact underwriting calculations"""

from mortgage_agent.schemas import Applicant, Debt, Gift
from datetime import date


def ltv(applicant: Applicant) -> float:
    """Loan-to-value ratio, as a percentage"""
    return applicant.loan.amount / applicant.loan.property_value * 100


def counts_toward_dti(debt: Debt) -> bool:
    """Installment debts with 10 or fewer payments left are excluded (B3-6-05).
    Revolving debts like credit cards (months_remaining is None) always count."""
    return debt.months_remaining is None or debt.months_remaining > 10


def dti(applicant: Applicant) -> float:
    """Debt-to-income ratio, as a percentage
    Uses verified income. (Lenders qualify borrowers on documented income, not claims.)"""
    other_debts = sum(d.monthly_payment for d in applicant.debts if counts_toward_dti(d))
    total_obligations = applicant.loan.monthly_housing_payment + other_debts
    return total_obligations / applicant.income.verified_monthly_income * 100


def funds_to_close(applicant: Applicant) -> float:
    """Cash needed at closing: down payment plus closing costs"""
    down_payment = applicant.loan.property_value - applicant.loan.amount
    return down_payment + applicant.loan.estimated_closing_costs


def is_large_deposit(amount: float, applicant: Applicant) -> bool:
    """A single deposit over 50% of monthly qualifying income (B3-4.2-02)."""
    return amount > 0.5 * applicant.income.verified_monthly_income


def unsourced_deposits(applicant: Applicant) -> float:
    """Total of large deposits with no documented source (B3-4.2-02)."""
    return sum(
        d.amount
        for d in applicant.assets.large_deposits
        if not d.source_documented and is_large_deposit(d.amount, applicant)
    )


ACCEPTABLE_DONORS = {"parent", "grandparent", "sibling", "spouse", "fiance", "other relative"}

def gift_allowed(gift: Gift, applicant: Applicant) -> bool:
    """A gift can be used only on a principal residence or second home,
    and only from an acceptable donor (B3-4.3-04)."""
    if gift.donor_relationship == "friend":
        raise ValueError(
            "A friend is an acceptable donor only with a long-standing "
            "familial-like relationship, which the file can't show."
        )

    return (
        applicant.loan.occupancy != "investment property"
        and gift.donor_relationship in ACCEPTABLE_DONORS
    )



def usable_assets(applicant: Applicant) -> float:
    """Verified funds: bank + vested retirement + gifts with a gift letter, 
    minus undocumented large deposits (B3-4.2-02, B3-4.3-04)"""
    a = applicant.assets
    gifts = sum(g.amount for g in a.gifts if g.has_gift_letter and gift_allowed(g, applicant))
    total = a.bank_balance + a.retirement_balance + gifts
    return total - unsourced_deposits(applicant)


def reserves_months(applicant: Applicant) -> float:
    """Months of PITIA left after closing (B3-4.1-01). Negative means not enough to close."""
    leftover = usable_assets(applicant) - funds_to_close(applicant)
    return leftover / applicant.loan.monthly_housing_payment


def add_years(d: date, years: int) -> date:
    """The same calendar day, a number of years later."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def unlettered_gifts(applicant: Applicant) -> float:
    """Total of gifts still missing a gift letter (B3-4.3-04)"""
    return sum(
        g.amount
        for g in applicant.assets.gifts
        if not g.has_gift_letter and gift_allowed(g, applicant)
    )


def excluded_gifts(applicant: Applicant) -> float:
    """Total of gifts that can't be used at all (B3-4.3-04)."""
    return sum(g.amount for g in applicant.assets.gifts if not gift_allowed(g, applicant))