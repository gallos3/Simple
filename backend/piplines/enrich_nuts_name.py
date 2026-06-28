import pandas as pd
from neo4j import GraphDatabase

# ---- ΡΥΘΜΙΣΕΙΣ ----
XLSX_PATH = "NUTS2021.xlsx"
SHEET_NAME = "NUTS & SR 2021"

import os

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")


# ---- ΔΙΑΒΑΖΟΥΜΕ EXCEL ----
df = pd.read_excel(XLSX_PATH, sheet_name=SHEET_NAME)

# Αναμένουμε columns:
# "Code 2021", "NUTS level", "NUTS level 1", "NUTS level 2", "NUTS level 3"
required_cols = {"Code 2021", "NUTS level", "NUTS level 1", "NUTS level 2", "NUTS level 3"}
missing = required_cols - set(df.columns)
if missing:
    raise ValueError(f"Missing columns in Excel sheet: {missing}")

# ---- ΦΤΙΑΧΝΟΥΜΕ MAP: code -> name, ανά level ----
# Στόχος: για κάθε code, να έχει το σωστό name που αντιστοιχεί στο επίπεδό του.
nuts_name_map: dict[str, str] = {}

for _, r in df.iterrows():
    code = r.get("Code 2021")
    lvl = r.get("NUTS level")

    if pd.isna(code) or pd.isna(lvl):
        continue

    code = str(code).strip()
    # κρατάμε μόνο ελληνικούς NUTS codes (EL...)
    if not code.startswith("EL"):
        continue

    try:
        lvl = int(lvl)
    except Exception:
        continue

    name = None
    if lvl == 1:
        name = r.get("NUTS level 1")
    elif lvl == 2:
        name = r.get("NUTS level 2")
    elif lvl == 3:
        name = r.get("NUTS level 3")
    else:
        # Level 0 (country) ή άλλα δεν μας χρειάζονται εδώ
        continue

    if isinstance(name, str):
        name = name.strip()
        if name:
            nuts_name_map[code] = name

if not nuts_name_map:
    raise RuntimeError("NUTS name map is empty. Check Excel sheet/columns.")

print(f"Loaded NUTS codes from Excel: {len(nuts_name_map)}")

# ---- UPDATE NEO4J ----
# Κανόνας:
# len(NUTS)=5 => map[NUTS] (NUTS3)
# len(NUTS)=4 => map[NUTS] (NUTS2)
# len(NUTS)=3 => map[NUTS] (NUTS1)
# γράφουμε σε property: NUTS_name

cypher = """
WITH $m AS m
MATCH (a:Buyer)
WHERE a.NUTS IS NOT NULL AND trim(toString(a.NUTS)) <> ""
WITH a, m, toString(a.NUTS) AS nuts
WITH a, m, nuts, size(nuts) AS nlen
SET a.NUTS_name =
CASE
  WHEN nlen = 5 THEN m[nuts]
  WHEN nlen = 4 THEN m[nuts]
  WHEN nlen = 3 THEN m[nuts]
  ELSE NULL
END
RETURN count(a) AS updated_count
"""

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
with driver.session() as session:
    res = session.run(cypher, m=nuts_name_map)
    updated = res.single()["updated_count"]
driver.close()

print(f"Done. Authorities updated: {updated}")
