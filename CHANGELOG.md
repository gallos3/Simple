# Changelog

Όλες οι σημαντικές αλλαγές στο Simple_Federated θα καταγράφονται εδώ.

## [0.3.0-alpha] - 2026-05-08
### Added
- **LegalEntity Hierarchy**: Δημιουργία δομής LegalEntity που συνδέει πολλαπλούς κόμβους Buyer βάσει ΑΦΜ (VAT), λύνοντας το πρόβλημα των πολλαπλών ονομασιών του ίδιου φορέα.
- **Agentic RAG Integration**: Προσθήκη βασικών δομικών στοιχείων (`agent_modules.py`) για τη μετάβαση στη Φάση 3 (Intelligence Layer).

### Changed
- **Predefined Queries**: Πλήρης προσαρμογή του `predefined_queries.json` στο νέο Master Schema. Η σχέση `:AWARDS_TO` άλλαξε σε `:WON_BY`, διορθώθηκαν τα ονόματα πεδίων (`value`, `identifier`) και προστέθηκε δυναμικός έλεγχος τύπου διαδικασίας (`ProcedureType`) μέσω του `Award.title` αντί για ξεχωριστούς κόμβους.
- **Entity Extraction**: Σταθεροποίηση της εξαγωγής οντοτήτων, διόρθωση σφαλμάτων εμβέλειας μεταβλητών (variable scoping bugs) και βελτιστοποίηση του inverted index.
- **KHMΔHS Alignment**: Επιβολή ντετερμινιστικής ταυτοποίησης συμβάσεων χρησιμοποιώντας το αναγνωριστικό ADAM (ref) και φιλτράρισμα ακυρωμένων (cancelled) αναθέσεων, εξασφαλίζοντας 1:1 αντιστοιχία με τα επίσημα δεδομένα.

## [0.2.0-alpha] - 2026-04-30
### Added
- `backend/schema_mapping.py`: Πίνακας μετάφρασης KIMDIS API ↔ ENDORSE/TED ↔ Master Schema (ePO).
  Περιλαμβάνει Ontology Policeman (validation rules) και property mapping utilities.
- `backend/entity_resolver.py`: Entity Resolution engine με:
  - VAT exact match (100% confidence)
  - Levenshtein + Token overlap fuzzy matching
  - NUTS geographic bonus
  - Composite award matching (buyer + value + year + CPV)
  - Confidence thresholds: auto-merge (≥0.90), pending review (0.75–0.90), low (0.60–0.75)
- `backend/federate_data.py`: Κεντρικό ETL pipeline:
  - Multi-database reader (KIMDIS API + ENDORSE/TED)
  - ΚΑΝΟΝΑΣ: Ποτέ δεν γράφει στις πηγές (READ-ONLY)
  - Batch UNWIND ingestion με provenance metadata
  - Dry-run mode για δοκιμαστική εκτέλεση
  - JSON ingestion reports στο `logs/`

## [0.1.0-alpha] - 2026-04-30
### Added
- Αρχικοποίηση φακέλου project.
- Δημιουργία αρχείων διαχείρισης (`README.md`, `TASKS.md`, `CHANGELOG.md`).
- Ρύθμιση `.gitignore`.
- Αρχικοποίηση Git repository.
