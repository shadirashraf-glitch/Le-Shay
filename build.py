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

# Owner funding ledger
inv = [{k: (v.strip() if isinstance(v, str) else v) for k, v in r.items()} for r in rd("investment_ledger.csv")]
for r in inv: r["amount_inr"] = int(r["amount_inr"])
adv = [dict(r, amount=int(r["amount"])) for r in rd("cash_advances.csv")]
cash = rd("cashbook.csv")
pending = [dict(r, amount=int(r["amount"])) for r in rd("pending.csv")]

EXPECT = {"Pre-opening investment": 1000359, "Operational cash advance": 106149, "October salaries": 20000,
          "October electricity": 15000, "Owner-funded stock": 4400}
cls = {}
for r in inv: cls[r["classification"]] = cls.get(r["classification"], 0) + r["amount_inr"]
problems = []
if len(inv) != 145: problems.append(f"expected 145 ledger rows, found {len(inv)}")
if len({r['transaction_id'] for r in inv}) != len(inv): problems.append("duplicate transaction IDs")
if sum(r["amount_inr"] for r in inv) != 1145908: problems.append(f"ledger total {sum(r['amount_inr'] for r in inv)} != 1145908")
if cls != EXPECT: problems.append(f"classification totals {cls} != {EXPECT}")
if sum(a["amount"] for a in adv) != EXPECT["Operational cash advance"]: problems.append("cash advance register does not match ledger")
dep = sum(r["amount_inr"] for r in inv if r["category"] == "Shop security deposit")
if dep != 150000: problems.append(f"deposit {dep} != 150000")
if problems: sys.exit("RECONCILIATION FAILED: " + "; ".join(problems))

out = {"updated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
       "sales": sales, "expenses": exp, "preopening": pre, "settings": cfg,
       "investment_ledger": inv, "funding_classes": cls, "deposit": dep,
       "cash_advances": adv, "cashbook": cash, "pending": pending}
json.dump(out, open(root / "ledger.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(sales), "days,", len(exp), "expense lines | funding reconciled:", sum(cls.values()), cls)
