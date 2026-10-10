"""Exact underwriting calculations"""

from mortgage_agent.schemas import Applicant, Debt


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


def usable_assets(applicant: Applicant) -> float:
    """Verified funds: bank + vested retirement + gifts with a gift letter, 
    minus undocumented large deposits (B3-4.2-02, B3-4.3-04)"""
    a = applicant.assets
    gifts = sum(g.amount for g in a.gifts if g.has_gift_letter)
    total = a.bank_balance + a.retirement_balance + gifts
    unsourced = sum(d.amount for d in a.large_deposits 
                    if not d.source_documented and is_large_deposit(d.amount, applicant))
    return total - unsourced


def reserves_months(applicant: Applicant) -> float:
    """Months of PITIA left after closing (B3-4.1-01). Negative means not enough to close."""
    leftover = usable_assets(applicant) - funds_to_close(applicant)
    return leftover / applicant.loan.monthly_housing_payment
