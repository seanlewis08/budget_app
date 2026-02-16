"""
Financial Advisor — Data Aggregation Service

Gathers and summarizes all financial data into a structured snapshot
that can be embedded into an AI prompt for personalized analysis.
"""

import logging
from datetime import date, datetime, timedelta
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from ..models import Transaction, Category, Account, Budget

logger = logging.getLogger(__name__)

# Same exclusion set used by cash-flow and spending endpoints
EXCLUDED_CATEGORIES = {
    "transfer", "credit_card_payment", "payment",
    "discover", "roundups",
}


def _get_excluded_ids(db: Session) -> set:
    """Get IDs of categories that represent internal transfers (not real spending)."""
    parents = db.query(Category.id).filter(
        Category.short_desc.in_(EXCLUDED_CATEGORIES)
    ).all()
    ids = {r[0] for r in parents}
    children = db.query(Category.id).filter(Category.parent_id.in_(ids)).all()
    ids.update(r[0] for r in children)
    return ids


def build_financial_snapshot(db: Session, inv_db=None, savings_goal: float = 20000.0) -> dict:
    """
    Build a comprehensive financial data snapshot for the AI advisor.

    Returns a dict with all the data needed to generate personalized advice:
    - income by month
    - expenses by category by month
    - recurring charges
    - cash flow trend
    - budget vs actual
    - account balances
    - investment summary
    - savings progress
    """
    today = date.today()
    current_year = today.year
    current_month = today.month
    year_start = date(current_year, 1, 1)

    excluded_ids = _get_excluded_ids(db)

    # Base query: confirmed transactions for current year, excluding transfers
    base_q = (
        db.query(Transaction)
        .filter(
            Transaction.status.in_(["confirmed", "auto_confirmed"]),
            Transaction.date >= year_start,
            Transaction.date <= today,
        )
    )

    # ── 1. Monthly Income ──
    income_txns = (
        base_q.filter(Transaction.amount < 0)
        .filter(~Transaction.category_id.in_(excluded_ids))
        .all()
    )
    income_by_month = defaultdict(float)
    income_by_source = defaultdict(float)
    for txn in income_txns:
        month_key = txn.date.strftime("%Y-%m")
        income_by_month[month_key] += abs(txn.amount)
        cat = txn.category
        source_name = cat.display_name if cat else "Uncategorized"
        income_by_source[source_name] += abs(txn.amount)

    # ── 2. Monthly Expenses by Category ──
    expense_txns = (
        base_q.filter(Transaction.amount > 0)
        .filter(~Transaction.category_id.in_(excluded_ids))
        .all()
    )
    expenses_by_category = defaultdict(lambda: defaultdict(float))
    expenses_by_parent = defaultdict(float)
    total_expenses = 0.0

    # Build category lookup
    all_categories = {c.id: c for c in db.query(Category).all()}

    for txn in expense_txns:
        month_key = txn.date.strftime("%Y-%m")
        cat = all_categories.get(txn.category_id)
        if cat:
            parent = all_categories.get(cat.parent_id) if cat.parent_id else cat
            parent_name = parent.display_name if parent else "Other"
            cat_name = cat.display_name
        else:
            parent_name = "Uncategorized"
            cat_name = "Uncategorized"
        expenses_by_category[parent_name][cat_name] += txn.amount
        expenses_by_parent[parent_name] += txn.amount
        total_expenses += txn.amount

    # ── 3. Recurring Charges ──
    recurring_categories = db.query(Category).filter(
        Category.is_recurring == True,
        Category.parent_id.isnot(None),
    ).all()

    recurring_charges = []
    for cat in recurring_categories:
        # Get last 3 months of this category
        three_months_ago = today - timedelta(days=90)
        recent_txns = (
            db.query(Transaction)
            .filter(
                Transaction.category_id == cat.id,
                Transaction.status.in_(["confirmed", "auto_confirmed"]),
                Transaction.date >= three_months_ago,
                Transaction.amount > 0,
            )
            .order_by(Transaction.date.desc())
            .all()
        )
        if recent_txns:
            monthly_amounts = defaultdict(float)
            for txn in recent_txns:
                mk = txn.date.strftime("%Y-%m")
                monthly_amounts[mk] += txn.amount
            avg_monthly = sum(monthly_amounts.values()) / max(len(monthly_amounts), 1)
            parent = all_categories.get(cat.parent_id)
            recurring_charges.append({
                "name": cat.display_name,
                "parent": parent.display_name if parent else "Other",
                "avg_monthly": round(avg_monthly, 2),
                "months_active": len(monthly_amounts),
                "last_amount": round(recent_txns[0].amount, 2),
            })

    recurring_charges.sort(key=lambda x: -x["avg_monthly"])
    total_recurring = sum(r["avg_monthly"] for r in recurring_charges)

    # ── 4. Cash Flow Trend (Monthly) ──
    twelve_months_ago = date(current_year - 1, current_month, 1)
    monthly_cashflow = []
    for i in range(12):
        m = current_month - 11 + i
        y = current_year
        if m <= 0:
            m += 12
            y -= 1
        month_start = date(y, m, 1)
        if m == 12:
            month_end = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(y, m + 1, 1) - timedelta(days=1)

        month_income = (
            db.query(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(
                Transaction.status.in_(["confirmed", "auto_confirmed"]),
                Transaction.date >= month_start,
                Transaction.date <= month_end,
                Transaction.amount < 0,
                ~Transaction.category_id.in_(excluded_ids),
            )
            .scalar()
        )
        month_expenses = (
            db.query(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(
                Transaction.status.in_(["confirmed", "auto_confirmed"]),
                Transaction.date >= month_start,
                Transaction.date <= month_end,
                Transaction.amount > 0,
                ~Transaction.category_id.in_(excluded_ids),
            )
            .scalar()
        )
        monthly_cashflow.append({
            "month": f"{y}-{m:02d}",
            "income": round(abs(month_income), 2),
            "expenses": round(month_expenses, 2),
            "net": round(abs(month_income) - month_expenses, 2),
        })

    # ── 5. Budget vs Actual (Current Month) ──
    current_month_str = f"{current_year}-{current_month:02d}"
    budgets = db.query(Budget).filter(Budget.month == current_month_str).all()
    budget_items = []
    for b in budgets:
        cat = all_categories.get(b.category_id)
        if not cat:
            continue
        spent = (
            db.query(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(
                Transaction.category_id == b.category_id,
                Transaction.status.in_(["confirmed", "auto_confirmed"]),
                Transaction.amount > 0,
                func.strftime("%Y-%m", Transaction.date) == current_month_str,
            )
            .scalar()
        )
        budget_items.append({
            "category": cat.display_name,
            "budgeted": round(b.amount, 2),
            "spent": round(spent, 2),
            "remaining": round(b.amount - spent, 2),
            "pct_used": round(spent / b.amount * 100, 1) if b.amount > 0 else 0,
        })
    budget_items.sort(key=lambda x: -x["pct_used"])

    # ── 6. Account Balances ──
    accounts = db.query(Account).all()
    account_balances = []
    total_checking = 0.0
    total_savings = 0.0
    total_credit_debt = 0.0

    for acct in accounts:
        bal = acct.balance_current or 0
        entry = {
            "name": acct.name,
            "type": acct.account_type,
            "institution": acct.institution,
            "balance": round(bal, 2),
        }
        if acct.account_type == "checking":
            total_checking += bal
        elif acct.account_type == "savings":
            total_savings += bal
        elif acct.account_type == "credit":
            total_credit_debt += abs(bal)
            entry["limit"] = acct.balance_limit
        account_balances.append(entry)

    # ── 7. Investment Summary ──
    investment_summary = None
    if inv_db:
        try:
            from ..models_investments import InvestmentAccount, Holding, Security
            inv_accounts = inv_db.query(InvestmentAccount).all()
            if inv_accounts:
                latest_date = inv_db.query(func.max(Holding.as_of_date)).scalar()
                if latest_date:
                    holdings = inv_db.query(Holding).filter(
                        Holding.as_of_date == latest_date
                    ).all()
                    total_value = sum(h.current_value or 0 for h in holdings)
                    total_cost = sum(h.cost_basis or 0 for h in holdings)
                    investment_summary = {
                        "total_value": round(total_value, 2),
                        "total_cost_basis": round(total_cost, 2),
                        "gain_loss": round(total_value - total_cost, 2),
                        "gain_loss_pct": round((total_value - total_cost) / total_cost * 100, 2) if total_cost > 0 else 0,
                        "num_accounts": len(inv_accounts),
                        "account_names": [a.account_name for a in inv_accounts],
                    }
        except Exception as e:
            logger.warning(f"Failed to get investment summary: {e}")

    # ── 8. Savings Progress ──
    total_income_ytd = sum(m["income"] for m in monthly_cashflow if m["month"] >= f"{current_year}-01")
    total_expenses_ytd = sum(m["expenses"] for m in monthly_cashflow if m["month"] >= f"{current_year}-01")
    net_savings_ytd = total_income_ytd - total_expenses_ytd
    avg_monthly_net = net_savings_ytd / max(current_month, 1)
    remaining_months = 12 - current_month
    liquid_savings = total_checking + total_savings

    if remaining_months > 0:
        required_monthly_savings = (savings_goal - net_savings_ytd) / remaining_months
    else:
        required_monthly_savings = savings_goal - net_savings_ytd

    # Monthly savings rate
    avg_monthly_income = total_income_ytd / max(current_month, 1)
    savings_rate = (avg_monthly_net / avg_monthly_income * 100) if avg_monthly_income > 0 else 0

    savings_progress = {
        "goal": savings_goal,
        "net_saved_ytd": round(net_savings_ytd, 2),
        "liquid_savings": round(liquid_savings, 2),
        "avg_monthly_net_savings": round(avg_monthly_net, 2),
        "savings_rate_pct": round(savings_rate, 1),
        "remaining_months": remaining_months,
        "required_monthly_savings": round(required_monthly_savings, 2),
        "on_track": avg_monthly_net >= required_monthly_savings if remaining_months > 0 else net_savings_ytd >= savings_goal,
    }

    # ── 9. Top Spending Categories (Year-to-date) ──
    top_categories = sorted(
        [{"name": k, "total": round(v, 2)} for k, v in expenses_by_parent.items()],
        key=lambda x: -x["total"],
    )[:10]

    # Subcategory detail for top 5
    top_categories_detail = []
    for parent in top_categories[:5]:
        subs = sorted(
            [{"name": k, "total": round(v, 2)} for k, v in expenses_by_category[parent["name"]].items()],
            key=lambda x: -x["total"],
        )
        top_categories_detail.append({
            "parent": parent["name"],
            "total": parent["total"],
            "subcategories": subs,
        })

    return {
        "as_of": today.isoformat(),
        "year": current_year,
        "months_elapsed": current_month,
        "income": {
            "total_ytd": round(total_income_ytd, 2),
            "by_month": dict(sorted(income_by_month.items())),
            "by_source": dict(sorted(income_by_source.items(), key=lambda x: -x[1])),
            "avg_monthly": round(avg_monthly_income, 2),
        },
        "expenses": {
            "total_ytd": round(total_expenses_ytd, 2),
            "avg_monthly": round(total_expenses_ytd / max(current_month, 1), 2),
            "top_categories": top_categories,
            "top_categories_detail": top_categories_detail,
        },
        "recurring": {
            "charges": recurring_charges,
            "total_monthly": round(total_recurring, 2),
            "total_annual_projected": round(total_recurring * 12, 2),
        },
        "cashflow": {
            "monthly": monthly_cashflow,
        },
        "budget": {
            "month": current_month_str,
            "items": budget_items,
        },
        "accounts": {
            "balances": account_balances,
            "total_checking": round(total_checking, 2),
            "total_savings": round(total_savings, 2),
            "total_credit_debt": round(total_credit_debt, 2),
        },
        "investments": investment_summary,
        "savings_progress": savings_progress,
    }


def format_snapshot_for_prompt(snapshot: dict) -> str:
    """Convert the snapshot dict into a readable text block for the AI prompt."""
    lines = []
    s = snapshot

    lines.append(f"=== FINANCIAL SNAPSHOT (as of {s['as_of']}) ===")
    lines.append(f"Year: {s['year']} | Months elapsed: {s['months_elapsed']}")
    lines.append("")

    # Income
    inc = s["income"]
    lines.append("── INCOME ──")
    lines.append(f"Total YTD: ${inc['total_ytd']:,.2f} | Monthly avg: ${inc['avg_monthly']:,.2f}")
    if inc["by_source"]:
        lines.append("Sources:")
        for src, amt in inc["by_source"].items():
            lines.append(f"  - {src}: ${amt:,.2f}")
    lines.append("Monthly breakdown:")
    for month, amt in inc["by_month"].items():
        lines.append(f"  {month}: ${amt:,.2f}")
    lines.append("")

    # Expenses
    exp = s["expenses"]
    lines.append("── EXPENSES ──")
    lines.append(f"Total YTD: ${exp['total_ytd']:,.2f} | Monthly avg: ${exp['avg_monthly']:,.2f}")
    lines.append("Top categories (YTD):")
    for cat in exp["top_categories"]:
        lines.append(f"  - {cat['name']}: ${cat['total']:,.2f}")
    if exp["top_categories_detail"]:
        lines.append("Detailed breakdown (top 5):")
        for parent in exp["top_categories_detail"]:
            lines.append(f"  {parent['parent']} (${parent['total']:,.2f}):")
            for sub in parent["subcategories"]:
                lines.append(f"    - {sub['name']}: ${sub['total']:,.2f}")
    lines.append("")

    # Recurring
    rec = s["recurring"]
    lines.append("── RECURRING CHARGES ──")
    lines.append(f"Total monthly recurring: ${rec['total_monthly']:,.2f} | Annual projected: ${rec['total_annual_projected']:,.2f}")
    for charge in rec["charges"]:
        lines.append(f"  - {charge['name']} ({charge['parent']}): ${charge['avg_monthly']:,.2f}/mo (last: ${charge['last_amount']:,.2f})")
    lines.append("")

    # Cash Flow
    lines.append("── MONTHLY CASH FLOW (Last 12 Months) ──")
    for m in s["cashflow"]["monthly"]:
        net_sign = "+" if m["net"] >= 0 else ""
        lines.append(f"  {m['month']}: Income ${m['income']:,.2f} | Expenses ${m['expenses']:,.2f} | Net {net_sign}${m['net']:,.2f}")
    lines.append("")

    # Budget
    bud = s["budget"]
    if bud["items"]:
        lines.append(f"── BUDGET vs ACTUAL ({bud['month']}) ──")
        for item in bud["items"]:
            status = "OVER" if item["pct_used"] > 100 else "OK"
            lines.append(f"  - {item['category']}: ${item['spent']:,.2f} / ${item['budgeted']:,.2f} ({item['pct_used']:.0f}%) [{status}]")
        lines.append("")

    # Accounts
    accts = s["accounts"]
    lines.append("── ACCOUNT BALANCES ──")
    for a in accts["balances"]:
        extra = f" (limit: ${a['limit']:,.2f})" if a.get("limit") else ""
        lines.append(f"  - {a['name']} ({a['type']}): ${a['balance']:,.2f}{extra}")
    lines.append(f"Total checking: ${accts['total_checking']:,.2f}")
    lines.append(f"Total savings: ${accts['total_savings']:,.2f}")
    lines.append(f"Total credit card debt: ${accts['total_credit_debt']:,.2f}")
    lines.append("")

    # Investments
    inv = s["investments"]
    if inv:
        lines.append("── INVESTMENT PORTFOLIO ──")
        lines.append(f"Total value: ${inv['total_value']:,.2f}")
        lines.append(f"Cost basis: ${inv['total_cost_basis']:,.2f}")
        lines.append(f"Gain/Loss: ${inv['gain_loss']:,.2f} ({inv['gain_loss_pct']:.1f}%)")
        lines.append(f"Accounts: {', '.join(inv['account_names'])}")
        lines.append("")

    # Savings Goal
    sp = s["savings_progress"]
    lines.append("── SAVINGS GOAL PROGRESS ──")
    lines.append(f"Goal: ${sp['goal']:,.2f} by end of {s['year']}")
    lines.append(f"Net saved YTD: ${sp['net_saved_ytd']:,.2f}")
    lines.append(f"Liquid savings (checking + savings): ${sp['liquid_savings']:,.2f}")
    lines.append(f"Avg monthly net savings: ${sp['avg_monthly_net_savings']:,.2f}")
    lines.append(f"Savings rate: {sp['savings_rate_pct']:.1f}%")
    lines.append(f"Remaining months: {sp['remaining_months']}")
    lines.append(f"Required monthly savings to hit goal: ${sp['required_monthly_savings']:,.2f}")
    lines.append(f"On track: {'YES' if sp['on_track'] else 'NO'}")

    return "\n".join(lines)
