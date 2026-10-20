"""Rebuild data/ledger.json from the CSV files. Run after adding a day."""
import csv, json, datetime, pathlib
root = pathlib.Path(__file__).parent / "data"
rd = lambda n: list(csv.DictReader(open(root / n, encoding="utf-8")))
sales = [{"date": r["date"], "sales": int(r["sales"])} for r in rd("sales.csv")]
exp = [{"date": r["date"], "item": r["item"], "category": r["category"], "amount": int(r["amount"])} for r in rd("expenses.csv")]
pre = [{"date": r["date"], "item": r["item"], "amount": int(r["amount"])} for r in rd("preopening.csv")]
inv = next(r for r in rd("settings.csv") if r["key"] == "investment")
out = {"updated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
       "investment": int(inv["value"]), "investment_note": inv["note"], "sales": sales, "expenses": exp, "preopening": pre}
json.dump(out, open(root / "ledger.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(sales), "days,", len(exp), "expense lines")
