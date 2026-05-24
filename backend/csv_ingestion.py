"""
Simple - CSV Ingestion
Ανάλυση και εισαγωγή CSV αρχείων στο Neo4j.
"""

import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any

from config import BASE_DIR

# =============================================================================
# CSV ANALYSIS
# =============================================================================
def analyze_csv(
    file_path: str, 
    mapping_path: str = None,
    mode: str = "dry_run"
) -> Dict[str, Any]:
    """
    Analyze a CSV file and suggest field mappings.
    
    Args:
        file_path: Path to CSV file
        mapping_path: Path to field mapping JSON (optional)
        mode: "dry_run" (preview only) or "execute" (actually import)
    
    Returns:
        Dict with suggested_mapping, cypher_preview, rows_used
    """
    # Load CSV
    df = pd.read_csv(file_path, sep=";")
    
    # Load field mapping
    if mapping_path is None:
        mapping_path = BASE_DIR / "field_mapping.json"
    else:
        mapping_path = Path(mapping_path)
    
    if mapping_path.exists():
        with open(mapping_path, encoding="utf-8") as f:
            mapping = json.load(f)
    else:
        mapping = {}
    
    # Match columns to fields
    suggestions = {}
    for col in df.columns:
        matched_field = mapping.get(col)
        if matched_field:
            suggestions[col] = matched_field
    
    # Generate preview Cypher statements
    cypher_statements = []
    preview_rows = df.head(3).to_dict(orient="records")
    
    for row in preview_rows:
        sets = []
        for col, field in suggestions.items():
            val = row.get(col)
            if val is not None:
                val_str = f'"{val}"' if isinstance(val, str) else str(val)
                sets.append(f"{field} = {val_str}")
        
        if sets:
            # Try to find a reference number for MERGE
            ref = row.get("REFERENCE_NUMBER") or row.get("reference_number") or row.get("id")
            if ref:
                cypher = f'MERGE (c:Contract {{reference_number: "{ref}"}})\nSET ' + ", ".join(sets)
                cypher_statements.append(cypher)
    
    return {
        "suggested_mapping": suggestions,
        "cypher_preview": cypher_statements,
        "rows_used": preview_rows
    }

# =============================================================================
# CSV IMPORT (Full)
# =============================================================================
def import_csv_to_neo4j(
    file_path: str,
    mapping_path: str = None,
    batch_size: int = 500
) -> Dict[str, Any]:
    """
    Import CSV data to Neo4j using high-performance UNWIND batches.
    """
    from database import execute_cypher
    
    # 1. Load Data
    df = pd.read_csv(file_path, sep=";")
    df = df.where(pd.notnull(df), None) # Handle NaNs
    
    # 2. Get Mapping
    if mapping_path is None:
        mapping_path = BASE_DIR / "field_mapping.json"
    with open(mapping_path, encoding="utf-8") as f:
        mapping = json.load(f)
    
    # Filter columns that are in our mapping
    active_cols = {col: mapping[col] for col in df.columns if col in mapping}
    
    # 3. Ingestion Query (The "Master" query)
    # This query handles normalized nodes and temporal dates
    ingest_query = """
    UNWIND $batch AS row
    // 1. Create/Merge Contract
    MERGE (c:Contract {reference_number: row.ref})
    SET c += row.props
    
    // 2. Handle Date Conversion
    WITH c, row
    WHERE row.signed_date IS NOT NULL
    SET c.signed_date = CASE 
        WHEN row.signed_date =~ '\\d{4}-\\d{2}-\\d{2}.*' THEN date(substring(row.signed_date, 0, 10))
        WHEN row.signed_date =~ '\\d{4}/\\d{2}/\\d{2}.*' THEN date(replace(substring(row.signed_date, 0, 10), '/', '-'))
        ELSE null
    END
    
    // 3. Normalized Authority
    WITH c, row
    WHERE row.authority_name IS NOT NULL
    MERGE (a:Authority {name: row.authority_name})
    MERGE (a)-[:AWARDS]->(c)
    
    // 4. Normalized Contractor
    WITH c, row
    WHERE row.contractor_name IS NOT NULL
    MERGE (co:Company {name: row.contractor_name})
    MERGE (c)-[:AWARDED_TO]->(co)
    
    // 5. Normalized CPV
    WITH c, row
    WHERE row.cpv_code IS NOT NULL
    MERGE (cpv:CPV {code: row.cpv_code})
    MERGE (c)-[:HAS_CPV]->(cpv)
    """
    
    rows_processed = 0
    batches = [df[i:i + batch_size] for i in range(0, df.shape[0], batch_size)]
    
    print(f"📦 Starting ingestion of {len(df)} rows in {len(batches)} batches...")
    
    for i, batch_df in enumerate(batches):
        batch_data = []
        for _, row in batch_df.iterrows():
            # Prepare properties
            props = {}
            for col, field in active_cols.items():
                # Extract clean field name (e.g. "Contract.title" -> "title")
                if "." in field:
                    _, clean_field = field.split(".", 1)
                    props[clean_field] = row[col]
            
            ref = row.get("REFERENCE_NUMBER") or row.get("reference_number") or row.get("id")
            
            # Extract common entities (if available in row)
            auth_name = row.get("AUTHORITY_NAME") or row.get("authority_name")
            cont_name = row.get("CONTRACTOR_NAME") or row.get("contractor_name")
            cpv = row.get("CPV_CODE") or row.get("cpv_code")
            s_date = row.get("SIGNED_DATE") or row.get("signed_date")
            
            batch_data.append({
                "ref": str(ref),
                "props": props,
                "authority_name": auth_name,
                "contractor_name": cont_name,
                "cpv_code": str(cpv) if cpv else None,
                "signed_date": str(s_date) if s_date else None
            })
            
        # Execute Batch
        execute_cypher(ingest_query, {"batch": batch_data}, format_output=False)
        rows_processed += len(batch_data)
        print(f"   ✅ Batch {i+1}/{len(batches)} completed ({rows_processed} rows)")
        
    return {
        "success": True,
        "rows_processed": rows_processed
    }
