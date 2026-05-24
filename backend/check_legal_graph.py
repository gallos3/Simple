from database import get_session

labels = ['LegalAct', 'Article', 'LegalConcept', 'ProcStage', 'LegalDecision']
with get_session() as s:
    print("\n=== Legal Knowledge Graph in Neo4j ===")
    for lbl in labels:
        r = s.run("MATCH (n:" + lbl + ") RETURN count(n) as c").single()
        print(f"  :{lbl:<20} {r['c']}")

    # Sample a few concepts
    print("\n--- Sample LegalConcepts ---")
    rows = s.run("MATCH (c:LegalConcept) RETURN c.name LIMIT 15")
    for row in rows:
        print(f"  {row['c.name']}")

    # Sample stages
    print("\n--- ProcStages ---")
    rows = s.run("MATCH (s:ProcStage) RETURN s.name")
    for row in rows:
        print(f"  {row['s.name']}")

    # Sample laws
    print("\n--- LegalActs ---")
    rows = s.run("MATCH (la:LegalAct) RETURN la.short_name, la.full_name LIMIT 10")
    for row in rows:
        print(f"  {row['la.short_name']} — {row['la.full_name']}")
