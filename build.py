"""Rebuild data/ledger.json from the CSV files. Run after adding a day."""
import csv, json, datetime, pathlib
root = pathlib.Path(__file__).parent / "data"
rd = lambda n: list(csv.DictReader(open(root / n, encoding="utf-8")))
sales = []
for r in rd("sales.csv"):
    x = {"date": r["date"], "sales": int(r["sales"])}
    for k in ("kitchen", "juice"):
        if (r.get(k) or "").strip() != "": x[k] = int(r[k])
    if (r.get("note") or "").strip(): x["note"] = r["note"].strip()
    sales.append(x)
exp = [{"date": r["date"], "item": r["item"], "category": r["category"], "amount": int(r["amount"])} for r in rd("expenses.csv")]
pre = [{"date": r["date"], "item": r["item"], "amount": int(r["amount"])} for r in rd("preopening.csv")]
invb = [{"item": r["item"], "amount": int(r["amount"])} for r in rd("investment.csv")]
cfg = {r["key"]: r["value"] for r in rd("settings.csv")}
if "est_from" in cfg:
    for x in sales:
        if x["date"] >= cfg["est_from"]:
            for k in ("kitchen", "juice"):
                if k not in x:
                    x[k] = round(x["sales"] * float(cfg[k + "_pct"])); x[k + "_est"] = True
inv = next(r for r in rd("settings.csv") if r["key"] == "investment")
out = {"updated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
       "investment": int(inv["value"]), "investment_note": inv["note"], "sales": sales, "expenses": exp, "preopening": pre, "investment_items": invb}
json.dump(out, open(root / "ledger.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(sales), "days,", len(exp), "expense lines")
