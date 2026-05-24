
from database import execute_cypher

def check_athens():
    query = 'MATCH (b:Buyer) WHERE b.name CONTAINS "Αθηνα" RETURN b.name as name, b.vat as vat'
    results = execute_cypher(query, format_output=False)
    for r in results:
        print(f"Name: {r['name']} | VAT: {r['vat']}")

if __name__ == "__main__":
    check_athens()
