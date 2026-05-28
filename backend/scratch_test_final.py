import sys
sys.stdout.reconfigure(encoding='utf-8')
from database import execute_cypher
from diagnostic_engine import calculate_full_diagnostics, get_diagnostic_reasoning

def test_final():
    buyer_name = "ΥΠΟΥΡΓΕΙΟ ΠΑΙΔΕΙΑΣ, ΕΡΕΥΝΑΣ ΚΑΙ ΘΡΗΣΚΕΥΜΑΤΩΝ"
    diag = calculate_full_diagnostics(authority_name=buyer_name, year="2024")
    
    print("\n[RECURRENCE]:")
    print(diag.get("recurrence"))
    
    print("\n[ICI]:")
    print(diag.get("ici"))

    print("\n" + "="*50)
    print("REASONING REPORT:")
    print("="*50)
    report = get_diagnostic_reasoning(diag)
    print(report)

if __name__ == "__main__":
    test_final()
