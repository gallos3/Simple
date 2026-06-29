# Simple_Federated

**Semantic Procurement Diagnosis and Training System based on Multi-Layer Market Analytics**

---

## Overview

Simple_Federated is a semantic procurement diagnostic and training system that combines:

- A **multi-layer analytical framework** for procurement markets  
- A **graph-native data infrastructure** integrating European and national data  
- A **RAG-based AI system grounded in legal and institutional sources**  

The system transforms procurement analytics from **measurement** to **diagnosis** by explaining not only what is observed, but also **why procurement markets behave the way they do**.

---

## Core Innovation

Traditional procurement analysis applies isolated indicators (e.g. HHI, red flags), leading to fragmented interpretations.

Simple_Federated introduces a fundamentally different paradigm:

- Indicators are computed across multiple analytical levels  
- Results are **interpreted jointly**  
- Observed outcomes are linked to **underlying mechanisms**  

👉 This transforms procurement analytics from:

**measurement → diagnosis**

---

## Graph-Native Data Infrastructure (Key Contribution)

The system operates on a **Neo4j knowledge graph** that integrates, for the first time in a unified analytical environment:

- **EU-level procurement data (TED)**  
- **National procurement data (KIMDIS – Greece)**  

All data are:

- Harmonised and resolved across sources  
- Represented as a single buyer–supplier network  
- Semantically structured using the **eProcurement Ontology (ePO)**  

### Semantic Representation

- Each **node and relationship is explicitly defined** using ePO  
- The graph encodes:
  - Buyers (contracting authorities)  
  - Suppliers  
  - Contracts  
  - CPV categories  
  - Institutional relationships  

👉 This enables **graph-native computation of all indicators** and preserves relational structure across all analytical levels.

---

## Multi-Layer Diagnostic Framework

The system implements a published framework structured across three levels:

### 1. Macro Level — Market Structure
- Entropy (H(X), H(Y))  
- Concentration (HHI, top-supplier share)  
- Value–Count Divergence (VCD)  

---

### 2. Meso Level — Relational Structure
- Conditional entropy (H(Y|X), H(X|Y))  
- Assortativity  

---

### 3. Micro Level — Institutional Dynamics
- Historical Frequency (HF)  
- Preferential Attachment (PA)  
- Adamic–Adar (AA)  

---

### Cross-Layer Diagnostics
- Institutional Closure Index (ICI)

---

## What Makes This System Unique

The system reads all indicators **jointly**, allowing it to distinguish between:

- Competitive vs concentrated markets  
- Efficient specialization vs preferential allocation  
- Open systems vs institutional lock-in  

👉 Similar aggregate metrics can reflect different mechanisms  
👉 Simple_Federated makes those mechanisms observable

---

## Local-First Architecture (Privacy-by-Design)

The system runs **fully locally** using:

- A lightweight local LLM:  
  `qwen2.5-3b-instruct-q4_k_m.gguf`

### Key Properties

- No cloud dependency  
- No data leaves the system by default  
- Designed for sensitive public procurement environments  

👉 All analysis is performed through:

- Graph queries (Neo4j)  
- Deterministic analytical pipelines (Python)  
- RAG (legal + knowledge retrieval)  

The LLM is used **only as an orchestration and interpretation layer**, not as a source of truth.

---

## Legal RAG Layer (Non-Hallucinatory AI)

All outputs are grounded in a **Retrieval-Augmented Generation (RAG)** pipeline.

The system retrieves:

- Procurement legislation (EU & national)  
- Court decisions  
- Official guidelines and administrative documents  

👉 Outputs are:

- Evidence-based  
- Traceable to sources  
- Non-hallucinatory  

---

## Web Search (Controlled & Privacy-Preserving)

The system includes an optional web search capability:

- Activated/deactivated via UI toggle  
- All outgoing queries undergo **strict anonymisation**  
- No sensitive user or system data is exposed  

### Retrieval Policy

- Priority-based source hierarchy  
- Trusted institutional sources preferred  
- All results include **explicit source citation**

---

## Audit Reports and Compliance Detection

The system automatically identifies:

- Contracting authorities with suspicious patterns  
- Potential **non-compliant direct awards**  

It produces structured audit reports including:

- Indicator diagnostics  
- Risk assessment  
- Legal justification  

---

## Legal Decision Support

Using the same RAG layer, the system provides:

- Answers to legal procurement questions  
- Retrieval of relevant laws, rulings, and guidance  
- Structured legal reasoning outputs  

---

## Simulation and Training Layer

A fully integrated procurement simulation and training environment.

---

### RAG-Based Scenario Generation

Scenarios are constructed from:

- Legal texts  
- Case law  
- Official guidance  

👉 Not generated via hallucination

---

### Graph-Based Scenario Structure

- Directed graph representation  
- Multi-step decisions (4–6 steps)  
- Multiple branching paths  

---

### Deterministic Evaluation

Each session produces:

- Score  
- Audit risk  
- Value-for-money risk  
- Administrative impact  

and a structured evaluation report.

---

### Scenario Authoring Workflow

- Expert requests scenario  
- System generates draft via RAG  
- Scenario provided as editable JSON  
- Expert validates and approves  

Approval logic:
- Draft → expert only  
- Approved → available to trainees  

---

## Human-Centered Interaction Layer

The system is designed not only as an analytical tool, but as an **interactive assistant**.

Users can:

- Ask system-related questions  
- Request legal or analytical insights  
- Use web search for general information  
- Engage in informal interaction (e.g. explanations, simple Q&A, domain-specific humor)

👉 This creates a more **human-like interaction model**, reducing friction in expert workflows.

---

## System Architecture

- **Backend:** Python (Flask)  
- **Frontend:** React  
- **Database:** Neo4j  
- **AI Layer:** Local LLM (Qwen 2.5–3B)  
- **Retrieval:** Graph RAG + Legal RAG  
- **Analytics:** Graph-native computation  

---

## Data and Reproducibility

A representative dataset is provided (Parquet format) for:

- Schema inspection  
- Reproducibility  
- Workflow testing  

⚠️ Full system requires Neo4j infrastructure.

---

## Repository Structure

- `backend/` – core logic, diagnostics, RAG, simulations  
- `frontend/` – interface and visualization  
- `generate_zenodo_sample.py` – dataset export tool  

---

## Keywords

public procurement, knowledge graphs, market diagnostics, network entropy, RAG, simulation, audit systems, governance analytics, decision support

---

## Tagline

**A graph-native, RAG-grounded system that turns procurement data into diagnosis, revealing how and why public procurement markets function.**