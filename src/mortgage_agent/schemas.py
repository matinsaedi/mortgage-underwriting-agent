"""Pydantic schemas for synthetic mortgage applicants."""

from datetime import date
from typing import Literal
from pydantic import BaseModel, Field

class Loan(BaseModel):
    """The mortgage being requested and the property behind it"""
    amount: float = Field(gt=0, description="Loan amount in dollars")
    property_value: float = Field(gt=0, description="Appraised value in dollars")
    monthly_housing_payment: float = Field(
        gt=0, description="Proposed monthly PITIA: principal, interest, taxes, insurance, HOA dues")
    estimated_closing_costs: float = Field(                                  
        ge=0, description="Estimated closing costs in dollars, paid at closing")
    property_type: Literal["1-unit", "2-4 unit"]
    occupancy: Literal["principal residence", "second home", "investment property"]
    underwriting: Literal["manual", "DU"]


class Income(BaseModel):
    """What the borrower states they earn, and what their pay stubs show."""
    employer: str = Field(min_length=1, description="Current employer name")
    monthly_income: float = Field(gt=0, description="Stated gross monthly income in dollars")
    verified_monthly_income: float = Field(                                  
        gt=0, description="Gross monthly income as shown on pay stubs and W-2s")
    years_employed: float = Field(ge=0, description="Years with current employer")
    pay_frequency: Literal["weekly", "biweekly", "semimonthly", "monthly"]
    self_employed: bool = False


class Debt(BaseModel):
    """One recurring monthly debt from the credit report"""
    kind: Literal["auto loan", "student loan", "credit card", "personal loan", "other"]
    monthly_payment: float = Field(ge=0, description="Required monthly payment in dollars")
    balance: float = Field(ge=0, description="Remaining balance in dollars")
    months_remaining: int | None = Field(default=None, ge=0, 
                                         description="Payments left; None for revolving debt like credit cards")

    
class Credit(BaseModel):
    """The borrower's credit score and major past credit events"""
    score: int = Field(ge=300, le=850, description="Representative credit score")
    bankruptcy_chapter: Literal[7, 13] | None = Field(                       
        default=None, description="Chapter 7 (liquidation) or 13 (repayment plan), if any")
    bankruptcy_discharge_date: date | None = Field(
        default=None, description="Date a bankruptcy was discharged, if any"
    )
    foreclosure_date: date | None = Field(
        default=None, description="Date a foreclosure was completed, if any")


class LargeDeposit(BaseModel):
    """A single large deposit found on a bank statement"""
    amount: float = Field(gt=0, description="Deposit amount in dollars")
    deposit_date: date
    source_documented: bool = Field(description="Whether the source of the funds is explained and documented")


class Gift(BaseModel):
    """Money given to the borrower to help with the purchase"""
    amount: float = Field(gt=0, description="Gift amount in dollars")
    donor_relationship: Literal["parent", "grandparent", "sibling", "spouse",
                                "fiance", "other relative", "friend", "interested party"]
    has_gift_letter: bool


class Assets(BaseModel):
    """The borrower's funds available for closing and reserves"""
    bank_balance: float = Field(ge=0, description="Checking and savings balance in dollars")
    retirement_balance: float = Field(default=0.0, ge=0, description="Vested 401(k)/IRA balance in dollars")
    large_deposits: list[LargeDeposit] = Field(default_factory=list)
    gifts: list[Gift] = Field(default_factory=list)


class ExpectedOutcome(BaseModel):
    """The correct underwriting decision, used only for grading. Never shown to the agent."""
    decision: Literal["approve", "approve with conditions", "decline"]
    reasons: list[str]
    rule_ids: list[str] = Field(description="Selling Guide rules that drive the decision")


class Applicant(BaseModel):
    """A complete synthetic mortgage application"""
    applicant_id: str
    name: str
    closing_date: date = Field(
        description="Planned loan closing date; waiting periods are measured to this date")
    loan: Loan
    income: Income
    debts: list[Debt] = Field(default_factory=list)
    credit: Credit
    assets: Assets
    expected: ExpectedOutcome