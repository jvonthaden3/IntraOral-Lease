"""Core calculator logic, shared by the API and any server-side rendering.
This is the single source of truth for the math -- the browser does a live
preview with the same formulas in static/calculator.js, but whatever gets
saved is always recomputed here so a tampered client can't store bad numbers.
"""


def pmt(annual_rate, term_months, principal):
    """Standard amortizing monthly payment (Excel PMT, sign-flipped positive)."""
    if term_months <= 0:
        return 0.0
    r = (annual_rate or 0) / 12.0
    if r == 0:
        return principal / term_months
    return principal * r * (1 + r) ** term_months / ((1 + r) ** term_months - 1)


def round_to_nearest(value, nearest):
    if not nearest:
        return value
    return round(value / nearest) * nearest


def compute(inputs: dict) -> dict:
    """Run the full lab-cost / doctor-price / credit-program calculation.

    `inputs` keys (all numeric unless noted):
      equipment_cost, lab_down_payment, lab_apr (0-1), lab_term (months)
      sell_price, discount, doctor_down_payment, doctor_apr (0-1), doctor_term
      round_to (dollars, default 5)
      credit_pct (0-1), low_threshold (dollars, default 500)
      unit_cost, unit_price (optional, for per-case profitability)
    """
    g = lambda k, d=0: float(inputs.get(k, d) or 0)

    equipment_cost = g("equipment_cost")
    lab_down = g("lab_down_payment")
    lab_apr = g("lab_apr")
    lab_term = int(g("lab_term", 36))

    sell_price = g("sell_price")
    discount = g("discount")
    doctor_down = g("doctor_down_payment")
    doctor_apr = g("doctor_apr")
    doctor_term = int(g("doctor_term", 40))
    round_to = g("round_to", 5)

    credit_pct = g("credit_pct")
    low_threshold = g("low_threshold", 500)

    unit_cost = g("unit_cost")
    unit_price = g("unit_price")

    lab_financed = max(0.0, equipment_cost - lab_down)
    lab_payment = pmt(lab_apr, lab_term, lab_financed)

    discounted_price = sell_price - discount
    doctor_financed = max(0.0, discounted_price - doctor_down)
    doctor_payment_raw = pmt(doctor_apr, doctor_term, doctor_financed)
    doctor_payment = round_to_nearest(doctor_payment_raw, round_to) if round_to else doctor_payment_raw

    margin_pct = ((sell_price - equipment_cost) / sell_price) if sell_price else 0.0
    monthly_spread = doctor_payment - lab_payment
    tail_months = max(0, doctor_term - lab_term)
    total_over_term = doctor_down + doctor_payment * doctor_term
    total_margin_over_term = (
        monthly_spread * min(lab_term, doctor_term)
        + doctor_payment * tail_months
        + (doctor_down - (equipment_cost - lab_financed))
    )

    breakeven_spend = (doctor_payment / credit_pct) if credit_pct else None

    profit_per_unit = None
    profit_margin_pct = None
    if unit_price:
        profit_per_unit = unit_price - unit_cost
        profit_margin_pct = profit_per_unit / unit_price if unit_price else None

    # Sample monthly-invoice schedule: from breakeven (rounded up to next $500)
    # down to $500, in $500 steps -- mirrors the step tables used in the
    # AmericaSmiles model this tool is generalized from.
    schedule = []
    if breakeven_spend:
        top = int((breakeven_spend // 500) * 500)
        if top < breakeven_spend:
            top += 500
        top = max(top, 500)
        levels = list(range(top, 0, -500))
        if not levels or levels[0] != top:
            levels = [top] + levels
        levels = [lv for lv in levels if lv >= 500]
    else:
        levels = [3000, 2500, 2000, 1500, 1000, 500]

    for invoice in levels:
        if invoice < low_threshold:
            credit = 0.0
        else:
            credit = credit_pct * invoice
        credit_applied = min(credit, doctor_payment)
        doctor_owes = max(0.0, doctor_payment - credit)
        row = {
            "invoice": invoice,
            "credit_applied": round(credit_applied, 2),
            "doctor_owes": round(doctor_owes, 2),
        }
        if profit_per_unit is not None and unit_price:
            units = invoice / unit_price
            profit = units * profit_per_unit
            net_profit = profit - credit_applied
            row["profit"] = round(profit, 2)
            row["net_profit"] = round(net_profit, 2)
            row["net_margin_pct"] = round(net_profit / invoice, 4) if invoice else 0
        schedule.append(row)

    return {
        "lab": {
            "equipment_cost": round(equipment_cost, 2),
            "financed": round(lab_financed, 2),
            "down_payment": round(lab_down, 2),
            "monthly_payment": round(lab_payment, 2),
            "apr": lab_apr,
            "term": lab_term,
        },
        "doctor": {
            "sell_price": round(sell_price, 2),
            "discount": round(discount, 2),
            "discounted_price": round(discounted_price, 2),
            "down_payment": round(doctor_down, 2),
            "financed": round(doctor_financed, 2),
            "monthly_payment_raw": round(doctor_payment_raw, 2),
            "monthly_payment": round(doctor_payment, 2),
            "apr": doctor_apr,
            "term": doctor_term,
            "total_over_term": round(total_over_term, 2),
        },
        "margin": {
            "sell_margin_pct": round(margin_pct, 4),
            "monthly_spread": round(monthly_spread, 2),
            "tail_months": tail_months,
            "total_margin_over_term": round(total_margin_over_term, 2),
        },
        "credit_program": {
            "credit_pct": credit_pct,
            "low_threshold": low_threshold,
            "breakeven_spend": round(breakeven_spend, 2) if breakeven_spend else None,
        },
        "unit_economics": {
            "unit_cost": unit_cost or None,
            "unit_price": unit_price or None,
            "profit_per_unit": round(profit_per_unit, 2) if profit_per_unit is not None else None,
            "profit_margin_pct": round(profit_margin_pct, 4) if profit_margin_pct is not None else None,
        },
        "schedule": schedule,
    }
