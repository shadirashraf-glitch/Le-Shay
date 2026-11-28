"""Rebuild data/ledger.json from the CSV files, and check the owner-funding reconciliation.
Run after adding a day. Stops with an error if the investment ledger no longer reconciles."""
import csv, json, datetime, pathlib, sys
root = pathlib.Path(__file__).parent / "data"
rd = lambda n: list(csv.DictReader(open(root / n, encoding="utf-8-sig")))

# Daily trading records (unchanged history)
sales = []
for r in rd("sales.csv"):
    x = {"date": r["date"], "sales": int(r["sales"])}
    for k in ("kitchen", "juice"):
        v = (r.get(k) or "").strip()
        if v.startswith("~"): x[k] = int(v[1:]); x[k + "_est"] = True
        elif v != "": x[k] = int(v)
    if (r.get("note") or "").strip(): x["note"] = r["note"].strip()
    sales.append(x)
exp = [{"date": r["date"], "item": r["item"], "category": r["category"], "amount": int(r["amount"])} for r in rd("expenses.csv")]
pre = [{"date": r["date"], "item": r["item"], "amount": int(r["amount"])} for r in rd("preopening.csv")]
cfg = {r["key"]: r["value"] for r in rd("settings.csv")}
if "est_from" in cfg:
    for x in sales:
        if x["date"] >= cfg["est_from"]:
            for k in ("kitchen", "juice"):
                if k not in x:
                    x[k] = round(x["sales"] * float(cfg[k + "_pct"])); x[k + "_est"] = True

# Current period (new Daily Closing template from 16 Nov). History to 15 Nov stays in sales.csv / expenses.csv.
CUR_FROM = "2026-11-16"
if any(x["date"] >= CUR_FROM for x in sales) or any(e["date"] >= CUR_FROM for e in exp):
    sys.exit("RECONCILIATION FAILED: sales.csv / expenses.csv must stop at 15 Nov; use daily_closing.csv and purchases.csv")
fmt = lambda d: str(int(d[8:])) + " " + datetime.date(2000, int(d[5:7]), 1).strftime("%b")
I = lambda v: int(v) if str(v).strip() != "" else 0
closing = [dict(r) for r in rd("daily_closing.csv")]
# One name per supplier account (raw sheet wording stays in the CSV as written)
SUPPLIER = {"Fish": "Fish / Water", "Banana": "Banana / Ice cream"}
canon = lambda n: SUPPLIER.get(n.strip(), n.strip())
purch = [dict(r, supplier=canon(r["supplier"]), sheet_name=r["supplier"], bill=I(r["bill"]), paid=I(r["paid"]), due=I(r["due"])) for r in rd("purchases.csv")]
duepay = [dict(r, supplier=canon(r["supplier"]), amount=I(r["amount"])) for r in rd("due_payments.csv")]
STAFF = [("staff_wages", "Daily staff wages", "Staff"), ("shop_rent", "Shop rent", "Rent"), ("gku_salary", "GKU salary", "GKU salary"),
         ("room_rent", "Room rent", "Room rent"), ("electricity", "Electricity", "Utilities & misc"), ("firoz_salary", "Firoz salary", "Firoz salary")]
problems, warnings, grand, sup_due, prev_close = [], [], 0, {}, None
for c in closing:
    d = c["date"]; k, j_, ct, tot = I(c["kitchen"]), I(c["juice"]), I(c["counter"]), I(c["total_sales"])
    if k + j_ + ct != tot: problems.append(f"{d}: sections {k}+{j_}+{ct} != total {tot}")
    pl = [p for p in purch if p["date"] == d]
    for p in pl:
        if p["paid"] + p["due"] != p["bill"]: problems.append(f"{d} {p['supplier']}: paid+due != bill")
    paid_dues = [x for x in duepay if x["date"] == d]
    dp = sum(x["amount"] for x in paid_dues)
    # paid_total = all supplier payments that day (today's bills + earlier dues); due_total = net due movement
    for lab, got, key in (("bills", sum(p["bill"] for p in pl), "bills_total"), ("supplier payments", sum(p["paid"] for p in pl) + dp, "paid_total"),
                          ("net due movement", sum(p["due"] for p in pl) - dp, "due_total")):
        if got != I(c[key]): problems.append(f"{d}: {lab} {got} != sheet {c[key]}")
    for p in pl: sup_due[p["supplier"]] = sup_due.get(p["supplier"], 0) + p["due"]
    for x in paid_dues:
        if sup_due.get(x["supplier"], 0) < x["amount"]: warnings.append(f"{d}: {x['supplier']} paid {x['amount'] - max(sup_due.get(x['supplier'], 0), 0)} more than owed, held as a supplier credit")
        sup_due[x["supplier"]] = sup_due.get(x["supplier"], 0) - x["amount"]
    grand += I(c["due_total"])
    if c["grand_due"].strip() and I(c["grand_due"]) != grand: problems.append(f"{d}: grand due {grand} != sheet {c['grand_due']}")
    staff_paid = sum(I(c[f]) for f, _, _ in STAFF)
    into_till = sum(int(a["amount"]) - sum(int(x["amount"]) for x in rd("supplier_settlements.csv") if x.get("funded_from") == a["advance_id"])
                    for a in rd("cash_advances.csv") if a.get("till_date") == d and not a["source_transaction"])
    if prev_close is not None and I(c["opening_cash"]) != prev_close + into_till:
        warnings.append(f"{fmt(d)}: opening cash {I(c['opening_cash']):,} differs from expected {prev_close + into_till:,} (previous closing {prev_close:,} + advance remainder {into_till:,})")
    c["into_till"] = into_till
    cash_in = I(c["cash_sales"]) if c["cash_sales"].strip() else tot
    calc = I(c["opening_cash"]) + I(c["owner_cash"]) + cash_in - I(c["paid_total"]) - staff_paid
    prev_close = calc
    c.update(staff_paid=staff_paid, due_paid=sum(x["amount"] for x in paid_dues), grand_calc=grand, closing_calc=calc, cash_assumed=not c["cash_sales"].strip())
    if c["closing_cash"].strip() and I(c["closing_cash"]) != calc: warnings.append(f"{d}: closing cash on sheet {c['closing_cash']} vs formula {calc}")
    if calc < 0: warnings.append(f"{fmt(d)}: estimated funding gap, calculated closing cash {calc:,}. Not verified physical cash. Verify additional funding or unrecorded cash movements. No owner advance created without confirmation.")
    x = {"date": d, "sales": tot, "kitchen": k, "juice": j_, "period": "current"}
    sales.append(x)
    for p in pl:
        tag = "" if not p["due"] else (" · unpaid" if not p["paid"] else " · part unpaid")
        if (p.get("verify") or "").startswith("UNVERIFIED"):
            tag += " · unverified"; warnings.append(f"{fmt(d)}: {p['supplier']} {p['bill']:,} {p['verify'][len('UNVERIFIED: '):]}")
        exp.append({"date": d, "item": p["supplier"] + tag, "category": p["category"], "amount": p["bill"], "period": "current"})
    for f, label, cat in STAFF:
        if I(c[f]): exp.append({"date": d, "item": label, "category": cat, "amount": I(c[f]), "period": "current"})
if problems: sys.exit("RECONCILIATION FAILED (daily closing): " + "; ".join(problems))
for w in warnings: print("WARNING:", w)
open_items = [dict(r, amount=I(r["amount"])) for r in rd("open_items.csv")]
current = {"open_items": open_items, "from": CUR_FROM, "closing": closing, "purchases": purch, "due_payments": duepay, "grand_due": grand,
           "supplier_due": {k: v for k, v in sup_due.items() if v}, "warnings": warnings,
           "unverified": sorted({p["supplier"] for p in purch if (p.get("verify") or "").startswith("UNVERIFIED")})}

# Owner funding ledger
inv = [{k: (v.strip() if isinstance(v, str) else v) for k, v in r.items()} for r in rd("investment_ledger.csv")]
for r in inv: r["amount_inr"] = int(r["amount_inr"])
adv = [dict(r, amount=int(r["amount"])) for r in rd("cash_advances.csv")]
cash = rd("cashbook.csv")
pending = [dict(r, amount=int(r["amount"])) for r in rd("pending.csv")]
# Historical supplier outstanding to 15 Nov (fixed register) and owner settlements against it
pay = [dict(r, amount=int(r["amount"])) for r in rd("payables.csv")]
hist = [x for x in pay if x["period"].startswith("Historical")]
if len(hist) != 9 or sum(x["amount"] for x in hist) != 31799: sys.exit("RECONCILIATION FAILED: historical supplier outstanding != 9 balances / 31799")
setl = [dict(r, amount=int(r["amount"])) for r in rd("supplier_settlements.csv")]
ids = {x["due_id"] for x in pay}
for s_ in setl:
    if s_["due_id"] not in ids: sys.exit(f"RECONCILIATION FAILED: settlement {s_['settlement_id']} references unknown due {s_['due_id']}")
for x in pay:
    paid = [s_ for s_ in setl if s_["due_id"] == x["due_id"]]
    x["settled"] = sum(s_["amount"] for s_ in paid)
    if x["settled"] > x["amount"]: sys.exit(f"RECONCILIATION FAILED: {x['due_id']} settled {x['settled']} > {x['amount']}")
    x["outstanding"] = x["amount"] - x["settled"]
    x["status"] = "Settled" if x["outstanding"] == 0 else ("Part settled" if x["settled"] else "Unpaid")
    x["last_paid"] = max((s_["date"] for s_ in paid), default="")

EXPECT = {"Pre-opening investment": 1000359, "Operational cash advance": 106149, "October management salaries": 20000,
          "October electricity": 15000, "Owner-funded stock": 4400}
cls = {}
for r in inv: cls[r["classification"]] = cls.get(r["classification"], 0) + r["amount_inr"]
problems = []
if len(inv) != 145: problems.append(f"expected 145 ledger rows, found {len(inv)}")
if len({r['transaction_id'] for r in inv}) != len(inv): problems.append("duplicate transaction IDs")
if sum(r["amount_inr"] for r in inv) != 1145908: problems.append(f"ledger total {sum(r['amount_inr'] for r in inv)} != 1145908")
if cls != EXPECT: problems.append(f"classification totals {cls} != {EXPECT}")
if sum(a["amount"] for a in adv if a["source_transaction"]) != EXPECT["Operational cash advance"]: problems.append("ledger-linked cash advances do not match ledger")
for a in adv:
    a["funds_used"] = sum(x["amount"] for x in setl if x.get("funded_from") == a["advance_id"])
    a["remainder"] = a["amount"] - a["funds_used"] if not a["source_transaction"] else None
    if a["remainder"] is not None and a["remainder"] < 0: problems.append(f"{a['advance_id']}: settlements {a['funds_used']} exceed advance {a['amount']}")
for x in setl:
    if x.get("funded_from") and x["funded_from"] not in {a["advance_id"] for a in adv}: problems.append(f"{x['settlement_id']}: unknown advance {x['funded_from']}")
dep = sum(r["amount_inr"] for r in inv if r["category"] == "Shop security deposit")
if dep != 150000: problems.append(f"deposit {dep} != 150000")
if problems: sys.exit("RECONCILIATION FAILED: " + "; ".join(problems))

out = {"updated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
       "sales": sales, "expenses": exp, "preopening": pre, "settings": cfg,
       "investment_ledger": inv, "funding_classes": cls, "deposit": dep,
       "cash_advances": adv, "cashbook": cash, "pending": pending, "payables": pay, "settlements": setl, "current": current, "period_closed": "2026-11-15"}
json.dump(out, open(root / "ledger.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(sales), "days,", len(exp), "expense lines | funding reconciled:", sum(cls.values()), cls)
