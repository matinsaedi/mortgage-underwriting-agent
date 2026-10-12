"""Generate synthetic mortgage applicants with known answers."""

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

from mortgage_agent.calculators import add_years, funds_to_close
from mortgage_agent.rules import (
    BANKRUPTCY_WAIT_YEARS,
    FORECLOSURE_WAIT_YEARS,
    check_applicant,
    required_reserves_months,
)
from mortgage_agent.schemas import (
    Applicant,
    Assets,
    Credit,
    Debt,
    ExpectedOutcome,
    Gift,
    Income,
    LargeDeposit,
    Loan,
)

PROPERTY_KINDS = [
    ("1-unit", "principal residence"),
    ("2-4 unit", "principal residence"),
    ("1-unit", "second home"),
    ("1-unit", "investment property"),
]
PROPERTY_WEIGHTS = [6, 1, 2, 1]


def monthly_pitia(loan_amount: float, property_value: float) -> float:
    """Rough monthly housing payment: principal and interest at about 6.5% over 30 years,
    plus property tax (1.2% of the value per year) and insurance ($100 a month)."""
    principal_and_interest = loan_amount * 0.00632
    taxes = property_value * 0.012 / 12
    insurance = 100
    return round(principal_and_interest + taxes + insurance)


def make_loan(rng: random.Random) -> Loan:
    """A random, healthy loan: 70-80% LTV, DU underwriting."""
    property_type, occupancy = rng.choices(PROPERTY_KINDS, weights=PROPERTY_WEIGHTS)[0]
    value = rng.randrange(250_000, 750_001, 5_000)
    ltv_pct = rng.choice([70, 75, 80])
    amount = value * ltv_pct / 100
    return Loan(
        amount=amount,
        property_value=value,
        monthly_housing_payment=monthly_pitia(amount, value),
        estimated_closing_costs=round(value * rng.uniform(0.02, 0.03)),
        property_type=property_type,
        occupancy=occupancy,
        underwriting="DU",
    )



EMPLOYERS = ["Maple Health", "Northwind Logistics", "Lakeshore Bank", "Bluefin Software", "Cedar School Board", "Harbor Engineering"]


def make_debts(rng: random.Random) -> list[Debt]:
    """Zero to two everyday debts. Installment debts all have more than 10 payments left,
    so every debt counts toward DTI."""
    debts = []
    for _ in range(rng.randint(0, 2)):
        kind = rng.choice(["auto loan", "student loan", "credit card"])
        if kind == "credit card":
            payment = rng.randrange(25, 151, 5)
            debts.append(Debt(kind=kind, monthly_payment=payment, balance=payment * rng.randint(20, 40)))
        else:
            payment = rng.randrange(150, 601, 10)
            months = rng.randint(12, 60)
            debts.append(Debt(kind=kind, monthly_payment=payment, balance=payment * months, months_remaining=months))
    return debts


def make_income(rng: random.Random, housing_payment: float, debts: list[Debt]) -> Income:
    """Income sized so DTI lands between 25% and 35%. Stated and verified income match."""
    target_dti = rng.uniform(0.25, 0.35)
    obligations = housing_payment + sum(d.monthly_payment for d in debts)
    monthly = math.ceil(obligations / target_dti / 100) * 100
    return Income(
        employer=rng.choice(EMPLOYERS),
        monthly_income=monthly,
        verified_monthly_income=monthly,
        years_employed=round(rng.uniform(2, 15), 1),
        pay_frequency=rng.choice(["weekly", "biweekly", "semimonthly", "monthly"]),
    )



FIRST_NAMES = ["Sarah", "Ben", "Lisa", "Omar", "Priya", "Tom", "Ana", "Mark", "Nina", "Raj", "Elena", "Kofi", "Mei", "Diego", "Hana", "Liam"]
LAST_NAMES = ["Chen", "Patel", "Nguyen", "Smith", "Garcia", "Kim", "Okafor", "Rossi", "Haddad", "Silva", "Novak", "Brown"]


def make_assets(rng: random.Random, loan: Loan) -> Assets:
    """Enough savings to close plus 8-24 months of PITIA left over:
    more than any reserve requirement (6 months at most)."""
    funds_to_close = loan.property_value - loan.amount + loan.estimated_closing_costs
    cushion = rng.randint(8, 24) * loan.monthly_housing_payment
    retirement = rng.choice([0, rng.randrange(10_000, 150_001, 1_000)])
    return Assets(
        bank_balance=math.ceil((funds_to_close + cushion) / 1_000) * 1_000,
        retirement_balance=retirement,
    )


def make_clean_applicant(rng: random.Random, applicant_id: str) -> Applicant:
    """A healthy borrower that every rule should approve."""
    loan = make_loan(rng)
    debts = make_debts(rng)
    applicant = Applicant(
        applicant_id=applicant_id,
        name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
        closing_date=date(2026, 11, 1) + timedelta(days=rng.randint(0, 60)),
        loan=loan,
        income=make_income(rng, loan.monthly_housing_payment, debts),
        debts=debts,
        credit=Credit(score=rng.randint(680, 800)),
        assets=make_assets(rng, loan),
        expected=ExpectedOutcome(decision="approve", reasons=[], rule_ids=[]),
    )
    applicant.expected = check_applicant(applicant)
    return applicant


# Traps: each one changes exactly one thing about a clean applicant.

def no_trap(rng: random.Random, a: Applicant) -> None:
    """Leave the clean applicant as it is."""


def trap_low_score(rng: random.Random, a: Applicant) -> None:
    """Credit score below the 620 minimum (B3-5.1-01)."""
    a.credit.score = rng.randint(560, 619)


def trap_high_dti(rng: random.Random, a: Applicant) -> None:
    """Pay stubs show much less than the stated income, pushing DTI over 50% (B3-6-02)."""
    obligations = a.loan.monthly_housing_payment + sum(d.monthly_payment for d in a.debts)
    a.income.verified_monthly_income = math.floor(obligations / rng.uniform(0.52, 0.65) / 100) * 100


def trap_short_debt(rng: random.Random, a: Applicant) -> None:
    """A big car loan with 10 or fewer payments left. Counting it would push DTI over 50%,
    but it is excluded (B3-6-05), so the loan is still fine."""
    obligations = a.loan.monthly_housing_payment + sum(d.monthly_payment for d in a.debts)
    payment = math.ceil((0.55 * a.income.verified_monthly_income - obligations) / 10) * 10
    months = rng.randint(2, 10)
    a.debts.append(Debt(kind="auto loan", monthly_payment=payment, balance=payment * months, months_remaining=months))


def trap_recent_bankruptcy(rng: random.Random, a: Applicant) -> None:
    """Bankruptcy discharged inside the waiting period (B3-5.3-07)."""
    chapter = rng.choice([7, 13])
    wait = BANKRUPTCY_WAIT_YEARS[chapter]
    a.credit.bankruptcy_chapter = chapter
    a.credit.bankruptcy_discharge_date = add_years(a.closing_date, -wait) + timedelta(days=rng.randint(1, 365))


def trap_old_bankruptcy(rng: random.Random, a: Applicant) -> None:
    """Bankruptcy discharged long enough ago: the waiting period is over (B3-5.3-07)."""
    chapter = rng.choice([7, 13])
    wait = BANKRUPTCY_WAIT_YEARS[chapter]
    a.credit.bankruptcy_chapter = chapter
    a.credit.bankruptcy_discharge_date = add_years(a.closing_date, -wait) - timedelta(days=rng.randint(0, 1000))


def trap_recent_foreclosure(rng: random.Random, a: Applicant) -> None:
    """Foreclosure completed inside the 7-year waiting period (B3-5.3-07)."""
    a.credit.foreclosure_date = add_years(a.closing_date, -FORECLOSURE_WAIT_YEARS) + timedelta(days=rng.randint(1, 1500))


def trap_old_foreclosure(rng: random.Random, a: Applicant) -> None:
    """Foreclosure completed more than 7 years ago: the waiting period is over (B3-5.3-07)."""
    a.credit.foreclosure_date = add_years(a.closing_date, -FORECLOSURE_WAIT_YEARS) - timedelta(days=rng.randint(0, 1000))


def money_needed(a: Applicant) -> float:
    """Funds to close plus the required reserves."""
    return funds_to_close(a) + required_reserves_months(a) * a.loan.monthly_housing_payment


def large_deposit_amount(rng: random.Random, a: Applicant) -> int:
    """A deposit well above 50% of monthly income, rounded to $1,000."""
    low = math.ceil(0.6 * a.income.verified_monthly_income / 1_000) * 1_000
    return rng.randrange(low, low + 40_001, 1_000)


def trap_deposit_needed(rng: random.Random, a: Applicant) -> None:
    """An undocumented large deposit that the borrower needs to close (B3-4.2-02)."""
    deposit = large_deposit_amount(rng, a)
    extra = rng.randrange(0, deposit, 100)
    a.assets.retirement_balance = 0
    a.assets.bank_balance = math.ceil(money_needed(a)) + extra
    a.assets.large_deposits = [
        LargeDeposit(amount=deposit, deposit_date=a.closing_date - timedelta(days=rng.randint(20, 80)), source_documented=False)
    ]


def trap_deposit_not_needed(rng: random.Random, a: Applicant) -> None:
    """An undocumented large deposit, but there is plenty of money without it (B3-4.2-02)."""
    deposit = large_deposit_amount(rng, a)
    a.assets.bank_balance = max(a.assets.bank_balance, math.ceil(money_needed(a)) + deposit)
    a.assets.large_deposits = [
        LargeDeposit(amount=deposit, deposit_date=a.closing_date - timedelta(days=rng.randint(20, 80)), source_documented=False)
    ]


def trap_short_funds(rng: random.Random, a: Applicant) -> None:
    """Not enough money to close and keep the required reserves (B3-4.1-01)."""
    a.assets.retirement_balance = 0
    a.assets.bank_balance = math.floor(money_needed(a) * rng.uniform(0.6, 0.95) / 100) * 100


def add_needed_gift(rng: random.Random, a: Applicant, donor: str, has_letter: bool) -> None:
    """Give the borrower a gift they need: own money alone falls short, own money plus the gift is enough."""
    a.assets.retirement_balance = 0
    needed = math.ceil(money_needed(a))
    gift = math.ceil(needed * rng.uniform(0.2, 0.6) / 1_000) * 1_000
    extra = rng.randrange(0, gift, 100)
    a.assets.bank_balance = needed - gift + extra
    a.assets.gifts = [Gift(amount=gift, donor_relationship=donor, has_gift_letter=has_letter)]


def make_owner_occupied(a: Applicant) -> None:
    """Gifts are only allowed on homes people live in or second homes, so turn a rental into a home."""
    if a.loan.occupancy == "investment property":
        a.loan.occupancy = "principal residence"


def trap_gift_ok(rng: random.Random, a: Applicant) -> None:
    """A needed gift from a relative, with a gift letter: nothing wrong (B3-4.3-04)."""
    make_owner_occupied(a)
    add_needed_gift(rng, a, rng.choice(["parent", "grandparent", "sibling", "spouse", "fiance", "other relative"]), True)


def trap_gift_no_letter(rng: random.Random, a: Applicant) -> None:
    """A needed gift from a relative, but the gift letter is missing (B3-4.3-04)."""
    make_owner_occupied(a)
    add_needed_gift(rng, a, rng.choice(["parent", "grandparent", "sibling", "spouse", "fiance", "other relative"]), False)


def trap_gift_bad_donor(rng: random.Random, a: Applicant) -> None:
    """A needed gift from an interested party, who is not an acceptable donor (B3-4.3-04)."""
    make_owner_occupied(a)
    add_needed_gift(rng, a, "interested party", True)


def trap_gift_rental(rng: random.Random, a: Applicant) -> None:
    """A needed gift on an investment property, where gifts are not allowed (B3-4.3-04)."""
    a.loan.occupancy = "investment property"
    a.loan.property_type = "1-unit"
    add_needed_gift(rng, a, "parent", True)


def second_home_at_90(a: Applicant) -> None:
    """Turn the loan into a 1-unit second home with 90% LTV."""
    a.loan.occupancy = "second home"
    a.loan.property_type = "1-unit"
    a.loan.amount = a.loan.property_value * 0.9
    a.loan.monthly_housing_payment = monthly_pitia(a.loan.amount, a.loan.property_value)


def add_gift_with_own_share(rng: random.Random, a: Applicant, own_share: float) -> None:
    """Own money is a set share of the price; a gift from a parent covers the rest."""
    a.assets.retirement_balance = 0
    own = math.ceil(a.loan.property_value * own_share / 100) * 100
    gift = math.ceil(money_needed(a)) - own + rng.randrange(0, 5_001, 100)
    a.assets.bank_balance = own
    a.assets.gifts = [Gift(amount=gift, donor_relationship="parent", has_gift_letter=True)]


def trap_min_contribution_short(rng: random.Random, a: Applicant) -> None:
    """Second home at 90% LTV with a gift, but own money is under 5% of the price (B3-4.3-04)."""
    second_home_at_90(a)
    add_gift_with_own_share(rng, a, rng.uniform(0.01, 0.045))


def trap_min_contribution_met(rng: random.Random, a: Applicant) -> None:
    """Second home at 90% LTV with a gift, and own money is at least 5% of the price (B3-4.3-04)."""
    second_home_at_90(a)
    add_gift_with_own_share(rng, a, rng.uniform(0.05, 0.08))

TRAPS = {
    "none": (no_trap, "approve"),
    "low_score": (trap_low_score, "decline"),
    "high_dti": (trap_high_dti, "decline"),
    "short_debt": (trap_short_debt, "approve"),
    "recent_bankruptcy": (trap_recent_bankruptcy, "decline"),
    "old_bankruptcy": (trap_old_bankruptcy, "approve"),
    "recent_foreclosure": (trap_recent_foreclosure, "decline"),
    "old_foreclosure": (trap_old_foreclosure, "approve"),
    "deposit_needed": (trap_deposit_needed, "approve with conditions"),
    "deposit_not_needed": (trap_deposit_not_needed, "approve"),
    "short_funds": (trap_short_funds, "decline"),
    "gift_ok": (trap_gift_ok, "approve"),
    "gift_no_letter": (trap_gift_no_letter, "approve with conditions"),
    "gift_bad_donor": (trap_gift_bad_donor, "decline"),
    "gift_rental": (trap_gift_rental, "decline"),
    "min_contribution_short": (trap_min_contribution_short, "decline"),
    "min_contribution_met": (trap_min_contribution_met, "approve"),
}


def make_applicant(rng: random.Random, applicant_id: str, trap: str) -> Applicant:
    """A clean applicant with one planted trap, graded by the rule checker."""
    applicant = make_clean_applicant(rng, applicant_id)
    plant, intended = TRAPS[trap]
    plant(rng, applicant)
    applicant.expected = check_applicant(applicant)
    if applicant.expected.decision != intended:
        raise ValueError(
            f"{applicant_id}: trap '{trap}' gave '{applicant.expected.decision}', expected '{intended}'"
        )
    return applicant


def generate_dataset(n_per_trap: int = 7, seed: int = 2026) -> list[tuple[str, Applicant]]:
    """n_per_trap applicants for every trap, in shuffled order, numbered G001, G002, ..."""
    rng = random.Random(seed)
    plan = [trap for trap in TRAPS for _ in range(n_per_trap)]
    rng.shuffle(plan)
    return [(trap, make_applicant(rng, f"G{i:03d}", trap)) for i, trap in enumerate(plan, start=1)]


def save_dataset(dataset: list[tuple[str, Applicant]], folder: Path) -> None:
    """One JSON file per applicant, plus a manifest of every applicant's trap and answer."""
    folder.mkdir(parents=True, exist_ok=True)
    manifest = []
    for trap, applicant in dataset:
        (folder / f"{applicant.applicant_id}.json").write_text(applicant.model_dump_json(indent=2))
        manifest.append(
            {
                "applicant_id": applicant.applicant_id,
                "trap": trap,
                "decision": applicant.expected.decision,
                "rule_ids": applicant.expected.rule_ids,
            }
        )
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))