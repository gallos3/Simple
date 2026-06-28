import sys
import os
import json
import csv
import re
from datetime import datetime, timezone

import pandas as pd

# Ensure we can import from backend when script is in backend/scratch/
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(BACKEND_DIR)

from data_access.database import execute_cypher


EXPORT_DIR = os.path.join(BACKEND_DIR, "exports", "zenodo_sample")

OUTPUT_FILES = {
    "parquet": "simple_public_procurement_sample.parquet",
    "metadata": "simple_public_procurement_sample_metadata.json",
    "dictionary": "data_dictionary.csv",
    "readme": "README.md",
}


FORBIDDEN_CYPHER_PATTERNS = [
    r"\bCREATE\b",
    r"\bMERGE\b",
    r"\bSET\b",
    r"\bDELETE\b",
    r"\bDETACH\s+DELETE\b",
    r"\bREMOVE\b",
    r"\bDROP\b",
    r"\bLOAD\s+CSV\b",
    r"\bCALL\s+apoc\.periodic\b",
]


FORBIDDEN_COLUMN_TERMS = [
    "email",
    "phone",
    "telephone",
    "address",
    "contact",
    "person",
    "user",
    "prompt",
    "chat",
    "log",
    "embedding",
    "vector",
    "password",
    "token",
    "secret",
    "api_key",
]


def ensure_no_html_entities_in_cypher(cypher_query: str) -> None:
    if "-&gt;" in cypher_query or "&gt;" in cypher_query:
        raise ValueError("SECURITY HALT: HTML entity detected in Cypher query. Use real '->' arrows.")


def ensure_read_only_cypher(cypher_query: str) -> None:
    ensure_no_html_entities_in_cypher(cypher_query)

    for pattern in FORBIDDEN_CYPHER_PATTERNS:
        if re.search(pattern, cypher_query, flags=re.IGNORECASE):
            raise ValueError(f"SECURITY HALT: Forbidden write operation detected: {pattern}")


def output_paths():
    return {key: os.path.join(EXPORT_DIR, filename) for key, filename in OUTPUT_FILES.items()}


def ensure_no_overwrite(paths: dict, overwrite: bool) -> None:
    if overwrite:
        return

    existing = [path for path in paths.values() if os.path.exists(path)]
    if existing:
        msg = (
            "Export files already exist. Refusing to overwrite.\n\n"
            "Existing files:\n"
            + "\n".join(f"- {p}" for p in existing)
            + "\n\nRun with --overwrite if you intentionally want to regenerate them."
        )
        raise FileExistsError(msg)


def normalise_list_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Neo4j StringArray properties may arrive as Python lists.
    For maximum Parquet/Zenodo compatibility, convert list values to pipe-separated strings.
    """
    df = df.copy()

    for col in df.columns:
        if df[col].apply(lambda x: isinstance(x, list)).any():
            df[col] = df[col].apply(
                lambda x: " | ".join(str(v) for v in x) if isinstance(x, list) else x
            )

    return df


def drop_forbidden_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols_to_keep = [
        col
        for col in df.columns
        if not any(term in col.lower() for term in FORBIDDEN_COLUMN_TERMS)
    ]
    return df[cols_to_keep].copy()


def write_data_dictionary(dict_path: str) -> None:
    dictionary_data = [
        {
            "column": "source_dataset",
            "dtype": "string",
            "description": "Original public procurement source dataset.",
            "source_field": "Award.source",
            "notes": "Expected values may include TED or KIMDIS/KHMDHS depending on source ingestion.",
        },
        {
            "column": "notice_id",
            "dtype": "string",
            "description": "Public notice or award identifier.",
            "source_field": "Award.identifier",
            "notes": "Retained as public procurement record identifier.",
        },
        {
            "column": "original_id",
            "dtype": "string",
            "description": "Original public source system identifier.",
            "source_field": "Award.original_id",
            "notes": "Retained if part of the source public procurement record.",
        },
        {
            "column": "award_date",
            "dtype": "string",
            "description": "Submission, publication or award-related date as stored.",
            "source_field": "Award.submission_date",
            "notes": "Date is preserved as stored in Neo4j.",
        },
        {
            "column": "year",
            "dtype": "integer",
            "description": "Award or publication year.",
            "source_field": "Award.year",
            "notes": "",
        },
        {
            "column": "contract_value_eur",
            "dtype": "float",
            "description": "Contract value.",
            "source_field": "Award.value",
            "notes": "Monetary value is preserved exactly as stored in the database.",
        },
        {
            "column": "cpv_code",
            "dtype": "string",
            "description": "Common Procurement Vocabulary code.",
            "source_field": "Award.cpv_code",
            "notes": "",
        },
        {
            "column": "cpv_division",
            "dtype": "string",
            "description": "First two digits of CPV code.",
            "source_field": "Derived from Award.cpv_code",
            "notes": "Useful for CPV-aware aggregation and diagnostics.",
        },
        {
            "column": "nuts_region",
            "dtype": "string",
            "description": "NUTS territorial code if available.",
            "source_field": "Award.nuts_code",
            "notes": "",
        },
        {
            "column": "buyer_name",
            "dtype": "string",
            "description": "Contracting authority name.",
            "source_field": "Buyer.name",
            "notes": "Retained as public procurement identifier from official sources.",
        },
        {
            "column": "buyer_vat",
            "dtype": "string",
            "description": "Contracting authority VAT / public identifier.",
            "source_field": "Buyer.vat",
            "notes": "Retained as public procurement identifier from official sources.",
        },
        {
            "column": "buyer_sources",
            "dtype": "string",
            "description": "Public source references for buyer data.",
            "source_field": "Buyer.sources",
            "notes": "List-like values converted to pipe-separated string.",
        },
        {
            "column": "supplier_name",
            "dtype": "string",
            "description": "Winning supplier name.",
            "source_field": "Winner.name",
            "notes": "Retained as public procurement identifier from official sources.",
        },
        {
            "column": "supplier_vat",
            "dtype": "string",
            "description": "Winning supplier VAT / public identifier.",
            "source_field": "Winner.vat",
            "notes": "Retained as public procurement identifier from official sources.",
        },
        {
            "column": "supplier_sources",
            "dtype": "string",
            "description": "Public source references for supplier data.",
            "source_field": "Winner.sources",
            "notes": "List-like values converted to pipe-separated string.",
        },
    ]

    with open(dict_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["column", "dtype", "description", "source_field", "notes"],
        )
        writer.writeheader()
        writer.writerows(dictionary_data)


def write_readme(readme_path: str) -> None:
    readme_content = (
        "# Simple Procurement Intelligence — Zenodo Sample Dataset\n\n"
        "This sample dataset is derived from the active Simple Neo4j database and contains "
        "public procurement records primarily from TED and KIMDIS/KHMDHS.\n\n"
        "## Files\n\n"
        "- `simple_public_procurement_sample.parquet`: contract-level sample dataset\n"
        "- `simple_public_procurement_sample_metadata.json`: metadata and extraction notes\n"
        "- `data_dictionary.csv`: column-level data dictionary\n"
        "- `README.md`: this file\n\n"
        "## Notes\n\n"
        "- Financial values are preserved exactly as stored in the database.\n"
        "- Buyer and supplier names/VAT numbers are retained because they are public procurement identifiers from official public records.\n"
        "- Obvious contact, personal, internal logging, embedding/vector, prompt/chat and secret/token fields are excluded.\n"
        "- Free-text titles are excluded from this first sample to reduce uncontrolled text exposure.\n"
        "- The dataset is intended for Zenodo testing, reproducibility and software demonstration.\n"
        "- The dataset should not be used for official audit conclusions.\n\n"
        "## Loading the Dataset\n\n"
        "```python\n"
        "import pandas as pd\n\n"
        "df = pd.read_parquet('simple_public_procurement_sample.parquet')\n"
        "print(df.head())\n"
        "```\n"
    )

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)


def write_metadata(metadata_path: str, cypher_query: str, df: pd.DataFrame) -> None:
    metadata = {
        "title": "Simple Procurement Intelligence - Public Procurement Zenodo Sample",
        "description": (
            "A flat contract-level sample of public procurement records exported from "
            "the active Simple Neo4j database for demonstration and reproducibility."
        ),
        "source_datasets": ["TED", "KIMDIS/KHMDHS"],
        "extraction_datetime": datetime.now(timezone.utc).isoformat(),
        "neo4j_schema": {
            "labels_used": ["Buyer", "Award", "Winner", "CPV"],
            "relationships_used": ["AWARDS", "WON_BY", "BELONGS_TO"],
        },
        "cypher_query_used": cypher_query.strip(),
        "sample_size": int(len(df)),
        "sampling_method": "Random sampling up to 5000 rows using ORDER BY rand() LIMIT 5000.",
        "columns": list(df.columns),
        "excluded_field_rules": {
            "excluded_column_name_terms": FORBIDDEN_COLUMN_TERMS,
            "excluded_fields_note": (
                "Contact/person/internal/log/prompt/chat/embedding/vector/secret fields "
                "are excluded if present in extracted columns. Award titles/free-text are "
                "not exported in this sample."
            ),
        },
        "financial_notes": (
            "Monetary values are preserved exactly as stored in Neo4j. No value anonymisation, "
            "bucketing or perturbation is applied."
        ),
        "public_identifier_notes": (
            "Buyer and supplier names/VATs are retained because they are public procurement "
            "identifiers from official public procurement sources."
        ),
        "license": "To be defined before Zenodo publication",
        "citation": "[Placeholder for Zenodo DOI citation]",
        "limitations": (
            "This sample is intended for demonstration, software reproducibility and methods "
            "review. It should not be used for official audit conclusions."
        ),
    }

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def validate_export(parquet_path: str, generated_paths: dict) -> None:
    print("\n--- VALIDATION ---")
    val_df = pd.read_parquet(parquet_path)

    print(f"Row count: {len(val_df)}")
    print(f"Target <= 5000: {len(val_df) <= 5000}")
    print(f"Columns: {list(val_df.columns)}")

    print("\nHead (5 rows):")
    print(val_df.head())

    print("\nFile sizes:")
    for label, fp in generated_paths.items():
        if os.path.exists(fp):
            print(f"{label}: {os.path.basename(fp)} — {os.path.getsize(fp) / 1024:.2f} KB")

    assert len(val_df) <= 5000, "Export contains more than 5000 rows."

    for col in val_df.columns:
        for term in FORBIDDEN_COLUMN_TERMS:
            assert term not in col.lower(), f"Forbidden term '{term}' found in column '{col}'."

    assert "contract_value_eur" in val_df.columns, "Missing contract_value_eur column."
    assert pd.api.types.is_numeric_dtype(val_df["contract_value_eur"]), "contract_value_eur is not numeric."
    assert "cpv_code" in val_df.columns or "cpv_division" in val_df.columns, "Missing CPV tracking column."

    print("\nValidation PASSED: row limit, forbidden-column checks, CPV check and monetary numeric check passed.")


def main():
    overwrite = "--overwrite" in sys.argv

    os.makedirs(EXPORT_DIR, exist_ok=True)
    paths = output_paths()
    ensure_no_overwrite(paths, overwrite=overwrite)

    cypher_query = """
    MATCH (b:Buyer)-[:AWARDS]->(a:Award)-[:WON_BY]->(w:Winner)
    OPTIONAL MATCH (a)-[:BELONGS_TO]->(c:CPV)
    RETURN
        a.source AS source_dataset,
        a.identifier AS notice_id,
        a.original_id AS original_id,
        a.submission_date AS award_date,
        a.year AS year,
        a.value AS contract_value_eur,
        a.cpv_code AS cpv_code,
        CASE
            WHEN a.cpv_code IS NULL THEN NULL
            ELSE substring(toString(a.cpv_code), 0, 2)
        END AS cpv_division,
        a.nuts_code AS nuts_region,
        b.name AS buyer_name,
        b.vat AS buyer_vat,
        b.sources AS buyer_sources,
        w.name AS supplier_name,
        w.vat AS supplier_vat,
        w.sources AS supplier_sources
    ORDER BY rand()
    LIMIT 5000
    """

    ensure_read_only_cypher(cypher_query)

    print("Executing Neo4j read-only export query...")
    results = execute_cypher(cypher_query)

    if not results:
        print("No records returned. No export files written.")
        return

    df = pd.DataFrame(results)
    df = drop_forbidden_columns(df)
    df = normalise_list_columns(df)

    print(f"Rows returned from Neo4j: {len(df)}")
    print(f"Export columns: {list(df.columns)}")

    parquet_path = paths["parquet"]

    try:
        df.to_parquet(parquet_path, engine="pyarrow", compression="zstd", index=False)
        parquet_compression = "zstd"
    except Exception as zstd_error:
        print(f"zstd Parquet compression failed, falling back to snappy. Reason: {zstd_error}")
        df.to_parquet(parquet_path, engine="pyarrow", compression="snappy", index=False)
        parquet_compression = "snappy"

    write_metadata(paths["metadata"], cypher_query, df)
    write_data_dictionary(paths["dictionary"])
    write_readme(paths["readme"])

    print(f"\nExport completed using Parquet compression: {parquet_compression}")
    print(f"Output directory: {EXPORT_DIR}")

    validate_export(parquet_path, paths)


if __name__ == "__main__":
    main()
