## Simple_Federated

**Semantic Procurement Diagnosis and Training System based on Multi-Layer Market Analytics**

### Overview

Simple_Federated is a semantic procurement diagnostic and training system that combines:

- A **multi-layer analytical framework** for procurement markets
- A **graph-native data infrastructure** integrating European and national procurement data
- A **RAG-based AI system grounded in legal, institutional and analytical sources**
- A **local-first AI architecture** designed for sensitive public-sector environments
- A **training and simulation layer** for procurement audit education

The system transforms procurement analytics from **measurement** to **diagnosis** by explaining not only what is observed, but also **why procurement markets behave the way they do**.

---

### Core Innovation

Traditional procurement analysis applies isolated indicators, such as HHI, red flags or contract-value thresholds, often leading to fragmented interpretations.

Simple_Federated introduces a different paradigm:

- Indicators are computed across multiple analytical levels
- Results are interpreted jointly
- Observed outcomes are linked to underlying market and institutional mechanisms
- Legal and analytical reasoning are combined in a single workflow

This transforms procurement analytics from:

**measurement → diagnosis**

The goal is not only to detect anomalies, but to help explain whether a procurement pattern reflects ordinary market concentration, efficient specialization, repeated institutional dependence, potential lock-in, or risk of non-compliance.

---

### Graph-Native Data Infrastructure

The system operates on a **Neo4j knowledge graph** that integrates procurement information in a unified analytical environment, including:

- **EU-level procurement data**
- **National procurement data**
- Buyer–supplier relationships
- Contracts and awards
- CPV categories
- Procurement procedures
- Institutional and market-level relationships

All data are:

- Harmonised across sources
- Resolved into a unified buyer–supplier network
- Structured for graph-native analytics
- Designed to support semantic interpretation and explainable diagnostics

#### Geographic Enrichment 

Automated integration with Eurostat NUTS 2021 classifications, enabling precise spatial tracking of procurement activity and semantic disambiguation of contracting authorities based on their location.

#### Advanced Data Engineering & Governance
Transforming messy public procurement data into a structured knowledge graph requires robust engineering. Simple_Federated implements a comprehensive 3-step pipeline:

1. Greek NLP Normalization (federate_data.py): A custom 9-step normalization pipeline that handles Greek character conversions, strips accents, standardizes punctuation, and dynamically expands over 100 domain-specific abbreviations.
2. Multi-Signal Entity Resolution (entity_resolver.py): A disambiguation engine that bridges EU (TED) and national (KIMDIS) entities. It relies on a hybrid matching algorithm combining exact VAT bridging, fuzzy string logic (Levenshtein & Jaccard), and Eurostat NUTS spatial integration.
3. Human-in-the-Loop Deduplication (generate_pending_reviews.py): An optimized blocking algorithm that flags edge-case entity pairs for manual review. It incorporates a persistent "rejection memory" to prevent recursive errors, ensuring the highest standards of data governance.

#### Semantic Representation

TThe graph represents procurement as a relational system rather than as isolated records. It is semantically structured using the official EU eProcurement Ontology (ePO).

Each node and relationship is explicitly mapped and strictly validated against ePO standards through a custom Ontology Enforcement Layer (schema_mapping.py), ensuring absolute data consistency between national and European data structures.

It encodes:

- Contracting authorities (epo:Buyer)
- Suppliers / economic operators (epo:Winner)
- Contracts and awards (epo:ContractAwardNotice)
- CPV categories
- Procurement procedures
- Buyer–supplier interactions
- Recurrent relational patterns

This enables the graph-native computation of indicators while preserving the relational structure of public procurement markets.

---

### Multi-Layer Diagnostic Framework

The system implements a multi-layer diagnostic framework structured across three analytical levels.

#### 1. Macro Level — Market Structure

The macro level examines the overall structure of procurement markets.

Implemented indicators include:

- Entropy — H(X), H(Y)
- Concentration — HHI, top-supplier share
- Value–Count Divergence (VCD)

#### 2. Meso Level — Relational Structure

The meso level examines how contracting authorities and suppliers are structurally connected.

Implemented indicators include:

- Conditional entropy — H(Y|X), H(X|Y)
- Assortativity
- Buyer–supplier dependency patterns

#### 3. Micro Level — Institutional Dynamics

The micro level examines repeated institutional relationships and local network mechanisms.

Implemented indicators include:

- Historical Frequency (HF)
- Preferential Attachment (PA)
- Adamic–Adar (AA)

#### Cross-Layer Diagnostics

The system also implements cross-layer diagnostic indicators, including:

- Institutional Closure Index (ICI)
- Market typology analysis
- Recurrence-based diagnostics
- Risk-oriented interpretation of repeated procurement relationships

---

### What Makes This System Unique

Simple_Federated reads indicators **jointly**, allowing the system to distinguish between:

- Competitive vs concentrated markets
- Efficient specialization vs preferential allocation
- Open systems vs institutional lock-in
- Ordinary recurrence vs suspicious repeated dependency
- Fragmented markets vs structurally closed procurement ecosystems

Similar aggregate metrics can reflect very different underlying mechanisms.

Simple_Federated makes those mechanisms observable.

---

### Local-First Architecture

The system is designed as a **local-first AI system**.

It can run locally using:

- A lightweight local LLM
- Neo4j graph database
- Python analytical pipelines
- Retrieval-Augmented Generation components
- React-based user interface

#### Key Properties

- No cloud dependency by default
- No sensitive procurement data leaves the system by default
- Suitable for sensitive public-sector and audit environments
- LLM used as an orchestration and interpretation layer, not as the source of truth
- Deterministic graph and analytical pipelines remain central to the system logic

The system is designed around the principle that AI should assist analysis, not replace evidence.

---

### Legal and Institutional RAG Layer

The system includes a Retrieval-Augmented Generation layer designed to support legal and institutional reasoning.

The system can retrieve and use:

- Procurement legislation
- Administrative guidance
- Institutional documents
- Legal and audit-relevant sources
- Domain-specific knowledge sources

The RAG layer is designed to reduce hallucination risk by grounding legal and analytical answers in retrieved material.

#### Design Principle

The LLM should not invent legal rules, thresholds, case law or institutional facts.

When reliable retrieved context is unavailable, the system is designed to avoid unsupported legal conclusions and to distinguish between:

- Retrieved legal evidence
- Analytical interpretation
- Missing or insufficient context

---

### Web Search

The system includes an optional web search capability.

Features include:

- UI-based activation/deactivation
- Query anonymisation before outgoing search
- Use of trusted institutional sources where possible
- Source-aware responses
- Separation between local analysis and external retrieval

The web layer is intended as an auxiliary retrieval channel and not as a replacement for the local graph, legal corpus or analytical modules.

---

### Audit Reports and Compliance Detection

The system automatically supports procurement audit workflows, including detection of:

- Contracting authorities with suspicious procurement patterns
- Potentially non-compliant direct awards
- Repeated awards to the same suppliers
- CPV-level threshold exceedances
- Supplier concentration
- Possible contract splitting risk
- Institutional lock-in patterns

It produces structured audit outputs including:

- Indicator diagnostics
- Risk assessment
- Legal and procedural justification
- Buyer–supplier summaries
- CPV-based analysis
- DOCX audit report exports

---

### Legal Decision Support

Using the same retrieval and diagnostic architecture, the system supports:

- Legal procurement questions
- Retrieval of relevant legal and institutional sources
- Structured legal reasoning
- Audit-oriented interpretation
- Evidence-aware answers

The system is not intended to replace legal judgement. It is designed as an assistive layer for procurement experts, auditors and public-sector analysts.

---

### Simulation and Training Layer

Simple_Federated includes a procurement simulation and training environment.

#### RAG-Based Scenario Generation

Training scenarios can be constructed from:

- Legal texts
- Institutional guidance
- Audit-relevant procurement cases
- Procurement procedures and decision points

#### Graph-Based Scenario Structure

Scenarios can be represented as directed decision graphs, including:

- Multi-step decision flows
- Branching paths
- Audit-risk consequences
- Value-for-money consequences
- Administrative impact

#### Deterministic Evaluation

Each training session can produce:

- Score
- Audit risk
- Value-for-money risk
- Administrative impact
- Structured evaluation report

#### Scenario Authoring Workflow

The system supports a human-in-the-loop scenario workflow:

1. Expert requests a scenario
2. System generates a draft
3. Scenario is provided as editable JSON
4. Expert reviews and validates the scenario (supported by an automated DFS graph-validation engine that checks structural integrity, reachability, and logic constraints).
5. Approved scenario becomes available to trainees

Approval logic:

- Draft scenarios remain expert-only
- Approved scenarios become available for training use

### Stateless Simulation Replay

The simulation engine does not rely on server-side session storage. At each turn, the backend reconstructs the current simulation state deterministically from the conversation history sent by the frontend. This makes the serious-game workflow resilient to backend restarts and avoids server-side session persistence complexity.

---

### Human-Centered Interaction Layer

The system is designed not only as an analytical tool, but also as an interactive assistant.

Users can:

- Ask procurement-related questions
- Request legal or analytical insights
- Ask for indicator interpretation
- Use web search for general information
- Request audit-style explanations
- Interact through a conversational interface

The goal is to reduce friction in expert workflows and make complex procurement analytics more accessible.

---

### Technical Highlights

The system includes several technical components designed specifically for public procurement analysis.

#### Custom ReAct Agent

Simple_Federated includes a custom ReAct-style agent built from scratch, without relying on heavy external agent frameworks.

The agent can:

- Reason over user questions
- Select appropriate analytical tools
- Call graph and audit functions
- Combine observations into a final response
- Support analytics such as entropy, ICI, VCD and market typology

This provides transparent orchestration between natural-language interaction and deterministic analytical tools.

#### Interactive Graph Visualization

The frontend supports interactive graph exploration using graph visualization components.

Capabilities include:

- Buyer–supplier network visualization
- Contract and award relationship exploration
- Graph-based views of procurement structures
- Temporal filtering / timeline-style exploration
- Risk-aware visual interpretation

This allows users to inspect procurement structures visually, not only through tables or text.

#### Voice Interface

The interface supports voice-based interaction features, including:

- Push-to-talk style interaction
- Speech-to-text support
- Greek-language interaction workflows
- Text-to-speech output for accessibility-oriented use cases

This makes the tool more accessible for auditors, trainees and non-technical public-sector users.

#### Advanced Entity Resolution and Greek NLP

The system includes preprocessing and normalization logic for Greek procurement data.

This includes:

- Greek text normalization
- Accent-insensitive matching
- Name cleaning
- Abbreviation handling
- Authority and supplier name normalization
- Multi-signal entity matching
- Support for noisy procurement records

This is critical for Greek public procurement data, where the same contracting authority or supplier may appear under multiple name variants.

#### Automated DOCX Audit Report Generation

The system can generate structured audit reports in Word format.

This supports practical audit workflows by producing documents that can be reviewed, edited, shared and archived by public-sector professionals.

#### Cache-Augmented Generation (CAG)

The system implements an advanced semantic caching layer (cag_cache.py) that uses vector embeddings (FAISS) to detect semantically similar user queries. Instead of relying on exact text matching, it understands the intent behind a question.

This improves:

Response speed: Near-instant answers for previously asked questions without invoking the LLM or Graph traversals.
Local resource efficiency: Dramatically reduces CPU load for the local LLM.
Data Governance: Different Time-To-Live (TTL) expiration rules for legal queries (stable) vs data queries (dynamic).

#### Feedback-Driven Debugging
An integrated tracing mechanism that captures end-to-end execution contexts (NLP, Cypher, LLM outputs) alongside user feedback, saving structured error reports for continuous system refinement.

---

### System Architecture

- **Backend:** Python / Flask
- **Frontend:** React.js (Vite), TailwindCSS, Cytoscape.js (Interactive Graph Visualization), Recharts (Dynamic Analytics), and Web Speech API (Push-to-Talk STT & Auto-TTS).
- **Database:** Neo4j
- **AI Layer:** Local LLM
- **Retrieval:** Graph RAG, Legal RAG, optional web retrieval
- **Analytics:** Graph-native computation
- **Reports:** Automated structured audit reports
- **Visualization:** Interactive graph-based frontend
- **Training:** Scenario simulation and evaluation layer
- **Natural Language Understanding:**  The NLU layer utilizes a pre-compiled, in-memory Entity Cache (rebuild_federated_cache.py), allowing ultra-fast entity extraction (Named Entity Recognition) without the latency of querying the graph database in real-time.

---

### AI-Assisted Development Methodology

Simple_Federated was developed through an expert-led Agentic AI workflow.

The system demonstrates how modern AI tools can enable domain experts to design, build and iteratively refine complex analytical software systems. The author’s role focused on the conceptual architecture, procurement theory, diagnostic model, tool orchestration, validation strategy, testing and continuous debugging.

AI coding and reasoning assistants, including ChatGPT, Microsoft Copilot, Claude and Antigravity, were used throughout the development process for implementation support, refactoring, documentation, error correction and rapid prototyping.

Rather than replacing domain expertise, the AI tools acted as engineering accelerators. The scientific logic, procurement interpretation, system architecture and validation of outputs remained human-led. In this sense, Simple_Federated is also a case study in how Agentic AI workflows can expand the implementation capacity of public-sector researchers and domain experts.

---

### Data and Reproducibility

A representative dataset can be provided for:

- Schema inspection
- Reproducibility
- Workflow testing
- Demonstration of graph-native procurement diagnostics

Full system functionality requires:

- Neo4j infrastructure
- Procurement data import
- Local backend services
- Frontend interface
- Configured analytical modules

---

### Repository Structure

backend/                  Core backend logic, diagnostics, RAG and audit modules
frontend/                 React interface and visualization layer
analytics/                Analytical indicators, audit checks and reporting
rag/                      Retrieval and grounding components
ai/                       LLM interface, agent modules and orchestration
data_access/              Database access, query matching and entity extraction
utils/                    Configuration and helper utilities
generate_zenodo_sample.py Dataset export / reproducibility utility

---

### Future Work & Roadmap
The core analytical pipeline and hybrid RAG are fully operational. However, the repository also includes advanced architectural components that have been developed and are currently in the validation phase, slated for the next major release:

- Pure Legal Knowledge Graph (legal_graph_ingest.py): An ingestion pipeline that converts unstructured legal texts (e.g., procurement laws, articles) directly into connected Neo4j nodes. This will eventually replace or augment the FAISS vector database to enable hybrid, multi-hop legal reasoning.
- Graph-Native Legal Thresholds (legal_rules_ingestion.py & map_rules_to_graph.py): A fully coded but pending-validation mechanism that decouples financial limits (e.g., the €30,000 threshold for direct awards) from the application logic. Instead of hardcoding rules in Python, thresholds are modeled as graph nodes (Threshold) connected to specific CPV nodes. This future-proofs the system, meaning legislative changes will instantly update the audit engine simply by modifying a node in the graph, requiring zero code changes.

## Related Research Outputs

The methodological framework underlying the diagnostic layer is described in:

Fountoukidis, I., Dafli, E., Antoniou, I. E., & Varsakelis, N. (2026). 
*A Multi-Layered Diagnostic Framework for Public Procurement Markets: Linking Market Structure, Relational Patterns, and Institutional Dynamics* (v1.0). Zenodo. 
https://doi.org/10.5281/zenodo.21062840

A representative parquet dataset / graph export is available at:
https://doi.org/10.5281/zenodo.21065450
