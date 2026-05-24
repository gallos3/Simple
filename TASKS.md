# Project Tasks & Roadmap

## Φάση 1: Υποδομή & Ασφάλεια (Infrastructure & Safety)
- [x] Αρχικοποίηση Git Repository & Branching Strategy `(v0.1.0)`
- [x] Δημιουργία `.gitignore` για προστασία από ανέβασμα μοντέλων/δεδομένων
- [x] Δημιουργία `backend/schema_mapping.py` (Ontology Policeman + ePO Mapping)
- [x] Δημιουργία `backend/entity_resolver.py` (Entity Resolution & Linking)
- [x] Δημιουργία `backend/federate_data.py` (ETL Ingestor)
- [x] Δημιουργία βάσης `federated` στη Neo4j (Constraints & Indexes implemented)
- [x] Δοκιμαστικό τρέξιμο `--dry-run` για επικύρωση Entity Resolution
- [x] Μεταφορά κώδικα Simple (config, database, engine, diagnostic_engine)
- [x] Προσαρμογή `predefined_queries.json` στο νέο Master Schema (Πλήρης προσαρμογή με διόρθωση labels :WON_BY, ονομάτων πεδίων, δυναμικό έλεγχο ProcedureType) `(v0.3.0)`

## Φάση 2: Ενοποίηση Δεδομένων (Data Federation)
- [x] Πρώτο Test Ingestion (KIMDIS only)
- [x] Πρώτο Test Ingestion (ENDORSE/TED only)
- [x] Full Ingestion (Initial snapshot of 8.5M nodes processed)
- [x] Ενσωμάτωση Provenance Metadata (source property on Award nodes)
- [x] Human-in-the-Loop Dashboard (`:PendingReview` approval UI)

## Φάση 3: Προηγμένη Νοημοσύνη (Intelligence Layer)
- [x] Αναβάθμιση σε Agentic RAG (Tool Use integration in `agent_modules.py` / `agentic_loop.py`)
- [x] Υλοποίηση Cognitive Memory (Reasoning Loops)
- [x] CAG (Cache Augmented Generation) για νομικά ερωτήματα
- [x] Ενσωμάτωση δεικτών ICI/VCD στο reasoning
- [x] Ενσωμάτωση δεδομένων από 3η χώρα (π.χ. Κύπρος)

---
*Status Notation: [ ] TODO | [/] In Progress | [x] Done*

