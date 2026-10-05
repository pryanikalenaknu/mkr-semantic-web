import csv
import json
import re
from datetime import datetime, timezone

import requests

ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "mkr1/1.0", "Accept": "application/sparql-results+json"}

COLUMNS = {
    "q1": ["item", "itemLabel", "value", "website"],
    "q2": ["region", "regionLabel", "cnt"],
    "q3": ["item", "itemLabel", "region", "regionLabel", "population"],
}


def run_query(query):
    response = requests.get(ENDPOINT, params={"query": query}, headers=HEADERS, timeout=120)
    response.raise_for_status()
    return response.json()["results"]["bindings"]


def save_csv(name, rows):
    with open(f"{name}.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS[name])
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, {}).get("value", "")
                             for column in COLUMNS[name]})


def first_value(rows, column):
    return rows[0][column]["value"] if rows else "—"


if __name__ == "__main__":
    query1 = open("q1.rq", encoding="utf-8").read()
    rows1 = run_query(query1)
    note = None

    if len(rows1) < 5:
        query1 = re.sub(r"\?value > \d+", "?value > 50", query1)
        rows1 = run_query(query1)
        note = "Примітка: Q1 повернув менше 5 рядків, поріг зменшено зі 100 до 50"
        with open("q1.rq", "w", encoding="utf-8") as f:
            f.write(query1)

    rows2 = run_query(open("q2.rq", encoding="utf-8").read())
    rows3 = run_query(open("q3.rq", encoding="utf-8").read())

    save_csv("q1", rows1)
    save_csv("q2", rows2)
    save_csv("q3", rows3)

    with open("meta.json", "w", encoding="utf-8") as f:
        json.dump({"retrieved_at": datetime.now(timezone.utc).isoformat()}, f, indent=2)

    answers = [
        f"Q1: {first_value(rows1, 'itemLabel')} — {first_value(rows1, 'value')}",
        f"Q2: {first_value(rows2, 'regionLabel')} — {first_value(rows2, 'cnt')}",
        f"Q3: {first_value(rows3, 'population')}",
    ]
    if note:
        answers.append(note)

    with open("ANSWERS.md", "w", encoding="utf-8") as f:
        f.write("\n".join(answers) + "\n")

    print(f"q1.csv: {len(rows1)} рядків")
    print(f"q2.csv: {len(rows2)} рядків")
    print(f"q3.csv: {len(rows3)} рядків")
    print()
    print("\n".join(answers))
