"""
Simple - Report Generator
Generation of Word (.docx) audit reports using Jinja2 templates.
Uses docxtpl for template-based document generation.
"""

import os
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from pathlib import Path

from config import (
    BASE_DIR, REPORTS_FOLDER, EXPORT_FOLDER, TEMPLATES_FOLDER,
    DirectAwardThresholds, EXCLUDED_CPV_CODES, get_threshold_for_cpv
)
from database import execute_cypher, get_predefined_query, run_queries_batch

# =============================================================================
# EXPORT PATH TRACKING
# =============================================================================
_latest_export_path = None

def save_export_path(path: str):
    """Save the path of the latest export."""
    global _latest_export_path
    _latest_export_path = path

def get_latest_export_path() -> Optional[str]:
    """Get the path of the latest export."""
    return _latest_export_path

# =============================================================================
# COMPLIANCE QUERIES (101-108, 500-501)
# =============================================================================
COMPLIANCE_QUERY_IDS = [101, 102, 103, 104, 105, 106, 107, 108, 500, 501]

def run_compliance_checks(authority: str, year: str) -> Dict[int, List[Dict]]:
    """Run all compliance check queries (101-108) for an authority."""
    return run_queries_batch(authority, year, COMPLIANCE_QUERY_IDS)

# =============================================================================
# DATA COLLECTION
# =============================================================================
def get_authority_statistics(authority: str, year: str) -> Dict[str, Any]:
    stats = {
        "total_awards": 0,
        "total_awards_value": 0.0,
        "procedures_count": [],
        "procedures_value": []
    }

    batch = run_queries_batch(authority, year, [201])

    total = batch.get(201, [])
    if total:
        stats["total_awards"] = total[0].get("total", 0)
        stats["total_awards_value"] = round(float(total[0].get("total_value", 0)), 2)

    # Q202/Q203 απαιτούν πεδίο τύπου διαδικασίας — δεν υπάρχει στη federated βάση

    return stats

def get_over_limit_cases(authority: str, year: str) -> Dict[str, Any]:
    """
    Εκτελεί ελέγχους S1–S4 απευθείας στη Neo4j με το σωστό schema.
    """
 
    # S1: Μεμονωμένες συμβάσεις > Όριο (δυναμικά από τον γράφο)
    q_s1 = '''
    MATCH (a:Buyer {name: $name})-[:AWARDS]->(c:Award)-[:HAS_CPV]->(cpv:CPV)-[:USE_THRESHOLD]->(t:Threshold)
    WHERE c.signed_date.year = $year
    AND c.Value > t.value
    RETURN c.title as Τίτλος,
           c.Value as Ποσό,
           cpv.code as CPV,
           c.signed_date as Ημερομηνία,
           t.value as Όριο
    ORDER BY c.Value DESC
    '''
 
    # S2: Άθροιση ανά CPV > Όριο
    q_s2 = '''
    MATCH (a:Buyer {name: $name})-[:AWARDS]->(c:Award)-[:HAS_CPV]->(cpv:CPV)-[:USE_THRESHOLD]->(t:Threshold)
    WHERE c.signed_date.year = $year
    WITH cpv.code as CPV, t.value as Όριο, sum(c.Value) as Σύνολο, count(c) as Πλήθος
    WHERE Σύνολο > Όριο
    RETURN CPV, Σύνολο, Πλήθος, Όριο
    ORDER BY Σύνολο DESC
    '''
 
    # S3: Άθροιση ανά CPV-5 > 30.000€ (Γενικό όριο για κλάσεις)
    q_s3 = '''
    MATCH (a:Buyer {name: $name})-[:AWARDS]->(c:Award)-[:HAS_CPV]->(cpv:CPV)
    WHERE c.signed_date.year = $year
    WITH left(cpv.code, 5) as CPV5, sum(c.Value) as Σύνολο, count(c) as Πλήθος
    WHERE Σύνολο > 30000
    RETURN CPV5, Σύνολο, Πλήθος
    ORDER BY Σύνολο DESC
    '''
 
    # S4: Άθροιση ανά ανάδοχο > 30.000€
    q_s4 = '''
    MATCH (a:Buyer {name: $name})-[:AWARDS]->(c:Award)-[:WON_BY]->(w:Winner)
    WHERE c.signed_date.year = $year
    WITH co.name as Ανάδοχος, sum(c.Value) as Σύνολο, count(c) as Πλήθος
    WHERE Σύνολο > 30000
    RETURN Ανάδοχος, Σύνολο, Πλήθος
    ORDER BY Σύνολο DESC
    '''
 
    params = {"name": authority, "year": int(year)}
 
    s1 = execute_cypher(q_s1, params, format_output=False) or []
    s2 = execute_cypher(q_s2, params, format_output=False) or []
    s3 = execute_cypher(q_s3, params, format_output=False) or []
    s4 = execute_cypher(q_s4, params, format_output=False) or []
 
    if not isinstance(s1, list): s1 = []
    if not isinstance(s2, list): s2 = []
    if not isinstance(s3, list): s3 = []
    if not isinstance(s4, list): s4 = []
 
    total_cases = len(s1)
    total_amount = sum(float(r.get("Ποσό", 0) or 0) for r in s1)
 
    over_limit_comment = (
        "Δεν εντοπίστηκαν μεμονωμένες απευθείας αναθέσεις με αξία πάνω από τα όρια."
        if total_cases == 0
        else f"Εντοπίστηκαν {total_cases} απευθείας αναθέσεις με αξία πάνω από 30.000€, "
             f"συνολικής αξίας {total_amount:,.2f}€."
    )
 
    return {
        "over_limit_summary": {
            "total_cases": total_cases,
            "total_amount": total_amount,
        },
        "over_limit_comment": over_limit_comment,
        "cpv_over_limit": s2,
        "cpv_over_limit_comment": (
            "Δεν εντοπίστηκαν CPV με αθροιστική υπέρβαση ορίων." if not s2
            else f"Εντοπίστηκαν {len(s2)} CPV με αθροιστική υπέρβαση ορίων."
        ),
        "cpv_class_over_limit": s3,
        "cpv_class_over_limit_comment": (
            "Δεν εντοπίστηκαν κλάσεις CPV-5 με αθροιστική υπέρβαση ορίων." if not s3
            else f"Εντοπίστηκαν {len(s3)} κλάσεις CPV-5 με υπέρβαση ορίων."
        ),
        "contractor_over_limit": s4,
        "contractor_over_limit_comment": (
            "Δεν εντοπίστηκαν ανάδοχοι με αθροιστικές υπερβάσεις ορίων." if not s4
            else f"Εντοπίστηκαν {len(s4)} ανάδοχοι με αθροιστική υπέρβαση ορίων."
        ),
    }
def get_flagged_awards_table(authority: str, year: str) -> str:
    query = '''
    MATCH (a:Buyer)-[:AWARDS]-(c:Award)
    WHERE a.name = $name 
    AND c.signed_date.year = $year
    AND c.procedure IN ["6", "16"]
    AND toFloat(c.Value) > 30000
    RETURN c.title as description,
           c.Value as amount,
           c.cpv as cpv,
           c.signed_date as date
    ORDER BY toFloat(c.Value) DESC
    LIMIT 50
    '''
    result = execute_cypher(query, {"name": authority, "year": int(year)}, format_output=False)
 
    if not result or not isinstance(result, list):
        return "Δεν εντοπίστηκαν συμβάσεις με υπέρβαση ορίων."
 
    lines = ["Πίνακας: Συμβάσεις απευθείας ανάθεσης με υπέρβαση ορίου\n"]
    for i, r in enumerate(result, 1):
        lines.append(
            f"{i}. {str(r.get('description',''))[:60]} | "
            f"{float(r.get('amount',0)):,.2f}€ | "
            f"CPV: {r.get('cpv','')} | "
            f"{r.get('date','')}"
        )
    return "\n".join(lines)
# =============================================================================
# MAIN REPORT GENERATION (using docxtpl)
# =============================================================================
def generate_report_for_authority(
    authority: str,
    year: str = None,
    audit_order_number: str = "",
    inspectors: str = "",
    period: str = ""
) -> str:
    """
    Generate audit report using docxtpl template.
    
    Args:
        authority: Authority name
        year: Year for audit (default: current year)
        audit_order_number: Audit order reference number
        inspectors: Names of inspectors
        period: Audit period description
    
    Returns:
        Path to generated .docx file
    """
    try:
        from docxtpl import DocxTemplate
    except ImportError:
        raise ImportError("docxtpl not installed. Run: pip install docxtpl")
    
    # Default year
    if not year:
        year = str(date.today().year)
    
    # Default period
    if not period:
        period = f"01/01/{year} - 31/12/{year}"
    
    # Template path
    template_path = TEMPLATES_FOLDER / "report_template.docx"
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    # Load template
    doc = DocxTemplate(str(template_path))
    
    # Collect data
    stats = get_authority_statistics(authority, year)
    over_limit = get_over_limit_cases(authority, year)
    flagged_table = get_flagged_awards_table(authority, year)
    
    # Generate summary comment
    summary_findings = generate_summary_comment(authority, stats, over_limit)
    
    # Greek month name
    month_names = {
        1: "Ιανουάριος", 2: "Φεβρουάριος", 3: "Μάρτιος", 4: "Απρίλιος",
        5: "Μάιος", 6: "Ιούνιος", 7: "Ιούλιος", 8: "Αύγουστος",
        9: "Σεπτέμβριος", 10: "Οκτώβριος", 11: "Νοέμβριος", 12: "Δεκέμβριος"
    }
    current_month = month_names.get(date.today().month, "")
    
    # Build context
    context = {
        # Basic info
        "year": date.today().year,
        "month": current_month,
        "authority_name": authority,
        "authority": authority,
        "audit_order_number": audit_order_number or f"ΕΛ-{year}/XXXX",
        "inspectors": inspectors or "Επιθεωρητής Α', Επιθεωρητής Β'",
        "period": period,
        
        # Statistics
        "total_awards": stats["total_awards"],
        "total_awards_value": f"{stats['total_awards_value']:,.2f}".replace(",", "."),
        "procedures_count": stats["procedures_count"],
        "procedures_value": stats["procedures_value"],
        
        # Over limit data
        "over_limit_summary": over_limit["over_limit_summary"],
        "over_limit_comment": over_limit["over_limit_comment"],
        "cpv_over_limit": over_limit["cpv_over_limit"],
        "cpv_over_limit_comment": over_limit["cpv_over_limit_comment"],
        "cpv_class_over_limit": over_limit["cpv_class_over_limit"],
        "cpv_class_over_limit_comment": over_limit["cpv_class_over_limit_comment"],
        "contractor_over_limit": over_limit["contractor_over_limit"],
        "contractor_over_limit_comment": over_limit["contractor_over_limit_comment"],
        
        # Summary and appendix
        "summary_findings_comment": summary_findings,
        "total_flagged_awards": flagged_table
    }
    
    # Render template
    doc.render(context)
    
    # Save output
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_authority = "".join(c if c.isalnum() else "_" for c in authority)[:30]
    filename = f"audit_{safe_authority}_{year}_{timestamp}.docx"
    
    output_path = REPORTS_FOLDER / filename
    doc.save(str(output_path))
    
    save_export_path(str(output_path))
    
    print(f"✅ Δημιουργήθηκε έκθεση: {output_path}")
    return str(output_path)

def generate_summary_comment(authority: str, stats: Dict, over_limit: Dict) -> str:
    """Generate summary findings comment for the report."""
    total_cases = over_limit["over_limit_summary"]["total_cases"]
    total_amount = over_limit["over_limit_summary"]["total_amount"]
    
    if total_cases == 0:
        return f"Από τον έλεγχο του φορέα {authority} δεν προέκυψαν ευρήματα υπέρβασης των ορίων απευθείας ανάθεσης του ν.4412/2016."
    
    comment = f"Από τον έλεγχο του φορέα {authority} προέκυψαν {total_cases} περιπτώσεις "
    comment += f"απευθείας αναθέσεων με υπέρβαση των νομίμων ορίων, συνολικής αξίας {total_amount:,.2f}€. "
    
    if over_limit["cpv_over_limit"]:
        comment += f"Επίσης, διαπιστώθηκαν {len(over_limit['cpv_over_limit'])} κωδικοί CPV "
        comment += "με αθροιστική υπέρβαση ορίων. "
    
    if over_limit["contractor_over_limit"]:
        comment += f"Εντοπίστηκαν {len(over_limit['contractor_over_limit'])} οικονομικοί φορείς "
        comment += "που έλαβαν αθροιστικά αναθέσεις πέραν των ορίων."
    
    return comment.replace(",", ".")

# =============================================================================
# LEGACY FUNCTIONS (for backward compatibility)
# =============================================================================
def generate_full_audit_report(
    authority: str,
    year: str,
    audit_order: str = "",
    inspectors: str = ""
) -> str:
    """Legacy wrapper - redirects to template-based generation."""
    return generate_report_for_authority(
        authority=authority,
        year=year,
        audit_order_number=audit_order,
        inspectors=inspectors
    )

def run_illegal_award_checks_and_export_docx(year: str = "2024") -> str:
    """
    Συνολική έκθεση μη νόμιμων απευθείας αναθέσεων για όλες τις αρχές.
    """
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        raise ImportError("python-docx not installed. Run: pip install python-docx")
 
    # Βρες όλες τις αρχές με απευθείας αναθέσεις > 30.000€
    query = '''
    MATCH (a:Buyer)-[:AWARDS]-(c:Award)
    WHERE c.signed_date.year = $year
    AND c.procedure IN ["6", "16"]
    AND toFloat(c.Value) > 30000
    RETURN DISTINCT a.name as authority
    ORDER BY a.name
    '''
    results = execute_cypher(query, {"year": int(year)}, format_output=False)
    if not isinstance(results, list):
        results = []
 
    doc = Document()
 
    title = doc.add_heading(
        f"Συγκεντρωτική Έκθεση Ελέγχου Απευθείας Αναθέσεων {year}", level=0
    )
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
 
    doc.add_paragraph(f"Ημερομηνία: {datetime.now().strftime('%d/%m/%Y')}")
    doc.add_paragraph(f"Πλήθος αναθετουσών αρχών με ευρήματα: {len(results)}")
    doc.add_paragraph()
 
    total_violations = 0
    total_amount = 0.0
 
    for record in results:
        authority_name = record.get("authority", "")
        if not authority_name:
            continue

        over_limit = get_over_limit_cases(authority_name, int(year))
        cases = over_limit["over_limit_summary"]["total_cases"]
        amount = over_limit["over_limit_summary"]["total_amount"]

        if cases == 0:
            continue

        doc.add_heading(authority_name, level=2)

        # --- S1: Μεμονωμένες συμβάσεις ---
        doc.add_heading("S1 – Μεμονωμένες συμβάσεις > 30.000€", level=3)
        doc.add_paragraph(f"Πλήθος: {cases}  |  Συνολικό ποσό: {amount:,.2f}€")

        # --- S2: Αθροιστική υπέρβαση ανά CPV ---
        s2 = over_limit["cpv_over_limit"]
        doc.add_heading("S2 – Αθροιστική υπέρβαση ανά CPV", level=3)
        if s2:
            table = doc.add_table(rows=1, cols=3)
            table.style = "Table Grid"
            hdr = table.rows[0].cells
            hdr[0].text, hdr[1].text, hdr[2].text = "CPV", "Σύνολο (€)", "Πλήθος"
            for row in s2:
                cells = table.add_row().cells
                cells[0].text = str(row.get("CPV", ""))
                cells[1].text = f"{float(row.get('Σύνολο', 0)):,.2f}"
                cells[2].text = str(row.get("Πλήθος", ""))
        else:
            doc.add_paragraph("Δεν εντοπίστηκαν αθροιστικές υπερβάσεις ανά CPV.")

        # --- S3: Αθροιστική υπέρβαση ανά CPV-5 ---
        s3 = over_limit["cpv_class_over_limit"]
        doc.add_heading("S3 – Αθροιστική υπέρβαση ανά κλάση CPV-5", level=3)
        if s3:
            table = doc.add_table(rows=1, cols=3)
            table.style = "Table Grid"
            hdr = table.rows[0].cells
            hdr[0].text, hdr[1].text, hdr[2].text = "CPV-5", "Σύνολο (€)", "Πλήθος"
            for row in s3:
                cells = table.add_row().cells
                cells[0].text = str(row.get("CPV5", ""))
                cells[1].text = f"{float(row.get('Σύνολο', 0)):,.2f}"
                cells[2].text = str(row.get("Πλήθος", ""))
        else:
            doc.add_paragraph("Δεν εντοπίστηκαν αθροιστικές υπερβάσεις ανά κλάση CPV-5.")

        # --- S4: Αθροιστική υπέρβαση ανά ανάδοχο ---
        s4 = over_limit["contractor_over_limit"]
        doc.add_heading("S4 – Αθροιστική υπέρβαση ανά ανάδοχο", level=3)
        if s4:
            table = doc.add_table(rows=1, cols=3)
            table.style = "Table Grid"
            hdr = table.rows[0].cells
            hdr[0].text, hdr[1].text, hdr[2].text = "Ανάδοχος", "Σύνολο (€)", "Πλήθος"
            for row in s4:
                cells = table.add_row().cells
                cells[0].text = str(row.get("Ανάδοχος", ""))
                cells[1].text = f"{float(row.get('Σύνολο', 0)):,.2f}"
                cells[2].text = str(row.get("Πλήθος", ""))
        else:
            doc.add_paragraph("Δεν εντοπίστηκαν αθροιστικές υπερβάσεις ανά ανάδοχο.")

        doc.add_paragraph()  # κενό διάστιχο

        total_violations += cases
        total_amount += amount
 
    filename = f"summary_report_{year}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
    filepath = EXPORT_FOLDER / filename
    doc.save(str(filepath))
    save_export_path(str(filepath))
 
    return str(filepath)

def generate_minimal_audit_report(authority: str, year: str) -> str:
    """Generate a minimal text-based report."""
    stats = get_authority_statistics(authority, year)
    over_limit = get_over_limit_cases(authority, year)
    
    report = f"""
=== Έκθεση Ελέγχου ===
Αναθέτουσα Αρχή: {authority}
Έτος: {year}
Ημερομηνία: {datetime.now().strftime('%d/%m/%Y')}

Στατιστικά:
- Συνολικές αναθέσεις: {stats['total_awards']}
- Συνολική αξία: {stats['total_awards_value']:,.2f}€

Ευρήματα:
- Υπερβάσεις ορίων: {over_limit['over_limit_summary']['total_cases']}
- Ποσό υπερβάσεων: {over_limit['over_limit_summary']['total_amount']:,.2f}€

Top 5 Ανάδοχοι με υπερβάσεις:
"""
    
    for contractor in over_limit["contractor_over_limit"][:5]:
        report += f"  - {contractor['name']}: {contractor['total']:,.2f}€\n"
    
    return report.replace(",", ".")
