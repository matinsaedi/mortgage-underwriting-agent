"""Tools the underwriting agent can call."""

from langchain_core.tools import tool
from mortgage_agent import calculators
from datetime import date
from mortgage_agent.retrieval import retrieve


@tool
def ltv(loan_amount: float, property_value: float) -> float:
    """Loan-to-value ratio as a percentage: loan amount divided by property value, times 100."""
    return round(loan_amount / property_value * 100, 2)


@tool
def dti(housing_payment: float, monthly_debts: list[float], monthly_income: float) -> float:
    """Debt-to-income ratio as a percentage: (monthly housing payment + the listed monthly
    debt payments) divided by monthly income, times 100. You decide which debts belong in
    monthly_debts and which income to use; this tool only does the arithmetic."""
    return round((housing_payment + sum(monthly_debts)) / monthly_income * 100, 2)



@tool
def funds_to_close(property_value: float, loan_amount: float, closing_costs: float) -> float:
    """Cash the borrower must bring to closing: the down payment (property value minus
    loan amount) plus closing costs."""
    return property_value - loan_amount + closing_costs



@tool
def reserves_months(available_funds: float, cash_to_close: float, monthly_pitia: float) -> float:
    """Months of housing payments (PITIA) the borrower could still cover after closing:
    (available funds minus cash to close) divided by monthly PITIA. A negative result means
    not enough money to close. You decide which funds count as available; this tool only
    does the arithmetic."""
    return round((available_funds - cash_to_close) / monthly_pitia, 2)



@tool
def add_years(start_date: str, years: int) -> str:
    """The same calendar day a number of years later, as YYYY-MM-DD. Use it to find when a
    waiting period ends. Example: add_years('2022-10-30', 4) returns '2026-10-30'."""
    return calculators.add_years(date.fromisoformat(start_date), years).isoformat()



@tool
def search_guide(query: str) -> str:
    """Search the Fannie Mae Selling Guide (Part B3, underwriting rules). Returns the 3 most
    relevant passages, each starting with its rule ID and title. Look up every rule before
    you apply it (limits, waiting periods, documentation) instead of relying on memory.
    Search one topic at a time, e.g. 'large deposit documentation' or
    'Chapter 7 bankruptcy waiting period'."""
    docs = retrieve(query, top_n=3)
    return "\n\n---\n\n".join(d.page_content for d in docs)
