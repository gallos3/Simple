
from database import execute_cypher

def check_counts():
    # 1. Total Awards for Athens (Any year)
    q1 = 'MATCH (b:Buyer {name: "Δήμος Αθηναίων"})-[:AWARDS]->(a:Award) RETURN count(a) as cnt'
    # 2. Total Awards in 2024 (Any buyer)
    q2 = 'MATCH (a:Award) WHERE a.signed_date.year = 2024 RETURN count(a) as cnt'
    # 3. Awards for Athens in 2024
    q3 = 'MATCH (b:Buyer {name: "Δήμος Αθηναίων"})-[:AWARDS]->(a:Award) WHERE a.signed_date.year = 2024 RETURN count(a) as cnt'
    
    print(f"Athens Total: {execute_cypher(q1, format_output=False)}")
    print(f"Global 2024 Total: {execute_cypher(q2, format_output=False)}")
    print(f"Athens 2024 Total: {execute_cypher(q3, format_output=False)}")

if __name__ == "__main__":
    check_counts()
