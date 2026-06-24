"""
Simple_Federated - Schema Mapping & Ontology Definition
========================================================
Ορίζει τον "πίνακα μετάφρασης" μεταξύ των διαφορετικών σχημάτων
(KIMDIS API, ENDORSE/TED) και του ενοποιημένου Master Schema.

Το Master Schema ακολουθεί το ePO (eProcurement Ontology) standard
με πρακτικά ονόματα για ευκολία στα Cypher queries.

Η ePO οντολογία εφαρμόζεται μέσω Neosemantics (n10s) στη Neo4j,
αλλά τα internal labels κρατάνε απλά ονόματα για αναγνωσιμότητα.
"""

# =============================================================================
# MASTER LABELS (ePO-aligned, human-readable)
# =============================================================================
# Αυτά είναι τα Labels που θα χρησιμοποιεί η νέα federated βάση.
# Κάθε label αντιστοιχεί σε ένα ePO class.

MASTER_LABELS = {
    "buyer":           "Buyer",           # ePO: epo:Buyer (Αναθέτουσα Αρχή)
    "award":           "Award",           # ePO: epo:ContractAwardNotice
    "winner":          "Winner",          # ePO: epo:Winner (Ανάδοχος/Εταιρεία)
    "cpv":             "CPV",             # ePO: cpv:Code
    "notice":          "Notice",          # ePO: epo:Notice (Προκήρυξη)
    "lot":             "Lot",             # ePO: epo:Lot (Τμήμα)
    "procedure_type":  "ProcedureType",   # ePO: epo:ProcedureType
}

# =============================================================================
# MASTER RELATIONSHIPS
# =============================================================================
MASTER_RELATIONSHIPS = {
    "buyer_awards":    "AWARDS",          # (Buyer)-[:AWARDS]->(Award)
    "award_won_by":    "WON_BY",          # (Award)-[:WON_BY]->(Winner)
    "award_has_cpv":   "HAS_CPV",         # (Award)-[:HAS_CPV]->(CPV)
    "award_has_lot":   "HAS_LOT",         # (Award)-[:HAS_LOT]->(Lot)
    "notice_issued":   "ISSUED_BY",       # (Notice)-[:ISSUED_BY]->(Buyer)
    "award_procedure": "HAS_PROCEDURE",   # (Award)-[:HAS_PROCEDURE]->(ProcedureType)
}

# =============================================================================
# MASTER PROPERTIES for Award node
# =============================================================================
# Αυτά είναι τα κανονικοποιημένα property names
MASTER_AWARD_PROPS = {
    "value":            "value",            # Ποσό σύμβασης (χωρίς ΦΠΑ)
    "year":             "year",             # Έτος ανάθεσης
    "cpv_code":         "cpv_code",         # Κύριος CPV κωδικός
    "procedure":        "procedure",        # Τύπος διαδικασίας (κείμενο)
    "nuts_code":        "nuts_code",        # NUTS γεωγραφικός κωδικός
    "identifier":       "identifier",       # Μοναδικός αριθμός (ΑΔΑΜ ή TED ID)
    "protocol_num":     "protocol_num",     # Αριθμός πρωτοκόλλου
    "cancelled":        "cancelled",        # Ακύρωση (true/false)
    "contract_type":    "contract_type",    # Τύπος σύμβασης (κωδικός)
    # --- Δείκτες (από papers) ---
    "ici_deg":          "ici_deg",          # Institutional Closure Index (degree)
    "deg":              "deg",              # Network degree (γενικός)
    # --- Provenance ---
    "source":           "source",           # Πηγή δεδομένων ("KIMDIS_API" | "TED")
    "ingested_at":      "ingested_at",      # Timestamp εισαγωγής
}

# =============================================================================
# SOURCE: KIMDIS API  →  Master Schema
# =============================================================================
KIMDIS_API_MAPPING = {
    "database": "neo4j",  # Όνομα βάσης στη Neo4j (αλλαγή αν διαφέρει)

    "labels": {
        "Auth":     MASTER_LABELS["buyer"],
        "Awr":      MASTER_LABELS["award"],
        "Comp":     MASTER_LABELS["winner"],
        "Cpv":      MASTER_LABELS["cpv"],
        "AuthUnit": None,  # Μονάδα αρχής – θα γίνει property του Buyer
    },

    "relationships": {
        "AWARDED":      MASTER_RELATIONSHIPS["buyer_awards"],
        "WON":          MASTER_RELATIONSHIPS["award_won_by"],
        "HAS_CPV":      MASTER_RELATIONSHIPS["award_has_cpv"],
        "UNIT_OF":      None,  # Θα γίνει ιεραρχικό property
    },

    # Property mapping: source_prop → master_prop
    "award_properties": {
        "cost_without_vat":   "value",
        "nuts_code":          "nuts_code",
        "protocol_num":       "protocol_num",
        "contract_type":      "contract_type",
        "cancellation":       "cancelled",
        "cpv_count":          "cpv_count",
        "has_multiple_cpv":   "has_multiple_cpv",
        "ici_deg":            "ici_deg",
    },

    "buyer_properties": {
        "name":               "name",
        # Αν υπάρχουν: afm, authority_code, nuts_name
    },

    "winner_properties": {
        "name":               "name",
        # Αν υπάρχουν: VATNumber, afm
    },
}

# =============================================================================
# SOURCE: ENDORSE (TED)  →  Master Schema
# =============================================================================
ENDORSE_TED_MAPPING = {
    "database": "endorse",  # Όνομα βάσης στη Neo4j

    "labels": {
        "Authority":      MASTER_LABELS["buyer"],
        "ContractAward":  MASTER_LABELS["award"],
        "Company":        MASTER_LABELS["winner"],
        "CPV":            MASTER_LABELS["cpv"],
        "Notice":         MASTER_LABELS["notice"],
        "Lot":            MASTER_LABELS["lot"],
    },

    "relationships": {
        "awardedTo":      MASTER_RELATIONSHIPS["award_won_by"],
        "publishedBy":    MASTER_RELATIONSHIPS["buyer_awards"],
        "issuedBy":       MASTER_RELATIONSHIPS["notice_issued"],
        "hasCPV":         MASTER_RELATIONSHIPS["award_has_cpv"],
        "hasLot":         MASTER_RELATIONSHIPS["award_has_lot"],
        "belongsToLot":   MASTER_RELATIONSHIPS["award_has_lot"],
    },

    # Property mapping: source_prop → master_prop
    "award_properties": {
        "contractValue":      "value",
        "awardYear":          "year",
        "mainCPV":            "cpv_code",
        "identifier":         "identifier",
        "deg":                "deg",
    },

    "buyer_properties": {
        "name":               "name",
    },

    "winner_properties": {
        "name":               "name",
        "VATNumber":          "vat_number",
    },

    "notice_properties": {
        "identifier":         "identifier",
        "dispatchDate":       "dispatch_date",
        "contractTypeCode":   "contract_type",
        "procedureTypeCode":  "procedure",
        "isCancelled":        "cancelled",
    },
}

# =============================================================================
# VALIDATION RULES (Ontology Policeman)
# =============================================================================
# Κάθε κόμβος στη federated βάση ΠΡΕΠΕΙ να έχει αυτά τα properties
REQUIRED_PROPERTIES = {
    "Buyer":  ["name"],
    "Award":  ["value", "source"],
    "Winner": ["name"],
    "CPV":    ["code"],
}

# Κανόνες τύπων (type validation)
PROPERTY_TYPES = {
    "value":        float,
    "year":         int,
    "cancelled":    bool,
    "ici_deg":      (int, float),
    "deg":          (int, float),
}

def validate_node(label: str, properties: dict) -> list:
    """
    Ελέγχει αν ένας κόμβος πληροί τους κανόνες του Schema.
    Επιστρέφει λίστα με σφάλματα (κενή αν είναι valid).
    """
    errors = []

    # 1. Required properties
    required = REQUIRED_PROPERTIES.get(label, [])
    for prop in required:
        if prop not in properties or properties[prop] is None:
            errors.append(f"Missing required property '{prop}' for :{label}")

    # 2. Type validation
    for prop, expected_type in PROPERTY_TYPES.items():
        if prop in properties and properties[prop] is not None:
            val = properties[prop]
            if not isinstance(val, expected_type):
                # Προσπάθεια μετατροπής
                try:
                    if expected_type == float:
                        float(val)
                    elif expected_type == int:
                        int(val)
                except (ValueError, TypeError):
                    errors.append(
                        f"Property '{prop}' has type {type(val).__name__}, "
                        f"expected {expected_type.__name__} for :{label}"
                    )

    return errors


def map_properties(source_props: dict, mapping: dict) -> dict:
    """
    Μετατρέπει τα properties μιας πηγής στα Master property names.

    Args:
        source_props: Τα πρωτότυπα properties (π.χ. {"cost_without_vat": 1234})
        mapping: Ο πίνακας αντιστοίχισης (π.χ. KIMDIS_API_MAPPING["award_properties"])

    Returns:
        dict με τα μετονομασμένα properties
    """
    result = {}
    for source_key, master_key in mapping.items():
        if source_key in source_props and source_props[source_key] is not None:
            result[master_key] = source_props[source_key]
    return result
