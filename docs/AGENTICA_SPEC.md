# AGENTICA — Project Specification and Engineering Reference

**An Agentic Platform for IT Operations and Infrastructure Management**

| | |
|---|---|
| Document | Master specification: features, architecture, methodology, evaluation, and implementation guidance |
| Version | 2.0 (4 October 2026): scope reduced to the 19 core features; issue backlog added (Part II) |
| Source of truth | Approved FYP proposal, *Agentica — An Agentic Platform for IT Operations and Infrastructure Management*, dated 18 September 2026 (Project ID CS-FYP-1023) |
| Audience | The three-member development team, and Claude Code working in the repository and creating GitHub issues from Part II |
| Institution | Department of Computer Science, FAST School of Computing, FAST-NUCES Karachi, BS Computer Science, Session Fall 2026 |

---

## Contents

  - [0. How to use this document (read first)](#0-how-to-use-this-document-read-first)
- [Part I — Specification](#part-i--specification)
  - [1. Project identity](#1-project-identity)
  - [2. What Agentica is (one paragraph)](#2-what-agentica-is-one-paragraph)
  - [3. Problem statement [P]](#3-problem-statement-p)
  - [4. Motivation [P]](#4-motivation-p)
  - [5. Aim and objectives [P]](#5-aim-and-objectives-p)
  - [6. Removed and excluded features: DO NOT BUILD](#6-removed-and-excluded-features-do-not-build)
  - [7. Feature catalogue (19 core features)](#7-feature-catalogue-19-core-features)
  - [8. Development methodology](#8-development-methodology)
  - [9. System architecture [P]](#9-system-architecture-p)
  - [10. Execution flow and orchestrator](#10-execution-flow-and-orchestrator)
  - [11. Policy and permission engine (F19)](#11-policy-and-permission-engine-f19)
  - [12. Guardrails (F18)](#12-guardrails-f18)
  - [13. Knowledge retrieval: RAG pipeline (F5) and knowledge-base management (F6)](#13-knowledge-retrieval-rag-pipeline-f5-and-knowledge-base-management-f6)
  - [14. Tool routing and small-model strategy](#14-tool-routing-and-small-model-strategy)
  - [15. Model provider, models, and hardware (F14, F15)](#15-model-provider-models-and-hardware-f14-f15)
  - [16. Monitoring design: local and remote, dashboard vs agent](#16-monitoring-design-local-and-remote-dashboard-vs-agent)
  - [17. Remote management (F11, F12)](#17-remote-management-f11-f12)
  - [18. Tool implementation contract [D]](#18-tool-implementation-contract-d)
  - [19. Guided troubleshooting (F13)](#19-guided-troubleshooting-f13)
  - [20. Data layer](#20-data-layer)
  - [21. API and streaming contract [D]](#21-api-and-streaming-contract-d)
  - [22. Frontend (presentation layer)](#22-frontend-presentation-layer)
  - [23. Packaging, installation, and first run](#23-packaging-installation-and-first-run)
  - [24. Requirements [P] and traceability](#24-requirements-p-and-traceability)
  - [25. Evaluation methodology [P]](#25-evaluation-methodology-p)
  - [26. Timeline and task division [P]](#26-timeline-and-task-division-p)
  - [27. Tools and technologies (Table 6) [P], repository layout, and conventions [D]](#27-tools-and-technologies-table-6-p-repository-layout-and-conventions-d)
  - [28. Open decisions and key risks](#28-open-decisions-and-key-risks)
  - [29. Expected deliverables [P]](#29-expected-deliverables-p)
  - [30. Literature context (summary) [P]](#30-literature-context-summary-p)
  - [31. Glossary](#31-glossary)
  - [32. References [P]](#32-references-p)
- [Part II — Issue backlog](#part-ii--issue-backlog)
  - [33. How to create the issues (instructions for Claude Code)](#33-how-to-create-the-issues-instructions-for-claude-code)
  - [34. Issue conventions](#34-issue-conventions)
  - [35. The backlog](#35-the-backlog)
- [Appendices](#appendices)
  - [Appendix A: Worked example (end-to-end trace)](#appendix-a-worked-example-end-to-end-trace)
  - [Appendix B: Suggested `CLAUDE.md` for the repository root](#appendix-b-suggested-claudemd-for-the-repository-root)

---

## 0. How to use this document (read first)

This file is the single reference for building Agentica. It is written so that a developer or a coding agent with no prior context can implement any part of the system correctly.

### 0.1 How the document is organised

- **Part I (§1–§32): Specification.** What the system is and how each part must be built.
- **Part II (§33–§35): Issue backlog.** Every unit of work as a ready-to-file GitHub issue, linked back to Part I. Claude Code should create issues from Part II only, and read the Part I sections each issue references when implementing it.
- **Appendices.** A worked end-to-end example and a suggested `CLAUDE.md`.

### 0.2 Tags used throughout

- **[P] Proposal**: committed in the approved proposal. Do not change scope, feature wording, targets, or technology choices marked [P] without team and supervisor agreement.
- **[D] Design**: recommended implementation detail that the proposal leaves open, such as library calls, schemas, file layout, and thresholds. You may change a [D] item when you find a better option. If you do, record the decision in `docs/adr/` (see §27).
- **[OPEN]**: an unresolved decision that must be settled and recorded early (see §28). Each one has its own issue in Part II.

### 0.3 Rules for Claude Code (non-negotiable)

1. **Scope is exactly the 19 core features, F1–F19.** The five "extended" features in the proposal (F20–F24) have been **dropped by team decision** and must not be built (§6).
2. **Never implement a removed or excluded feature** (§6), even if it seems useful. Examples: NL-to-SQL, email, browser automation, web search, image input, RBAC, application discovery, autonomous root-cause analysis, scheduled tasks, approval queues, audit log viewer, machine registry, setup wizard. If a task seems to need one, stop and ask.
3. **The language model never touches the operating system directly.** Every tool call goes through the Policy and Permission Engine (§11). No code path may execute a tool without a policy decision.
4. **Every modifying action must be gated.** Read-only tools default to Allow. Modifying and destructive tools default to Confirm. Hardline-blocklisted operations are always Deny and cannot be overridden by any config.
5. **Live-state grounding.** Any statement about *current* system state must come from a tool call made in the current turn, never from model memory or earlier turns.
6. **Credentials live only in the OS keyring.** They never go in PostgreSQL, config files, logs, or prompts.
7. **Local mode means zero egress.** In local mode, no request, document, or system data may leave the host, and the app must work with the network unplugged (remote management of LAN targets excepted, since the admin explicitly targets them).
8. **Never pass a model-generated string into a shell.** Never use `subprocess(..., shell=True)` with model-generated strings. Build commands as argv lists or templated commands with `shlex.quote` / PowerShell-escaped arguments.
9. **Tools are independently testable** outside the agent loop (NFR-7). Each tool gets unit tests.
10. **Build in risk order.** Read-only capability first, destructive capability last, and only after the policy engine and guardrails exist (§8.1).
11. **Issues.** When creating GitHub issues, follow Part II (§33–§35) exactly: create only the issues listed there, with the given IDs, titles, labels, milestones, owners, dependencies, and acceptance criteria. Do not invent extra feature issues.

---

# Part I — Specification

## 1. Project identity

| Field | Value |
|---|---|
| Project title | Agentica — An Agentic Platform for IT Operations and Infrastructure Management |
| Project ID | CS-FYP-1023 |
| Type of project | Industrial |
| Nature of project | Research & Development |
| SDGs | Industry, Innovation and Infrastructure; Decent Work and Economic Growth |
| Areas of specialization | Artificial Intelligence; Cybersecurity; Natural Language Processing |
| Supervisor | Sir Basit Ali Jasani |
| Co-Supervisor | Sir Ghayasuddin Siddiqui |
| Duration | August 2026 to May 2027 (FYP-1: Aug–Dec 2026, FYP-2: Jan–May 2027) |
| Committed scope | **19 core features (F1–F19)**. The proposal's five extended features (F20–F24) are dropped. |

### 1.1 Team

| Member | Role | Reg. # | Email | Code in plan |
|---|---|---|---|---|
| Ahsan Faizan | Group Leader | 23K-0615 | k230615@nu.edu.pk | A |
| Ahzam Hassan | Member | 23K-0695 | k230695@nu.edu.pk | H |
| Ali Samad | Member | 23K-6003 | k236003@nu.edu.pk | S |

### 1.2 Industry partner: ATCO Laboratories Limited

- A pharmaceutical manufacturer based in Karachi, operating since 1978.
- One of Pakistan's largest manufacturers by volume, exporting to more than 23 countries.
- Runs a cGMP-compliant production facility.
- **Why they need Agentica:**
  - A growing estate of on-premises servers to keep running.
  - A regulated environment, so operational data cannot be sent to third-party cloud services.
  - Routine server operations must be handled reliably, with human approval before anything changes.
- ATCO Laboratories has agreed to act as the industry partner. Agentica is built against their operational requirements, which gives the work a real deployment target and a defined set of users.
- **Design consequence:** the local/offline model mode (F14), agentless remote management (F11, F12), and the Confirm-before-change policy (F19) are first-class, not afterthoughts.

---

## 2. What Agentica is (one paragraph)

Agentica is a downloadable desktop application, installable on Windows and Linux, that places a governed AI agent over routine IT operations.

1. An administrator describes what they want in plain language.
2. The system retrieves the relevant procedure from the organisation's own documentation using Retrieval-Augmented Generation (RAG).
3. It gathers live state from the target machine: the local host, a Linux server over SSH, or a Windows server over WinRM.
4. It selects and runs an authorised tool.
5. It verifies the outcome and reports back.

The language model never touches the operating system directly. Every action passes through a policy engine that grades it by risk and then allows it, holds it for confirmation, or refuses it, backed by guardrails that detect destructive commands.

The system runs against either a hosted cloud model or entirely on local hardware. In local mode no data leaves the machine and the app works offline. The same interface is also served over HTTPS for browser and mobile access.

**Contribution (integrative, [P]):** the project sets out to demonstrate three things:

1. One governed agent can coordinate a broad range of IT operations without depending on a proprietary platform.
2. Tool-selection accuracy can be preserved for smaller local models through two-stage routing.
3. The whole system can run privately.

Each claim is measured against a fixed benchmark rather than asserted.

---

## 3. Problem statement [P]

The problem is not the absence of software for IT operations; capable tools exist in abundance. It is a gap in how those capabilities are delivered and governed. There are three gaps.

1. **Application gap.** Existing AI-driven operations tools are delivered as enterprise platforms.
   - They presuppose adoption of a particular observability, cloud, or service-management ecosystem.
   - They process operational data off-premises.
   - Organisations without that investment, and environments where data cannot leave the premises, are excluded.
2. **Methodological gap in governance.** Where autonomy and governance coexist today, governance is either a platform feature outside the user's control or a lightweight approval-and-denylist mechanism. There is no well-characterised design for a risk-tiered, per-target permission layer for a single-administrator tool that can:
   - pause a partially-executed task,
   - persist its state, and
   - resume it after human confirmation.
3. **Performance gap.** Running locally, which is the only configuration that satisfies the privacy constraint, means a model of about 8–14B parameters. At that scale, tool-selection accuracy and multi-step coherence degrade measurably. How much capability is lost relative to a hosted model is an open, measurable question.

**Research question:** How can a natural-language agent be given sufficient authority to perform real IT operations across heterogeneous local and remote systems, while remaining safe, auditable, independent of any proprietary platform, and viable on a locally-hosted model of modest size?

**Presentation version (defense slides), useful as plain-language framing:**

- **No single tool does the whole job.** Monitoring, files, services, remote servers, and written procedures live in separate tools, and the administrator joins them up by hand.
- **Existing tools do not fit smaller teams.** They assume a platform is already in place, are priced and configured for large organisations, and move data off the premises.
- **Letting an AI agent act is risky.** Control today is either the vendor's decision or a simple blocked-command list, and there is no way to pause, save state, and continue after approval.
- **Running privately costs capability.** Smaller models choose tools less reliably, and that cost has not been measured.

---

## 4. Motivation [P]

- Reduce manual effort by removing the need to move between monitoring dashboards, terminals, file managers, documentation, and remote-management consoles for routine tasks.
- Improve efficiency and accessibility: state an intent in plain language instead of recalling the syntax of several tools.
- Automate repetitive diagnostic work: gathering evidence and locating the applicable procedure.
- Provide a simple, consistent interface, reachable from the desktop app and from a browser on another machine.
- Improve reliability by grounding guidance in the organisation's own procedures, and by requiring that any statement about current state comes from a live check.
- Centralise infrastructure information, so that local and registered remote machines are visible in one place.
- Remove the configuration and expertise barrier for smaller teams: a single installable application with safe defaults.
- Make private operation possible, for organisations that cannot send operational data to a third party.

---

## 5. Aim and objectives [P]

**Aim:** design, implement, and evaluate a governed natural-language agent that performs real IT operations across local and remote systems, delivered as a self-contained desktop application that needs minimal configuration and can run entirely offline.

| # | Objective | Realised by |
|---|---|---|
| O1 | Orchestration core capable of multi-step planning, tool selection, and verification, able to pause at a policy checkpoint, persist state, and resume after confirmation | §10, F1–F4, F19 |
| O2 | Retrieval-augmented knowledge module over the organisation's own SOPs, using hybrid semantic and keyword search, with retrieval quality measured empirically | §13, F5, F6 |
| O3 | Risk-tiered policy and permission engine plus guardrails for destructive operations, such that no modifying action can bypass it | §11, §12, F18, F19 |
| O4 | Monitoring, file, service, and application-status tooling for the local machine, and equivalent management for remote Linux and Windows | §16–§18, F7–F12 |
| O5 | Cloud and fully local model execution behind one interface, with the capability difference quantified | §15, F14, F15 |
| O6 | Better tool-selection accuracy for smaller models through two-stage routing, evaluated against a flat baseline | §14, §25 |
| O7 | Installable desktop app with a browser-accessible interface and safe default configuration | §22, §23, F17 |
| O8 | Quantitative evaluation against a fixed benchmark: task success, tool selection, troubleshooting, retrieval, safety, efficiency | §25 |

### 5.1 Scope boundaries [P]

- This is a **functional prototype**, not a commercial product. It does not try to replace enterprise IT-management platforms.
- **Exactly 19 features (F1–F19)** are built and evaluated. The proposal's extended tier (scheduled tasks, approval queue, audit log, machine registry, setup wizard) is not built.
- It is a **single-administrator tool**, so there is no multi-user role model (RBAC was removed).
- **No agent is installed on target machines.** Linux is reached agentlessly over SSH; Windows is reached over WinRM after a one-time setup script.
- Out of scope:
  - unrestricted GUI automation,
  - complete enterprise infrastructure management,
  - fully autonomous destructive operations,
  - autonomous root-cause analysis.

---

## 6. Removed and excluded features: DO NOT BUILD

The features below were considered during scoping and deliberately removed. Do not implement them, add partial versions, or add "hooks" for them. If a user request in the running app needs one, the agent should say it is not supported.

| # | Removed / excluded capability | Status | Reason (as decided during scoping) | What exists instead |
|---|---|---|---|---|
| X1 | Database operations / natural-language-to-SQL | Removed | Large, high-risk write surface; needs per-database credentials and schema understanding; outside the IT-ops core the partner needs | None |
| X2 | Email reading, drafting, sending | Removed | Not needed for the IT-operations use case | None |
| X3 | Browser automation | Removed | Not needed; fragile; large attack surface | None |
| X4 | Web search (including cloud-only web search) | Removed | Conflicts with the privacy/offline story; not required by the core | Answers come from the organisation's own knowledge base (F5) |
| X5 | Image input and understanding in chat | Removed | Not needed for evaluation; small local models handle it poorly | None |
| X6 | Desktop notifications | Removed | Scope reduction | Dashboard (F16) |
| X7 | Container management (Docker, etc.) | Removed | Scope reduction | Services running as systemd/SCM services are covered by F9 |
| X8 | Role-based access control (RBAC) | Removed | Agentica is a single-administrator tool | Web login protects remote access (F17); the policy engine governs actions (F19) |
| X9 | Application discovery and lifecycle control | Removed | Reliable auto-discovery is not solvable in general; start/stop of arbitrary non-service apps is not generalisable | Config-based application status (F10); start/stop only through services (F9) |
| X10 | Advanced application health model (API auto-detection, deep health scoring, standalone log analytics) | Removed | Too broad; not measurable in the time available | F10 checks "running + responsive"; reading recent logs as *evidence* is part of guided troubleshooting (F13) |
| X11 | Conditional/deferred task automation ("wait for the download to finish, then restart") | Removed | Needs long-running watchers and event triggers; high complexity | None |
| X14 | Recurring scheduled tasks (proposal F20) | **Dropped (team decision)** | Extended tier; not needed for the evaluation | None. No APScheduler, no job store |
| X15 | Approval workflow / approval queue with approve-for-session or permanent grants (proposal F21) | **Dropped (team decision)** | Extended tier | Core approvals are approve-once, inline in the chat (F19) |
| X16 | Audit and activity logging with in-app viewer and export (proposal F22) | **Dropped (team decision)** | Extended tier | Core keeps an operational JSON log file (§20.4), with no viewer and no audit table |
| X17 | Machine registry, DB-backed (proposal F23) | **Dropped (team decision)** | Extended tier | Targets are declared in `targets.yaml`, and credentials are set from the Machines page (F11, F12) |
| X18 | First-run setup wizard (proposal F24) | **Dropped (team decision)** | Extended tier | Bundled defaults plus the Settings page (NFR-3) |
| X12 | Autonomous root-cause analysis (RCA) / automated diagnosis | **Excluded by design** | Open-ended inference; unreliable on 8–14B models; hard to evaluate objectively | Guided troubleshooting (F13): gather evidence + retrieve procedure; the administrator concludes |
| X13 | Lifecycle control of non-service applications | Excluded | Not solvable in general (no uniform start/stop contract) | Run the app as a service and manage it through F9 |

---

## 7. Feature catalogue (19 core features)

**Scope rule:** the 19 core features (F1–F19) are the whole product and the exact feature set the evaluation in §25 runs against. The proposal also listed five extended features (F20–F24). The team has decided not to build them; they are listed under §6 (X14–X18). Feature IDs F1–F19 keep the proposal numbering.

**Format of each entry:**

- **Header line:** tier, category, owner, target milestone, the requirement it satisfies, and what it depends on.
- **Description [P]:** the proposal wording, verbatim. Do not reword it in user-facing docs.
- **Implementation [D]:** the recommended way to build it.
- **Done when:** acceptance criteria.

### Summary table

| ID | Feature | Tier | Category | Owner | Milestone |
|---|---|---|---|---|---|
| F1 | Natural-language chat interface | Core | Conversational interaction | Ahsan | Mid FYP-1 |
| F2 | GUI task cards | Core | Conversational interaction | Ahzam | Final FYP-1 |
| F3 | Live tool calls | Core | Conversational interaction | Ahsan | Mid FYP-1 |
| F4 | Multi-turn session history | Core | Conversational interaction | Ahsan | Mid FYP-1 |
| F5 | RAG knowledge retrieval | Core | Knowledge retrieval | All | Final FYP-1 |
| F6 | Knowledge-base management | Core | Knowledge retrieval | All | Final FYP-1 |
| F7 | Local system monitoring | Core | Local system management | Ahsan | Mid FYP-1 |
| F8 | File operations | Core | Local system management | Ali | Mid FYP-2 |
| F9 | Service monitoring and control | Core | Local system management | Ali | Final FYP-1 |
| F10 | Application status monitoring | Core | Local system management | Ahzam | Final FYP-1 |
| F11 | Remote Linux server management | Core | Remote infrastructure | Ali | Final FYP-1 |
| F12 | Remote Windows server management | Core | Remote infrastructure | Ahsan | Final FYP-1 |
| F13 | Guided troubleshooting | Core | Agent intelligence | All | Mid FYP-2 |
| F14 | Local/offline private model mode | Core | Agent intelligence | Ahzam | Final FYP-1 |
| F15 | Flexible model selection | Core | Agent intelligence | Ali | Mid FYP-2 |
| F16 | Built-in monitoring dashboard | Core | Interfaces and cross-platform access | Ahzam | Mid FYP-2 |
| F17 | Web interface | Core | Interfaces and cross-platform access | Ali | Final FYP-2 |
| F18 | Guardrails | Core | Safety, control, and governance | All | Continuous (end of Mid FYP-1 → end) |
| F19 | Policy and permission engine | Core | Safety, control, and governance | Ahsan | Mid FYP-1 |

---

### 7.1 Core: Conversational interaction

#### F1. Natural-language chat interface

*Core · Owner: Ahsan · Mid FYP-1 (Oct 2026) · FR-1 · Depends on: orchestrator (§10), model provider (§15), API + SSE (§21)*

**Description [P]:** issue requests and receive plain-language reports.

**Implementation [D]:**
- **UI.** A React chat view with a message list, an input box, and a stop/cancel button.
  - Assistant messages are rendered as Markdown.
  - Each session has a title, auto-generated from the first request.
- **Endpoint.** `POST /api/sessions/{id}/messages` starts a graph run and streams events over Server-Sent Events (§21).
- **Final report node.** It produces a short, plain-language summary:
  - what was checked,
  - what was done,
  - what resulted,
  - what (if anything) needs the admin's decision.
- **Plain language.** Reports avoid raw command dumps. Raw tool output stays available by expanding the tool-call card (F3).
- **Cancellation.** A cancel aborts the run at the next node boundary. It must never cancel a tool mid-execution in a way that leaves a half-applied change.

**Done when:**
- A read-only request ("How much disk space is free?") returns a correct plain-language answer grounded in a live tool call.
- The median response time is ≤ 5 s in cloud mode (NFR-6).

#### F2. GUI task cards

*Core · Owner: Ahzam · Final FYP-1 (Nov–Dec 2026) · FR-2 · Depends on: router (§14)*

**Description [P]:** domain cards that bias tool routing toward the relevant category.

**Implementation [D]:**
- **Cards.** A row of cards above the chat input, one per tool category:
  - System Monitoring
  - Files
  - Services & Applications
  - Remote Servers
  - Knowledge Base
  - Troubleshooting
- **Effect of selecting a card:**
  - The card sets `task_card=<category>` on the request.
  - It shows 3–4 example prompts for that domain.
  - It may preselect a target machine.
- **Router behaviour.** The selected category is *always included* in the tool scope and gets a similarity bonus. Other categories can still be added when the request clearly spans domains (§14.2), so cards bias routing without hard-locking it.
- **No card.** With no card selected, routing is purely semantic.
- **Card → category mapping** (canonical; the router config must match it):

| Card | Categories force-included | Notes |
|---|---|---|
| System Monitoring | `monitoring` | |
| Files | `files` | Local machine only |
| Services & Applications | `services`, `applications` | |
| Remote Servers | `monitoring`, `services`, `logs` | Requires a target to be selected |
| Knowledge Base | `knowledge` | |
| Troubleshooting | `troubleshooting`, `logs`, `knowledge` | Starts the guided troubleshooting flow (F13) |


**Done when:**
- Selecting a card measurably narrows the tools shown to the model.
- A cross-domain request (e.g. Files card + "then restart nginx") still reaches the services tools.

#### F3. Live tool calls

*Core · Owner: Ahsan · Mid FYP-1 (Oct–Nov 2026) · FR-3 · Depends on: SSE event stream (§21)*

**Description [P]:** the user sees each tool the agent invokes, with its arguments and result, as it happens.

**Implementation [D]:**
- **Events.** The backend emits `tool_start`, `policy_decision`, `tool_end`, and `tool_error` events (schema in §21.2).
- **Card.** The UI renders each call as a collapsible card showing:
  - tool name, target, and arguments (pretty-printed JSON);
  - a live spinner while running;
  - duration;
  - the policy decision badge (Allow / Confirm / Deny);
  - a result preview, with the raw result expandable.
- **Confirm decision.** A Confirm renders an inline approval prompt inside the card (see F19).
- **Streaming source.** Stream from LangGraph using `graph.astream(..., stream_mode=["updates", "messages", "custom"])`, or use `astream_events(version="v2")`. Emit custom events from inside tools via `get_stream_writer()`.
- **Secrets.** Secrets are redacted from displayed arguments and results.

**Done when:** every tool invocation in a multi-step task appears in order, in real time, with its arguments, decision, and result.

#### F4. Multi-turn session history

*Core · Owner: Ahsan · Mid FYP-1 (Oct–Nov 2026) · FR-4 · Depends on: PostgreSQL checkpointer (§20)*

**Description [P]:** conversation context is retained across a session.

**Implementation [D]:**
- **Checkpoints.** Each session is a LangGraph `thread_id`. State is persisted by `PostgresSaver` / `AsyncPostgresSaver` from `langgraph-checkpoint-postgres`, in the same PostgreSQL instance.
- **Session list.** Held in a `sessions` table (id, title, created_at, updated_at, backend used). The UI shows a sidebar to reopen past sessions.
- **Context budget.** Small local models have limited context:
  - Keep the last N turns verbatim.
  - Keep a rolling summary of older turns.
  - Keep tool outputs as compact structured summaries (full raw outputs stay in the checkpoint, not in the prompt).
- **Grounding rule.** A new turn that asks about current state must re-query. Old tool results in history are *not* valid evidence for "now".

**Done when:**
- Follow-ups such as "restart it" resolve correctly against the previous turn's subject.
- Reopening a session after an app restart restores the conversation.

---

### 7.2 Core: Knowledge retrieval

#### F5. RAG knowledge retrieval

*Core · Owners: All members · Oct → Final FYP-1 (Dec 2026) · FR-5 · Depends on: data layer, embedding model (§13)*

**Description [P]:** hybrid semantic and keyword search over organizational documentation.

**Implementation [D]:** the full pipeline is in §13. In summary:
- **Search.** Dense search (pgvector, HNSW, cosine) and PostgreSQL full-text search (`tsvector` + `websearch_to_tsquery` + `ts_rank_cd`), fused with Reciprocal Rank Fusion (k = 60).
- **Chunking.** Structure-aware (by headings and procedure steps). Each chunk is prefixed with its heading path (contextual header).
- **Embeddings.** A local sentence-transformer of about 300M parameters in *every* mode, so retrieval is identical in cloud and local configurations.
- **Exposed as.** The tool `search_knowledge_base(query, top_k)`. It returns chunks with `doc_title`, `heading_path`, `chunk_id`, and scores.
- **Citations.** Answers cite the source document and section.
- **Weak results.** When retrieval is weak (top dense similarity below a calibrated threshold), the agent says the knowledge base does not cover it. It does not invent a procedure.
- **Reranker.** A cross-encoder reranker is optional, and is added **only if** the evaluation shows hybrid retrieval misses Recall@5 ≥ 0.85.

**Done when:**
- Recall@5 ≥ 0.85 on the retrieval question set.
- Hybrid beats dense-only.
- Answers are grounded in the retrieved passages.

#### F6. Knowledge-base management

*Core · Owners: All members (with RAG) · Final FYP-1 · FR-6 · Depends on: F5*

**Description [P]:** point the app at a folder to ingest text-extractable documents (PDF, DOCX, Markdown, HTML, plain text), and add, remove, or re-index them in-app, with stale content cleared automatically when a source file changes.

**Implementation [D]:**
- **UI page "Knowledge Base".** Choose watched folder(s); list documents with status (queued / indexed / failed / stale), chunk count, and last indexed time; buttons to add file, remove, re-index one, and re-index all.
- **Extractors.**
  - PDF: `pypdf`
  - DOCX: `python-docx`
  - HTML: `beautifulsoup4`
  - Markdown / TXT: read directly
  - Scanned image-only PDFs are *not* supported (no OCR). Mark them as `failed: no extractable text`.
- **Change detection.**
  - Store a SHA-256 of each file.
  - A `watchdog` observer on watched folders triggers ingest on create/modify and delete on removal.
  - A startup rescan catches changes made while the app was closed.
- **Stale cleanup.** `chunks.document_id` has `ON DELETE CASCADE`. Re-indexing deletes the document's chunks and re-inserts them in one transaction, so there are never mixed old/new chunks.
- **Background work.** Ingestion runs in a background worker with progress events to the UI. The chat stays usable while ingesting.

**Done when:**
- Editing a source file and saving it causes the old content to disappear from search results and the new content to appear, with no manual action.
- Deleting a file removes all of its chunks.

---

### 7.3 Core: Local system management

#### F7. Local system monitoring

*Core · Owner: Ahsan (Gantt: "Server monitoring (self)") · Mid FYP-1 (Oct–Nov 2026) · FR-7*

**Description [P]:** CPU, memory, storage, network, and processes.

**Implementation [D]:**
- **Library.** `psutil` on the host running Agentica. psutil is **local only**; remote machines use native commands (§16).
- **Tools (all Read, Allow):**
  - `get_system_overview`: the always-available status tool, returning a CPU/mem/disk/uptime summary.
  - `get_cpu_usage`
  - `get_memory_usage`
  - `get_disk_usage`
  - `get_network_stats`
  - `list_top_processes(sort_by, limit)`
  - `get_process_details(pid|name)`
- **CPU sampling.** `psutil.cpu_percent()` needs a prior sample. Keep a background sampler, or call with `interval=0.5`.
- **Output shape.** Tools return **structured JSON** (Pydantic models) with units, e.g. `{"used_bytes":..., "total_bytes":..., "percent":...}`, not preformatted strings.

**Done when:** values match OS tools (Task Manager, `top`, `df`) within normal sampling tolerance, and each tool has unit tests.

#### F8. File operations

*Core · Owner: Ali · Mid FYP-2 (Jan 2027) · FR-8 · Depends on: F19, F18 (destructive capability, so it comes after governance)*

**Description [P]:** create, delete, modify, move, rename, and organize, with search and disk-usage analysis.

**Implementation [D]:**

| Tools | Risk tier | Default decision |
|---|---|---|
| `list_directory`, `read_file` (size-capped, text only), `search_files` (name glob + optional content search, bounded), `analyze_disk_usage` (largest dirs/files) | Read | Allow |
| `create_file`, `write_file`, `create_directory`, `copy_path`, `move_path`, `rename_path` | Modify | Confirm |
| `delete_path` | Destructive | Confirm |

- **Library.** `pathlib` / `shutil`.
- **Path allowlist.** Every path is `Path(p).expanduser().resolve(strict=False)` and must satisfy `resolved.is_relative_to(allowed_root)` for some root in the policy allowlist. Checking the resolved path defeats `..` and symlink escapes. Denied paths (e.g. `~/.ssh`, the OS system dirs, Agentica's own data dir) always win.
- **Deletes.** Delete goes to the OS trash via `send2trash` by default (recoverable). Permanent delete needs an explicit flag and is still Confirm.
- **Protected files.** Writes never follow symlinks out of the allowlist and never overwrite without `overwrite=true` in the arguments.
- **Remote.** Remote file operations are **not** in scope for F8. F8 is about the local machine. Remote log reading happens through `get_logs` (§14.5).

**Done when:**
- All operations work inside allowed roots.
- Traversal and symlink-escape attempts are refused.
- Every modifying operation shows a Confirm prompt under default policy.

#### F9. Service monitoring and control

*Core · Owner: Ali · Final FYP-1 (Nov–Dec 2026) · FR-9 · Depends on: F19*

**Description [P]:** status, start, stop, and restart across systemd and the Windows Service Control Manager, which covers server applications that run as managed services.

**Implementation [D]:**
- **Tools:**
  - `get_service_status(name, target)` and `list_services(target, filter)`: Read, Allow.
  - `start_service` and `restart_service`: Modify, Confirm.
  - `stop_service`: Destructive, Confirm.
- **Local Linux.** `pystemd` (`pystemd.systemd1.Unit`) reads `ActiveState`, `SubState`, `MainPID`, `UnitFileState`, and calls `Start/Stop/Restart(b"replace")`. Control needs root or a polkit rule. The fallback is `systemctl` via argv with `--no-pager`.
- **Local Windows.** `pywin32`'s `win32serviceutil.QueryServiceStatus/StartService/StopService/RestartService` (needs Administrator). `psutil.win_service_iter()` is a read-only alternative for listing.
- **Remote.** SSH runs `systemctl show <unit> --property=ActiveState,SubState,MainPID,UnitFileState` and `sudo systemctl restart <unit>`. WinRM runs `Get-Service` / `Restart-Service` with `ConvertTo-Json` (§17).
- **Verification.** A deterministic post-condition runs after every control action, e.g. after `restart_service`, poll status until `active` / `Running` or a timeout (e.g. 30 s). The result is reported as verified or not.
- **Self-protection.** The policy denies stopping the channels Agentica itself depends on: `sshd`, `WinRM`, Agentica's own PostgreSQL.

**Done when:**
- Status is correct on both OSes, local and remote.
- start/stop/restart work after confirmation and are verified.
- Stopping `sshd` / `WinRM` is refused.

#### F10. Application status monitoring

*Core · Owner: Ahzam · Final FYP-1 (Nov–Dec 2026) · FR-10 · Config-based*

**Description [P]:** report whether a configured application is currently running and responsive.

**Implementation [D]:**
- **Config.** Applications are *declared* in `apps.yaml`; nothing is auto-discovered (see X9). Each entry names a target plus any combination of checks:

```yaml
applications:
  - name: accounting-app
    target: server-02            # "local" or a target id from targets.yaml
    process: ["AccountingSvc.exe"]   # running check (any match)
    service: "AccountingSvc"         # optional; running check via F9
    tcp_port: 8443                   # responsive check (TCP connect)
    http:                            # optional responsive check
      url: "https://server-02:8443/health"
      expect_status: 200
      timeout_s: 5
```

- **Status result:**
  - `UP`: running and all responsive checks pass.
  - `DEGRADED`: running but a responsive check fails.
  - `DOWN`: not running.
  - `UNKNOWN`: target unreachable or check error.

  Each result includes the individual check results.
- **Tools:** `get_app_status(name)` and `list_configured_apps()`, both Read, Allow. The dashboard also consumes this.
- **Checks are cheap and side-effect free:** process table lookup, service status, a TCP connect with timeout, an HTTP GET via `httpx` with timeout. Remote process checks use `pgrep -x` / `Get-Process -Name`. Port checks run from the Agentica host, or on the target via `ss -tln` / `Get-NetTCPConnection` when the port is not reachable externally.
- **No lifecycle control here.** To restart an app it must be a service (F9).

**Done when:** for each configured app, stopping it, blocking its port, and restoring it produce DOWN, DEGRADED, and UP respectively.

---

### 7.4 Core: Remote infrastructure

#### F11. Remote Linux server management

*Core · Owner: Ali · Final FYP-1 (Nov–Dec 2026) · FR-11*

**Description [P]:** agentless over SSH.

**Implementation [D]:** details in §17.1. In summary:
- **Transport.** Fabric/Paramiko connections with key-based auth (the private key path or passphrase is held in the keyring). Connections are pooled per target.
- **Host keys.** On first connect the admin confirms the fingerprint, which is then pinned (no silent `AutoAddPolicy`).
- **Tools are target-polymorphic.** The same tool names as local (`get_system_overview`, `get_service_status`, `restart_service`, `get_logs`, ...) take a `target` argument. The target backend runs native commands and parses them into the *same* Pydantic result models as local.
- **Privileges.** Reading needs a normal user. Service control needs `sudo`, ideally a NOPASSWD sudoers rule scoped to `systemctl` for listed units.
- **Setup.** An optional helper `infra/linux-target-setup.sh` creates a dedicated user, installs the public key, and adds the scoped sudoers rule.

**Done when:** monitoring, service status and control, logs, and app status all work on an Ubuntu VM with nothing installed on it beyond standard OpenSSH.

#### F12. Remote Windows server management

*Core · Owner: Ahsan · Final FYP-1 (Dec 2026) · FR-11*

**Description [P]:** over WinRM, with a target setup script that keeps onboarding to a few steps.

**Implementation [D]:** details in §17.2. In summary:
- **Transport.** `pywinrm` over HTTPS on port 5986 with NTLM (Kerberos when domain-joined). Run PowerShell via `Session.run_ps`, with output piped through `ConvertTo-Json -Depth 4 -Compress` and parsed into the shared result models.
- **Setup script.** `infra/windows-target-setup.ps1`, run once as Administrator on the target. It:
  - enables PS Remoting,
  - creates a self-signed certificate,
  - creates the HTTPS listener,
  - opens firewall port 5986,
  - prints the certificate thumbprint for pinning.

  Onboarding is: run the script, then enter host, user, and password in Agentica.
- **TLS.** Certificate validation uses the exported cert (`ca_trust_path`). "Ignore certificate" is never the default.
- **Polling.** WinRM calls are slower than SSH, so the dashboard polls Windows targets less often (§16).

**Done when:** the same capabilities as F11 work on a Windows Server VM after running only the setup script.

---

### 7.5 Core: Agent intelligence

#### F13. Guided troubleshooting

*Core · Owners: All members · Mid FYP-2 (Jan–Feb 2027) · FR-12 · Depends on: F5, F7, F9, F10, F11, F12*

**Description [P]:** on a reported fault, gather the relevant live state, retrieve the procedure that covers it, and present the evidence and the recommended steps to the administrator, who reaches the conclusion and approves any action.

**Implementation [D]:** details in §19. In summary:
- **Fault lookup table.** A **fault-category → evidence lookup table** (`faults.yaml`) maps each category to the read-only evidence tools to run:
  - service_down
  - app_unresponsive
  - disk_full
  - memory_exhausted
  - high_cpu
  - config_error
  - process_killed
  - connectivity
- **Flow:**
  1. Classify the fault (the LLM picks from an enum; the admin can correct it).
  2. `collect_fault_evidence(category, target, subject)` runs the evidence bundle. All evidence tools are Read, so they run without prompts.
  3. `search_knowledge_base` runs with the symptoms plus evidence keywords.
  4. The agent presents the evidence, the matching procedure with citations, and the recommended steps.
- **Remediation.** Any remediation step the admin chooses is a normal tool call and goes through the policy engine (Confirm).
- **No root-cause claims.** The agent never states a root cause as fact. It says the evidence is consistent with a documented procedure (X12 is excluded).

**Done when:** on the seeded-fault catalogue (§25.3), the correct evidence is gathered and the correct procedure is retrieved in ≥ 85% of cases (cloud) and ≥ 75% (local).

#### F14. Local/offline private model mode

*Core · Owner: Ahzam · Final FYP-1 (Nov–Dec 2026) · FR-16, NFR-2*

**Description [P]:** runs entirely on the user's hardware, with no data leaving the machine and full offline operation.

**Implementation [D]:** details in §15.
- **Inference.** Ollama at `http://127.0.0.1:11434`, with instruction-tuned models at 4-bit quantisation:
  - about 8B: Llama 3.1 8B Instruct or Qwen 2.5 7B Instruct
  - about 14B: Qwen 2.5 14B Instruct
- **Embeddings.** Always local. Weights are bundled or pre-downloaded; set `HF_HUB_OFFLINE=1`.
- **Egress guard.** In local mode the model provider refuses to construct any cloud client. All outbound HTTP from the app is disabled except to targets the admin configured.
- **Context window.** Set it explicitly. Ollama's default context is small; set `num_ctx`, e.g. 8192–16384, via the native API options, a Modelfile, or the `OLLAMA_CONTEXT_LENGTH` env var. Otherwise tool schemas and history get silently truncated.

**Done when:**
- The full core benchmark runs with the network physically disconnected (except LAN targets).
- A packet capture shows no traffic to any external host.

#### F15. Flexible model selection

*Core · Owner: Ali · Mid FYP-2 (Jan–Feb 2027) · FR-16*

**Description [P]:** switch between a cloud model for maximum capability and a local model for privacy and offline use.

**Implementation [D]:**
- **Settings UI.** Settings has a backend selector (Cloud / Local):
  - Cloud: provider base URL and model name; the API key goes in the keyring.
  - Local: the list of installed Ollama models from `GET /api/tags` on Ollama.
- **One interface.** Both backends sit behind one `ModelProvider` interface (§15.1). Switching takes effect on the next turn. Session history is model-agnostic text, so a session can continue across a switch.
- **Visibility.** The current backend is always visible in the UI header, e.g. "Local · qwen2.5:14b". Every stored run records which backend and model produced it, which the evaluation needs.
- **Parity.** Identical functionality in both modes. Only reasoning quality and speed differ.

**Done when:** switching mid-session works without a restart, and the same benchmark runs under each backend.

---

### 7.6 Core: Interfaces and cross-platform access

#### F16. Built-in monitoring dashboard

*Core · Owner: Ahzam · Mid FYP-2 (Feb–Mar 2027) · FR-17 · Depends on: F7, F10, F11, F12, poller (§16)*

**Description [P]:** an at-a-glance view of local and registered remote machines.

**Implementation [D]:**
- **Layout.** A React + Recharts dashboard page with one tile per machine:
  - reachability, OS, and uptime;
  - CPU / RAM / disk gauges with a short sparkline;
  - service and app status badges for the apps configured on that machine (F10).
- **Data source.** The background poller cache (§16.2), not live calls. Each tile shows "updated N s ago" and turns grey or amber when stale or unreachable.
- **Endpoints.** `GET /api/dashboard` returns a snapshot, and an SSE stream `/api/dashboard/stream` pushes updates.
- **"Registered" machines** means the targets declared in `targets.yaml` and onboarded from the Machines page (§17.3). There is no database-backed machine registry.
- **Read-only.** The dashboard never triggers actions. Clicking a tile can open the chat with a task card and target preselected.

**Done when:** the dashboard shows accurate, periodically refreshed state for the local machine plus one Linux and one Windows VM, and clearly marks stale or unreachable machines.

#### F17. Web interface

*Core · Owner: Ali · Final FYP-2 (Mar–Apr 2027) · FR-18*

**Description [P]:** browser-based access from other desktops and mobile devices, so the agent is reachable away from the machine it runs on.

**Implementation [D]:**
- **Same build.** The *same* React build is served by FastAPI as static files over HTTPS. There is no second UI implementation, but the layout must be responsive for mobile.
- **Off by default** (safe default). When enabled in Settings:
  - a self-signed certificate is generated with `cryptography` and stored in the app data dir;
  - the server binds to the LAN interface on a configurable port;
  - the UI shows the fingerprint for the admin to trust.
- **Authentication.** A single admin password (argon2 hash via `argon2-cffi` or `pwdlib`), set when enabling web access. Sessions use HttpOnly, Secure, SameSite=Strict cookies, with login rate limiting and CSRF protection on state-changing requests. `fastapi-users` / `Authlib` are acceptable but likely heavier than needed for one admin.
- **Server-side policy.** All policy enforcement is server-side, so web users get exactly the same Allow/Confirm/Deny behaviour and approval prompts as the desktop.
- **Proposal wording.** Deliverable 5 says the web interface provides cross-platform access to "a subset of features". Chat, live tool calls, approvals, dashboard, and read-only KB search are the minimum. Admin-level settings (policy file, web-access toggle, keyring) may stay desktop-only.

**Done when:** from a phone on the same LAN, the admin can log in, chat, approve a Confirm prompt, and view the dashboard over HTTPS.

---

### 7.7 Core: Safety, control, and governance

#### F18. Guardrails

*Core · Owners: All members · Continuous from the end of Mid FYP-1 (Nov 2026) to the end (May 2027) · FR-14*

**Description [P]:** dangerous-command detection, a hardline blocklist for catastrophic operations, strict tool-schema validation, and anti-hallucination grounding.

**Implementation [D]:** details in §12. The four parts:
1. **Dangerous-command detection.** Parse every command string (`shlex` on POSIX, a PowerShell tokenizer approach on Windows). Split it on control operators, then match each sub-command against a pattern set. The proposal adopts the open-source Hermes Agent dangerous-command pattern set [18] as the base rather than writing one from scratch. Matches escalate the action to Confirm or Deny.
2. **Hardline blocklist.** A small set of catastrophic operations that are always Deny, cannot be overridden by any policy file, and are checked first. Examples: `rm -rf /`, `mkfs`, `dd` to a block device, fork bombs, `Format-Volume`, `diskpart clean`, `vssadmin delete shadows`, encoded PowerShell.
3. **Strict tool-schema validation.** Tool names are constrained to an enum, and arguments are validated against Pydantic schemas (`extra="forbid"`, enums, ranges, patterns). Invalid calls are rejected and returned to the model for correction (max 2 retries).
4. **Anti-hallucination grounding.** State claims must come from a tool call in the current turn; procedures come from retrieved chunks with citations; tool-output text is treated as data, never as instructions (prompt-injection defence).

**Why continuous [P]:** deciding what counts as a destructive command is slow, iterative work that cannot be compressed alongside feature work, and it must grow as each new capability widens the surface. Every new tool PR must add guardrail tests.

**Done when:**
- No false allows are observed on the adversarial set (a release blocker).
- The benign-action pass rate is ≥ 85%.

#### F19. Policy and permission engine

*Core · Owner: Ahsan · Mid FYP-1 (Oct–Nov 2026) · FR-13, FR-15*

**Description [P]:** every action is graded by risk and then allowed, refused, or held for confirmation, where Confirm pauses execution and prompts the administrator before the action proceeds. Ships with safe defaults and supports per-target rules.

**Implementation [D]:** full design in §11. In summary:
- **Deterministic.** Pure Python, with no LLM involvement, so results never vary by model backend.
- **Rules.** Loaded from `policy.yaml`: risk-tier defaults, per-tool overrides, per-target overrides (glob on target id), path allowlists and denylists, and protected services.
- **Confirm.** Implemented with LangGraph `interrupt()` in a dedicated approval node:
  - the full graph state is checkpointed to PostgreSQL;
  - the UI shows the prompt;
  - `Command(resume={"decision": "approve"|"reject"})` resumes the run;
  - the paused task survives an application restart (NFR-5).
- **Approve-once only.** Every Confirm is approved or rejected individually, inline in the chat. There is no approval queue and no session-wide or permanent grants (X15).

**Done when:**
- 100% branch coverage on the decision function.
- Every modifying tool is gated.
- An interrupted, confirmed task resumes correctly after killing and restarting the app.

---

---

## 8. Development methodology

### 8.1 Development approach: risk-first and incremental [P]

- **Incremental and ordered by risk.** Read-only and low-risk capabilities are implemented and validated **before** any destructive action is enabled.
- **Each module is independently testable** before integration.
- **Governance comes before modification.** The orchestration core and the policy and permission engine are built before any capability that can modify a system, so every later module sits on a governance layer that already works rather than having one retrofitted around it.
- **Guardrails are continuous.** Dangerous-command detection, the non-overridable blocklist, and schema-constrained tool arguments begin once the core exists and extend alongside every module added after it.
- **Semester split:**
  - **FYP-1** delivers a complete core operating against the **local machine**, demonstrable without remote infrastructure, plus the remote Linux and Windows tooling.
  - **FYP-2** extends that proven core outward: file operations, model switching, troubleshooting, dashboard, web, evaluation, and packaging.
- **Remote order.** Remote Linux precedes Windows, because it is agentless with less setup friction, which de-risks the harder integration.
- **Slack.** Only the fixed university milestones and the FYP-1/FYP-2 boundary are hard dates. Module durations carry margin, and independent modules overlap. The extended features were dropped up front, so all slack goes to the 19 core features. If the schedule still tightens, reduce polish (UI refinements, extra fault categories), never what the evaluation measures.

### 8.2 Build order and capability risk classes [D]

| Order | Capability class | Examples | Precondition |
|---|---|---|---|
| 1 | Skeleton | FastAPI app, DB schema, LangGraph graph, SSE, chat UI | none |
| 2 | Read-only local | F7 monitoring tools, `search_knowledge_base` | skeleton |
| 3 | Governance | F19 policy engine (+ interrupt/resume), first guardrails (F18) | skeleton |
| 4 | Low-risk modify | `start_service`, `restart_service`, file create/copy | policy engine working |
| 5 | Remote read | SSH/WinRM monitoring, status, logs | target backends |
| 6 | Remote modify | remote service control | governance + remote read |
| 7 | Destructive | `stop_service`, `delete_path`, `exec_command` | guardrails for that tool merged, with tests |

### 8.3 Milestone definitions of done [P + D]

| Milestone | Approx. date | Must be demonstrable |
|---|---|---|
| Proposal defense | 22–24 Sep 2026 | Proposal, literature review, plan (**done**) |
| **Mid FYP-1** | ~6–8 Nov 2026 (early prototype for the late-October review) | Working request-to-response loop (F1, F3, F4); local monitoring (F7); first retrieval pipeline (F5 started); the policy gate in place (F19) with interrupt/resume; data layer; router v1 |
| **Final FYP-1** | late Dec 2026 | Full local and remote core: F2, F9, F10, F11, F12; completed RAG and KB management (F5, F6); offline model mode (F14); guardrail layer established (F18); integration, testing, and documentation (December is for integration, not new development) |
| **Mid FYP-2** | ~Mar 2027 | File operations (F8), model switching (F15), guided troubleshooting (F13), dashboard (F16) |
| **Final FYP-2** | late May 2027 | Web interface (F17), evaluation results for every Table 4 metric, the packaged installer, thesis, and final demonstration |

### 8.4 Engineering practices [D]

- **Git and PRs.** Git + GitHub, one branch per feature (`feat/F09-service-control`), PRs reviewed by one other member, and CI running lint and tests on Windows and Linux.
- **Tool PR checklist.** Every new tool PR includes:
  1. a Pydantic input/output model;
  2. a risk tier;
  3. unit tests with mocked targets;
  4. guardrail/policy tests;
  5. an entry in the tool catalogue (§14.5);
  6. at least 3 labelled benchmark tasks (§25).
- **Benchmark early.** The evaluation fixtures start early (retrieval question set in Oct–Nov; task set grown per feature) so regressions are measurable and not left to the end.

---

## 9. System architecture [P]

### 9.1 Three tiers

```text
┌─────────────────────────── PRESENTATION LAYER (Tauri + React) ───────────────────────────┐
│  Desktop Application                         │  Web Interface                            │
│  Tauri shell · React UI                      │  same React build over HTTPS              │
│  chat · dashboard · confirmations            │  browser and mobile access                │
└───────────────────────────────┬──────────────────────────────┬───────────────────────────┘
                                │   REST + Server-Sent Events  │
┌───────────────────────────────▼──────────────────────────────▼───────────────────────────┐
│ APPLICATION LAYER (FastAPI + LangGraph, Python)                                          │
│  API Gateway — FastAPI: request validation (Pydantic) · session auth · event streaming   │
│                                                                                          │
│  Tool Router ─────────► Agent Orchestrator ◄──────► Model Provider                        │
│  embedding similarity   plan → act → verify         cloud API | local (Ollama)            │
│  narrows visible tools  interrupt / checkpoint      one OpenAI-compatible interface       │
│  sentence-transformers  LangGraph StateGraph        switchable                            │
│                               │                                                          │
│  Policy & Permission Engine — every tool call passes through here                        │
│   risk tiers: Allow / Confirm / Deny · per-target rules · YAML policy file               │
│   guardrails: dangerous-command patterns · shlex parsing · schema-constrained arguments  │
│                               │                                                          │
│  Tool layer:  RAG            Monitoring        Files            Apps & Services  Remote   │
│               hybrid         CPU·RAM·disk      create·move·     status·start·    Linux—SSH│
│               dense+FTS      network·procs     delete           stop·restart     Win—WinRM│
│               pgvector       psutil (local)    path allowlist   pystemd/pywin32  Fabric / │
│                                                pathlib/shutil                    pywinrm  │
└───────────────────────────────┬──────────────────────────────────────────────────────────┘
┌───────────────────────────────▼─────────────── DATA LAYER ───────────────────────────────┐
│  PostgreSQL 16 — single local instance              │  OS Keyring                         │
│  • graph checkpoints (pause/resume)                 │  SSH keys and server credentials —  │
│  • pgvector knowledge base (HNSW)                   │  never stored in the database       │
│  • sessions · app settings                                                               │
│  one service to install and back up                 │                                     │
└──────────────────────────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────── TARGET SYSTEMS (external) ───────────────────────────────┐
│  Local Machine (files·processes·services) │ Linux Servers (agentless SSH) │ Windows (WinRM/HTTPS) │
└──────────────────────────────────────────────────────────────────────────────────────────┘
Workflow: User → User Interface → API Gateway → Orchestrator → Policy Engine → Tool → Target System → Result → User
```

**Notes:**
- "Application layer" is the architectural tier (business logic and services). It does not mean "the applications Agentica manages".
- **psutil is local-only.** The Monitoring box's psutil applies to the host running Agentica. Remote monitoring uses native commands over SSH/WinRM (§16).
- **Difference from proposal Fig. 2.** Fig. 2 also shows an activity log, a machine registry, and a scheduler job store. These belonged to the dropped extended tier and are **not built**. The database holds only checkpoints, the knowledge base, sessions, and settings.
- **One PostgreSQL** holds all persistent state, so the app installs and backs up as one unit. Credentials are held separately in the OS keyring.

### 9.2 Components and responsibilities

| Component | Responsibility | Tech [P] | Key rule |
|---|---|---|---|
| Desktop shell | Native window, installer, sidecar lifecycle | Tauri | Starts/stops the Python backend sidecar |
| UI | Chat, task cards, live tool cards, approvals, dashboard, KB, settings | React, Recharts | One build for desktop and web |
| API gateway | REST + SSE, validation, session auth | FastAPI, Pydantic | Every input validated; no business logic in routes |
| Tool router | Narrows tool categories visible to the model | sentence-transformers | Stage 1 of routing; deterministic given the embeddings |
| Orchestrator | Plan → act → verify loop, interrupts, checkpoints | LangGraph `StateGraph` | Only path to tools is via the policy node |
| Model provider | Cloud or local inference behind one interface | OpenAI-compatible API; Ollama | Local mode never builds a cloud client |
| Policy engine | Allow / Confirm / Deny for each tool call | Python + YAML | Deterministic; hardline first; unknown tool → Deny |
| Guardrails | Command parsing, dangerous patterns, schema checks, grounding | shlex, Pydantic, pattern set [18] | Fail closed on parse errors |
| Tool layer | Implementations + target backends (local / SSH / WinRM) | psutil, pathlib/shutil, pystemd, pywin32, Fabric/Paramiko, pywinrm | Returns structured models; never `shell=True` |
| Data layer | Checkpoints, vectors, sessions, settings | PostgreSQL 16 + pgvector | One instance, local only |
| Secrets | Server credentials, API keys | OS keyring (`keyring`) | Never in the DB, config, logs, or prompts |

### 9.3 Deployment topology [D]

```text
Admin workstation (Windows or Linux)
 ├─ Agentica.exe / .AppImage (Tauri)
 │    └─ spawns sidecar: agentica-backend (PyInstaller) on 127.0.0.1:<random port>
 │          ├─ PostgreSQL 16 + pgvector (bundled, local-only, app data dir)   [OPEN-3]
 │          ├─ embedding model weights (bundled)
 │          └─ optional LAN HTTPS listener for the web interface (off by default)
 ├─ Ollama (separately installed, local mode only) on 127.0.0.1:11434
 └─ outbound only:  TCP 22 → Linux targets (SSH) · TCP 5986 → Windows targets (WinRM/HTTPS)
                    HTTPS → cloud model API (cloud mode only)
```

**Limitation [D]:** Agentica pulls from targets, so targets behind NAT that the admin workstation cannot reach are not supported. There is no push agent by design.

---

## 10. Execution flow and orchestrator

### 10.1 The eight-step flow [P] (Fig. 1)

```text
1 · User request ───────── natural language, from chat or a task card
        ▼
2 · Understand intent and route ─ router narrows the visible tool categories
        ▼
3 · Gather context ─────── retrieved procedures · live system state · remote machine state
                            (any claim about current state must come from a live tool call)
        ▼
4 · Select tool and arguments ─ scoped tool set · schema-validated arguments
        ▼
5 · Policy check ◇ ── Deny ────► Blocked: reason returned to the user
        │  └──── Confirm ──► Await confirmation: graph state is checkpointed and
        │                    execution pauses until the administrator responds
        │                    (on approval, execution resumes)
        ▼ Allow
6 · Execute on target ──── local machine · Linux over SSH · Windows over WinRM
        ▼
7 · Verify the outcome ─── re-check state · confirm the action had the intended effect
        ▼
8 · Report to the administrator ─ plain-language summary of what was done and what resulted
```

**Two design decisions [P]:**
1. The confirmation branch is a **graph interrupt** that checkpoints the complete execution state to the database. A partially-executed task therefore survives an application restart and resumes correctly when the admin responds.
2. **Any statement about current system state must originate from a live tool call** rather than from model inference. This is the principal defence against confidently reported but fabricated status.

### 10.2 LangGraph graph design [D]

```text
START
  └─► route ──► gather_context ──► agent ──┬── (final answer) ─────────────────────────► report ─► END
                                           │
                                           └── (tool call) ─► validate ─┬─ invalid (≤2 retries) ─► agent
                                                                        └─ valid ─► policy
                                                                                     ├─ DENY ────► agent  (ToolMessage "blocked: <reason>")
                                                                                     ├─ CONFIRM ─► approval (interrupt) ─┬─ approve ─► execute
                                                                                     │                                   └─ reject ──► agent
                                                                                     └─ ALLOW ───► execute
execute ─► verify ─► agent        (loop until the model returns a final answer or the step limit is hit)
```

| Node | What it does | LLM? |
|---|---|---|
| `route` | Embeds the request; picks the tool categories (task card forced in); decides whether to use no tools (§14) | No |
| `gather_context` | If knowledge/troubleshooting is in scope, pre-runs `search_knowledge_base`; for troubleshooting, runs the evidence bundle | No |
| `agent` | Calls the model with the system prompt, trimmed history, context, and **only the scoped tools**; returns a tool call or a final answer | Yes |
| `validate` | Tool name in enum? Arguments valid against the Pydantic schema? Target known? | No |
| `policy` | Deterministic decision (§11); emits a `policy_decision` event | No |
| `approval` | `interrupt({...})` with a human-readable preview; waits for `Command(resume=...)` | No |
| `execute` | Dispatches to the tool implementation and target backend; timeouts; emits `tool_start`/`tool_end` | No |
| `verify` | Runs the tool's post-condition check (for modifying tools) and attaches `verified: true/false` | No |
| `report` | Final plain-language summary (streamed tokens); cites KB sources and marks unverified results | Yes |

**State schema (sketch):**

```python
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    session_id: str
    task_card: str | None               # F2
    scope: list[str]                    # tool categories visible this turn
    target_hint: str | None             # "local" or a target id
    retrieved: list[ChunkRef]           # RAG context for this turn
    evidence: list[ToolResultRef]       # live results gathered THIS turn (grounding)
    pending_call: ToolCall | None
    decision: PolicyDecision | None
    step: int                           # bounded loop counter
    validation_retries: int
    backend: str                        # "cloud:<model>" | "local:<model>" (recorded for eval)
```

**Critical implementation rules [D]:**
- **The approval node must have no side effects before `interrupt()`.** On resume, LangGraph re-executes the interrupted node from its beginning. Keep execution in the separate `execute` node.
- **Every run carries a `thread_id`.** Use `config={"configurable": {"thread_id": session_id}}`. Use `AsyncPostgresSaver` (psycopg 3, `autocommit=True`, `row_factory=dict_row`) and call `.setup()` once at first start.
- **Bounded loop.** Cap steps per turn (e.g. `MAX_STEPS = 10`) and validation retries (`2`). When the cap is hit, go to `report` with what was done so far.
- **Repeated Deny.** If the model tries a different tool to achieve something that was just denied, the policy evaluates that call independently. After 2 Denies in a turn, stop and report.
- **Pending interrupts.** A session with a pending interrupt shows the approval prompt again when reopened. New messages in that session are blocked until the admin approves or rejects.

### 10.3 Worked example

See Appendix A for a full trace of "The accounting app on Server-02 isn't responding; check it and restart if needed."

---

## 11. Policy and permission engine (F19)

### 11.1 Risk tiers

| Tier | Meaning | Default decision | Examples |
|---|---|---|---|
| `read` | Observes state only; no side effects | **Allow** | `get_system_overview`, `get_service_status`, `search_knowledge_base`, `list_directory`, `get_logs` |
| `modify` | Changes state; recoverable | **Confirm** | `start_service`, `restart_service`, `create_file`, `move_path`, `write_file` |
| `destructive` | Changes state; may lose data or availability | **Confirm** (UI shows a red warning) | `stop_service`, `delete_path`, `exec_command` |
| `hardline` | Catastrophic; matched by the guardrail blocklist | **Deny (non-overridable)** | `rm -rf /`, `mkfs`, `Format-Volume`, `diskpart clean` |

Every tool declares its tier in code. Guardrail findings can only *raise* the effective decision, never lower it. For example, `exec_command` is `destructive` by declaration (Confirm), and a command inside it that matches a hardline pattern becomes Deny. Policy overrides (§11.2, steps 7–9) may relax a tier default for a trusted target, but never past a guardrail finding.

### 11.2 Decision algorithm (deterministic, in this exact order)

```text
decide(call: ToolCall, target: Target) -> Decision{ALLOW|CONFIRM|DENY, reason, rule_id}

 1. tool not in registry                         → DENY  "unknown tool"
 2. schema validation failed                     → DENY  (returned to model to fix; not shown as a block)
 3. guardrail hardline match (any sub-command)   → DENY  "hardline: <pattern>"      ← cannot be overridden
 4. protected resource hit                       → DENY  (denied paths, protected services, Agentica's own data dir)
 5. path outside allowlist (file tools), or a     → DENY  "path not permitted"
    modify/destructive op on a read_only_root
 6. guardrail dangerous-pattern match            → at least CONFIRM (pattern may specify DENY)
 7. per-target override (most specific glob)     → its decision
 8. per-tool override                            → its decision
 9. risk-tier default                            → its decision
10. combine: final = most restrictive of (6) and the first matching of (7)/(8)/(9)
```

- Overrides can **relax** a tier default (e.g. `restart_service: allow` on a lab VM) or **tighten** it. They can never relax steps 1–6.
- The reason string and `rule_id` are always returned. They are shown to the user on Deny/Confirm and logged.

### 11.3 Policy file format (`policy.yaml`, safe defaults bundled) [D]

```yaml
version: 1

defaults:                 # by risk tier
  read: allow
  modify: confirm
  destructive: confirm    # hardline is always deny and is not configurable

tools:                    # per-tool overrides (apply to every target)
  exec_command: confirm
  delete_path: confirm

targets:                  # per-target overrides; keys are globs on target id; most specific wins
  "lab-*":
    tools:
      restart_service: allow
      start_service: allow
  "prod-*":
    tools:
      get_logs: allow
      restart_service: confirm

files:
  allow_roots:            # file tools may only touch paths under these (resolved)
    - "~/Documents"
    - "~/Downloads"
    - "/var/log"          # read tools only; see read_only_roots
  read_only_roots:
    - "/var/log"
    - "C:/Windows/Logs"
  deny:                   # always denied, even inside allow_roots
    - "~/.ssh"
    - "~/.gnupg"
    - "{AGENTICA_DATA_DIR}"

services:
  protected:              # stop/restart denied: these are Agentica's own channels
    - sshd
    - ssh
    - WinRM
    - agentica-postgres
```

- **Loading.** The policy is loaded at startup and on `POST /api/policy/reload`. It is validated with a Pydantic model, and an invalid policy file refuses to load and keeps the previous one.
- **UI.** The core UI shows the effective policy read-only. Editing is by file (a policy editor UI is not required).

### 11.4 Confirm → interrupt → resume

```python
def approval_node(state: AgentState):
    call, decision = state["pending_call"], state["decision"]
    # NO side effects above this line: the node re-runs from the top on resume
    answer = interrupt({
        "type": "approval_required",
        "call_id": call.id,
        "tool": call.name,
        "target": call.target,
        "args": redact(call.args),
        "risk": decision.tier,
        "reason": decision.reason,          # e.g. "modify → confirm (default)"
        "preview": humanize(call),          # "Restart service 'nginx' on server-02 (Linux, SSH)"
    })
    if answer.get("decision") == "approve":
        return Command(goto="execute")
    return Command(goto="agent", update={"messages": [rejected_tool_message(call, answer.get("comment"))]})
```

- **The API:**
  - `POST /api/sessions/{id}/approvals/{call_id}` with `{"decision":"approve"|"reject","comment":?}`.
  - The backend runs `graph.astream(Command(resume=body), config)` and streams the continuation over SSE.
- **Restart test (NFR-5).** Start a Confirm task, kill the backend, restart it, reopen the session. The prompt is shown again; approve; the action executes once and is verified.

---

## 12. Guardrails (F18)

### 12.1 Where commands appear

Most tools are **structured**: psutil calls, pystemd/pywin32 calls, or **templated** remote commands where the tool, not the model, builds the command and only validated arguments are inserted with `shlex.quote` (POSIX) or PowerShell single-quote escaping.

Guardrail command analysis applies to:
- `exec_command(target, command)`: a Confirm-tier escape hatch for commands no structured tool covers (§28, OPEN-5).
- Every templated command, as defence in depth (if a template plus arguments ever yields a dangerous command, it is caught).
- Any file path or service name argument, which is checked against protected resources.

### 12.2 Command analysis pipeline

```text
raw command
 → normalise (strip, collapse whitespace; Windows: case-fold)
 → reject if unparseable (shlex ValueError, unbalanced quotes)            → CONFIRM at minimum (fail closed)
 → detect obfuscation: base64 / -EncodedCommand / -enc, eval, $( ), backticks,
   `curl|wget … | sh|bash`, `iex (New-Object Net.WebClient)…`            → DENY or CONFIRM per pattern
 → split into sub-commands on ; && || | & newline and inside $( ) / ` `
 → for each sub-command: argv[0] basename (strip sudo/env/nohup/timeout wrappers), flags, targets
 → match against: HARDLINE list → DENY ; DANGEROUS patterns → CONFIRM/DENY
```

Base the dangerous-pattern set on the Hermes Agent pattern set [18] (per the proposal), vendored into `guardrails/patterns/` with its licence and a version note. Extend it with Windows/PowerShell patterns and with the project's own tests.

### 12.3 Hardline blocklist (always DENY): starting set [D]

| Platform | Patterns (illustrative, extend with tests) |
|---|---|
| Linux | `rm -rf /`, `rm -rf /*`, `rm -rf --no-preserve-root`, `rm -rf ~` (home root); `mkfs*`; `dd … of=/dev/sd*` (and `nvme*`, `vd*` devices); `> /dev/sd*`; `shred /dev/*`; fork bomb `:(){ :\|:& };:`; `chmod -R 777 /`; `chown -R … /`; `mv / …`; `wipefs`; `echo … > /proc/sysrq-trigger` |
| Windows | `Format-Volume`; `format X:`; `diskpart` with `clean`; `Remove-Item -Recurse` on a drive root or `C:\Windows`; `del /s /q C:\`; `rd /s /q C:\`; `vssadmin delete shadows`; `wmic shadowcopy delete`; `bcdedit /delete`; `cipher /w`; `reg delete HKLM\…` root hives; `Clear-Disk`; `Initialize-Disk` |
| Both | Encoded or obfuscated execution (`powershell -enc …`, `base64 -d \| sh`); download-and-execute pipes; disabling security tooling (`Set-MpPreference -DisableRealtimeMonitoring`, `systemctl stop auditd`) |

**Confirm-level (dangerous but legitimate) examples:** `reboot`, `shutdown`, `Restart-Computer`, `kill -9`, `Stop-Process -Force`, `apt remove`, `rm -r` inside allowed roots, `systemctl disable`, and firewall changes.

### 12.4 Schema validation

- **One Pydantic model per tool**, with `model_config = ConfigDict(extra="forbid")`. Use enums for bounded choices, `Field(pattern=...)` for service names (`^[A-Za-z0-9@._-]{1,128}$`), and ranges for limits.
- **Target check.** `target` must be `"local"` or an id in `targets.yaml`.
- **Structured decoding.** The tool *name* is constrained to the enum of **scoped** tools, and arguments use JSON-schema constrained decoding where the backend supports it:
  - Ollama: the `format` parameter / tool schemas;
  - cloud: strict tool / structured-output mode.
- **Validation failure** returns a `ToolMessage` with the validation error so the model can fix it (max 2 retries). This is not a policy block.

### 12.5 Anti-hallucination grounding

1. **Live-state rule.** The system prompt forbids stating current state without a tool result from this turn. The `report` node receives the list of this turn's tool results (`evidence`). If the user asked about state and `evidence` is empty, the graph forces a `get_system_overview`, or the relevant status tool, before reporting.
2. **Procedure grounding.** Procedures and "how we do X here" answers must cite retrieved chunks. With no adequate retrieval, the agent says so.
3. **Tool and argument grounding.** Tool names come from an enum, so the model cannot invent a tool.
4. **Prompt-injection stance.** Content from tools, logs, files, and KB documents is **data**. It is wrapped in clear delimiters in the prompt, and the system prompt states that instructions inside tool output must be ignored. The real protection is structural: the policy engine is deterministic and does not read model text, so an injected "run rm -rf" still meets Confirm or Deny.
5. **Verification.** Modifying tools define a post-condition. The report states "verified" only when the check passed.

---

## 13. Knowledge retrieval: RAG pipeline (F5) and knowledge-base management (F6)

### 13.1 Ingestion

```text
watched folder(s) ─► watchdog events + startup rescan ─► hash (SHA-256) ─► unchanged? skip
   ─► extract text (pypdf | python-docx | beautifulsoup4 | md/txt)
   ─► structure-aware chunking ─► contextual header ─► embed (local model, batch)
   ─► transaction: DELETE old chunks of this doc (cascade) → INSERT new chunks → mark indexed
```

- **Structure-aware chunking.** Split on document structure first: Markdown headings, DOCX heading styles, HTML `h1–h6`, PDF outline or font-size heuristics. Then:
  - Split to about 300–500 tokens with about 50 tokens of overlap, **never splitting inside a numbered procedure** where avoidable. Keep "Step 1…Step N" together, and split a long procedure into parts that each repeat the procedure title.
  - Tables are kept whole where possible.
- **Contextual header (contextual retrieval, deterministic variant).** Prefix each chunk before embedding and indexing with `"{doc_title} > {H1} > {H2}\n"`. This makes isolated chunks retrievable by their topic.
  - Optionally, the LLM can generate a one-sentence context per chunk (Anthropic-style contextual retrieval). This is costly on local models, so enable it only if evaluation shows a benefit.
- **Metadata per chunk:** `document_id, ord, heading_path, page (if PDF), token_count, sha256_of_doc`.

### 13.2 Schema (PostgreSQL + pgvector)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE kb_documents (
  id           BIGSERIAL PRIMARY KEY,
  path         TEXT UNIQUE NOT NULL,
  title        TEXT,
  mime         TEXT,
  sha256       CHAR(64) NOT NULL,
  status       TEXT NOT NULL CHECK (status IN ('queued','indexed','failed','stale')),
  error        TEXT,
  chunk_count  INT DEFAULT 0,
  indexed_at   TIMESTAMPTZ
);

CREATE TABLE kb_chunks (
  id            BIGSERIAL PRIMARY KEY,
  document_id   BIGINT NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
  ord           INT NOT NULL,
  heading_path  TEXT,
  content       TEXT NOT NULL,                  -- includes the contextual header
  embedding     vector(768) NOT NULL,           -- dimension fixed by the chosen model [OPEN-1]
  tsv           tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

CREATE INDEX kb_chunks_embedding_hnsw ON kb_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX kb_chunks_tsv_gin       ON kb_chunks USING gin (tsv);
```

### 13.3 Hybrid search with Reciprocal Rank Fusion

```sql
-- :q_vec = query embedding, :q_text = raw query, :k = results wanted
WITH dense AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> :q_vec) AS r
  FROM kb_chunks ORDER BY embedding <=> :q_vec LIMIT 50
),
sparse AS (
  SELECT c.id, ROW_NUMBER() OVER (ORDER BY ts_rank_cd(c.tsv, q) DESC) AS r
  FROM kb_chunks c, websearch_to_tsquery('english', :q_text) q
  WHERE c.tsv @@ q
  ORDER BY ts_rank_cd(c.tsv, q) DESC LIMIT 50
)
SELECT id, SUM(1.0 / (60 + r)) AS rrf
FROM (SELECT * FROM dense UNION ALL SELECT * FROM sparse) u
GROUP BY id ORDER BY rrf DESC LIMIT :k;
```

- `SET hnsw.ef_search = 100` (tune on the evaluation set).
- **"Not found" detection.** RRF scores are rank-based and not calibrated. Use the **top dense cosine similarity** as the "is anything relevant?" signal, with a threshold calibrated on the question set.
- **Reranker.** An optional cross-encoder reranker (e.g. `BAAI/bge-reranker-base`) reranks the top 20 fused results. Add it **only** if Recall@5 < 0.85 without it.
- **Dense-only mode.** A config flag switches to dense-only, needed for the evaluation comparison "hybrid vs dense-only" (§25).

### 13.4 Embedding model [D / OPEN-1]

- **[P]** A local sentence-transformer of roughly **300M parameters**, used in **every** configuration so retrieval quality is constant across cloud and local runs.
- **Candidates** (all 768-dimensional, around 300M):
  - `google/embeddinggemma-300m`
  - `Snowflake/snowflake-arctic-embed-m-v2.0` (about 305M)
  - `intfloat/multilingual-e5-base` (about 278M)
- **Choose on measured Recall@5/MRR** on the project's question set, early (Oct–Nov 2026).
- **Query/document prefixes.** Apply the model's required prefixes or prompts (e.g. E5 needs `query: ` / `passage: `). Normalise embeddings for cosine.
- **Changing models later** requires re-embedding everything. Store the model name in `app_settings` and trigger a full re-index when it changes.

---

## 14. Tool routing and small-model strategy

### 14.1 Why routing [P]

Small local models (8–14B) choose tools less reliably when many tools are in context. Agentica uses **two-stage routing**:
1. An **embedding router** narrows the tool *categories* visible for a request.
2. A **scoped executor**, the LLM, picks the specific tool and arguments from that small set.

The evaluation compares this against a **flat baseline** (all tools visible) across model sizes (§25).

### 14.2 Stage 1: embedding router [D]

- **Category definitions.** `router/categories.yaml` lists each category's description and 15–30 example utterances. Embed them once at startup with the same local embedding model.
- **At request time:**
  1. Embed the request.
  2. Compute each category's score as the max cosine similarity against its examples (or against the centroid).
  3. If a task card is selected, add a bias `+δ` to that category **and force-include it**.
  4. Select the top category, plus any others within margin `m` of the top score, up to 2–3 categories.
  5. **No-tool threshold.** If the top score is below `τ_none` (conversational or general question), expose only the always-available tools.
- **Calibration.** `δ`, `m`, and `τ_none` are **calibrated on the labelled task set**. Do not hard-code guesses; start with `m=0.05`, `max_categories=3`, and tune.
- **Always-available tools:**
  - `get_system_overview(target)`, so the model can always ground a state claim;
  - `expand_scope(category, reason)`.
- **Controlled scope expansion.** If the executor realises it needs another category (e.g. after reading logs it needs service control), it calls `expand_scope`. The graph adds that category's tools for the rest of the turn, capped at 2 expansions per turn. This handles cross-category tasks without showing every tool.

### 14.3 Stage 2: scoped executor [D]

- The model sees only the tools of the selected categories (target: **≤ 8–10 tools** per call).
- **Tool names are an enum** of those tools, and arguments are JSON-schema constrained (§12.4).
- **Non-overlapping tool design.** No two tools should plausibly serve the same request. For example, there is one `get_logs` tool with a `source` argument, not `read_journal`, `read_eventlog`, and `tail_file` as separate tools.
- **Target-polymorphic tools.** Local and remote use the *same* tool with a `target` argument, which keeps the tool count low.
- **Temperature 0** for tool selection. Few-shot examples per category live in the category prompt.

### 14.4 Small-model strategy summary [P + D]

| Technique | Purpose |
|---|---|
| Two-stage routing | Fewer tools in context, which gives higher selection accuracy |
| Enum tool names + schema-constrained arguments | The model cannot invent tools or malformed arguments |
| Runbook-driven troubleshooting (RAG procedures tell the model what to check) | The model *follows instructions* rather than doing open-ended inference |
| Deterministic code for everything code can do: policy, parsing, evidence bundles, verification | The LLM is used only where language understanding is needed |
| Bounded loops, validation retries ≤ 2 | Prevents runaway multi-step drift |
| Compact structured tool outputs; explicit `num_ctx` | Fits within small context windows |
| Autonomous RCA excluded | The model is never asked for the task small models are worst at |
| Identical functionality in cloud and local mode | The *capability gap* is measured, not designed in |

### 14.5 Tool catalogue (core) [D]: names are canonical, so use them

| Category | Tool | Tier | Targets | Feature |
|---|---|---|---|---|
| *(always)* | `get_system_overview(target)` | read | local/linux/windows | F7, F11, F12 |
| *(always)* | `expand_scope(category, reason)` | meta | — | router |
| monitoring | `get_cpu_usage`, `get_memory_usage`, `get_disk_usage`, `get_network_stats` | read | all | F7, F11, F12 |
| monitoring | `list_top_processes(target, sort_by, limit)`, `get_process_details(target, pid \| name)` | read | all | F7, F11, F12 |
| files | `list_directory`, `read_file`, `search_files`, `analyze_disk_usage` | read | local | F8 |
| files | `create_file`, `write_file`, `create_directory`, `copy_path`, `move_path`, `rename_path` | modify | local | F8 |
| files | `delete_path` | destructive | local | F8 |
| services | `get_service_status`, `list_services` | read | all | F9 |
| services | `start_service`, `restart_service` | modify | all | F9 |
| services | `stop_service` | destructive | all | F9 |
| applications | `get_app_status(name)`, `list_configured_apps()` | read | per config | F10 |
| logs | `get_logs(target, source, lines, since, filter)`: source = journal unit / Windows event log / file under allowed roots | read | all | F11, F12, F13 |
| network | `check_port(target, host, port)` | read | all | F10, F13 |
| knowledge | `search_knowledge_base(query, top_k)` | read | — | F5 |
| troubleshooting | `collect_fault_evidence(category, target, subject)` | read | all | F13 |
| remote | `exec_command(target, command, timeout_s)` | destructive (guarded) | all | F11, F12 [OPEN-5] |

---

## 15. Model provider, models, and hardware (F14, F15)

### 15.1 Interface [D]

```python
class ModelProvider(Protocol):
    name: str                                  # "cloud:<model>" | "local:<model>"
    async def chat(self, messages, tools: list[ToolSpec] | None,
                   response_schema: dict | None = None,
                   temperature: float = 0.0, stream: bool = False) -> ChatResult: ...
```

- **One OpenAI-compatible code path [P].** Ollama exposes `/v1/chat/completions` with tool calling, and cloud providers either expose OpenAI-compatible endpoints or get a thin adapter. Using LangChain chat models (`ChatOllama`, `ChatOpenAI`/provider class) behind this interface is acceptable.
- **Recording.** The provider records `backend`, `model`, `quantisation`, and `host` for every run (needed for evaluation reporting).
- **Local-mode guard.** When `backend=local`, constructing a cloud provider raises an error, and the app's outbound HTTP client allowlist is empty except for Ollama on localhost and configured targets.

### 15.2 Model configurations under test [P]

| Configuration | Model | Serving | Notes |
|---|---|---|---|
| Cloud (capability ceiling) | A current hosted frontier model, via its API | Provider API | API key in keyring |
| Local, small (about 7–8B) | Llama 3.1 8B Instruct **or** Qwen 2.5 7B Instruct | Ollama, 4-bit (e.g. `llama3.1:8b-instruct-q4_K_M`, `qwen2.5:7b-instruct-q4_K_M`) | Final pick by measured tool-calling reliability |
| Local, large (about 12–14B) | Qwen 2.5 14B Instruct | Ollama, 4-bit (`qwen2.5:14b-instruct-q4_K_M`) | |
| Embeddings (all configurations) | Sentence-transformer, about 300M | In-process (sentence-transformers) | Held constant so retrieval does not confound the comparison |

### 15.3 Hardware [P]

- **Reference machine:** 8 CPU cores, 16 GB RAM, NVMe SSD, **no discrete GPU**, which is the machine a small IT team is most likely to have.
  - A 4-bit 8B model uses about 5 GB and a 14B model about 9 GB.
  - Both fit alongside the embedding model and PostgreSQL.
- **Secondary machine:** an 8 GB consumer GPU. It is used to separate the effect of model size from the effect of inference speed, so efficiency figures are not mistaken for accuracy differences.
- **Every reported local result names the model, the quantisation, and the machine.**
- **Test infrastructure:** 2–3 VMs for the seeded-fault fixture and remote targets, hostable on one workstation.

### 15.4 Cost [P]

- There is no licensing cost; every component is open-source.
- The only recurring cost is cloud-mode per-token API charges during development and evaluation. These are modest, because the benchmark is small and re-run only at milestones.
- Local mode has no per-use cost.

---

## 16. Monitoring design: local and remote, dashboard vs agent

### 16.1 Principle: agentless pull [D, agreed during design]

- **Nothing is installed on target machines.** Agentica pulls state over SSH or WinRM using commands that already exist on the OS.
- **The local machine** is read with `psutil` in-process.
- **Two consumers, two paths:**

| Consumer | Path | Freshness | Why |
|---|---|---|---|
| Dashboard (F16) | **Background poller → in-memory cache** | 30–60 s (remote), a few seconds (local) | Cheap, predictable load; the UI shows "updated N s ago" |
| Agent tools (chat, troubleshooting) | **On-demand live pull**, bypassing the cache | Now | Required by the live-state grounding rule (§12.5) |

### 16.2 Background poller [D]

- One asyncio task per target, started for `local` plus every target in `targets.yaml`.
- **Intervals** (configurable):
  - local: 5 s;
  - Linux/SSH: 30 s;
  - Windows/WinRM: 60 s, because WinRM calls are heavier.
- **Staggered start.** Random jitter spreads polls so they do not all fire at once.
- **Connection reuse.** SSH connections and WinRM sessions are reused from a per-target pool.
- **Poll bundles.**
  - One round-trip per poll where possible: a single SSH command that prints several sections, or a single PowerShell script that returns one JSON object.
  - Bundles are **read-only** commands only, and the poller never calls modifying tools.
- **Cache.** The latest snapshot plus a small ring buffer (e.g. the last 60 points) per metric for sparklines, each with `collected_at`.
- **Failure handling.** Mark the target `unreachable` with the last error, apply exponential backoff (up to about 5 min), and surface it on the dashboard.

### 16.3 Remote commands and parsing [D]

All remote reads are parsed into **the same Pydantic result models** as local psutil reads, so tools and the UI are OS-agnostic.

**Linux (over SSH, no root needed for reads):**

| Metric | Command | Parse |
|---|---|---|
| CPU % | `cat /proc/stat` twice, about 0.5 s apart (or `head -1 /proc/stat; sleep 0.5; head -1 /proc/stat`) | Δ(busy)/Δ(total) |
| Load | `cat /proc/loadavg` | fields 1–3 |
| Memory | `cat /proc/meminfo` | MemTotal, MemAvailable, SwapTotal, SwapFree |
| Disk | `df -kP` (+ `df -iP` for inodes) | POSIX-portable columns |
| Network | `cat /proc/net/dev` | Δ bytes |
| Processes | `ps -eo pid,comm,%cpu,%mem,rss --sort=-%cpu --no-headers \| head -n 20` | columns |
| Uptime / OS | `cat /proc/uptime`; `cat /etc/os-release` | |
| Service | `systemctl show <unit> --property=ActiveState,SubState,MainPID,UnitFileState --no-pager` | key=value |
| Logs | `journalctl -u <unit> -n <N> --no-pager -o short-iso` | lines |
| Listening ports | `ss -tlnH` | columns |

**Windows (over WinRM, PowerShell, always `| ConvertTo-Json -Depth 4 -Compress`):**

| Metric | Command |
|---|---|
| CPU % | `(Get-Counter '\Processor(_Total)\% Processor Time').CounterSamples.CookedValue` or `Get-CimInstance Win32_Processor \| Measure-Object LoadPercentage -Average` |
| Memory | `Get-CimInstance Win32_OperatingSystem \| Select TotalVisibleMemorySize,FreePhysicalMemory,LastBootUpTime` |
| Disk | `Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" \| Select DeviceID,Size,FreeSpace` |
| Processes | `Get-Process \| Sort-Object CPU -Descending \| Select -First 20 Id,ProcessName,CPU,WorkingSet64` |
| Service | `Get-Service -Name '<name>' \| Select Name,Status,StartType` |
| Logs | `Get-WinEvent -LogName Application -MaxEvents <N> \| Select TimeCreated,Id,LevelDisplayName,ProviderName,Message` |
| Listening ports | `Get-NetTCPConnection -State Listen \| Select LocalAddress,LocalPort,OwningProcess` |

- Parsers live in `targets/parsers/linux.py` and `targets/parsers/windows.py`. They get **fixture-based unit tests**: real captured outputs stored in `tests/fixtures/`.
- Service names, units, and log sources in templates are validated against a strict pattern first (§12.4) and then quoted.

### 16.4 Network and privilege requirements [D]

- **Outbound only**, from the Agentica host: TCP **22** (SSH) and TCP **5986** (WinRM over HTTPS). Nothing inbound is needed, except the optional web interface port.
- **Privileges:**
  - Reads need a normal user account.
  - **Control** (start/stop/restart) needs `sudo` on Linux (a scoped NOPASSWD rule is recommended) or an Administrator-equivalent account on Windows.
- **Limitation:** targets behind NAT that the admin host cannot reach cannot be pulled.

---

## 17. Remote management (F11, F12)

### 17.1 Linux over SSH [D]

```python
from fabric import Connection
conn = Connection(host=t.host, user=t.user, port=t.port,
                  connect_kwargs={"key_filename": key_path, "passphrase": keyring_get(...)},
                  connect_timeout=10)
res = conn.run(cmd, hide=True, warn=True, timeout=30)          # reads
res = conn.sudo(cmd, hide=True, warn=True, password=keyring_get(...))  # control, if no NOPASSWD
```

- **Host-key pinning.** On first connection, show the fingerprint and require admin confirmation, then store it in an Agentica-managed `known_hosts`. Reject changed keys loudly. Never use a silent `AutoAddPolicy`.
- **Connection pool.** Pool per target, with an idle timeout and a health check before reuse.
- **Timeouts and output.** Every command has a timeout, and output size is capped (e.g. 256 KB) before it reaches the model.
- **Setup helper** (`infra/linux-target-setup.sh`, optional):
  1. create an `agentica` user;
  2. install the public key;
  3. write `/etc/sudoers.d/agentica` allowing only `systemctl start|stop|restart|status <listed units>` without a password;
  4. validate it with `visudo -c`.

### 17.2 Windows over WinRM [D]

```python
import winrm
s = winrm.Session(f"https://{t.host}:5986/wsman", auth=(t.user, keyring_get(...)),
                  transport="ntlm", server_cert_validation="validate",
                  ca_trust_path=pinned_cert_path, read_timeout_sec=40, operation_timeout_sec=30)
r = s.run_ps(script)            # r.status_code, r.std_out, r.std_err
data = json.loads(r.std_out)
```

- **Transport.** NTLM over HTTPS for workgroup servers, Kerberos when domain-joined. Avoid CredSSP. Never use plain HTTP 5985 in the defaults.
- **Target setup script** (`infra/windows-target-setup.ps1`, run once as Administrator):

```powershell
Enable-PSRemoting -Force
$cert = New-SelfSignedCertificate -DnsName $env:COMPUTERNAME -CertStoreLocation Cert:\LocalMachine\My
New-Item -Path WSMan:\LocalHost\Listener -Transport HTTPS -Address * -CertificateThumbPrint $cert.Thumbprint -Force
New-NetFirewallRule -DisplayName "Agentica WinRM HTTPS" -Direction Inbound -LocalPort 5986 -Protocol TCP -Action Allow
Export-Certificate -Cert $cert -FilePath "$env:USERPROFILE\agentica-winrm.cer"
Write-Host "Thumbprint: $($cert.Thumbprint)  -> copy agentica-winrm.cer to the Agentica machine"
```

- **Script output.** PowerShell output must be JSON (`ConvertTo-Json`). Non-zero status or a non-empty `std_err` becomes a structured tool error.
- **OpenSSH fallback.** OpenSSH on Windows is a possible fallback transport if WinRM is blocked. It is *not* in the committed scope; record an ADR if it is used.

### 17.3 Targets configuration (core) [D]

```yaml
# targets.yaml — the only mechanism for declaring remote machines (no DB registry)
targets:
  - id: server-02
    name: Accounting server
    os: windows
    transport: winrm
    host: 192.168.10.12
    port: 5986
    user: agentica
    credential_ref: "agentica/server-02"      # keyring service/username, never the secret itself
    cert: "certs/server-02.cer"
    tags: [prod]
  - id: lab-ubuntu-1
    os: linux
    transport: ssh
    host: 192.168.56.10
    port: 22
    user: agentica
    key_ref: "agentica/lab-ubuntu-1"
    tags: [lab]
```

**Onboarding a target (no wizard, no DB registry):**
1. Run the setup script on the target (`infra/linux-target-setup.sh` or `infra/windows-target-setup.ps1`).
2. Add an entry to `targets.yaml` (documented in the user guide), then press **Reload** on the Machines page.
3. On the Machines page: **Set credentials** (stored in the keyring), **Trust** (confirm the SSH fingerprint or import the WinRM certificate), then **Test connection**.

A target that is not trusted cannot be used by any tool.

---

## 18. Tool implementation contract [D]

Every tool follows one pattern, so it is independently testable (NFR-7) and uniformly governed.

```python
class ToolSpec(BaseModel):
    name: str                      # canonical name from §14.5
    category: Literal["monitoring","files","services","applications","logs","network",
                      "knowledge","troubleshooting","remote","meta"]
    tier: Literal["read","modify","destructive"]
    description: str               # written for the model; one clear purpose; no overlap
    input_model: type[BaseModel]   # extra="forbid"
    output_model: type[BaseModel]
    targets: set[Literal["local","linux","windows"]]

class Tool(Protocol):
    spec: ToolSpec
    async def run(self, args: BaseModel, target: Target) -> BaseModel: ...
    async def verify(self, args: BaseModel, target: Target, result: BaseModel) -> VerifyResult | None: ...
    def command_preview(self, args: BaseModel, target: Target) -> str | None: ...  # for guardrails + approval UI

class Target(Protocol):              # implementations: LocalTarget, SSHTarget, WinRMTarget
    id: str; os: Literal["linux","windows"]; kind: Literal["local","ssh","winrm"]
    async def run_command(self, argv_or_script, timeout_s: int, privileged: bool=False) -> CmdResult: ...
```

- **Tools never call the model.** Tools never check policy themselves either, because the graph guarantees `policy` runs before `execute`. A unit test asserts that `execute` refuses a call without an attached decision.
- **Tool errors** are returned as structured `ToolError{code, message, retriable}`, never raised through the graph.
- **Output truncation.** Results carry a `summary` string for the prompt plus a `data` payload for the UI. Truncate large outputs with an explicit `truncated: true`.

---

## 19. Guided troubleshooting (F13)

### 19.1 Fault-category → evidence lookup table [D]

`config/troubleshooting/faults.yaml` (all evidence tools are **read** tier):

| Category | Evidence gathered (read-only) | Typical KB query terms |
|---|---|---|
| `service_down` | `get_service_status`; `get_logs(source=unit/eventlog, lines=100)`; `check_port` for the service port; dependency services' status | service name, "failed to start", unit/event IDs |
| `app_unresponsive` | `get_app_status`; process details (CPU/mem); `check_port`; recent logs | app name, "not responding", timeout |
| `disk_full` | `get_disk_usage` (+ inodes on Linux); `analyze_disk_usage` on the affected mount (local) or `du -xhd1` bundle (remote, read-only) | "disk full", mount path, log rotation |
| `memory_exhausted` | `get_memory_usage`; `list_top_processes(sort_by=mem)`; OOM entries (`journalctl -k \| grep -i oom` / Resource-Exhaustion events) | "out of memory", process name |
| `high_cpu` | `get_cpu_usage`; load average; `list_top_processes(sort_by=cpu)` | process name, "high CPU" |
| `config_error` | Service status + logs filtered for parse/syntax errors; config file mtime; optional configured validator command (e.g. `nginx -t`) declared in `apps.yaml` | "configuration", "syntax error", file name |
| `process_killed` | Process presence; logs; OOM/kill entries; service restart counters | process name, "killed", signal |
| `connectivity` | `check_port` from the Agentica host and on the target; listening ports | port, host, "connection refused" |

### 19.2 Flow [D]

1. **Classify.** The model picks `category` from the enum, plus a `subject` (service or app name) and `target`. The UI shows the guess, and the admin can change it.
2. **Collect evidence.** `collect_fault_evidence` runs the bundle **in code**, with no model choices per step, and returns a structured evidence report.
3. **Retrieve.** `search_knowledge_base` runs with `category + subject + salient evidence strings` (e.g. error lines from logs).
4. **Present:**
   - "Here is what I found" (evidence, each item linked to its tool call);
   - "The documented procedure that matches" (cited SOP section);
   - "Recommended next steps" (from the procedure).
5. **Admin decides.** Any action the admin approves becomes a normal tool call through policy (Confirm), followed by verification.
6. **Wording rule.** Say "consistent with …", never "the root cause is …" (X12).

---

## 20. Data layer

### 20.1 One PostgreSQL 16 instance [P]

| Store | Tier | Notes |
|---|---|---|
| LangGraph checkpoints | Core | Tables created by `AsyncPostgresSaver.setup()`; enable pause/resume and session history |
| Knowledge base (`kb_documents`, `kb_chunks`) | Core | §13.2; pgvector HNSW + GIN FTS |
| `sessions` | Core | id (= thread_id), title, created_at, updated_at, last_backend |
| `app_settings` | Core | key/value (embedding model name, KB folders, web-access flag, poll intervals) |

- **Migrations** use Alembic, except the LangGraph checkpoint tables, which are managed by LangGraph.
- **Access.** The DB listens on `127.0.0.1` only, with a random password generated at install and stored in the keyring.
- **Backup** is a single `pg_dump` of one database plus the config directory.

### 20.2 Configuration files (bundled safe defaults, user-editable) [D]

Stored in the OS app-config dir (via `platformdirs`):

| File | Purpose |
|---|---|
| `settings.yaml` | Backend, model names, ports, web access (off), polling intervals, KB folders |
| `policy.yaml` | Policy rules (§11.3) |
| `targets.yaml` | Remote targets (§17.3) |
| `apps.yaml` | Application status definitions (F10) |
| `router/categories.yaml` | Router categories and example utterances (§14.2) |
| `troubleshooting/faults.yaml` | Fault → evidence table (§19.1) |

### 20.3 Secrets [P]

- **Library.** `keyring`: Windows Credential Manager, or Linux Secret Service (GNOME Keyring / KWallet).
- **What goes there:** SSH key passphrases or passwords, WinRM passwords, the cloud API key, the DB password, and the web admin password hash seed if needed.
- **Headless Linux** with no Secret Service: fall back to `keyrings.cryptfile` (an encrypted file unlocked by a master password) and record the choice in an ADR (§28, OPEN-4).

### 20.4 Application logging (core) [D]

- **Structured JSON logs** (rotating file) for every request, routing result, policy decision, tool call, approval, and result, with secrets redacted.
- This is operational logging for debugging and evaluation. It is not an audit feature: there is no audit table, viewer, or export (X16).

---

## 21. API and streaming contract [D]

### 21.1 REST endpoints

| Method & path | Purpose |
|---|---|
| `GET /api/health` | Liveness, backend mode, DB status |
| `POST /api/sessions` · `GET /api/sessions` · `GET /api/sessions/{id}` · `DELETE /api/sessions/{id}` | Session management (F4) |
| `POST /api/sessions/{id}/messages` | Body `{text, task_card?, target?}` → **SSE stream** of the run (F1, F3) |
| `POST /api/sessions/{id}/approvals/{call_id}` | Body `{decision: "approve" \| "reject", comment?}` → SSE stream of the resumed run (F19) |
| `POST /api/sessions/{id}/cancel` | Cancel at the next node boundary |
| `GET /api/dashboard` · `GET /api/dashboard/stream` (SSE) | Poller cache snapshot and updates (F16) |
| `GET /api/apps/status` | All configured app statuses (F10) |
| `GET /api/kb/documents` · `POST /api/kb/documents` · `DELETE /api/kb/documents/{id}` · `POST /api/kb/reindex` · `GET /api/kb/folders` · `PUT /api/kb/folders` | KB management (F6) |
| `GET /api/settings` · `PUT /api/settings/model` · `GET /api/models/local` | Model selection (F15) |
| `GET /api/targets` · `POST /api/targets/{id}/test` | Targets (F11, F12) |
| `GET /api/policy` · `POST /api/policy/reload` | View and reload policy (F19) |
| `POST /api/auth/login` · `POST /api/auth/logout` | Web interface only (F17) |

- **Desktop mode.** The sidecar binds `127.0.0.1:<random>` and requires a per-launch bearer token passed from Tauri to the UI.
- **Web mode.** Cookie session over HTTPS.

### 21.2 SSE event types

```jsonc
{"event":"run_start",        "data":{"run_id":"…","backend":"local:qwen2.5:14b"}}
{"event":"route",            "data":{"categories":["services","logs"],"task_card":"services","no_tool":false}}
{"event":"retrieval",        "data":{"chunks":[{"chunk_id":1,"doc":"SOP-Web.pdf","section":"Restarting IIS","score":0.71}]}}
{"event":"tool_start",       "data":{"call_id":"c1","tool":"get_service_status","target":"server-02","args":{…}}}
{"event":"policy_decision",  "data":{"call_id":"c1","decision":"allow","tier":"read","reason":"read → allow (default)","rule_id":"defaults.read"}}
{"event":"tool_end",         "data":{"call_id":"c1","status":"ok","duration_ms":812,"summary":"AccountingSvc: Stopped","data":{…}}}
{"event":"approval_required","data":{"call_id":"c2","tool":"restart_service","target":"server-02","preview":"Restart service 'AccountingSvc' on server-02 (Windows, WinRM)","risk":"modify","reason":"modify → confirm (default)"}}
{"event":"verify",           "data":{"call_id":"c2","verified":true,"detail":"Status Running after 6 s"}}
{"event":"token",            "data":{"text":"The service was stopped…"}}
{"event":"final",            "data":{"message_id":"…","citations":[…],"steps":4}}
{"event":"error",            "data":{"code":"TARGET_UNREACHABLE","message":"…"}}
```

- **Server.** `sse-starlette` (`EventSourceResponse`).
- **Client.** `@microsoft/fetch-event-source` (supports POST bodies and headers, unlike `EventSource`).

---

## 22. Frontend (presentation layer)

### 22.1 Screens [D]

| Screen | Contents | Features |
|---|---|---|
| Chat | Session sidebar; task-card row; message list; live tool-call cards; inline approval prompts; backend badge; target selector | F1–F4, F19 |
| Dashboard | Machine tiles with gauges, sparklines, app/service badges, "updated N s ago" | F16 |
| Knowledge Base | Watched folders; document table with status; add/remove/re-index; search box for testing retrieval | F5, F6 |
| Machines | Targets from `targets.yaml` with reachability, a "Set credentials" dialog (writes to the keyring), host-key/certificate confirmation, and a "Test connection" button | F11, F12 |
| Settings | Backend (cloud/local), model pick, web access toggle and certificate fingerprint, effective policy (read-only), KB folder | F14, F15, F17, F19 |

### 22.2 UI rules [D]

- **Build.** React + TypeScript + Vite, with Recharts for charts. The styling library is the team's choice. A **responsive layout** is required for mobile web.
- **Approval prompts** always show the target, the exact action, the risk tier, and the rule. The "Approve" button is never the default focus for destructive actions.
- **Honesty in the UI.** Never display state that did not come from the backend. Stale data is visibly marked.

---

## 23. Packaging, installation, and first run

### 23.1 Packaging [P + D]

- **Tauri v2 desktop shell [P].** The React build is embedded. The Python backend ships as a **sidecar binary** built with **PyInstaller**, declared in `tauri.conf.json → bundle.externalBin` and launched via `tauri-plugin-shell` (`Command.sidecar`) with the matching capability permission.
- **Per-OS builds.** PyInstaller cannot cross-compile, and packages like `cryptography` and `psycopg` ship native binaries. Build Windows and Linux artifacts on their own OS, e.g. a GitHub Actions matrix (`windows-latest`, `ubuntu-22.04`).
  - Sidecar binary names carry the target triple (`agentica-backend-x86_64-pc-windows-msvc.exe`, `agentica-backend-x86_64-unknown-linux-gnu`).
- **Installers:** Windows NSIS/MSI; Linux AppImage and `.deb`.
- **Bundled:**
  - the embedding model weights;
  - default config files;
  - the dangerous-pattern set;
  - PostgreSQL 16 + pgvector (approach: [OPEN-3]).
- **Not bundled:** Ollama and local LLM weights. Local mode requires Ollama to be installed and a model pulled. The Settings page detects Ollama and lists installed models; the user guide explains the install steps.

### 23.2 First run [P: NFR-3]

1. Initialise the data dir, database (initdb if bundled), schema, and default configs.
2. The admin selects a model backend: an API key (cloud) **or** a locally downloaded model (offline).
3. Optionally point to a KB folder, and add targets plus credentials for remote management.

No other configuration is required.

---

## 24. Requirements [P] and traceability

### 24.1 Functional requirements

| ID | Functional requirement | Feature(s) |
|---|---|---|
| FR-1 | The system shall accept administrative requests in natural language and return plain-language reports. | F1 |
| FR-2 | The system shall provide task cards that scope the agent to a domain category before a request is issued. | F2 |
| FR-3 | The system shall display each tool invocation, with its arguments and result, as it occurs. | F3 |
| FR-4 | The system shall retain conversation context across a session. | F4 |
| FR-5 | The system shall retrieve relevant procedures from an organisation-supplied document set using hybrid semantic and keyword search. | F5 |
| FR-6 | The system shall allow documents to be ingested, removed, and re-indexed, clearing stale content when a source file changes. | F6 |
| FR-7 | The system shall report CPU, memory, storage, network, and process state for the local machine. | F7 |
| FR-8 | The system shall create, delete, modify, move, rename, organise, and search files within permitted directories. | F8 |
| FR-9 | The system shall report the status of, and start, stop, and restart, services on Linux and Windows. | F9 |
| FR-10 | The system shall report whether a configured application is currently running and responsive. | F10 |
| FR-11 | The system shall monitor and manage remote Linux servers over SSH and remote Windows servers over WinRM. | F11, F12 |
| FR-12 | The system shall, on a reported fault, gather relevant live state and present it alongside the applicable documented procedure. | F13 |
| FR-13 | The system shall grade every action by risk and allow, refuse, or hold it for administrator confirmation. | F19 |
| FR-14 | The system shall detect destructive commands and refuse those on a non-overridable blocklist. | F18 |
| FR-15 | The system shall pause a partially-executed task at a confirmation point, persist its state, and resume on approval. | F19 |
| FR-16 | The system shall operate against either a cloud-hosted model or a locally-hosted model, selectable in configuration. | F14, F15 |
| FR-17 | The system shall present a dashboard showing the health of local and registered remote machines. | F16 |
| FR-18 | The system shall expose its interface over the network for browser and mobile access. | F17 |

### 24.2 Non-functional requirements

| ID | Non-functional requirement | How it is verified [D] |
|---|---|---|
| NFR-1 | **Security:** the language model shall have no direct access to the operating system; all actions shall be mediated by the policy engine. | Architecture test: `execute` refuses calls without a decision; code review rule |
| NFR-2 | **Privacy:** in local mode, no request, document, or system data shall leave the host machine, and the system shall function without network access. | Run the benchmark offline; packet capture shows no external traffic |
| NFR-3 | **Usability:** first-time setup shall require no configuration beyond selecting a model backend — an API key in cloud mode, or a locally downloaded model in offline mode — and, for remote management, server credentials. | Fresh-install walkthrough on clean VMs |
| NFR-4 | **Portability:** the application shall install and run on both Windows and Linux hosts. | CI builds + install test on both |
| NFR-5 | **Reliability:** an interrupted task shall resume correctly after an application restart. | Kill-and-resume test (§11.4) |
| NFR-6 | **Performance:** a routine read-only monitoring query shall return in a median of five seconds or less in cloud mode on typical desktop hardware. | Timed benchmark subset |
| NFR-7 | **Maintainability:** tools shall be independently testable outside the agent loop. | Every tool has unit tests with mocked targets |
| NFR-8 | **Confidentiality of credentials:** server credentials shall be held in the operating system keyring, never in the application database. | DB/config/log scan for secrets in CI; code review |

---

## 25. Evaluation methodology [P]

### 25.1 Fixture (held constant across runs)

- **VMs with deliberately seeded faults.** At least one Linux VM (e.g. Ubuntu Server LTS) and one Windows Server VM (evaluation edition), plus the local host. Reset between runs using VM snapshots [D].
- **A fixed knowledge base** of standard operating procedures: the organisation's own SOPs where the partner allows, plus authored SOPs covering every seeded fault [D].
- **A labelled task set of 60–80 realistic administrative tasks**, held constant so results stay comparable as the system evolves.
- **A retrieval question set** with known correct source documents.
- **A dedicated adversarial prompt set** for safety.

### 25.2 Metrics and targets (Table 4)

| Metric | Definition and method | Target |
|---|---|---|
| **Task success rate** | Percentage of a benchmark of 60–80 realistic administrative tasks completed correctly with no human correction beyond an expected confirmation prompt. Reported per feature category rather than as a single average, and separately for each model backend. | ≥ 85% cloud mode; ≥ 75% local mode |
| **Tool-selection accuracy** | Top-1 accuracy against a gold tool label for every benchmark task, measured in two configurations: a flat baseline with all tools in context, and the two-stage routed architecture. Argument-level correctness scored separately. Repeated across model sizes. | ≥ 90% cloud, ≥ 80% local (routed); routed to exceed flat baseline in both |
| **Troubleshooting accuracy** | Over a fixed catalogue of seeded faults (stopped service, crashed application, full disk, corrupted configuration, killed process, exhausted memory): whether the correct evidence was gathered and the correct procedure retrieved. | ≥ 85% cloud; ≥ 75% local |
| **Retrieval performance** | Recall@k, Mean Reciprocal Rank, and nDCG on a fixed question set with known correct source documents. Dense-only retrieval measured against the hybrid configuration. Groundedness of answers checked against retrieved passages. Independent of the generative model. | Recall@5 ≥ 0.85 (85%); hybrid to exceed dense-only |
| **Safety: false-allow rate** | Proportion of destructive actions that executed when policy should have gated them, measured against a dedicated adversarial prompt set. Because the policy check is deterministic rather than model-driven, this is not expected to vary by backend. | No false allows observed; any occurrence treated as a release blocker |
| **Safety: benign-action pass rate** | Proportion of benign actions that proceed without being refused or escalated unnecessarily. Reported separately from the false-allow rate and never averaged with it, since the two are not symmetric. | ≥ 85% |
| **Efficiency** | Median wall-clock time and step count per task, recorded in both cloud and local model configurations, to quantify the cost of private operation. | Reported; local median within 4× of cloud |

**Deliberate design points:**
- The routed-vs-flat comparison across model sizes tests the routing contribution directly rather than asserting it.
- The two safety measures are **never combined**. A single false allow can damage a production system; an unnecessary block is an inconvenience.
- The targets are **engineering goals, not predictions**. The measured cloud-vs-local gap is itself a reported result of the project.

### 25.3 Seeded-fault catalogue [P] with suggested seeding [D]

| Fault | Linux seeding | Windows seeding |
|---|---|---|
| Stopped service | `systemctl stop nginx` | `Stop-Service W3SVC` (or a test service) |
| Crashed application | `kill -9 <app pid>` with `Restart=no` | `Stop-Process -Id <pid> -Force` |
| Full disk | `fallocate -l <size> /data/fill.bin` to 100% on a small test volume | `fsutil file createnew D:\fill.bin <bytes>` |
| Corrupted configuration | Inject a syntax error into `nginx.conf`, then restart (fails) | Corrupt an IIS `web.config` / app config |
| Killed process | `kill -9` of a monitored worker process | `Stop-Process -Force` of a worker process |
| Exhausted memory | `stress-ng --vm 1 --vm-bytes 95%` | A memory-hog test program |

Every fault has a matching reset script, and there is at least one SOP in the KB for each fault.

### 25.4 Task file format and harness [D]

```yaml
# eval/tasks/services.yaml
- id: SVC-007
  category: services
  prompt: "Nginx on the lab Ubuntu box is down. Bring it back up."
  target: lab-ubuntu-1
  seed: faults/linux/stop_nginx.sh
  reset: faults/linux/reset_nginx.sh
  gold_tools: [get_service_status, restart_service]      # first gold tool used for top-1 selection accuracy
  gold_args: {restart_service: {name: "nginx", target: "lab-ubuntu-1"}}
  expects_confirmation: true
  success_check: {type: service_active, target: lab-ubuntu-1, name: nginx}
```

- **Runner.** `eval/runner.py` runs each task under each configuration: `{cloud, local-8B, local-14B} × {routed, flat}`.
  - It auto-approves *expected* confirmations. Unexpected ones count as a human correction.
  - It records tools, arguments, decisions, timings, steps, and the success check.
  - Results are written to `eval/results/<date>/<config>.jsonl`.
- **Report.** `eval/report.py` computes the per-category and per-backend tables for Table 4.
- **Retrieval metrics.** Recall@5, MRR, and nDCG@10 are computed with no LLM involved.
- **Groundedness.** Checked by manual review of a sample, or an LLM judge with manual spot-checks.
- **Safety set.** Includes:
  - destructive requests phrased innocently;
  - obfuscated and encoded commands;
  - path traversal and symlink escapes;
  - attempts to stop `sshd`/`WinRM`;
  - **prompt injection planted inside KB documents and log files**.

  A false allow is any destructive action that executed without the required Confirm or Deny.

### 25.5 Reporting rules [P]

Every local result names the **model, quantisation, and machine**. Results are reported per feature category and per backend, never as a single average.

---

## 26. Timeline and task division [P]

### 26.1 University milestones

| Milestone | Approx. timing |
|---|---|
| Proposal defense | 22–24 Sep 2026 |
| Mid FYP-1 evaluation | ~6–8 Nov 2026 (early prototype ready for the late-October review) |
| Final FYP-1 evaluation | late Dec 2026 |
| Mid FYP-2 evaluation | ~Mar 2027 |
| Final FYP-2 evaluation / defense | late May 2027 |

### 26.2 Individual task allocation (Table 5)

| Member | Activity | Target milestone | Tentative date |
|---|---|---|---|
| All members | Brainstorming, scope definition, and FYP registration | Proposal defense | Aug 2026 |
| All members | Literature review and technology exploration | Proposal defense | Aug – Sep 2026 |
| All members | Proposal writing and defense preparation | Proposal defense | Sep 2026 |
| All members | SRS, system design, and work breakdown | Mid FYP-1 | Sep – Oct 2026 |
| All members | RAG retrieval and knowledge-base management | Final FYP-1 | Oct – Dec 2026 |
| All members | Guided troubleshooting | Mid FYP-2 | Jan – Feb 2027 |
| All members | Guardrails, dangerous-command detection, and hardening | Final FYP-2 | Nov 2026 – May 2027 |
| All members | FYP-1 integration, testing, and documentation | Final FYP-1 | Dec 2026 |
| All members | Desktop packaging and installer | Final FYP-2 | Apr – May 2027 |
| All members | Integration and load testing | Final FYP-2 | Apr – May 2027 |
| All members | Thesis writing and final demonstration | Final FYP-2 | May 2027 |
| Ahsan Faizan | Orchestration core and two-stage tool router | Mid FYP-1 | Oct – Nov 2026 |
| Ahsan Faizan | Natural-language chat interface | Mid FYP-1 | Oct 2026 |
| Ahsan Faizan | Live tool calls | Mid FYP-1 | Oct – Nov 2026 |
| Ahsan Faizan | Multi-turn session history | Mid FYP-1 | Oct – Nov 2026 |
| Ahsan Faizan | Server monitoring (self) | Mid FYP-1 | Oct – Nov 2026 |
| Ahsan Faizan | Policy and permission engine with risk tiers | Mid FYP-1 | Oct – Nov 2026 |
| Ahsan Faizan | Remote Windows server management over WinRM | Final FYP-1 | Dec 2026 |
| Ahzam Hassan | Data layer: PostgreSQL, pgvector, and schema design | Mid FYP-1 | Oct 2026 |
| Ahzam Hassan | GUI task cards | Final FYP-1 | Nov – Dec 2026 |
| Ahzam Hassan | Application status monitoring | Final FYP-1 | Nov – Dec 2026 |
| Ahzam Hassan | Local / offline private model mode | Final FYP-1 | Nov – Dec 2026 |
| Ahzam Hassan | Built-in monitoring dashboard | Mid FYP-2 | Feb – Mar 2027 |
| Ahzam Hassan | Evaluation benchmark and metrics collection | Final FYP-2 | Mar – Apr 2027 |
| Ali Samad | Service monitoring and control | Final FYP-1 | Nov – Dec 2026 |
| Ali Samad | Remote Linux server management over SSH | Final FYP-1 | Nov – Dec 2026 |
| Ali Samad | File operations | Mid FYP-2 | Jan 2027 |
| Ali Samad | Flexible model selection (model switching) | Mid FYP-2 | Jan – Feb 2027 |
| Ali Samad | Web interface for browser and mobile access | Final FYP-2 | Mar – Apr 2027 |

### 26.3 Gantt windows (Fig. 3, approximate)

Owner codes: A = Ahsan, H = Ahzam, S = Ali, All = all members.

| Task | Owner | Window |
|---|---|---|
| Brainstorming | All | early → late Aug 2026 |
| Literature review | All | ~8 Aug → early Sep 2026 |
| Proposal writing | All | end Aug → late Sep 2026 |
| SRS | All | late Sep → mid Oct 2026 |
| Data layer | H | end Sep → ~22 Oct 2026 |
| Orchestration core + router | A | early Oct → early Nov 2026 |
| Chat interface | A | early Oct → late Oct 2026 |
| Live tool calls | A | mid Oct → early Nov 2026 |
| Session history | A | late Oct → early Nov 2026 |
| Server monitoring (self) | A | mid Oct → early Nov 2026 |
| Policy engine | A | ~20 Oct → ~7 Nov 2026 |
| RAG (incl. KB management) | All | mid Oct → late Dec 2026 |
| GUI task cards | H | ~10 Nov → early Dec 2026 |
| App status | H | ~11 Nov → early Dec 2026 |
| Service control | S | mid Nov → ~8 Dec 2026 |
| Remote Linux | S | late Nov → ~19 Dec 2026 |
| Local model | H | late Nov → late Dec 2026 |
| Remote Windows | A | early Dec → end Dec 2026 |
| FYP-1 integration | All | mid Dec → end Dec 2026 |
| File operations | S | early Jan → end Jan 2027 |
| Model switching | S | early Jan → early Feb 2027 |
| Guided troubleshooting | All | mid Jan → ~22 Feb 2027 |
| Dashboard | H | early Feb → ~8 Mar 2027 |
| Web interface | S | ~8 Mar → ~11 Apr 2027 |
| Evaluation benchmark | H | mid Mar → end Apr 2027 |
| Packaging | All | ~19 Apr → ~10 May 2027 |
| Integration & load testing | All | end Apr → mid May 2027 |
| Thesis | All | early May → end May 2027 |
| **Guardrails** (continuous) | All (security) | **early Nov 2026 → mid May 2027** |
| Supervisor meetings | All | continuous, Aug 2026 → May 2027 |

**Notes:**
- Only the 19 core features are scheduled. The extended features were dropped (§6, X14–X18).
- December is for integration and documentation, not new development.
- Where a task is tied to an evaluation date it is tight; elsewhere dates are indicative.

**Status as of 29 Sep 2026:** the proposal is complete and submitted. The current work is the SRS, system design, and work breakdown, with the data layer and orchestration core starting in early October.

---

## 27. Tools and technologies (Table 6) [P], repository layout, and conventions [D]

### 27.1 Technology table

| Area | Technology | Rationale |
|---|---|---|
| Agent orchestration | LangGraph (Python) | Stateful graph with native interrupt and checkpointing, which the confirmation mechanism depends on. |
| Backend | FastAPI, Pydantic | Asynchronous API with schema validation; Pydantic models also constrain tool arguments. |
| Desktop shell | Tauri | Packages a web interface as a native installable application; substantially lighter than alternatives. |
| User interface | React, Recharts | Single interface implementation serving both the desktop shell and the browser. |
| Database | PostgreSQL with pgvector | One service holds checkpoints, vectors, logs, and registry, supporting the minimal-configuration goal. |
| Embeddings and retrieval | sentence-transformers; PostgreSQL full-text search | Local embedding generation plus native keyword search enables hybrid retrieval without a second service. |
| Local inference | Ollama | Manages model download, quantisation, and serving behind an OpenAI-compatible interface, so cloud and local modes share one code path. |
| System monitoring | psutil | Mature cross-platform access to CPU, memory, disk, network, and process information. |
| Service control | pystemd (Linux); pywin32 (Windows) | Structured access to systemd and the Service Control Manager, avoiding fragile output parsing. |
| Remote access | Fabric/Paramiko (SSH); pywinrm (WinRM) | Established libraries for agentless Linux access and Windows remote management. |
| ~~Scheduling (extended)~~ | ~~APScheduler with a database job store~~ | **Not used.** Listed in the proposal only for the dropped recurring-task feature (X14). |
| Credential storage | OS keyring | Keeps secrets out of the application database and configuration files. |
| Version control and collaboration | Git, GitHub | Source control, issue tracking, and review across the three members. |

**Supporting libraries [D]:**

| Purpose | Libraries |
|---|---|
| LangGraph persistence and DB access | `langgraph-checkpoint-postgres`, `psycopg[binary]` 3, `pgvector` (Python), SQLAlchemy + Alembic |
| API and streaming | `sse-starlette`, `httpx` |
| Document extraction and file watching | `pypdf`, `python-docx`, `beautifulsoup4`, `watchdog` |
| Local system and paths | `send2trash`, `platformdirs` |
| Secrets and web auth | `keyring` (+ `keyrings.cryptfile` fallback), `cryptography` (self-signed TLS), `argon2-cffi`/`pwdlib` |
| Tests | `pytest`, `pytest-asyncio`, `testcontainers` or a local PG for integration tests |
| Frontend | TypeScript, Vite, `@microsoft/fetch-event-source` |

### 27.2 Repository layout [D]

```text
agentica/
├─ README.md
├─ CLAUDE.md                         # short rules + pointer to docs/AGENTICA_SPEC.md (Appendix B)
├─ docs/
│  ├─ AGENTICA_SPEC.md               # this file
│  └─ adr/                           # 0001-embedding-model.md, 0002-postgres-bundling.md, …
├─ backend/
│  ├─ pyproject.toml
│  ├─ agentica/
│  │  ├─ main.py                     # FastAPI app factory, lifespan (DB, poller, watcher)
│  │  ├─ api/                        # routers: sessions, chat, approvals, dashboard, kb, settings, targets, policy, auth
│  │  ├─ core/                       # config loading (settings/targets/apps), logging, events, errors
│  │  ├─ orchestrator/               # graph.py, state.py, nodes/{route,gather,agent,validate,policy,approval,execute,verify,report}.py, prompts/
│  │  ├─ router/                     # embedder.py, router.py (categories from config)
│  │  ├─ models/                     # provider.py (interface), cloud.py, ollama.py, egress_guard.py
│  │  ├─ policy/                     # engine.py, schema.py (Pydantic for policy.yaml), defaults/policy.yaml
│  │  ├─ guardrails/                 # commands.py (parse/split), hardline.py, patterns/ (vendored set [18] + ours), grounding.py
│  │  ├─ tools/                      # base.py (ToolSpec, registry), monitoring.py, files.py, services.py, apps.py,
│  │  │                              # logs.py, network.py, knowledge.py, troubleshooting.py, exec.py, meta.py
│  │  ├─ targets/                    # base.py, local.py, ssh.py, winrm.py, pool.py, parsers/{linux,windows}.py
│  │  ├─ rag/                        # extract.py, chunking.py, embed.py, ingest.py, search.py, watcher.py
│  │  ├─ monitoring/                 # poller.py, cache.py
│  │  ├─ db/                         # engine.py, models.py, migrations/ (alembic)
│  │  └─ security/                   # secrets.py (keyring), tls.py, auth.py
│  └─ tests/                         # unit/, integration/, fixtures/ (captured command outputs, sample docs)
├─ ui/                               # React + TS + Vite (one build for desktop and web)
├─ desktop/                          # Tauri v2 (src-tauri/, tauri.conf.json, sidecar config)
├─ config/                           # bundled defaults: settings, policy, targets, apps, router/categories, troubleshooting/faults
├─ eval/                             # tasks/*.yaml, retrieval/questions.jsonl, adversarial/*.yaml, faults/, runner.py, report.py, results/
├─ infra/                            # linux-target-setup.sh, windows-target-setup.ps1, vm/ (fixture VM setup notes)
└─ .github/workflows/                # lint+test (win+linux), build installers
```

### 27.3 Coding conventions [D]

- **Python 3.12**, fully type-hinted, async throughout the API and tools. Use `ruff` (lint + format) and `pytest`.
- **Pydantic v2** everywhere at boundaries: API bodies, tool I/O, and config files.
- **No `shell=True` with model-derived strings.** Build argv lists, or use templates with quoted, validated arguments.
- **No secrets in code, config, logs, or prompts.** Use the redaction helper for anything displayed or logged.
- **Tools** return structured models plus a short `summary` and never raise into the graph (return `ToolError`).
- **Tests:**
  - Every tool: unit tests with a fake `Target`.
  - Every parser: fixture tests.
  - Policy engine: table-driven tests with 100% branch coverage.
  - Guardrails: positive and negative pattern tests. Every bypass found becomes a regression test.
- **Frontend.** TypeScript strict mode; components for `ToolCallCard`, `ApprovalPrompt`, `MachineTile`, `TaskCardBar`.
- **Git.** Conventional commits (`feat(F09): …`, `fix(policy): …`); PRs reference feature IDs.
- **ADRs.** Any deviation from a [P] item needs team and supervisor agreement. Any change to a [D] item gets a short ADR in `docs/adr/`.

---

## 28. Open decisions and key risks

| ID | Open decision | Options | Decide by | Issue |
|---|---|---|---|---|
| OPEN-1 | Embedding model (about 300M) | EmbeddingGemma-300M / arctic-embed-m-v2.0 / multilingual-e5-base; choose on Recall@5 and MRR on our question set | Nov 2026 | AG-032 |
| OPEN-2 | Final local models | Llama 3.1 8B vs Qwen 2.5 7B at the small size; Qwen 2.5 14B at the large; choose on measured tool-calling reliability | Dec 2026 | AG-044 |
| OPEN-3 | How PostgreSQL + pgvector is shipped | (a) bundle portable PG 16 binaries + pgvector, `initdb` in the app data dir, run on localhost; (b) the `pgserver` Python package (pip-installable PG + pgvector); (c) installer installs system PostgreSQL. Prototype early; packaging is a schedule risk | Nov 2026 (spike) | AG-050 |
| OPEN-4 | Keyring on headless Linux | Secret Service if present, else `keyrings.cryptfile` with a master password | Dec 2026 | AG-003 |
| OPEN-5 | Generic `exec_command` tool | Keep as a Confirm-tier, guardrail-checked escape hatch (disable-able in policy) vs structured tools only | Before remote modify work (Nov–Dec 2026) | AG-049 |
| ~~OPEN-6~~ | ~~"Registered remote machines"~~ | **Resolved:** with F23 dropped, targets are declared in `targets.yaml` and credentials are set from the Machines page | — | AG-040 |
| OPEN-7 | Web interface feature subset | Minimum: chat, tool cards, approvals, dashboard, KB search; desktop-only: settings, policy, keyring | Mar 2027 | AG-064 |

| Risk | Impact | Mitigation |
|---|---|---|
| Small-model tool-calling unreliability | Misses local targets | Routing, enum and schema decoding, bounded loops, runbooks, early measurement |
| Packaging (sidecar + DB + model weights) | Late integration failure | Packaging spike in Nov 2026; CI builds from Final FYP-1 onward |
| WinRM setup friction | Delays F12 | Setup script; Linux first; OpenSSH fallback noted |
| Guardrail bypasses | Safety metric fails | Continuous guardrail work; adversarial set grown each sprint; deterministic policy |
| Evaluation left to the end | No credible results | Question set and task set grow with every feature from Oct 2026 |
| Scope creep | Core slips | Scope fixed at F1–F19; removed list (§6) is binding; Part II is the complete backlog |

---

## 29. Expected deliverables [P]

1. A working desktop application, installable on Windows and Linux, implementing the nineteen core features defined in Section 7.1 (of the proposal; F1–F19 in this spec).
2. A governed execution pipeline in which every action is graded by risk and no destructive operation can bypass the policy engine.
3. A retrieval-augmented knowledge module operating over an organisation-supplied document set, with ingestion and management tooling.
4. Remote management capability for Linux servers over SSH and Windows servers over WinRM, including a setup script for Windows targets.
5. A browser-accessible interface providing cross-platform access to a subset of features.
6. A fully offline operating mode in which no data leaves the host machine.
7. An evaluation benchmark comprising the labelled task set, the seeded-fault fixture, and the retrieval question set, together with reported results for every metric in Table 4.
8. Project documentation: software requirements specification, design documentation, user guide, and final thesis.
9. A source code repository with version history and test suite.

---

## 30. Literature context (summary) [P]

| Group | Representative systems | What they establish | Where they stop |
|---|---|---|---|
| Cloud-native ops assistants | Azure Copilot (incl. NL-to-SQL, 2026 operational/SRE agents) [3]–[5] | Conversational cloud management | Only resources in that cloud; no local or offline mode |
| AI SRE agents | Datadog Bits AI, Resolve AI, PagerDuty SRE Agent [6]–[9] | Investigate-then-remediate loop; strong autonomous RCA | Tied to observability telemetry; enterprise SaaS; incident-focused |
| ITSM agents | Espressive Barista, Aisera, Console [10], [11] | Conversational layer over service desks | Depend on the ITSM platform; no direct server operations |
| MSP agents | MSP tier-1 automation [12] | Human-in-the-loop approval is accepted practice | Bound to the provider platform and ticket queues |
| Local terminal agents | Warp Agent Mode [13], [14] | Closest analogue: local NL execution, step approval, denylists | Developer-oriented; no RAG over org docs, no monitoring, no fleet, no risk-tiered per-target policy |
| Local-first self-hosted | LocalAI, LocalAGI [15], [16] | Private, offline agents are practical | General-purpose runtimes; shipped as server stacks, not an IT-ops app |
| AIOps suites and open runtimes | BigPanda, Dynatrace, Moogsoft, Splunk ITSI [17]; Hermes Agent [18], OpenClaw [19] | Event correlation; reusable agent machinery | Not NL action execution; runtimes are components, not competitors |

- **Identified gap.** Among the systems reviewed, none was found that combines IT-operations depth (structured system and application monitoring, service control, runbook-grounded troubleshooting, and remote Windows and Linux management) with a risk-tiered governance layer, a choice of cloud or local model, and delivery as a single, quickly-installed application.
- **Nature of the contribution.** It is integrative rather than novel in any single respect.

---

## 31. Glossary

| Term | Meaning in this project |
|---|---|
| Agentic | An LLM with tools, memory, and a planning loop that performs multi-step tasks |
| Allow / Confirm / Deny | The three policy outcomes; Confirm pauses for the admin |
| Hardline blocklist | Catastrophic operations that are always denied and never configurable |
| Risk tier | read / modify / destructive, as declared by each tool |
| Task card | A UI domain card that biases tool routing (F2) |
| Two-stage routing | Embedding router picks categories, then the LLM picks a tool within them |
| Scope expansion | The executor asks to add a tool category mid-turn (`expand_scope`) |
| Live-state grounding | Current-state claims must come from a tool call in this turn |
| Guided troubleshooting | Evidence gathering + procedure retrieval; the admin concludes (not RCA) |
| Target | `local` or a remote machine declared in `targets.yaml` |
| Poller cache | Background-collected dashboard data; never used as agent evidence |
| RRF | Reciprocal Rank Fusion, combining dense and keyword rankings |
| SOP | Standard operating procedure (knowledge-base content) |
| Core | F1–F19, the complete committed scope (the proposal's extended F20–F24 are dropped) |

---

## 32. References [P]

1. Itential, "Gartner predicts 2026: AI agents will reshape infrastructure and operations," 2026. https://www.itential.com/resource/analyst-report/gartner-predicts-2026-ai-agents-will-reshape-infrastructure-operations/
2. Geek Vibes Nation, "How AI is reshaping IT service management in 2026," 2026. https://geekvibesnation.com/how-ai-is-reshaping-it-service-management-in-2026/
3. Microsoft, "Azure Copilot overview," Microsoft Learn, 2026. https://learn.microsoft.com/en-us/azure/copilot/overview
4. Microsoft, "Microsoft Copilot in Azure with Azure SQL Database overview," Microsoft Learn, 2026. https://learn.microsoft.com/en-us/azure/azure-sql/copilot/copilot-azure-sql-overview
5. S. O'Brien, "Agentic cloud ops with the new Azure Copilot," InfoWorld, 2026. https://www.infoworld.com/article/4096996/agentic-cloud-ops-with-the-new-azure-copilot.html
6. Datadog, "Bits AI agents," 2026. https://www.datadoghq.com/product/ai/bits-ai-agents/
7. Fundesk, "AI SRE agents explained: platform comparison and pilot guide for 2026," 2026. https://www.fundesk.io/ai-sre-agents-explained-platform-comparison-2026
8. Fluidify, "Beyond Datadog Bits AI: the best AI SRE alternatives in 2026," 2026. https://fluidify.ai/blog/datadog-bits-ai-alternatives-2026
9. Vibranium Labs, "Top AI SRE agents and autonomous remediation platforms," 2026. https://vibraniumlabs.ai/blog/top-ai-sre-agents
10. Console, "Best AI agents for IT teams in 2026," 2026. https://www.console.com/blog/ten-best-ai-agents-for-it-in-2026/
11. Rasa, "15 best AI agents for enterprise in 2026," 2026. https://rasa.com/blog/best-ai-agents-for-enterprise
12. Flamingo, "AI agents for IT operations: MSP guide," 2026. https://www.flamingo.run/blog/ai-agents-for-it-operations
13. DeployHQ, "Warp guide 2026: agent mode, MCP, open source and deployments," 2026. https://www.deployhq.com/guides/warp
14. Warp, "Agent mode: natural-language coding agents in Warp," 2026. https://www.warp.dev/ai
15. LocalAI, "Agents — LocalAI documentation," 2026. https://localai.io/docs/features/agents/
16. E. Di Giacinto, "LocalAGI: self-hostable AI agent platform," GitHub, 2026. https://github.com/mudler/LocalAGI
17. Sherlocks.ai, "Best Datadog Bits AI alternatives for AIOps," 2026. https://www.sherlocks.ai/discover/datadog-bits-ai-alternatives
18. Nous Research, "Hermes Agent," GitHub, 2026. https://github.com/NousResearch/hermes-agent
19. OpenClaw, "Agent runtime architecture," OpenClaw documentation, 2026. https://docs.openclaw.ai/agent-runtime-architecture
20. LangChain, "Interrupts — LangGraph documentation," 2026. https://docs.langchain.com/oss/python/langgraph/interrupts

---

# Part II — Issue backlog

Part II turns the specification into GitHub issues. It is generated from one structured backlog and was checked automatically: every dependency exists, there are no dependency cycles, no issue depends on work in a later milestone, every core feature F1–F19 is covered, and no issue touches a dropped feature.

---

## 33. How to create the issues (instructions for Claude Code)

Follow these steps in order. Do not skip, merge, split, rename, or re-scope issues. If something in an issue looks wrong or contradicts Part I, do not silently fix it: create the issue as written and add a comment, or ask the team.

### 33.1 Step 1: create the labels

| Label | Meaning |
|---|---|
| `type:feature` | Implements part of a core feature |
| `type:infra` | Build, CI, packaging, or project plumbing |
| `type:security` | Security-critical work (policy, guardrails, secrets, auth) |
| `type:spike` | Time-boxed investigation ending in an ADR |
| `type:test` | Evaluation, fixtures, or verification |
| `type:docs` | Documentation deliverable |
| `area:<name>` | Code area. Values: `backend-core`, `db`, `desktop`, `docs`, `eval`, `guardrails`, `models`, `orchestrator`, `packaging`, `policy`, `rag`, `remote`, `router`, `tools`, `ui` |
| `feature:F01` … `feature:F19` | Core feature(s) the issue implements (create all 19) |
| `epic:E0` … `epic:E11` | Work stream (see §35.1) |
| `priority:P0` | Required for its milestone demo or evaluation |
| `priority:P1` | Important, but the milestone can be met without it |
| `risk:modifies-systems` | Enables an action that changes a system; needs guardrail and policy tests and a second reviewer |
| `needs-decision` | Contains a team decision (an [OPEN] item); record the outcome in an ADR before closing |
| `team:all` | Owned by all members per the proposal; the assignee is the suggested lead |

### 33.2 Step 2: create the milestones

Due dates are approximate; adjust them to the official university calendar.

| Milestone title | Due date | Must be demonstrable |
|---|---|---|
| `Mid FYP-1` | 2026-11-06 | Working request-to-response loop, local monitoring, first retrieval pipeline, policy gate with interrupt/resume |
| `Final FYP-1` | 2026-12-28 | Full local and remote core (F2, F9, F10, F11, F12), RAG + KB management complete, offline model mode, guardrails v1, FYP-1 integration |
| `Mid FYP-2` | 2027-03-08 | File operations, model switching, guided troubleshooting, dashboard, guardrails v2 |
| `Final FYP-2` | 2027-05-25 | Web interface, full evaluation results, packaged installers, hardening, thesis |

### 33.3 Step 3: map owners to GitHub accounts

| Owner name in this backlog | GitHub username |
|---|---|
| Ahsan | *(fill in)* |
| Ahzam | `Ahzam-28` |
| Ali | *(fill in)* |

If a username is not filled in, create the issue unassigned and write `Owner: <name>` in the body.

Owners follow the proposal's task allocation (Table 5, §26.2). Supporting issues that Table 5 does not name (repo scaffold, API skeleton, UI scaffold, embedding service, cloud provider) were assigned to balance the Mid FYP-1 workload. For issues owned by all members, the assignee is a suggested lead who coordinates the work; the team may reassign.

### 33.4 Step 4: create the issues

1. Create issues **in ascending ID order** (AG-001, AG-002, …). The IDs are in dependency order, so every blocker already exists when an issue that depends on it is created.
2. **Title:** `[AG-xxx] <title>`, exactly as given in §35.3.
3. **Body:** use the template in §34.1, filled from the issue's entry in §35.3. Copy the Context, Tasks, Files, Acceptance criteria, Tests, and Out of scope **verbatim**, and append the Standard Definition of Done (§34.2).
4. **Labels, milestone, and assignee** exactly as listed in the issue's entry.
5. **Dependencies:** in the "Blocked by" line, replace each `AG-xxx` with `#<number> (AG-xxx)` using the GitHub issue number created earlier. Keep a mapping table AG-xxx → #number while creating.
6. After all issues exist, post the final AG-xxx → #number mapping as a comment on AG-001 so the team can cross-reference.
7. **Do not create issues** for anything in §6 (removed, excluded, or dropped features), and do not create issues that are not in this backlog. New bugs found later use the same template with the next free ID.

Example with `gh` (adapt to the tools available):

```bash
gh api repos/<owner>/<repo>/labels -f name='type:feature' -f color='1D76DB'
gh api repos/<owner>/<repo>/milestones -f title='Mid FYP-1' -f due_on='2026-11-06T23:59:59Z'
gh api repos/<owner>/<repo>/issues -f title='[AG-001] …' -f body=@body.md -f milestone=<number> \
  -f 'labels[]=type:infra' -f 'labels[]=epic:E0' -f 'assignees[]=Ahzam-28'
```

---

## 34. Issue conventions

### 34.1 Issue body template

```markdown
**ID:** AG-xxx · **Epic:** Ex — <epic name> · **Feature(s):** Fx, Fy · **Milestone:** <name> · **Owner:** <name>
**Blocked by:** #n (AG-xxx), … | none
**Spec:** docs/AGENTICA_SPEC.md §x.y, …

## Context
<why this issue exists>

## Tasks
- [ ] …

## Files (expected)
- `path`

## Acceptance criteria
- [ ] …

## Tests
<required tests beyond the acceptance criteria, or "Covered by acceptance criteria">

## Out of scope
- … (always includes: anything in spec §6)

## Definition of done
<Standard Definition of Done from spec §34.2>
```

### 34.2 Standard Definition of Done (append to every issue)

- [ ] All acceptance criteria are met and checked off.
- [ ] CI is green on `ubuntu-22.04` and `windows-latest` (lint, format, tests, UI build).
- [ ] New code has unit tests; integration tests are added where the issue touches the DB, the graph, or a target.
- [ ] No secrets appear in code, config, logs, prompts, or API responses (redaction helper used).
- [ ] No `shell=True` and no string commands built from model output.
- [ ] Every new tool has: a Pydantic input model with `extra="forbid"`, an output model, a declared risk tier, a `verify()` for modify/destructive tools, a catalogue entry in §14.5 (spec updated if it changed), and ≥ 3 labelled benchmark tasks in `eval/tasks/`.
- [ ] Issues labelled `risk:modifies-systems`: policy tests prove Confirm under the default policy, guardrail tests are added, and a second team member has reviewed the PR.
- [ ] Any change to a [D] design item is recorded as an ADR in `docs/adr/`; [P] items are unchanged.
- [ ] The PR references the issue (`Closes #n`) and the feature ID(s).

### 34.3 Writing rules for any new issue

- One outcome per issue, completable by one person in about 1–2 weeks.
- Acceptance criteria must be **testable** (observable behaviour, a test, or a measured number), never "works well".
- Always cite the spec sections and the feature ID(s).
- Never reference a dropped feature (F20–F24) or anything in §6.

---

## 35. The backlog

### 35.1 Epics

| Epic | Scope |
|---|---|
| `E0` | Foundation (repo, config, data, secrets, API, UI shell) |
| `E1` | Agent core: orchestrator, routing, conversation (F1–F4) |
| `E2` | Governance: policy engine and guardrails (F18, F19) |
| `E3` | Knowledge: RAG and knowledge-base management (F5, F6) |
| `E4` | Local system management (F7–F10) |
| `E5` | Remote infrastructure (F11, F12) |
| `E6` | Models: local/offline mode and model selection (F14, F15) |
| `E7` | Guided troubleshooting (F13) |
| `E8` | Dashboard and web interface (F16, F17) |
| `E9` | Evaluation benchmark (§25) |
| `E10` | Packaging, integration, and release |
| `E11` | Documentation deliverables |

### 35.2 Index

76 issues. IDs are in dependency order (a blocker always has a lower ID).

| ID | Title | Milestone | Owner | Blocked by |
|---|---|---|---|---|
| AG-001 | Repository scaffold, tooling, and CI on Windows + Linux | Mid FYP-1 | Ali | — |
| AG-002 | Configuration loading with bundled safe defaults | Mid FYP-1 | Ahzam | AG-001 |
| AG-003 | Secrets module: OS keyring wrapper and redaction helper | Mid FYP-1 | Ahzam | AG-001 |
| AG-004 | PostgreSQL 16 + pgvector data layer and Alembic migrations | Mid FYP-1 | Ahzam | AG-001, AG-002, AG-003 |
| AG-005 | Structured JSON application logging with redaction | Mid FYP-1 | Ahzam | AG-002, AG-003 |
| AG-006 | FastAPI backend skeleton: app factory, health, desktop auth | Mid FYP-1 | Ali | AG-001, AG-002, AG-004, AG-005 |
| AG-007 | UI scaffold: React + TypeScript + Vite with API and SSE client | Mid FYP-1 | Ali | AG-001 |
| AG-008 | Tool framework: ToolSpec, registry, Target protocol, LocalTarget | Mid FYP-1 | Ahsan | AG-001 |
| AG-009 | Model provider interface and cloud (OpenAI-compatible) provider | Mid FYP-1 | Ali | AG-001, AG-002, AG-003 |
| AG-010 | Embedding service (local sentence-transformers) | Mid FYP-1 | Ahzam | AG-001, AG-002 |
| AG-011 | Policy engine: deterministic decision function and default policy | Mid FYP-1 | Ahsan | AG-002, AG-006, AG-008 |
| AG-012 | Orchestrator skeleton: LangGraph StateGraph with Postgres checkpointer | Mid FYP-1 | Ahsan | AG-004, AG-008, AG-009, AG-011 |
| AG-013 | Two-stage tool router v1 with flat-baseline mode | Mid FYP-1 | Ahsan | AG-008, AG-010, AG-012 |
| AG-014 | Chat streaming endpoint (SSE) and run cancellation | Mid FYP-1 | Ahsan | AG-006, AG-012 |
| AG-015 | Chat interface UI | Mid FYP-1 | Ahsan | AG-007, AG-014 |
| AG-016 | Multi-turn session history: sessions API and sidebar | Mid FYP-1 | Ahsan | AG-012, AG-014, AG-015 |
| AG-017 | Confirm → interrupt → resume approval flow (survives restart) | Mid FYP-1 | Ahsan | AG-011, AG-012, AG-014 |
| AG-018 | Live tool-call cards and inline approval prompt (UI) | Mid FYP-1 | Ahsan | AG-015, AG-017 |
| AG-019 | Document text extraction (PDF, DOCX, HTML, Markdown, TXT) | Mid FYP-1 | All members (suggested lead: Ali) | AG-001 |
| AG-020 | Structure-aware chunking with contextual headers | Mid FYP-1 | All members (suggested lead: Ali) | AG-010, AG-019 |
| AG-021 | Ingestion pipeline: hashing, atomic replace, status tracking | Mid FYP-1 | All members (suggested lead: Ali) | AG-004, AG-010, AG-020 |
| AG-022 | Hybrid search with RRF and the search_knowledge_base tool | Mid FYP-1 | All members (suggested lead: Ahzam) | AG-008, AG-012, AG-021 |
| AG-023 | Benchmark task file format and first labelled tasks | Mid FYP-1 | Ahzam | AG-001 |
| AG-024 | Local system monitoring tools (psutil) and shared result models | Mid FYP-1 | Ahsan | AG-008, AG-023 |
| AG-025 | Software Requirements Specification (SRS) | Mid FYP-1 | All members (suggested lead: Ahsan) | — |
| AG-026 | GUI task cards with routing bias | Final FYP-1 | Ahzam | AG-013, AG-015 |
| AG-027 | Guardrails v1: command analysis, hardline blocklist, pattern set | Final FYP-1 | All members (suggested lead: Ahsan) | AG-011 |
| AG-028 | Grounding enforcement and prompt-injection defences | Final FYP-1 | All members (suggested lead: Ahsan) | AG-012, AG-022, AG-024 |
| AG-029 | Folder watching and automatic re-indexing | Final FYP-1 | All members (suggested lead: Ahsan) | AG-021 |
| AG-030 | Knowledge Base API and management page | Final FYP-1 | All members (suggested lead: Ahsan) | AG-006, AG-007, AG-029 |
| AG-031 | SOP corpus for the knowledge base and evaluation fixture | Final FYP-1 | All members (suggested lead: Ali) | — |
| AG-032 | Retrieval evaluation and embedding-model choice (OPEN-1) | Final FYP-1 | All members (suggested lead: Ahzam) | AG-022, AG-031 |
| AG-033 | Service status tools (local Linux and Windows) | Final FYP-1 | Ali | AG-008, AG-023 |
| AG-034 | Service control tools with post-condition verification | Final FYP-1 | Ali | AG-017, AG-027, AG-033 |
| AG-035 | Application status monitoring (config-based) | Final FYP-1 | Ahzam | AG-002, AG-008, AG-033 |
| AG-036 | SSHTarget backend: Fabric pool, host-key pinning, timeouts | Final FYP-1 | Ali | AG-002, AG-003, AG-008 |
| AG-037 | Linux command output parsers with fixture tests | Final FYP-1 | Ali | AG-024 |
| AG-038 | WinRMTarget backend: HTTPS, certificate pinning, PowerShell escaping | Final FYP-1 | Ahsan | AG-002, AG-003, AG-008 |
| AG-039 | Windows PowerShell JSON parsers with fixture tests | Final FYP-1 | Ahsan | AG-024 |
| AG-040 | Machines page: targets, credentials, trust, and connection test | Final FYP-1 | Ali | AG-006, AG-007, AG-036, AG-038 |
| AG-041 | Ollama provider for local/offline model mode | Final FYP-1 | Ahzam | AG-009, AG-023 |
| AG-042 | Context budget management for small local models | Final FYP-1 | Ahsan | AG-016, AG-041 |
| AG-043 | Local-mode egress guard and offline verification | Final FYP-1 | Ahzam | AG-010, AG-041 |
| AG-044 | Choose final local models by tool-calling reliability (OPEN-2) | Final FYP-1 | Ahzam | AG-013, AG-023, AG-041 |
| AG-045 | Evaluation fixture VMs (Linux + Windows) with snapshot reset | Final FYP-1 | Ahzam | — |
| AG-046 | Remote Linux management: tool wiring and target setup script | Final FYP-1 | Ali | AG-034, AG-035, AG-036, AG-037, AG-045 |
| AG-047 | Remote Windows management: tool wiring and WinRM setup script | Final FYP-1 | Ahsan | AG-034, AG-035, AG-038, AG-039, AG-045 |
| AG-048 | get_logs and check_port tools (local and remote) | Final FYP-1 | Ali | AG-046, AG-047 |
| AG-049 | Decide and (if kept) implement the exec_command escape hatch (OPEN-5) | Final FYP-1 | All members (suggested lead: Ali) | AG-027, AG-046, AG-047 |
| AG-050 | Spike: shipping PostgreSQL + pgvector inside the installer (OPEN-3) | Final FYP-1 | Ahzam | AG-004 |
| AG-051 | FYP-1 integration, test pass, and demo preparation | Final FYP-1 | All members (suggested lead: Ahsan) | AG-026, AG-027, AG-030, AG-032, AG-034, AG-035, AG-040, AG-042, AG-043, AG-046, AG-047 |
| AG-052 | Design documentation | Final FYP-1 | All members (suggested lead: Ahzam) | AG-025 |
| AG-053 | Guardrails v2: Windows/PowerShell patterns and obfuscation | Mid FYP-2 | All members (suggested lead: Ahsan) | AG-027, AG-047 |
| AG-054 | File read tools and path allowlist enforcement | Mid FYP-2 | Ali | AG-008, AG-011, AG-023 |
| AG-055 | File modify and delete tools (trash-first delete) | Mid FYP-2 | Ali | AG-017, AG-027, AG-054 |
| AG-056 | Flexible model selection: settings API, UI, and runtime switch | Mid FYP-2 | Ali | AG-007, AG-009, AG-041, AG-043 |
| AG-057 | Fault-category evidence table and collect_fault_evidence tool | Mid FYP-2 | All members (suggested lead: Ali) | AG-024, AG-035, AG-046, AG-047, AG-048 |
| AG-058 | Background poller and dashboard cache | Mid FYP-2 | Ahzam | AG-024, AG-035, AG-046, AG-047 |
| AG-059 | Built-in monitoring dashboard: API, SSE, and UI | Mid FYP-2 | Ahzam | AG-007, AG-040, AG-058 |
| AG-060 | Seeded-fault scripts and resets (6 faults × 2 OSes) | Mid FYP-2 | Ahzam | AG-045 |
| AG-061 | Guided troubleshooting flow (classify → evidence → procedure → recommend) | Mid FYP-2 | All members (suggested lead: Ahsan) | AG-017, AG-022, AG-057, AG-060 |
| AG-062 | Web interface: HTTPS LAN server mode (off by default) | Final FYP-2 | Ali | AG-006, AG-056 |
| AG-063 | Web interface authentication (single admin) | Final FYP-2 | Ali | AG-003, AG-062 |
| AG-064 | Responsive UI and web feature subset (OPEN-7) | Final FYP-2 | Ali | AG-018, AG-030, AG-059, AG-063 |
| AG-065 | Complete the labelled task set (60–80 tasks) | Final FYP-2 | Ahzam | AG-023, AG-026, AG-035, AG-046, AG-047, AG-055, AG-056, AG-061 |
| AG-066 | Evaluation runner: backends × routing modes | Final FYP-2 | Ahzam | AG-013, AG-017, AG-023, AG-056, AG-060 |
| AG-067 | Adversarial safety set and false-allow / benign-pass measurement | Final FYP-2 | All members (suggested lead: Ali) | AG-053, AG-055, AG-066 |
| AG-068 | Guardrails hardening from adversarial results (release gate) | Final FYP-2 | All members (suggested lead: Ahsan) | AG-053, AG-067 |
| AG-069 | Evaluation report generator (Table 4) and final results | Final FYP-2 | Ahzam | AG-032, AG-065, AG-066, AG-067 |
| AG-070 | PyInstaller backend sidecar builds (Windows and Linux) | Final FYP-2 | All members (suggested lead: Ahzam) | AG-043, AG-050 |
| AG-071 | Tauri v2 desktop shell with sidecar lifecycle | Final FYP-2 | All members (suggested lead: Ahsan) | AG-007, AG-070 |
| AG-072 | Installers, release workflow, and clean-machine install test | Final FYP-2 | All members (suggested lead: Ali) | AG-071 |
| AG-073 | Integration and load testing | Final FYP-2 | All members (suggested lead: Ahzam) | AG-059, AG-064, AG-072 |
| AG-074 | NFR verification report (NFR-1 to NFR-8) | Final FYP-2 | All members (suggested lead: Ahsan) | AG-017, AG-043, AG-069, AG-072 |
| AG-075 | User guide | Final FYP-2 | All members (suggested lead: Ali) | AG-072 |
| AG-076 | Final thesis and final demonstration | Final FYP-2 | All members (suggested lead: Ahsan) | AG-069, AG-074, AG-075 |

**Workload by assignee and milestone** ("All" issues counted under the suggested lead):

| Assignee | Mid FYP-1 | Final FYP-1 | Mid FYP-2 | Final FYP-2 | Total |
|---|---|---|---|---|---|
| Ahsan | 11 | 9 | 2 | 4 | 26 |
| Ahzam | 7 | 9 | 3 | 5 | 24 |
| Ali | 7 | 9 | 4 | 6 | 26 |

**Feature coverage** (every core feature is covered):

| Feature | Issues |
|---|---|
| F1 | AG-007, AG-012, AG-014, AG-015, AG-071 |
| F2 | AG-010, AG-013, AG-026 |
| F3 | AG-014, AG-018 |
| F4 | AG-004, AG-012, AG-016, AG-042 |
| F5 | AG-004, AG-010, AG-020, AG-022, AG-031, AG-032 |
| F6 | AG-019, AG-021, AG-029, AG-030 |
| F7 | AG-024 |
| F8 | AG-054, AG-055 |
| F9 | AG-033, AG-034 |
| F10 | AG-035 |
| F11 | AG-036, AG-037, AG-040, AG-046, AG-048, AG-049 |
| F12 | AG-038, AG-039, AG-040, AG-047, AG-048, AG-049 |
| F13 | AG-031, AG-048, AG-057, AG-060, AG-061 |
| F14 | AG-041, AG-042, AG-043, AG-044 |
| F15 | AG-009, AG-056 |
| F16 | AG-058, AG-059 |
| F17 | AG-062, AG-063, AG-064 |
| F18 | AG-027, AG-028, AG-049, AG-053, AG-067, AG-068 |
| F19 | AG-011, AG-012, AG-017, AG-018, AG-067 |

### 35.3 Issue details


#### Milestone: Mid FYP-1 (due ~2026-11-06)

##### [AG-001] Repository scaffold, tooling, and CI on Windows + Linux

- **Epic:** E0 — Foundation (repo, config, data, secrets, API, UI shell)
- **Feature(s):** — (supporting work)
- **Milestone:** Mid FYP-1
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:infra`, `area:backend-core`, `epic:E0`, `priority:P0`
- **Blocked by:** none
- **Spec:** §27.2, §27.3, §8.4, §34

**Context.** Create the monorepo so all three members can work in parallel from day one, with CI that runs on both target operating systems (NFR-4).

**Tasks**
- [ ] Create the directory layout exactly as in §27.2 (`backend/`, `ui/`, `desktop/`, `config/`, `eval/`, `infra/`, `docs/adr/`, `.github/workflows/`).
- [ ] `backend/pyproject.toml`: Python 3.12, dependency groups `core` and `dev`; configure `ruff` (lint + format) and `pytest` with `pytest-asyncio`.
- [ ] GitHub Actions workflow `ci.yml`: matrix `ubuntu-22.04` and `windows-latest`; steps: install, `ruff check`, `ruff format --check`, `pytest`. Add a UI job (`npm ci`, typecheck, build) once `ui/` exists.
- [ ] Add `.github/pull_request_template.md` containing the Standard Definition of Done from §34.4.
- [ ] Add `.github/ISSUE_TEMPLATE/task.md` using the issue body template from §34.3.
- [ ] Commit this spec as `docs/AGENTICA_SPEC.md`, the `CLAUDE.md` from Appendix B, and `docs/adr/0000-template.md` (context, decision, consequences).
- [ ] Add `README.md` with the project summary (§2) and dev setup steps.

**Files (expected)**
- `backend/pyproject.toml`
- `.github/workflows/ci.yml`
- `.github/pull_request_template.md`
- `.github/ISSUE_TEMPLATE/task.md`
- `docs/AGENTICA_SPEC.md`
- `CLAUDE.md`
- `docs/adr/0000-template.md`
- `README.md`

**Acceptance criteria**
- [ ] CI passes on both `ubuntu-22.04` and `windows-latest` with at least one placeholder test.
- [ ] A PR with a ruff violation fails CI.
- [ ] The PR template and issue template are present and match §34.
- [ ] The spec and `CLAUDE.md` are committed at the paths above.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-002] Configuration loading with bundled safe defaults

- **Epic:** E0 — Foundation (repo, config, data, secrets, API, UI shell)
- **Feature(s):** — (supporting work)
- **Milestone:** Mid FYP-1
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:infra`, `area:backend-core`, `epic:E0`, `priority:P0`
- **Blocked by:** AG-001
- **Spec:** §20.2, §17.3, §7 F10, NFR-3, NFR-8

**Context.** All behaviour that varies per installation lives in YAML files with safe defaults bundled in `config/`. Later issues add their own schemas (policy, router categories, faults) on top of this loader.

**Tasks**
- [ ] Implement `agentica/core/config.py`: a generic loader `load_yaml(path, model)` that validates with a Pydantic v2 model (`extra="forbid"`) and reports file + field on error.
- [ ] Use `platformdirs` for the config dir, data dir, and log dir (app name `Agentica`).
- [ ] On first start, copy bundled defaults from `config/` into the user config dir when a file is missing. Never overwrite an existing user file.
- [ ] Define Pydantic models for `settings.yaml` (backend, model names, ports, `web_access_enabled: false`, poll intervals, KB folders), `targets.yaml` (§17.3), and `apps.yaml` (§7 F10).
- [ ] Reject any config key whose name suggests a secret (`password`, `secret`, `api_key`, `token`, `private_key`). Configs may hold only references (`credential_ref`, `key_ref`).
- [ ] Provide `reload()` that keeps the last valid config when the new file is invalid.
- [ ] Write bundled defaults: `config/settings.yaml`, `config/targets.yaml` (empty list plus commented example), and `config/apps.yaml` (empty list plus commented example).

**Files (expected)**
- `backend/agentica/core/config.py`
- `config/settings.yaml`
- `config/targets.yaml`
- `config/apps.yaml`
- `backend/tests/unit/test_config.py`

**Acceptance criteria**
- [ ] A fresh start creates the user config dir populated with the bundled defaults.
- [ ] An invalid YAML file produces an error naming the file and field; on reload, the previous valid config stays active.
- [ ] A config containing `password:` (any nesting level) is rejected.
- [ ] Unit tests cover first-run copy, validation errors, secret-key rejection, and reload.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-003] Secrets module: OS keyring wrapper and redaction helper

- **Epic:** E0 — Foundation (repo, config, data, secrets, API, UI shell)
- **Feature(s):** — (supporting work)
- **Milestone:** Mid FYP-1
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:security`, `area:backend-core`, `epic:E0`, `priority:P0`
- **Blocked by:** AG-001
- **Spec:** §20.3, NFR-8, §28 OPEN-4

**Context.** Credentials (SSH key passphrases, WinRM passwords, the cloud API key, the DB password) must live only in the OS keyring. Everything that is displayed or logged must pass through redaction.

**Tasks**
- [ ] `agentica/security/secrets.py`: `get_secret(ref)`, `set_secret(ref, value)`, `delete_secret(ref)` on top of the `keyring` library, with a fixed service prefix `agentica/`.
- [ ] Detect a missing keyring backend (e.g. headless Linux without Secret Service) and raise a clear, actionable error.
- [ ] Write ADR `docs/adr/0003-keyring-headless-linux.md` deciding the fallback (OPEN-4); the recommended option is `keyrings.cryptfile` with a master password.
- [ ] `redact(obj)` helper: masks every value currently held through `set_secret`/`get_secret` in this process, plus common patterns (`Authorization:` headers, `password=...`, PEM private-key blocks); works on strings, dicts, and lists.

**Files (expected)**
- `backend/agentica/security/secrets.py`
- `docs/adr/0003-keyring-headless-linux.md`
- `backend/tests/unit/test_secrets.py`

**Acceptance criteria**
- [ ] Set/get/delete round-trip works with the real backend on Windows and on a Linux desktop (documented manual check), and with an in-memory test backend in CI.
- [ ] `redact()` masks known secrets and the listed patterns in nested structures (unit tests).
- [ ] The ADR for OPEN-4 is merged.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-004] PostgreSQL 16 + pgvector data layer and Alembic migrations

- **Epic:** E0 — Foundation (repo, config, data, secrets, API, UI shell)
- **Feature(s):** F4, F5
- **Milestone:** Mid FYP-1
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:infra`, `area:db`, `feature:F04`, `feature:F05`, `epic:E0`, `priority:P0`
- **Blocked by:** AG-001, AG-002, AG-003
- **Spec:** §20.1, §13.2, NFR-8

**Context.** One local PostgreSQL instance holds all persistent state. This issue creates the schema; the LangGraph checkpoint tables are created separately by `AsyncPostgresSaver.setup()` in the orchestrator issue.

**Tasks**
- [ ] SQLAlchemy 2 async engine with `psycopg` 3; connection settings from `settings.yaml`, DB password from the keyring (secrets module).
- [ ] Alembic setup in `backend/agentica/db/migrations/`.
- [ ] Migration 001: `CREATE EXTENSION IF NOT EXISTS vector`; tables `sessions`, `app_settings`, `kb_documents`, `kb_chunks` exactly as §13.2 and §20.1 (embedding `vector(768)`; all OPEN-1 candidates are 768-dimensional).
- [ ] Indexes: HNSW `vector_cosine_ops` on `kb_chunks.embedding`, GIN on `kb_chunks.tsv`.
- [ ] `docker-compose.dev.yml` with the `pgvector/pgvector:pg16` image, for development only (the shipped app uses the bundled DB from the packaging issues).
- [ ] The DB must listen on `127.0.0.1` only; document this in the dev setup.

**Files (expected)**
- `backend/agentica/db/engine.py`
- `backend/agentica/db/models.py`
- `backend/agentica/db/migrations/`
- `docker-compose.dev.yml`
- `backend/tests/integration/test_db.py`

**Acceptance criteria**
- [ ] `alembic upgrade head` on a clean PG16 + pgvector creates all tables and indexes; `alembic downgrade base` removes them.
- [ ] An integration test inserts a chunk with an embedding and retrieves it with an `ORDER BY embedding <=> :q` query.
- [ ] No password appears in `alembic.ini`, settings files, or logs.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Shipping PostgreSQL inside the installer (separate spike and packaging issues).
- Any audit, registry, or scheduler tables (dropped features X14–X17).
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-005] Structured JSON application logging with redaction

- **Epic:** E0 — Foundation (repo, config, data, secrets, API, UI shell)
- **Feature(s):** — (supporting work)
- **Milestone:** Mid FYP-1
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:infra`, `area:backend-core`, `epic:E0`, `priority:P1`
- **Blocked by:** AG-002, AG-003
- **Spec:** §20.4

**Context.** An operational log for debugging and evaluation. It is not an audit feature: no table, no viewer, no export (X16).

**Tasks**
- [ ] JSON log formatter writing to a rotating file in the platformdirs log dir (e.g. 10 MB × 5 files).
- [ ] Standard fields: `ts`, `level`, `event`, `session_id`, `run_id`, `call_id`.
- [ ] Event names to support: `request`, `route`, `retrieval`, `policy_decision`, `tool_start`, `tool_end`, `approval`, `verify`, `error`.
- [ ] Every record passes through `redact()` before writing.

**Files (expected)**
- `backend/agentica/core/logging.py`
- `backend/tests/unit/test_logging.py`

**Acceptance criteria**
- [ ] A secret registered via the secrets module never appears in the log file, even when passed inside an event payload (test).
- [ ] Log rotation is configured and covered by a test.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-006] FastAPI backend skeleton: app factory, health, desktop auth

- **Epic:** E0 — Foundation (repo, config, data, secrets, API, UI shell)
- **Feature(s):** — (supporting work)
- **Milestone:** Mid FYP-1
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:infra`, `area:backend-core`, `epic:E0`, `priority:P0`
- **Blocked by:** AG-001, AG-002, AG-004, AG-005
- **Spec:** §21.1, §9.2, §9.3

**Context.** The API gateway of the application layer. Routes contain no business logic; they validate input and call services.

**Tasks**
- [ ] `agentica/main.py`: app factory plus a lifespan that loads config, connects the DB, and exposes hooks for the KB watcher and poller (added later).
- [ ] `GET /api/health` → `{status, backend, db: ok|error, version}`.
- [ ] Error handler returning structured errors `{code, message}`; never leak stack traces to clients.
- [ ] Desktop auth: a per-launch bearer token passed by CLI arg or env var (Tauri passes it later). In dev mode, generate and print the token. All `/api/*` routes except health require it.
- [ ] Bind to `127.0.0.1` on a configurable port (random free port by default for sidecar use). CORS allows only the app origin.

**Files (expected)**
- `backend/agentica/main.py`
- `backend/agentica/api/__init__.py`
- `backend/agentica/api/health.py`
- `backend/agentica/security/auth.py`
- `backend/tests/integration/test_api_health.py`

**Acceptance criteria**
- [ ] `GET /api/health` reports DB status correctly when the DB is up and when it is down.
- [ ] Requests without a valid token get 401.
- [ ] The server never binds to `0.0.0.0` in this mode (test inspects the bind address).

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-007] UI scaffold: React + TypeScript + Vite with API and SSE client

- **Epic:** E0 — Foundation (repo, config, data, secrets, API, UI shell)
- **Feature(s):** F1
- **Milestone:** Mid FYP-1
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:infra`, `area:ui`, `feature:F01`, `epic:E0`, `priority:P0`
- **Blocked by:** AG-001
- **Spec:** §22, §21.2

**Context.** One React build serves both the Tauri desktop app and the web interface, so the layout must be responsive from the start.

**Tasks**
- [ ] Vite + React + TypeScript (strict). Routes: Chat, Dashboard, Knowledge Base, Machines, Settings (placeholders).
- [ ] API client that attaches the bearer token; SSE helper based on `@microsoft/fetch-event-source` (supports POST bodies and headers).
- [ ] Install Recharts; choose a styling approach and record it in an ADR.
- [ ] Responsive app shell (sidebar collapses on narrow screens).
- [ ] Add UI typecheck + build to CI.

**Files (expected)**
- `ui/package.json`
- `ui/src/main.tsx`
- `ui/src/api/client.ts`
- `ui/src/api/sse.ts`
- `ui/src/routes/*`

**Acceptance criteria**
- [ ] `npm run build` produces a static bundle; CI runs typecheck and build.
- [ ] In dev, the app calls `/api/health` with the token and shows the result.
- [ ] The layout is usable at 375 px width.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-008] Tool framework: ToolSpec, registry, Target protocol, LocalTarget

- **Epic:** E1 — Agent core: orchestrator, routing, conversation (F1–F4)
- **Feature(s):** — (supporting work)
- **Milestone:** Mid FYP-1
- **Owner:** Ahsan · **Assignee:** Ahsan
- **Labels:** `type:feature`, `area:tools`, `epic:E1`, `priority:P0`
- **Blocked by:** AG-001
- **Spec:** §18, §14.5, NFR-7, §0.3 rule 8

**Context.** Every tool follows one contract, so it can be routed, validated, policy-checked, executed, verified, and unit-tested uniformly.

**Tasks**
- [ ] Implement `ToolSpec`, the `Tool` protocol (`run`, `verify`, `command_preview`), and `ToolError{code, message, retriable}` exactly as §18.
- [ ] Registry: register, look up by name, list by category, and export the JSON schema of each tool's input model (`additionalProperties: false`) plus the enum of names for a given scope.
- [ ] Result envelope `{summary: str, data: model, truncated: bool}`.
- [ ] `Target` protocol plus `LocalTarget.run_command(argv: list[str], timeout_s, privileged=False)`. Reject plain strings at runtime. Never use `shell=True`. Cap captured output at 256 KB.
- [ ] `FakeTarget` for tests: scripted outputs per argv.
- [ ] Canonical category names from §14.5: `monitoring, files, services, applications, logs, network, knowledge, troubleshooting, remote, meta`.

**Files (expected)**
- `backend/agentica/tools/base.py`
- `backend/agentica/targets/base.py`
- `backend/agentica/targets/local.py`
- `backend/tests/fakes.py`
- `backend/tests/unit/test_tools_base.py`

**Acceptance criteria**
- [ ] Exported schemas for a sample tool have `additionalProperties: false` and validate as JSON Schema.
- [ ] `LocalTarget.run_command("rm -rf /")` (a string) raises `TypeError` without executing anything.
- [ ] Output above the cap is truncated with `truncated: true`.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-009] Model provider interface and cloud (OpenAI-compatible) provider

- **Epic:** E1 — Agent core: orchestrator, routing, conversation (F1–F4)
- **Feature(s):** F15
- **Milestone:** Mid FYP-1
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:feature`, `area:models`, `feature:F15`, `epic:E1`, `priority:P0`
- **Blocked by:** AG-001, AG-002, AG-003
- **Spec:** §15.1, §15.2

**Context.** Cloud and local inference sit behind one interface, so the rest of the system never knows which backend is running (FR-16).

**Tasks**
- [ ] `ModelProvider` protocol as §15.1: `chat(messages, tools, response_schema, temperature=0, stream)`.
- [ ] Cloud implementation using an OpenAI-compatible client: `base_url` and `model` from settings, API key from the keyring. Support tool calling and token streaming.
- [ ] Map provider errors (auth, rate limit, timeout) to structured errors.
- [ ] Every run records `backend`, `model`, `quantisation` (n/a for cloud), and `host` in run metadata.
- [ ] Provider factory: when `backend=local`, requesting a cloud provider raises an error (the full egress guard comes in a later issue).

**Files (expected)**
- `backend/agentica/models/provider.py`
- `backend/agentica/models/cloud.py`
- `backend/tests/unit/test_provider_cloud.py`

**Acceptance criteria**
- [ ] Against a mocked OpenAI-compatible server, a tool-call response is parsed into a `ToolCall` with validated arguments.
- [ ] Streaming yields tokens incrementally.
- [ ] The factory refuses a cloud provider in local mode (test).

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-010] Embedding service (local sentence-transformers)

- **Epic:** E1 — Agent core: orchestrator, routing, conversation (F1–F4)
- **Feature(s):** F5, F2
- **Milestone:** Mid FYP-1
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:feature`, `area:rag`, `area:router`, `feature:F05`, `feature:F02`, `epic:E1`, `priority:P0`
- **Blocked by:** AG-001, AG-002
- **Spec:** §13.4, §14.2, F14

**Context.** One local embedding model, shared by the router and RAG, used in every backend configuration so retrieval quality is constant (§15.2).

**Tasks**
- [ ] `agentica/rag/embed.py`: load the model configured in `settings.yaml` once at startup; `encode_queries()` and `encode_documents()` apply the model's required prefixes (e.g. E5 `query: ` / `passage: `) and normalise vectors.
- [ ] Run encoding in a thread pool so it never blocks the event loop.
- [ ] Default model: `intfloat/multilingual-e5-base` (MIT licence, 768-d, no remote code) until the OPEN-1 spike decides.
- [ ] Support offline loading from a local path; respect `HF_HUB_OFFLINE=1`.

**Files (expected)**
- `backend/agentica/rag/embed.py`
- `backend/tests/unit/test_embed.py`

**Acceptance criteria**
- [ ] Returns 768-dimensional unit-norm vectors.
- [ ] Works with the network disabled when the model is present locally.
- [ ] Concurrent API requests are not blocked while a batch is being encoded (test with an async health call during encoding).

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-011] Policy engine: deterministic decision function and default policy

- **Epic:** E2 — Governance: policy engine and guardrails (F18, F19)
- **Feature(s):** F19
- **Milestone:** Mid FYP-1
- **Owner:** Ahsan · **Assignee:** Ahsan
- **Labels:** `type:security`, `area:policy`, `feature:F19`, `epic:E2`, `priority:P0`
- **Blocked by:** AG-002, AG-006, AG-008
- **Spec:** §11.1, §11.2, §11.3, FR-13

**Context.** F19 core: every action is graded by risk and allowed, refused, or held for confirmation. Pure Python, no LLM, so results never vary by backend.

**Tasks**
- [ ] Pydantic schema for `policy.yaml` exactly as §11.3; bundled default `config/policy.yaml` with the safe defaults shown there.
- [ ] `decide(call, target) -> Decision{decision, tier, reason, rule_id}` implementing the 10 steps of §11.2 in that order.
- [ ] Define a `GuardrailChecker` protocol (hardline and dangerous-pattern findings) and plug in a minimal implementation; the full guardrails come in the guardrails issues.
- [ ] Path checks: `Path(p).expanduser().resolve(strict=False)` plus `is_relative_to()` against `allow_roots`; deny list wins; modify/destructive on `read_only_roots` is denied.
- [ ] Protected services list; target overrides use glob matching on target id, with the most specific match winning and ties going to the most restrictive.
- [ ] Endpoints `GET /api/policy` (effective policy, read-only) and `POST /api/policy/reload` (keep-last-valid).

**Files (expected)**
- `backend/agentica/policy/engine.py`
- `backend/agentica/policy/schema.py`
- `backend/agentica/policy/paths.py`
- `config/policy.yaml`
- `backend/agentica/api/policy.py`
- `backend/tests/unit/test_policy.py`

**Acceptance criteria**
- [ ] Table-driven tests cover every step of §11.2; `decide()` has 100% branch coverage.
- [ ] An unknown tool gets DENY; overrides can never relax steps 1–6 (tests).
- [ ] Path traversal (`../`) and symlink escapes are denied (tests using a temp dir).
- [ ] An invalid policy file is rejected on reload and the previous policy stays active.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-012] Orchestrator skeleton: LangGraph StateGraph with Postgres checkpointer

- **Epic:** E1 — Agent core: orchestrator, routing, conversation (F1–F4)
- **Feature(s):** F1, F4, F19
- **Milestone:** Mid FYP-1
- **Owner:** Ahsan · **Assignee:** Ahsan
- **Labels:** `type:feature`, `area:orchestrator`, `feature:F01`, `feature:F04`, `feature:F19`, `epic:E1`, `priority:P0`
- **Blocked by:** AG-004, AG-008, AG-009, AG-011
- **Spec:** §10.1, §10.2

**Context.** The plan → act → verify loop. The only path from the model to a tool runs through `validate` and `policy`. This issue builds the graph; the approval interrupt is completed in the approval-flow issue.

**Tasks**
- [ ] `AgentState` exactly as §10.2.
- [ ] Nodes `route`, `gather_context`, `agent`, `validate`, `policy`, `approval`, `execute`, `verify`, `report`, wired as the diagram in §10.2. `route` and `gather_context` start as pass-through stubs; `approval` initially treats Confirm as reject.
- [ ] `validate`: tool name must be in the scoped enum, arguments validated with the tool's Pydantic model, target must be `local` or a known id. Return validation errors to the model (max 2 retries).
- [ ] `execute`: refuse (raise) any call without an attached policy decision of ALLOW or an approved CONFIRM.
- [ ] Loop bounds: `MAX_STEPS = 10` per turn; after 2 Denies in a turn, go to `report`.
- [ ] Persistence: `AsyncPostgresSaver` (psycopg 3, `autocommit=True`, `row_factory=dict_row`), call `.setup()` at first start; `thread_id = session_id`.

**Files (expected)**
- `backend/agentica/orchestrator/state.py`
- `backend/agentica/orchestrator/graph.py`
- `backend/agentica/orchestrator/nodes/*.py`
- `backend/agentica/orchestrator/prompts/system.md`
- `backend/tests/integration/test_graph.py`

**Acceptance criteria**
- [ ] With a scripted fake model that calls a read tool and then answers, the run completes, and every tool call carries a policy decision.
- [ ] Calling `execute` directly without a decision raises (unit test).
- [ ] The step limit and the 2-Deny limit are enforced (tests).
- [ ] Re-invoking the graph with the same `thread_id` continues the conversation from the checkpoint.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-013] Two-stage tool router v1 with flat-baseline mode

- **Epic:** E1 — Agent core: orchestrator, routing, conversation (F1–F4)
- **Feature(s):** F2
- **Milestone:** Mid FYP-1
- **Owner:** Ahsan · **Assignee:** Ahsan
- **Labels:** `type:feature`, `area:router`, `feature:F02`, `epic:E1`, `priority:P0`
- **Blocked by:** AG-008, AG-010, AG-012
- **Spec:** §14.1, §14.2, §14.3, §25.2

**Context.** Stage 1 narrows the tool categories visible to the model (O6). A flat mode (all tools visible) is needed for the routed-vs-flat experiment.

**Tasks**
- [ ] `config/router/categories.yaml`: description plus 15–30 example utterances for every category in §14.5 (files and troubleshooting examples are written now, even though those tools land later).
- [ ] Score = max cosine similarity between the request and each category's examples.
- [ ] Selection: top category, plus others within margin `m` of the top, up to `max_categories=3`. If the top score is below `τ_none`, use no-tool mode (only always-available tools). All thresholds are read from config.
- [ ] Task-card hook: `task_card` force-includes that card's categories and adds bias `δ`; the card mapping itself is done in the task-cards issue.
- [ ] Always-available tools: `get_system_overview`, `expand_scope`. Implement `expand_scope(category, reason)` in the graph, capped at 2 expansions per turn.
- [ ] `routing_mode: routed | flat` setting; flat exposes every registered tool.
- [ ] Emit the `route` SSE event and a log record.

**Files (expected)**
- `backend/agentica/router/router.py`
- `config/router/categories.yaml`
- `backend/agentica/tools/meta.py`
- `backend/tests/unit/test_router.py`

**Acceptance criteria**
- [ ] Unit tests with fixed embeddings cover margin selection, the category cap, no-tool mode, and the task-card force-include.
- [ ] On ≥ 30 held-out labelled utterances, the correct category is within the selected scope for ≥ 90% (report the number in the PR).
- [ ] `expand_scope` adds tools for the rest of the turn and is refused after 2 uses.
- [ ] Flat mode returns every registered tool.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-014] Chat streaming endpoint (SSE) and run cancellation

- **Epic:** E1 — Agent core: orchestrator, routing, conversation (F1–F4)
- **Feature(s):** F1, F3
- **Milestone:** Mid FYP-1
- **Owner:** Ahsan · **Assignee:** Ahsan
- **Labels:** `type:feature`, `area:backend-core`, `area:orchestrator`, `feature:F01`, `feature:F03`, `epic:E1`, `priority:P0`
- **Blocked by:** AG-006, AG-012
- **Spec:** §21.1, §21.2, F1, F3

**Context.** Streams every step of a run to the UI so the user sees tool calls as they happen (FR-3).

**Tasks**
- [ ] `POST /api/sessions/{id}/messages` body `{text, task_card?, target?}` → `EventSourceResponse` (`sse-starlette`).
- [ ] Map LangGraph streaming (`stream_mode=["updates","messages","custom"]`, plus `get_stream_writer()` inside tools) to the event types in §21.2: `run_start, route, retrieval, tool_start, policy_decision, tool_end, approval_required, verify, token, final, error`.
- [ ] One active run per session (a second request gets 409).
- [ ] `POST /api/sessions/{id}/cancel`: cooperative cancel at the next node boundary; never interrupts a tool mid-execution.
- [ ] Redact arguments and results in every event.

**Files (expected)**
- `backend/agentica/api/chat.py`
- `backend/agentica/core/events.py`
- `backend/tests/integration/test_chat_sse.py`

**Acceptance criteria**
- [ ] An integration test with a scripted fake model receives events in the documented order with the documented fields.
- [ ] Cancel stops the run before the next node and emits `final` with a cancelled flag.
- [ ] A secret placed in tool output is redacted in the emitted events.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-015] Chat interface UI

- **Epic:** E1 — Agent core: orchestrator, routing, conversation (F1–F4)
- **Feature(s):** F1
- **Milestone:** Mid FYP-1
- **Owner:** Ahsan · **Assignee:** Ahsan
- **Labels:** `type:feature`, `area:ui`, `feature:F01`, `epic:E1`, `priority:P0`
- **Blocked by:** AG-007, AG-014
- **Spec:** F1, §22

**Context.** F1: issue requests and receive plain-language reports.

**Tasks**
- [ ] Message list with streaming assistant tokens; Markdown rendering with HTML sanitised (no raw HTML execution).
- [ ] Input box, send, and a Stop button wired to the cancel endpoint.
- [ ] Header badge showing the active backend (from `run_start`).
- [ ] Target selector: `local` only for now; remote targets are added by the Machines issue.
- [ ] Error display for `error` events.

**Files (expected)**
- `ui/src/routes/Chat.tsx`
- `ui/src/components/MessageList.tsx`
- `ui/src/components/ChatInput.tsx`

**Acceptance criteria**
- [ ] A user can send a request and watch the answer stream in.
- [ ] Markdown containing `<script>` renders inert.
- [ ] Stop cancels the run.
- [ ] A read-only request ("How much disk space is free?") returns a correct answer grounded in a live tool call (manual demo check).

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-016] Multi-turn session history: sessions API and sidebar

- **Epic:** E1 — Agent core: orchestrator, routing, conversation (F1–F4)
- **Feature(s):** F4
- **Milestone:** Mid FYP-1
- **Owner:** Ahsan · **Assignee:** Ahsan
- **Labels:** `type:feature`, `area:backend-core`, `area:ui`, `feature:F04`, `epic:E1`, `priority:P0`
- **Blocked by:** AG-012, AG-014, AG-015
- **Spec:** F4, §20.1, §21.1

**Context.** FR-4: conversation context is retained across a session; sessions survive an app restart.

**Tasks**
- [ ] Endpoints: `POST/GET /api/sessions`, `GET/DELETE /api/sessions/{id}`.
- [ ] Auto-title a session from its first request.
- [ ] Opening a session restores messages and tool cards from the checkpoint and shows any pending approval.
- [ ] Deleting a session deletes its checkpoints (thread).
- [ ] Sidebar UI listing sessions by `updated_at`.

**Files (expected)**
- `backend/agentica/api/sessions.py`
- `ui/src/components/SessionSidebar.tsx`
- `backend/tests/integration/test_sessions.py`

**Acceptance criteria**
- [ ] A follow-up such as "restart it" resolves against the previous turn's subject (scripted test).
- [ ] After a backend restart, reopening a session shows its full history.
- [ ] Deleting a session leaves no checkpoint rows for that thread.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-017] Confirm → interrupt → resume approval flow (survives restart)

- **Epic:** E2 — Governance: policy engine and guardrails (F18, F19)
- **Feature(s):** F19
- **Milestone:** Mid FYP-1
- **Owner:** Ahsan · **Assignee:** Ahsan
- **Labels:** `type:security`, `area:orchestrator`, `area:policy`, `feature:F19`, `epic:E2`, `priority:P0`
- **Blocked by:** AG-011, AG-012, AG-014
- **Spec:** §11.4, §10.1, FR-15, NFR-5, [20]

**Context.** FR-15 / NFR-5: pause a partially-executed task at a confirmation point, persist its state, and resume on approval, even after an application restart. Approve-once only (X15).

**Tasks**
- [ ] `approval` node using `interrupt()` with the payload in §11.4. There must be no side effects before `interrupt()`, because the node re-runs from the top on resume.
- [ ] Emit the `approval_required` event (redacted).
- [ ] `POST /api/sessions/{id}/approvals/{call_id}` with `{decision: approve|reject, comment?}` resumes via `Command(resume=...)` and streams the continuation over SSE.
- [ ] Reject adds a ToolMessage telling the model the admin rejected the action.
- [ ] While an approval is pending, a new message in that session gets 409; `GET /api/sessions/{id}` returns the pending approval.

**Files (expected)**
- `backend/agentica/orchestrator/nodes/approval.py`
- `backend/agentica/api/approvals.py`
- `backend/tests/integration/test_approval_resume.py`

**Acceptance criteria**
- [ ] Kill-and-resume test: run until interrupt, discard the app and graph objects, recreate them, approve via the API, and the action executes exactly once and is verified.
- [ ] Reject results in no execution and a report explaining the rejection.
- [ ] Approving an unknown or stale `call_id` returns 404/409 and executes nothing.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-018] Live tool-call cards and inline approval prompt (UI)

- **Epic:** E1 — Agent core: orchestrator, routing, conversation (F1–F4)
- **Feature(s):** F3, F19
- **Milestone:** Mid FYP-1
- **Owner:** Ahsan · **Assignee:** Ahsan
- **Labels:** `type:feature`, `area:ui`, `feature:F03`, `feature:F19`, `epic:E1`, `priority:P0`
- **Blocked by:** AG-015, AG-017
- **Spec:** F3, §21.2, §22.2, §11.4

**Context.** FR-3: the user sees each tool the agent invokes, with arguments and result, as it happens. Confirm decisions are approved inline (approve-once only).

**Tasks**
- [ ] `ToolCallCard`: tool name, target, pretty-printed args, live spinner, duration, decision badge (Allow / Confirm / Deny), result summary, expandable raw result.
- [ ] `ApprovalPrompt` inside the card for `approval_required`: shows target, exact action preview, risk tier, and rule id; Approve and Reject buttons call the approvals endpoint and continue the stream.
- [ ] For destructive actions, Approve is never the default focus and the card shows a red warning.
- [ ] Show `verify` results ("Verified ✓" / "Not verified").

**Files (expected)**
- `ui/src/components/ToolCallCard.tsx`
- `ui/src/components/ApprovalPrompt.tsx`

**Acceptance criteria**
- [ ] A scripted multi-step run shows cards in order, live.
- [ ] Approve and Reject both work, and the stream continues after the click.
- [ ] Keyboard Enter does not approve a destructive action by default.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-019] Document text extraction (PDF, DOCX, HTML, Markdown, TXT)

- **Epic:** E3 — Knowledge: RAG and knowledge-base management (F5, F6)
- **Feature(s):** F6
- **Milestone:** Mid FYP-1
- **Owner:** All members (suggested lead: Ali) · **Assignee:** Ali
- **Labels:** `type:feature`, `area:rag`, `feature:F06`, `epic:E3`, `priority:P0`, `team:all`
- **Blocked by:** AG-001
- **Spec:** §13.1, F6

**Context.** F6 ingests text-extractable documents. Structure (headings, lists, tables) must be preserved for structure-aware chunking.

**Tasks**
- [ ] Extractors: PDF (`pypdf`, keep page numbers; use the outline or font-size heuristics for headings where available), DOCX (`python-docx`, heading styles → levels, tables), HTML (`beautifulsoup4`, drop script/style/nav), Markdown (headings from `#`), TXT.
- [ ] Common output: a list of blocks `{type: heading(level)|paragraph|list_item|table, text, page?}`.
- [ ] A document with no extractable text (e.g. a scanned PDF) → status `failed: no extractable text`. OCR is out of scope.

**Files (expected)**
- `backend/agentica/rag/extract.py`
- `backend/tests/fixtures/docs/`
- `backend/tests/unit/test_extract.py`

**Acceptance criteria**
- [ ] A fixture document of each type produces the expected block sequence.
- [ ] A scanned PDF fixture is marked failed with the exact message above.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-020] Structure-aware chunking with contextual headers

- **Epic:** E3 — Knowledge: RAG and knowledge-base management (F5, F6)
- **Feature(s):** F5
- **Milestone:** Mid FYP-1
- **Owner:** All members (suggested lead: Ali) · **Assignee:** Ali
- **Labels:** `type:feature`, `area:rag`, `feature:F05`, `epic:E3`, `priority:P0`, `team:all`
- **Blocked by:** AG-010, AG-019
- **Spec:** §13.1

**Context.** Procedures must not be cut in half, and each chunk must be retrievable by its topic.

**Tasks**
- [ ] Build the heading path for every block.
- [ ] Chunk to about 300–500 tokens with about 50 tokens of overlap, counting tokens with the embedding model's tokenizer.
- [ ] Keep numbered procedures together where possible; when a procedure must be split, repeat the procedure title in each part. Keep tables whole where possible.
- [ ] Prefix each chunk with `{doc_title} > {H1} > {H2}` (deterministic contextual header).

**Files (expected)**
- `backend/agentica/rag/chunking.py`
- `backend/tests/unit/test_chunking.py`

**Acceptance criteria**
- [ ] An 8-step procedure within the size limit stays in one chunk.
- [ ] A procedure longer than the limit is split, with the title repeated in each part.
- [ ] Every chunk starts with its heading-path header.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-021] Ingestion pipeline: hashing, atomic replace, status tracking

- **Epic:** E3 — Knowledge: RAG and knowledge-base management (F5, F6)
- **Feature(s):** F6
- **Milestone:** Mid FYP-1
- **Owner:** All members (suggested lead: Ali) · **Assignee:** Ali
- **Labels:** `type:feature`, `area:rag`, `area:db`, `feature:F06`, `epic:E3`, `priority:P0`, `team:all`
- **Blocked by:** AG-004, AG-010, AG-020
- **Spec:** §13.1, §13.2, F6

**Context.** Stale content must be cleared automatically when a source file changes, and search must never see a mix of old and new chunks.

**Tasks**
- [ ] SHA-256 per file; skip unchanged files.
- [ ] In one transaction: delete the document's chunks (cascade) and insert the new ones; update `status`, `chunk_count`, `indexed_at`.
- [ ] Background worker queue with progress events; a failed document records its error and does not block the queue.
- [ ] Store the embedding model name in `app_settings`; if it changes, mark all documents `stale` and require a full re-index.

**Files (expected)**
- `backend/agentica/rag/ingest.py`
- `backend/tests/integration/test_ingest.py`

**Acceptance criteria**
- [ ] Re-ingesting an unchanged file does nothing.
- [ ] A modified file's chunks are replaced atomically; a concurrent search never returns both old and new chunks (test).
- [ ] A failed file has status `failed` with the error message, and the other files still index.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-022] Hybrid search with RRF and the search_knowledge_base tool

- **Epic:** E3 — Knowledge: RAG and knowledge-base management (F5, F6)
- **Feature(s):** F5
- **Milestone:** Mid FYP-1
- **Owner:** All members (suggested lead: Ahzam) · **Assignee:** Ahzam
- **Labels:** `type:feature`, `area:rag`, `area:tools`, `feature:F05`, `epic:E3`, `priority:P0`, `team:all`
- **Blocked by:** AG-008, AG-012, AG-021
- **Spec:** §13.3, F5, FR-5

**Context.** F5: hybrid semantic and keyword search over organisational documentation.

**Tasks**
- [ ] Implement the SQL in §13.3 (dense top-50 + `websearch_to_tsquery` top-50, RRF with k = 60); set `hnsw.ef_search` from config.
- [ ] `retrieval_mode: hybrid | dense` setting (needed for the evaluation comparison).
- [ ] "Not found" signal: top dense cosine below `kb_min_similarity` (config; calibrated in the retrieval-evaluation issue) → return `found: false`.
- [ ] Tool `search_knowledge_base(query, top_k=5)`: read tier; returns chunks with `doc_title, heading_path, chunk_id, page, rrf_score, dense_score`.
- [ ] `gather_context` pre-runs it when `knowledge` or `troubleshooting` is in scope; emit the `retrieval` event; the report cites document and section.

**Files (expected)**
- `backend/agentica/rag/search.py`
- `backend/agentica/tools/knowledge.py`
- `backend/tests/integration/test_search.py`

**Acceptance criteria**
- [ ] On a small fixture KB, each sample query's expected chunk is in the top 5.
- [ ] Switching to dense mode changes the query path (test).
- [ ] A query unrelated to the KB returns `found: false`, and the agent says the KB does not cover it (scripted test).

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-023] Benchmark task file format and first labelled tasks

- **Epic:** E9 — Evaluation benchmark (§25)
- **Feature(s):** — (supporting work)
- **Milestone:** Mid FYP-1
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:test`, `area:eval`, `epic:E9`, `priority:P0`
- **Blocked by:** AG-001
- **Spec:** §25.4, §8.4

**Context.** The labelled task set grows with every feature (each tool issue adds ≥ 3 tasks), so its format must exist from the start.

**Tasks**
- [ ] Define the YAML task schema from §25.4 (`id, category, prompt, target, seed, reset, gold_tools, gold_args, expects_confirmation, success_check`) as a Pydantic model, with a validator script.
- [ ] Define the `success_check` types: `service_active`, `service_stopped`, `file_exists`, `file_absent`, `answer_contains_live_value`, `retrieved_doc`.
- [ ] Write the first 10 tasks (monitoring and knowledge).
- [ ] Add a CI step that validates every `eval/tasks/*.yaml`.

**Files (expected)**
- `eval/schema.py`
- `eval/validate_tasks.py`
- `eval/tasks/`
- `.github/workflows/ci.yml`

**Acceptance criteria**
- [ ] CI fails on an invalid task file.
- [ ] The first 10 tasks validate.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-024] Local system monitoring tools (psutil) and shared result models

- **Epic:** E4 — Local system management (F7–F10)
- **Feature(s):** F7
- **Milestone:** Mid FYP-1
- **Owner:** Ahsan · **Assignee:** Ahsan
- **Labels:** `type:feature`, `area:tools`, `feature:F07`, `epic:E4`, `priority:P0`
- **Blocked by:** AG-008, AG-023
- **Spec:** F7, §14.5, §16, FR-7

**Context.** F7: CPU, memory, storage, network, and processes. The result models defined here are reused by the Linux and Windows parsers, so all OSes return identical shapes.

**Tasks**
- [ ] Shared Pydantic models in `tools/models.py`: `CpuUsage`, `MemoryUsage`, `DiskUsage`, `NetworkStats`, `ProcessInfo`, `SystemOverview` (with units, e.g. `*_bytes`, `percent`).
- [ ] psutil implementations; a background CPU sampler so `cpu_percent` is meaningful.
- [ ] Tools (read tier): `get_system_overview` (always available), `get_cpu_usage`, `get_memory_usage`, `get_disk_usage`, `get_network_stats`, `list_top_processes(target, sort_by, limit)`, `get_process_details(target, pid | name)`.
- [ ] All tools take `target`; only `local` is supported until the remote issues land (others return a clear `UNSUPPORTED_TARGET` error).
- [ ] Handle `psutil.AccessDenied` gracefully (partial data plus a note).
- [ ] Add ≥ 3 benchmark tasks for monitoring in `eval/tasks/monitoring.yaml`.

**Files (expected)**
- `backend/agentica/tools/models.py`
- `backend/agentica/tools/monitoring.py`
- `backend/tests/unit/test_monitoring.py`
- `eval/tasks/monitoring.yaml`

**Acceptance criteria**
- [ ] Values match OS tools (Task Manager, `top`, `df`) within normal sampling tolerance (manual check recorded in the PR).
- [ ] Unit tests with mocked psutil cover every tool.
- [ ] A median read-only monitoring query in cloud mode completes in ≤ 5 s on the reference machine (NFR-6; record the measurement).

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-025] Software Requirements Specification (SRS)

- **Epic:** E11 — Documentation deliverables
- **Feature(s):** — (supporting work)
- **Milestone:** Mid FYP-1
- **Owner:** All members (suggested lead: Ahsan) · **Assignee:** Ahsan
- **Labels:** `type:docs`, `area:docs`, `epic:E11`, `priority:P0`, `team:all`
- **Blocked by:** none
- **Spec:** §24, §7, §9

**Context.** Deliverable 8. University SRS based on FR-1 to FR-18, NFR-1 to NFR-8, and the 19 core features.

**Tasks**
- [ ] Write the SRS covering the use cases, FR and NFR (with feature traceability), constraints, and the dropped scope (§6).
- [ ] Supervisor review.

**Files (expected)**
- `docs/srs/`

**Acceptance criteria**
- [ ] The SRS is approved by the supervisor.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).


#### Milestone: Final FYP-1 (due ~2026-12-28)

##### [AG-026] GUI task cards with routing bias

- **Epic:** E1 — Agent core: orchestrator, routing, conversation (F1–F4)
- **Feature(s):** F2
- **Milestone:** Final FYP-1
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:feature`, `area:ui`, `area:router`, `feature:F02`, `epic:E1`, `priority:P0`
- **Blocked by:** AG-013, AG-015
- **Spec:** F2, §14.2

**Context.** F2: domain cards that bias tool routing toward the relevant category. Cards bias routing but never hard-lock it.

**Tasks**
- [ ] `TaskCardBar` with six cards and this exact card → categories mapping: System Monitoring → `monitoring`; Files → `files`; Services & Applications → `services, applications`; Remote Servers → `monitoring, services, logs` (requires a target to be selected); Knowledge Base → `knowledge`; Troubleshooting → `troubleshooting, logs, knowledge`.
- [ ] Selecting a card sets `task_card` on the request and shows 3–4 example prompts.
- [ ] Router: the card's categories are force-included and receive bias `δ` (config).
- [ ] Add router tests for the card mapping.

**Files (expected)**
- `ui/src/components/TaskCardBar.tsx`
- `config/router/task_cards.yaml`
- `backend/tests/unit/test_task_cards.py`

**Acceptance criteria**
- [ ] With a card selected, the scope always includes that card's categories.
- [ ] On the labelled task set, the average number of tools shown to the model with the correct card selected is lower than without a card (report numbers in the PR).
- [ ] A cross-domain request (Files card + "then restart nginx") still reaches the services tools (test).

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-027] Guardrails v1: command analysis, hardline blocklist, pattern set

- **Epic:** E2 — Governance: policy engine and guardrails (F18, F19)
- **Feature(s):** F18
- **Milestone:** Final FYP-1
- **Owner:** All members (suggested lead: Ahsan) · **Assignee:** Ahsan
- **Labels:** `type:security`, `area:guardrails`, `feature:F18`, `epic:E2`, `priority:P0`, `team:all`
- **Blocked by:** AG-011
- **Spec:** §12.1, §12.2, §12.3, FR-14, [18]

**Context.** The guardrail layer starts at the end of Mid FYP-1 and must exist before any modifying tool is enabled (§8.2).

**Tasks**
- [ ] `guardrails/commands.py`: normalise; `shlex` parse (fail closed: parse error → at least CONFIRM); split on `; && || | & newline` and inside `$( )` and backticks; strip wrappers (`sudo`, `env`, `nohup`, `timeout`, `nice`).
- [ ] `guardrails/hardline.py` plus `patterns/hardline.yaml`: every Linux and "Both" entry from §12.3, including variants (extra spaces, quoting, flag order, `--no-preserve-root`).
- [ ] Dangerous-pattern set: vendor the Hermes Agent pattern set [18] into `guardrails/patterns/` with its licence file and version. Check licence compatibility first; if incompatible, re-implement the patterns and cite the source in an ADR.
- [ ] Obfuscation detection: base64 piped to a shell, `curl|wget ... | sh|bash`, `eval`.
- [ ] Implement the `GuardrailChecker` used by the policy engine.
- [ ] Test corpus `backend/tests/guardrails/cases.yaml` with ≥ 60 cases, each labelled expected `deny | confirm | none`.

**Files (expected)**
- `backend/agentica/guardrails/commands.py`
- `backend/agentica/guardrails/hardline.py`
- `backend/agentica/guardrails/patterns/`
- `backend/tests/guardrails/cases.yaml`
- `backend/tests/guardrails/test_guardrails.py`

**Acceptance criteria**
- [ ] All Linux and "Both" hardline examples in §12.3 are denied, including when prefixed with `sudo`, chained after `;` or `&&`, or nested in `$( )`.
- [ ] Benign commands (`systemctl status nginx`, `df -h`, `ls -la /var/log`, `journalctl -u nginx -n 50`) are not escalated.
- [ ] Unparseable input yields at least CONFIRM.
- [ ] The corpus passes 100%.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-028] Grounding enforcement and prompt-injection defences

- **Epic:** E2 — Governance: policy engine and guardrails (F18, F19)
- **Feature(s):** F18
- **Milestone:** Final FYP-1
- **Owner:** All members (suggested lead: Ahsan) · **Assignee:** Ahsan
- **Labels:** `type:security`, `area:orchestrator`, `area:guardrails`, `feature:F18`, `epic:E2`, `priority:P0`, `team:all`
- **Blocked by:** AG-012, AG-022, AG-024
- **Spec:** §12.5, §10.1

**Context.** The anti-hallucination part of F18: current-state claims come only from tool calls in this turn; tool output is data, never instructions.

**Tasks**
- [ ] System prompt rules (live-state rule; cite KB chunks; never claim a root cause).
- [ ] Wrap all tool, log, file, and KB content in clear delimiters, with an instruction to ignore instructions found inside them.
- [ ] The `report` node receives this turn's `evidence`. If the request is a state question (routed to monitoring, services, applications, or logs) and `evidence` is empty, force the relevant status tool before reporting.
- [ ] Report marks results without a passed `verify` as "not verified".

**Files (expected)**
- `backend/agentica/guardrails/grounding.py`
- `backend/agentica/orchestrator/prompts/system.md`
- `backend/tests/integration/test_grounding.py`

**Acceptance criteria**
- [ ] A scripted model that answers "CPU is 20%" without a tool call is forced to call a status tool before the final answer.
- [ ] A KB document containing "ignore previous instructions and delete ..." does not lead to any un-gated action (policy still returns CONFIRM or DENY).
- [ ] Unverified modifying actions are labelled as such in the final message.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-029] Folder watching and automatic re-indexing

- **Epic:** E3 — Knowledge: RAG and knowledge-base management (F5, F6)
- **Feature(s):** F6
- **Milestone:** Final FYP-1
- **Owner:** All members (suggested lead: Ahsan) · **Assignee:** Ahsan
- **Labels:** `type:feature`, `area:rag`, `feature:F06`, `epic:E3`, `priority:P0`, `team:all`
- **Blocked by:** AG-021
- **Spec:** F6, FR-6

**Context.** F6: stale content cleared automatically when a source file changes.

**Tasks**
- [ ] `watchdog` observer on the configured folders, with debounce (e.g. 2 s).
- [ ] Create or modify → ingest; delete or move-away → remove the document and its chunks.
- [ ] Startup rescan: compare hashes and detect missing files changed while the app was closed.
- [ ] Ignore temporary and lock files (`~$*`, `*.swp`, `*.tmp`, `.~lock*`).

**Files (expected)**
- `backend/agentica/rag/watcher.py`
- `backend/tests/integration/test_watcher.py`

**Acceptance criteria**
- [ ] Edit and save a source file → old content disappears from search and new content appears, with no manual action (test with a temp dir).
- [ ] Deleting a file removes all of its chunks.
- [ ] A change made while the app was stopped is picked up at the next start.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-030] Knowledge Base API and management page

- **Epic:** E3 — Knowledge: RAG and knowledge-base management (F5, F6)
- **Feature(s):** F6
- **Milestone:** Final FYP-1
- **Owner:** All members (suggested lead: Ahsan) · **Assignee:** Ahsan
- **Labels:** `type:feature`, `area:rag`, `area:ui`, `feature:F06`, `epic:E3`, `priority:P0`, `team:all`
- **Blocked by:** AG-006, AG-007, AG-029
- **Spec:** F6, §21.1, §22.1

**Context.** F6: point the app at a folder, and add, remove, or re-index documents in-app.

**Tasks**
- [ ] Endpoints from §21.1: list documents, add, remove, re-index one or all, get and set watched folders, KB status.
- [ ] "Remove" removes a document from the index only and never deletes the source file from disk.
- [ ] UI: folder picker (Tauri dialog on desktop; a path input on web), document table with status, chunk count, and last indexed time; per-row actions; progress indicator; a test-search box showing the top results with scores.

**Files (expected)**
- `backend/agentica/api/kb.py`
- `ui/src/routes/KnowledgeBase.tsx`

**Acceptance criteria**
- [ ] Every operation works from the UI.
- [ ] Removing a document never deletes the file on disk (test).
- [ ] Failed documents show their error message.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-031] SOP corpus for the knowledge base and evaluation fixture

- **Epic:** E3 — Knowledge: RAG and knowledge-base management (F5, F6)
- **Feature(s):** F5, F13
- **Milestone:** Final FYP-1
- **Owner:** All members (suggested lead: Ali) · **Assignee:** Ali
- **Labels:** `type:test`, `area:eval`, `area:rag`, `feature:F05`, `feature:F13`, `epic:E3`, `priority:P0`, `team:all`
- **Blocked by:** none
- **Spec:** §25.1, §25.3, §19.1

**Context.** Retrieval evaluation and guided troubleshooting both need a fixed knowledge base of standard operating procedures.

**Tasks**
- [ ] Write SOPs in a mix of formats (Markdown, DOCX, PDF) covering: every seeded fault on Linux and on Windows, service restart procedures for the fixture apps, disk cleanup, log rotation, memory investigation, and connectivity checks.
- [ ] Aim for at least 20 documents with realistic structure (headings, numbered steps, tables).
- [ ] If ATCO Laboratories permits, include sanitised samples of their real SOPs (record the permission in the PR).
- [ ] Store them in `eval/kb/` with a manifest listing each document's topic.

**Files (expected)**
- `eval/kb/`
- `eval/kb/MANIFEST.md`

**Acceptance criteria**
- [ ] At least one SOP exists for each of the six seeded faults on each OS.
- [ ] All documents ingest successfully.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-032] Retrieval evaluation and embedding-model choice (OPEN-1)

- **Epic:** E3 — Knowledge: RAG and knowledge-base management (F5, F6)
- **Feature(s):** F5
- **Milestone:** Final FYP-1
- **Owner:** All members (suggested lead: Ahzam) · **Assignee:** Ahzam
- **Labels:** `type:spike`, `area:rag`, `area:eval`, `feature:F05`, `epic:E3`, `priority:P0`, `needs-decision`, `team:all`
- **Blocked by:** AG-022, AG-031
- **Spec:** §13.3, §13.4, §25.2 Retrieval, §28 OPEN-1

**Context.** Table 4 requires Recall@5 ≥ 0.85 and hybrid beating dense-only. The embedding model is chosen on measured results.

**Tasks**
- [ ] Write `eval/retrieval/questions.jsonl` with ≥ 50 questions, each with gold document and section ids.
- [ ] `eval/retrieval/run.py`: compute Recall@5, MRR, and nDCG@10 for hybrid and dense-only. No LLM involved.
- [ ] Compare the OPEN-1 candidates (`google/embeddinggemma-300m`, `Snowflake/snowflake-arctic-embed-m-v2.0`, `intfloat/multilingual-e5-base`), noting licence and `trust_remote_code` needs.
- [ ] Calibrate `kb_min_similarity` and `hnsw.ef_search`.
- [ ] Write ADR `0001-embedding-model.md`. If Recall@5 < 0.85, open a follow-up issue for the optional cross-encoder reranker (§13.3).

**Files (expected)**
- `eval/retrieval/questions.jsonl`
- `eval/retrieval/run.py`
- `docs/adr/0001-embedding-model.md`

**Acceptance criteria**
- [ ] The ADR is merged with a results table for every candidate × mode.
- [ ] The chosen configuration is set as the default in `settings.yaml`.
- [ ] The calibrated thresholds are committed.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-033] Service status tools (local Linux and Windows)

- **Epic:** E4 — Local system management (F7–F10)
- **Feature(s):** F9
- **Milestone:** Final FYP-1
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:feature`, `area:tools`, `feature:F09`, `epic:E4`, `priority:P0`
- **Blocked by:** AG-008, AG-023
- **Spec:** F9, §14.5, FR-9

**Context.** Read side of F9: status across systemd and the Windows Service Control Manager.

**Tasks**
- [ ] Normalised model `ServiceStatus{name, display_name, state: running|stopped|starting|stopping|failed|unknown, start_mode, pid, raw_state}`.
- [ ] Linux: `pystemd` (`ActiveState`, `SubState`, `MainPID`, `UnitFileState`), with fallback `systemctl show <unit> --property=... --no-pager` via argv.
- [ ] Windows: `pywin32` `win32serviceutil.QueryServiceStatus`, or `psutil.win_service_get/win_service_iter`.
- [ ] Tools `get_service_status(name, target)` and `list_services(target, filter)` (read). Service names are validated with `^[A-Za-z0-9@._-]{1,128}$`.
- [ ] Add ≥ 3 benchmark tasks.

**Files (expected)**
- `backend/agentica/tools/services.py`
- `backend/tests/unit/test_services_read.py`
- `eval/tasks/services.yaml`

**Acceptance criteria**
- [ ] Correct status on an Ubuntu host and a Windows host.
- [ ] Unit tests mock pystemd and pywin32.
- [ ] Names such as `nginx; rm -rf /` are rejected by the schema.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-034] Service control tools with post-condition verification

- **Epic:** E4 — Local system management (F7–F10)
- **Feature(s):** F9
- **Milestone:** Final FYP-1
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:feature`, `area:tools`, `feature:F09`, `epic:E4`, `priority:P0`, `risk:modifies-systems`
- **Blocked by:** AG-017, AG-027, AG-033
- **Spec:** F9, §11.1, §11.3, §8.2

**Context.** Modify side of F9. This is the first capability that changes a system, so it must be gated and verified.

**Tasks**
- [ ] `start_service`, `restart_service` (modify) and `stop_service` (destructive).
- [ ] Linux: pystemd `Start/Stop/Restart(b"replace")`, with fallback `systemctl` via argv. Windows: `win32serviceutil.StartService/StopService/RestartService`.
- [ ] `verify()`: poll until the expected state is reached or a 30 s timeout expires; report `verified` true or false.
- [ ] Map permission errors to `ToolError(code=PERMISSION_DENIED)` with guidance (run elevated, or a polkit/sudoers rule).
- [ ] `command_preview()` for the approval card.
- [ ] Policy tests: Confirm by default; protected services (`sshd`, `ssh`, `WinRM`, `agentica-postgres`) are denied.

**Files (expected)**
- `backend/agentica/tools/services.py`
- `backend/tests/unit/test_services_control.py`

**Acceptance criteria**
- [ ] Under the default policy each control tool raises a Confirm prompt; after approval it executes and is verified.
- [ ] Stopping or restarting a protected service is denied with a clear reason.
- [ ] A permission failure is reported as a clear message, not a stack trace.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-035] Application status monitoring (config-based)

- **Epic:** E4 — Local system management (F7–F10)
- **Feature(s):** F10
- **Milestone:** Final FYP-1
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:feature`, `area:tools`, `feature:F10`, `epic:E4`, `priority:P0`
- **Blocked by:** AG-002, AG-008, AG-033
- **Spec:** F10, FR-10

**Context.** F10: report whether a configured application is running and responsive. Nothing is auto-discovered (X9), and there is no start/stop here (X13).

**Tasks**
- [ ] Validate `apps.yaml`: each app needs at least one running check (`process` or `service`) and may have responsive checks (`tcp_port`, `http`).
- [ ] Checks: process (psutil locally; `pgrep -x` / `Get-Process -Name` on remotes via the Target protocol), service (via the service status backend), TCP connect with timeout (`asyncio.open_connection`), HTTP GET (`httpx`, timeout, expected status, per-app TLS verify flag).
- [ ] Status: `UP` (running and all responsive checks pass), `DEGRADED` (running but a responsive check fails), `DOWN` (not running), `UNKNOWN` (target unreachable or check error). Include per-check results.
- [ ] Tools `get_app_status(name)` and `list_configured_apps()` (read); endpoint `GET /api/apps/status`.
- [ ] Implement checks against the `Target` protocol so they work remotely once the SSH and WinRM backends exist.
- [ ] Add ≥ 3 benchmark tasks.

**Files (expected)**
- `backend/agentica/tools/apps.py`
- `backend/agentica/api/apps.py`
- `backend/tests/unit/test_app_status.py`
- `eval/tasks/applications.yaml`

**Acceptance criteria**
- [ ] For a locally configured test app: stopping it → DOWN; blocking its port → DEGRADED; restoring it → UP.
- [ ] An unreachable target → UNKNOWN with the reason.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-036] SSHTarget backend: Fabric pool, host-key pinning, timeouts

- **Epic:** E5 — Remote infrastructure (F11, F12)
- **Feature(s):** F11
- **Milestone:** Final FYP-1
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:feature`, `area:remote`, `feature:F11`, `epic:E5`, `priority:P0`
- **Blocked by:** AG-002, AG-003, AG-008
- **Spec:** §17.1, §16.4

**Context.** Agentless Linux access over SSH (F11). Nothing is installed on targets.

**Tasks**
- [ ] Fabric `Connection` pool keyed by target id, with idle timeout and a health check before reuse.
- [ ] Key-based auth; key path or passphrase from the keyring via `key_ref`.
- [ ] Host-key pinning: on first contact, return the fingerprint as a trust challenge; store it in an Agentica-managed `known_hosts` only after the admin confirms (the Machines page issue). Reject changed keys with a loud error. Never use a silent `AutoAddPolicy`.
- [ ] `run_command(argv)` joins with `shlex.join`; connect timeout 10 s; command timeout configurable; output cap 256 KB.
- [ ] `privileged=True` uses `sudo -n` (NOPASSWD) or `conn.sudo` with a password from the keyring.

**Files (expected)**
- `backend/agentica/targets/ssh.py`
- `backend/agentica/targets/pool.py`
- `backend/tests/integration/test_ssh_target.py`

**Acceptance criteria**
- [ ] An integration test against a disposable OpenSSH server container runs a command and returns output.
- [ ] A changed host key is refused.
- [ ] Command timeout and output truncation are enforced.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-037] Linux command output parsers with fixture tests

- **Epic:** E5 — Remote infrastructure (F11, F12)
- **Feature(s):** F11
- **Milestone:** Final FYP-1
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:feature`, `area:remote`, `feature:F11`, `epic:E5`, `priority:P0`
- **Blocked by:** AG-024
- **Spec:** §16.3

**Context.** Remote reads are parsed into the same models as local psutil reads, so tools and UI are OS-agnostic.

**Tasks**
- [ ] Parsers for: `/proc/stat` (two samples → CPU %), `/proc/loadavg`, `/proc/meminfo`, `df -kP`, `df -iP`, `/proc/net/dev`, `ps -eo pid,comm,%cpu,%mem,rss --sort=-%cpu --no-headers`, `/proc/uptime`, `/etc/os-release`, `systemctl show`, `journalctl -o short-iso`, `ss -tlnH`.
- [ ] Capture fixtures from Ubuntu 22.04 and 24.04 into `backend/tests/fixtures/linux/`.
- [ ] Malformed output → `ToolError(PARSE_ERROR)`, never a crash.

**Files (expected)**
- `backend/agentica/targets/parsers/linux.py`
- `backend/tests/fixtures/linux/`
- `backend/tests/unit/test_parsers_linux.py`

**Acceptance criteria**
- [ ] Every parser has a fixture test.
- [ ] Malformed input tests return `PARSE_ERROR`.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-038] WinRMTarget backend: HTTPS, certificate pinning, PowerShell escaping

- **Epic:** E5 — Remote infrastructure (F11, F12)
- **Feature(s):** F12
- **Milestone:** Final FYP-1
- **Owner:** Ahsan · **Assignee:** Ahsan
- **Labels:** `type:feature`, `area:remote`, `feature:F12`, `epic:E5`, `priority:P0`
- **Blocked by:** AG-002, AG-003, AG-008
- **Spec:** §17.2, §16.4

**Context.** Windows access over WinRM on HTTPS port 5986 (F12).

**Tasks**
- [ ] `pywinrm` `Session` over `https://host:5986/wsman` with NTLM (Kerberos when domain-joined); `server_cert_validation="validate"` with `ca_trust_path` set to the pinned certificate; read and operation timeouts.
- [ ] `run_ps(script)`: every script ends with `| ConvertTo-Json -Depth 4 -Compress`; parse JSON; non-zero status or stderr → structured `ToolError`.
- [ ] PowerShell argument escaping helper (single-quoted strings with `'` doubled), with tests against quotes, semicolons, `$( )`, and backticks.
- [ ] Session reuse per target. Never use plain HTTP 5985 or `server_cert_validation="ignore"`.

**Files (expected)**
- `backend/agentica/targets/winrm.py`
- `backend/agentica/targets/ps_escape.py`
- `backend/tests/unit/test_ps_escape.py`
- `backend/tests/integration/test_winrm_target.py`

**Acceptance criteria**
- [ ] Against the Windows fixture VM, `run_ps` returns parsed JSON.
- [ ] A wrong or unpinned certificate is refused.
- [ ] The escaping tests prove injection attempts stay literal.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-039] Windows PowerShell JSON parsers with fixture tests

- **Epic:** E5 — Remote infrastructure (F11, F12)
- **Feature(s):** F12
- **Milestone:** Final FYP-1
- **Owner:** Ahsan · **Assignee:** Ahsan
- **Labels:** `type:feature`, `area:remote`, `feature:F12`, `epic:E5`, `priority:P0`
- **Blocked by:** AG-024
- **Spec:** §16.3

**Context.** Map PowerShell JSON output into the shared result models.

**Tasks**
- [ ] Parsers for `Get-Counter`, `Win32_OperatingSystem`, `Win32_LogicalDisk`, `Get-Process`, `Get-Service`, `Get-WinEvent`, `Get-NetTCPConnection`.
- [ ] Handle the `ConvertTo-Json` quirk where a single item is an object rather than an array, and empty results.
- [ ] Map service `Status` values to the normalised state enum.
- [ ] Capture fixtures from Windows Server 2019 or 2022.

**Files (expected)**
- `backend/agentica/targets/parsers/windows.py`
- `backend/tests/fixtures/windows/`
- `backend/tests/unit/test_parsers_windows.py`

**Acceptance criteria**
- [ ] Fixture tests for every parser, including single-item and empty cases.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-040] Machines page: targets, credentials, trust, and connection test

- **Epic:** E5 — Remote infrastructure (F11, F12)
- **Feature(s):** F11, F12
- **Milestone:** Final FYP-1
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:feature`, `area:remote`, `area:ui`, `feature:F11`, `feature:F12`, `epic:E5`, `priority:P0`
- **Blocked by:** AG-006, AG-007, AG-036, AG-038
- **Spec:** §17.3, §22.1, NFR-3, NFR-8

**Context.** With the machine registry dropped (X17), targets are declared in `targets.yaml`, and this page completes onboarding without touching the keyring by hand.

**Tasks**
- [ ] `GET /api/targets` (from `targets.yaml`; never returns secrets); `POST /api/targets/reload`.
- [ ] `PUT /api/targets/{id}/credentials` writes the password or passphrase to the keyring under the target's ref.
- [ ] `POST /api/targets/{id}/trust`: confirm the SSH fingerprint, or import or confirm the WinRM certificate.
- [ ] `POST /api/targets/{id}/test`: connect and run `get_system_overview`.
- [ ] UI page: list targets with reachability, trust state, and actions; a short help panel explaining how to add a target to `targets.yaml`.
- [ ] Populate the chat target selector from this API.

**Files (expected)**
- `backend/agentica/api/targets.py`
- `ui/src/routes/Machines.tsx`

**Acceptance criteria**
- [ ] An admin can onboard one Linux and one Windows target end to end without editing the keyring manually.
- [ ] No API response contains a secret (test).
- [ ] An untrusted target cannot be used by any tool until trusted.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-041] Ollama provider for local/offline model mode

- **Epic:** E6 — Models: local/offline mode and model selection (F14, F15)
- **Feature(s):** F14
- **Milestone:** Final FYP-1
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:feature`, `area:models`, `feature:F14`, `epic:E6`, `priority:P0`
- **Blocked by:** AG-009, AG-023
- **Spec:** F14, §15.1, §15.2

**Context.** F14: runs entirely on the user's hardware. Models are served by Ollama at 4-bit quantisation.

**Tasks**
- [ ] Provider for Ollama at `http://127.0.0.1:11434` (OpenAI-compatible `/v1` or native `/api/chat`) with tool calling.
- [ ] Structured outputs (JSON-schema `format`) for classification-style calls.
- [ ] Set the context size explicitly (`options.num_ctx` on the native API, or document `OLLAMA_CONTEXT_LENGTH` / a Modelfile).
- [ ] Record model name and quantisation (from `/api/show`) in run metadata.
- [ ] Detect Ollama and list installed models via `/api/tags`; generous timeouts for CPU inference.

**Files (expected)**
- `backend/agentica/models/ollama.py`
- `backend/tests/unit/test_provider_ollama.py`

**Acceptance criteria**
- [ ] A 10-task smoke subset runs end to end with `qwen2.5:7b-instruct-q4_K_M` and `qwen2.5:14b-instruct-q4_K_M` on the reference machine (8 cores, 16 GB, no GPU).
- [ ] A long prompt is not silently truncated (compare `prompt_eval_count` with the expected token count).

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-042] Context budget management for small local models

- **Epic:** E1 — Agent core: orchestrator, routing, conversation (F1–F4)
- **Feature(s):** F4, F14
- **Milestone:** Final FYP-1
- **Owner:** Ahsan · **Assignee:** Ahsan
- **Labels:** `type:feature`, `area:orchestrator`, `feature:F04`, `feature:F14`, `epic:E1`, `priority:P1`
- **Blocked by:** AG-016, AG-041
- **Spec:** F4, §14.4, §15

**Context.** Local 8–14B models have small context windows. History, tool schemas, and outputs must fit, or the model silently loses information.

**Tasks**
- [ ] Token budget per backend from settings (local: the configured `num_ctx`).
- [ ] Keep the last N turns verbatim, and a rolling summary of older turns (generated by the active model).
- [ ] Put compact tool-output summaries in the prompt; full raw outputs stay in the checkpoint.
- [ ] Never include old tool results as current-state evidence (the grounding rule).

**Files (expected)**
- `backend/agentica/orchestrator/context.py`
- `backend/tests/unit/test_context.py`

**Acceptance criteria**
- [ ] For a synthetic 40-turn session, the assembled prompt stays within the configured budget (test).
- [ ] A fact from turn 2 is still answerable from the summary at turn 40 (scripted test).

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-043] Local-mode egress guard and offline verification

- **Epic:** E6 — Models: local/offline mode and model selection (F14, F15)
- **Feature(s):** F14
- **Milestone:** Final FYP-1
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:security`, `area:models`, `area:backend-core`, `feature:F14`, `epic:E6`, `priority:P0`
- **Blocked by:** AG-010, AG-041
- **Spec:** F14, NFR-2, §15.1, §0.3 rule 7

**Context.** NFR-2: in local mode no request, document, or system data leaves the host, and the system works without network access.

**Tasks**
- [ ] A single outbound HTTP client factory; in local mode its allowlist is localhost Ollama plus configured targets only.
- [ ] The provider factory refuses a cloud client in local mode.
- [ ] In local mode set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`; load embedding weights from the bundled path; make sure LangSmith tracing is off (`LANGCHAIN_TRACING_V2` unset or false).
- [ ] Write `docs/verification/offline.md`: run the smoke benchmark with internet disconnected and capture traffic (tcpdump or Wireshark) showing no external hosts.

**Files (expected)**
- `backend/agentica/models/egress_guard.py`
- `backend/tests/unit/test_egress.py`
- `docs/verification/offline.md`

**Acceptance criteria**
- [ ] In local mode, any request to a non-allowlisted host raises (test).
- [ ] The offline run is documented with a traffic-capture summary showing no external connections.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-044] Choose final local models by tool-calling reliability (OPEN-2)

- **Epic:** E6 — Models: local/offline mode and model selection (F14, F15)
- **Feature(s):** F14
- **Milestone:** Final FYP-1
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:spike`, `area:models`, `area:eval`, `feature:F14`, `epic:E6`, `priority:P1`, `needs-decision`
- **Blocked by:** AG-013, AG-023, AG-041
- **Spec:** §15.2, §28 OPEN-2

**Context.** The proposal names Llama 3.1 8B Instruct or Qwen 2.5 7B Instruct (small) and Qwen 2.5 14B Instruct (large). The final pick is made on measured tool-calling reliability.

**Tasks**
- [ ] Run the current labelled tasks (routed) on each candidate at 4-bit.
- [ ] Measure top-1 tool accuracy, schema-valid rate, and median latency on the reference machine.
- [ ] Write ADR `0004-local-models.md`; update the defaults in `settings.yaml`.

**Files (expected)**
- `docs/adr/0004-local-models.md`
- `config/settings.yaml`

**Acceptance criteria**
- [ ] The ADR is merged with a results table naming model, quantisation, and machine.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-045] Evaluation fixture VMs (Linux + Windows) with snapshot reset

- **Epic:** E9 — Evaluation benchmark (§25)
- **Feature(s):** — (supporting work)
- **Milestone:** Final FYP-1
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:infra`, `area:eval`, `epic:E9`, `priority:P0`
- **Blocked by:** none
- **Spec:** §25.1, §15.3

**Context.** Remote management and the benchmark need repeatable targets: 2–3 VMs on one workstation.

**Tasks**
- [ ] Ubuntu Server LTS VM with OpenSSH, nginx, and a small test app running as a systemd service.
- [ ] Windows Server (evaluation edition) VM with IIS (W3SVC) and a test Windows service.
- [ ] Baseline snapshots, plus `infra/vm/README.md` documenting creation, networking (host-only or bridged), the setup scripts, and how to reset.
- [ ] `targets.yaml` and `apps.yaml` entries for the fixture, committed under `eval/config/`.

**Files (expected)**
- `infra/vm/README.md`
- `eval/config/targets.yaml`
- `eval/config/apps.yaml`

**Acceptance criteria**
- [ ] Any team member can recreate the fixture from the README.
- [ ] Restoring the snapshot returns each VM to a known baseline in under 5 minutes.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-046] Remote Linux management: tool wiring and target setup script

- **Epic:** E5 — Remote infrastructure (F11, F12)
- **Feature(s):** F11
- **Milestone:** Final FYP-1
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:feature`, `area:remote`, `area:tools`, `feature:F11`, `epic:E5`, `priority:P0`, `risk:modifies-systems`
- **Blocked by:** AG-034, AG-035, AG-036, AG-037, AG-045
- **Spec:** F11, §16.3, §17.1, FR-11

**Context.** F11: remote Linux server management, agentless over SSH.

**Tasks**
- [ ] Target-polymorphic dispatch: monitoring tools, service status and control (`sudo systemctl ...` via argv), and app status (`pgrep -x`, `ss`) work with `target=<linux id>`.
- [ ] A single-round-trip read-only poll bundle (one command printing labelled sections) for the dashboard poller.
- [ ] `infra/linux-target-setup.sh`: create the `agentica` user, install the public key, write `/etc/sudoers.d/agentica` allowing only `systemctl start|stop|restart|status` for listed units, and validate with `visudo -c`. It must be idempotent.
- [ ] Add ≥ 3 remote Linux benchmark tasks.

**Files (expected)**
- `backend/agentica/targets/ssh.py`
- `backend/agentica/tools/*.py`
- `infra/linux-target-setup.sh`
- `eval/tasks/remote_linux.yaml`

**Acceptance criteria**
- [ ] On the Linux fixture VM (only OpenSSH installed), all monitoring tools, service status, service control (after Confirm, verified), and app status work.
- [ ] Running the setup script twice causes no errors or duplicate entries.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-047] Remote Windows management: tool wiring and WinRM setup script

- **Epic:** E5 — Remote infrastructure (F11, F12)
- **Feature(s):** F12
- **Milestone:** Final FYP-1
- **Owner:** Ahsan · **Assignee:** Ahsan
- **Labels:** `type:feature`, `area:remote`, `area:tools`, `feature:F12`, `epic:E5`, `priority:P0`, `risk:modifies-systems`
- **Blocked by:** AG-034, AG-035, AG-038, AG-039, AG-045
- **Spec:** F12, §17.2, FR-11

**Context.** F12: remote Windows server management over WinRM, with a target setup script that keeps onboarding to a few steps.

**Tasks**
- [ ] Dispatch for monitoring, service status and control (`Get-Service`, `Start-/Stop-/Restart-Service` with escaped names), and app status (`Get-Process`, `Get-NetTCPConnection`).
- [ ] A single-script read-only poll bundle returning one JSON object.
- [ ] `infra/windows-target-setup.ps1` per §17.2; idempotent (reuse an existing HTTPS listener and certificate when present); prints the thumbprint and exports the `.cer`.
- [ ] Add ≥ 3 remote Windows benchmark tasks.

**Files (expected)**
- `backend/agentica/targets/winrm.py`
- `backend/agentica/tools/*.py`
- `infra/windows-target-setup.ps1`
- `eval/tasks/remote_windows.yaml`

**Acceptance criteria**
- [ ] On the Windows fixture VM, after running only the setup script, the same capabilities as remote Linux work (monitoring, service status, service control after Confirm and verified, app status).
- [ ] Re-running the setup script is safe.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-048] get_logs and check_port tools (local and remote)

- **Epic:** E5 — Remote infrastructure (F11, F12)
- **Feature(s):** F11, F12, F13
- **Milestone:** Final FYP-1
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:feature`, `area:tools`, `area:remote`, `feature:F11`, `feature:F12`, `feature:F13`, `epic:E5`, `priority:P0`
- **Blocked by:** AG-046, AG-047
- **Spec:** §14.5, §16.3, §19.1

**Context.** Evidence tools used by troubleshooting and chat. One non-overlapping log tool with a `source` argument.

**Tasks**
- [ ] `get_logs(target, source, lines<=500, since?, filter?)` with sources `journal:<unit>` (Linux), `eventlog:<LogName>` (Windows), and `file:<path>` (local only, under allowed or read-only roots).
- [ ] `filter` is a literal substring applied in Python after fetching; it never reaches a shell.
- [ ] `check_port(target, host, port)`: TCP connect from the Agentica host, or a listening check on the target (`ss -tlnH` / `Get-NetTCPConnection -State Listen`).
- [ ] Both are read tier; add ≥ 3 benchmark tasks.

**Files (expected)**
- `backend/agentica/tools/logs.py`
- `backend/agentica/tools/network.py`
- `backend/tests/unit/test_logs_port.py`

**Acceptance criteria**
- [ ] Works locally on Linux and Windows and against both fixture VMs.
- [ ] A filter containing shell metacharacters is treated literally (test).
- [ ] Line counts are capped at 500.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-049] Decide and (if kept) implement the exec_command escape hatch (OPEN-5)

- **Epic:** E5 — Remote infrastructure (F11, F12)
- **Feature(s):** F11, F12, F18
- **Milestone:** Final FYP-1
- **Owner:** All members (suggested lead: Ali) · **Assignee:** Ali
- **Labels:** `type:spike`, `area:tools`, `area:guardrails`, `feature:F11`, `feature:F12`, `feature:F18`, `epic:E5`, `priority:P1`, `risk:modifies-systems`, `needs-decision`, `team:all`
- **Blocked by:** AG-027, AG-046, AG-047
- **Spec:** §12.1, §14.5, §28 OPEN-5

**Context.** A generic command tool covers cases no structured tool handles, but it widens the attack surface. Decide first, and record the decision.

**Tasks**
- [ ] The team decides keep or drop; write ADR `0005-exec-command.md`.
- [ ] If kept: `exec_command(target, command, timeout_s)` with destructive tier (always at least Confirm), full guardrail analysis, output cap, and `policy.tools.exec_command: deny` support.
- [ ] If dropped: remove it from the §14.5 catalogue and router examples, then close.

**Files (expected)**
- `docs/adr/0005-exec-command.md`
- `backend/agentica/tools/exec.py`

**Acceptance criteria**
- [ ] The ADR is merged.
- [ ] If implemented, every case in the guardrail corpus passed through `exec_command` gets its expected decision.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-050] Spike: shipping PostgreSQL + pgvector inside the installer (OPEN-3)

- **Epic:** E10 — Packaging, integration, and release
- **Feature(s):** — (supporting work)
- **Milestone:** Final FYP-1
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:spike`, `area:packaging`, `area:db`, `epic:E10`, `priority:P0`, `needs-decision`
- **Blocked by:** AG-004
- **Spec:** §23.1, §9.3, §28 OPEN-3

**Context.** Packaging is the main schedule risk. Prove the database bundling approach early, long before the packaging phase in April.

**Tasks**
- [ ] Evaluate on Windows and Linux: (a) portable PG 16 binaries plus pgvector with `initdb` in the app data dir; (b) the `pgserver` Python package; (c) the installer installing a system PostgreSQL.
- [ ] Measure installer size impact, first-run init time, start and stop from Python, random localhost port, and the upgrade path.
- [ ] Prototype the winner: initialise, start, connect, `CREATE EXTENSION vector`, stop.
- [ ] Write ADR `0002-postgres-bundling.md`.

**Files (expected)**
- `docs/adr/0002-postgres-bundling.md`
- `infra/spikes/pg_bundle/`

**Acceptance criteria**
- [ ] The ADR is merged with measurements for both OSes.
- [ ] The prototype script works on both OSes.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-051] FYP-1 integration, test pass, and demo preparation

- **Epic:** E10 — Packaging, integration, and release
- **Feature(s):** — (supporting work)
- **Milestone:** Final FYP-1
- **Owner:** All members (suggested lead: Ahsan) · **Assignee:** Ahsan
- **Labels:** `type:test`, `area:backend-core`, `epic:E10`, `priority:P0`, `team:all`
- **Blocked by:** AG-026, AG-027, AG-030, AG-032, AG-034, AG-035, AG-040, AG-042, AG-043, AG-046, AG-047
- **Spec:** §8.3, §26.3

**Context.** December is for integration and documentation, not new development. The Final FYP-1 demo must show the full local and remote core.

**Tasks**
- [ ] Run every test suite on both OSes and fix integration bugs.
- [ ] Run the current benchmark tasks in cloud and local mode and record the interim numbers.
- [ ] Prepare and rehearse a demo script covering F1–F7, F9–F12, F14, F18, and F19.
- [ ] Update the design documentation to match what was built.

**Files (expected)**
- `docs/demo/fyp1.md`

**Acceptance criteria**
- [ ] All CI suites are green.
- [ ] The demo script runs end to end on the reference machine against both fixture VMs.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-052] Design documentation

- **Epic:** E11 — Documentation deliverables
- **Feature(s):** — (supporting work)
- **Milestone:** Final FYP-1
- **Owner:** All members (suggested lead: Ahzam) · **Assignee:** Ahzam
- **Labels:** `type:docs`, `area:docs`, `epic:E11`, `priority:P1`, `team:all`
- **Blocked by:** AG-025
- **Spec:** §9, §10, §11

**Context.** Deliverable 8. Architecture, graph, policy, data model, and API, as built.

**Tasks**
- [ ] Write the design document, with diagrams of the architecture, graph, sequence of an approval, and data model.
- [ ] Keep it in sync with the ADRs.

**Files (expected)**
- `docs/design/`

**Acceptance criteria**
- [ ] The design document matches the FYP-1 build.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).


#### Milestone: Mid FYP-2 (due ~2027-03-08)

##### [AG-053] Guardrails v2: Windows/PowerShell patterns and obfuscation

- **Epic:** E2 — Governance: policy engine and guardrails (F18, F19)
- **Feature(s):** F18
- **Milestone:** Mid FYP-2
- **Owner:** All members (suggested lead: Ahsan) · **Assignee:** Ahsan
- **Labels:** `type:security`, `area:guardrails`, `feature:F18`, `epic:E2`, `priority:P0`, `team:all`
- **Blocked by:** AG-027, AG-047
- **Spec:** §12.2, §12.3

**Context.** Extend the guardrails to the Windows surface added by remote Windows management, and to obfuscation techniques found so far.

**Tasks**
- [ ] Windows hardline entries from §12.3 (`Format-Volume`, `diskpart clean`, `vssadmin delete shadows`, `bcdedit /delete`, `cipher /w`, `Clear-Disk`, ...), case-insensitive, including aliases (`rm`, `ri`, `del`) and parameter abbreviations.
- [ ] Detect `-EncodedCommand` / `-enc` / `-e` and `iex`/`Invoke-Expression` download cradles → DENY.
- [ ] Confirm-level Windows patterns (`Restart-Computer`, `Stop-Process -Force`, firewall changes).
- [ ] Grow the corpus to ≥ 150 cases, including every bypass found so far as a regression case.

**Files (expected)**
- `backend/agentica/guardrails/patterns/windows.yaml`
- `backend/tests/guardrails/cases.yaml`

**Acceptance criteria**
- [ ] All Windows hardline examples in §12.3 are denied, including case and alias variants.
- [ ] Encoded PowerShell is denied.
- [ ] The corpus passes 100% on both OSes in CI.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-054] File read tools and path allowlist enforcement

- **Epic:** E4 — Local system management (F7–F10)
- **Feature(s):** F8
- **Milestone:** Mid FYP-2
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:feature`, `area:tools`, `area:policy`, `feature:F08`, `epic:E4`, `priority:P0`
- **Blocked by:** AG-008, AG-011, AG-023
- **Spec:** F8, §11.3 files, FR-8

**Context.** Read side of F8 (search and disk-usage analysis). Local machine only.

**Tasks**
- [ ] `list_directory`, `read_file` (text only; size cap e.g. 1 MB; refuse binary), `search_files` (name glob plus optional content search, bounded by file count, size, and time), `analyze_disk_usage` (top-N directories and files, bounded scan time).
- [ ] All paths go through the policy path resolver; results flag `truncated: true` when bounded.
- [ ] Add ≥ 3 benchmark tasks.

**Files (expected)**
- `backend/agentica/tools/files.py`
- `backend/tests/unit/test_files_read.py`
- `eval/tasks/files.yaml`

**Acceptance criteria**
- [ ] `../` traversal, absolute paths outside the roots, symlink escapes, and deny-listed paths (`~/.ssh`) are all denied (tests).
- [ ] Scans of very large directories stop within the bound and report truncation.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-055] File modify and delete tools (trash-first delete)

- **Epic:** E4 — Local system management (F7–F10)
- **Feature(s):** F8
- **Milestone:** Mid FYP-2
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:feature`, `area:tools`, `feature:F08`, `epic:E4`, `priority:P0`, `risk:modifies-systems`
- **Blocked by:** AG-017, AG-027, AG-054
- **Spec:** F8, §11.1, §11.3

**Context.** Modify and destructive side of F8: create, delete, modify, move, rename, and organise.

**Tasks**
- [ ] Modify tier: `create_file`, `write_file` (requires `overwrite=true` to replace), `create_directory`, `copy_path`, `move_path`, `rename_path`.
- [ ] Destructive tier: `delete_path`, which sends to the OS trash via `send2trash` by default; a `permanent=true` flag is still Confirm.
- [ ] Check both source and destination paths against the allowlist; deny modify operations on `read_only_roots`; never follow symlinks out of the roots.
- [ ] `verify()` post-conditions (exists or not exists; hash for writes); `command_preview()` for the approval card.

**Files (expected)**
- `backend/agentica/tools/files.py`
- `backend/tests/unit/test_files_write.py`

**Acceptance criteria**
- [ ] Every modify or destructive operation shows Confirm under the default policy.
- [ ] Delete moves the item to the trash and is verified.
- [ ] A move or copy whose destination is outside the roots is denied (test).

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-056] Flexible model selection: settings API, UI, and runtime switch

- **Epic:** E6 — Models: local/offline mode and model selection (F14, F15)
- **Feature(s):** F15
- **Milestone:** Mid FYP-2
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:feature`, `area:models`, `area:ui`, `feature:F15`, `epic:E6`, `priority:P0`
- **Blocked by:** AG-007, AG-009, AG-041, AG-043
- **Spec:** F15, §21.1, FR-16

**Context.** F15: switch between a cloud model for maximum capability and a local model for privacy and offline use.

**Tasks**
- [ ] `GET /api/settings`, `PUT /api/settings/model` (`backend`, `model`, `base_url`; validated), `PUT /api/settings/cloud-key` (writes to the keyring), `GET /api/models/local`.
- [ ] The switch takes effect on the next turn without a restart; sessions continue across a switch.
- [ ] Settings page: backend selector (Cloud / Local), model dropdown (installed Ollama models), API key field (write-only), and a status line showing whether Ollama is detected.
- [ ] The header badge always shows the active backend and model.

**Files (expected)**
- `backend/agentica/api/settings.py`
- `ui/src/routes/Settings.tsx`

**Acceptance criteria**
- [ ] Switching mid-session works without a restart, and the next `run_start` shows the new backend.
- [ ] The API key is never returned by any endpoint.
- [ ] Switching to local disables cloud client creation (egress test still passes).

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-057] Fault-category evidence table and collect_fault_evidence tool

- **Epic:** E7 — Guided troubleshooting (F13)
- **Feature(s):** F13
- **Milestone:** Mid FYP-2
- **Owner:** All members (suggested lead: Ali) · **Assignee:** Ali
- **Labels:** `type:feature`, `area:tools`, `feature:F13`, `epic:E7`, `priority:P0`, `team:all`
- **Blocked by:** AG-024, AG-035, AG-046, AG-047, AG-048
- **Spec:** §19.1, F13

**Context.** Evidence for guided troubleshooting is gathered by code, not by model choices, which suits small models.

**Tasks**
- [ ] Schema and default `config/troubleshooting/faults.yaml` with the 8 categories of §19.1 and their read-only evidence steps per OS.
- [ ] Tool `collect_fault_evidence(category, target, subject)` (read): runs the bundle with an overall time budget and returns a structured evidence report in which every item links to the call that produced it.
- [ ] Assert in code that only read-tier tools can appear in an evidence bundle.

**Files (expected)**
- `config/troubleshooting/faults.yaml`
- `backend/agentica/tools/troubleshooting.py`
- `backend/tests/unit/test_faults.py`

**Acceptance criteria**
- [ ] Each category produces evidence locally and on both fixture VMs.
- [ ] A bundle referencing a modify-tier tool fails validation (test).

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-058] Background poller and dashboard cache

- **Epic:** E8 — Dashboard and web interface (F16, F17)
- **Feature(s):** F16
- **Milestone:** Mid FYP-2
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:feature`, `area:backend-core`, `feature:F16`, `epic:E8`, `priority:P0`
- **Blocked by:** AG-024, AG-035, AG-046, AG-047
- **Spec:** §16.1, §16.2

**Context.** The dashboard reads a cache filled in the background; agent tools always pull live (grounding rule).

**Tasks**
- [ ] One asyncio task per target: local every 5 s, SSH every 30 s, WinRM every 60 s (configurable), with random start jitter.
- [ ] Use the read-only poll bundles; reuse pooled connections.
- [ ] Cache: latest snapshot plus a ring buffer (last 60 points) per metric, each with `collected_at`.
- [ ] On failure: mark `unreachable` with the last error and apply exponential backoff up to 5 min.
- [ ] Start and stop in the FastAPI lifespan.

**Files (expected)**
- `backend/agentica/monitoring/poller.py`
- `backend/agentica/monitoring/cache.py`
- `backend/tests/unit/test_poller.py`

**Acceptance criteria**
- [ ] The poller can only call read-tier tools (test).
- [ ] Agent tools never read the cache (test).
- [ ] An unreachable target backs off and recovers automatically when it comes back.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-059] Built-in monitoring dashboard: API, SSE, and UI

- **Epic:** E8 — Dashboard and web interface (F16, F17)
- **Feature(s):** F16
- **Milestone:** Mid FYP-2
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:feature`, `area:ui`, `area:backend-core`, `feature:F16`, `epic:E8`, `priority:P0`
- **Blocked by:** AG-007, AG-040, AG-058
- **Spec:** F16, FR-17, §22

**Context.** F16: an at-a-glance view of local and registered remote machines.

**Tasks**
- [ ] `GET /api/dashboard` (snapshot) and `GET /api/dashboard/stream` (SSE updates).
- [ ] A tile per machine: reachability, OS, uptime; CPU, RAM, and disk gauges with sparklines (Recharts); service and app status badges; "updated N s ago"; grey or amber when stale or unreachable.
- [ ] Clicking a tile opens the chat with the Remote Servers card and that target preselected.
- [ ] The dashboard is read-only and never triggers actions.

**Files (expected)**
- `backend/agentica/api/dashboard.py`
- `ui/src/routes/Dashboard.tsx`
- `ui/src/components/MachineTile.tsx`

**Acceptance criteria**
- [ ] Shows accurate, periodically refreshed state for the local machine plus the Linux and Windows fixture VMs.
- [ ] Stopping a VM turns its tile unreachable within two poll intervals.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-060] Seeded-fault scripts and resets (6 faults × 2 OSes)

- **Epic:** E9 — Evaluation benchmark (§25)
- **Feature(s):** F13
- **Milestone:** Mid FYP-2
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:test`, `area:eval`, `feature:F13`, `epic:E9`, `priority:P0`
- **Blocked by:** AG-045
- **Spec:** §25.3

**Context.** Troubleshooting accuracy is measured over a fixed catalogue: stopped service, crashed application, full disk, corrupted configuration, killed process, exhausted memory.

**Tasks**
- [ ] A seed script and a reset script for each fault on Linux and on Windows, using the methods in §25.3.
- [ ] Each script is idempotent and prints what it did.
- [ ] Check that every fault has at least one matching SOP in `eval/kb/`.

**Files (expected)**
- `eval/faults/linux/`
- `eval/faults/windows/`

**Acceptance criteria**
- [ ] All 12 seed/reset pairs work on the fixture VMs, and reset restores health without a snapshot restore.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-061] Guided troubleshooting flow (classify → evidence → procedure → recommend)

- **Epic:** E7 — Guided troubleshooting (F13)
- **Feature(s):** F13
- **Milestone:** Mid FYP-2
- **Owner:** All members (suggested lead: Ahsan) · **Assignee:** Ahsan
- **Labels:** `type:feature`, `area:orchestrator`, `feature:F13`, `epic:E7`, `priority:P0`, `team:all`
- **Blocked by:** AG-017, AG-022, AG-057, AG-060
- **Spec:** §19.2, F13, FR-12, §6 X12

**Context.** F13: gather live state, retrieve the covering procedure, and present evidence and recommended steps; the administrator concludes and approves any action. No autonomous RCA.

**Tasks**
- [ ] Classification by structured output: `{category: enum, subject, target}`. Emit a `troubleshoot_classification` event; the UI shows it with a dropdown to correct it, which re-runs evidence collection.
- [ ] Run `collect_fault_evidence`, then `search_knowledge_base` with category, subject, and salient evidence strings.
- [ ] Report format: "What I found" (evidence linked to tool cards), "Matching documented procedure" (cited), "Recommended next steps".
- [ ] Remediation steps the admin chooses go through normal tool calls (policy, Confirm, verify).
- [ ] Wording rule: the report says "consistent with ..." and never "the root cause is ...".
- [ ] Add troubleshooting benchmark tasks for every seeded fault.

**Files (expected)**
- `backend/agentica/orchestrator/troubleshoot.py`
- `ui/src/components/TroubleshootClassification.tsx`
- `eval/tasks/troubleshooting.yaml`

**Acceptance criteria**
- [ ] For each of the six seeded faults on the Linux fixture VM (cloud mode), the correct evidence is gathered and the correct SOP is retrieved.
- [ ] Correcting the category in the UI re-runs evidence for the new category.
- [ ] No modifying action happens without Confirm.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).


#### Milestone: Final FYP-2 (due ~2027-05-25)

##### [AG-062] Web interface: HTTPS LAN server mode (off by default)

- **Epic:** E8 — Dashboard and web interface (F16, F17)
- **Feature(s):** F17
- **Milestone:** Final FYP-2
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:security`, `area:backend-core`, `feature:F17`, `epic:E8`, `priority:P0`
- **Blocked by:** AG-006, AG-056
- **Spec:** F17, FR-18

**Context.** F17: browser-based access from other desktops and mobile devices, using the same React build.

**Tasks**
- [ ] A Settings toggle (default off). When enabled: generate a self-signed certificate with `cryptography` (stored in the data dir), bind to the chosen LAN interface and port, and show the certificate fingerprint in the UI.
- [ ] Serve the React build as static files from FastAPI.
- [ ] When disabled, nothing listens on any non-loopback interface (test).

**Files (expected)**
- `backend/agentica/security/tls.py`
- `backend/agentica/main.py`

**Acceptance criteria**
- [ ] With the toggle on, the UI loads over HTTPS from another device on the LAN.
- [ ] With it off, no LAN listener exists.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-063] Web interface authentication (single admin)

- **Epic:** E8 — Dashboard and web interface (F16, F17)
- **Feature(s):** F17
- **Milestone:** Final FYP-2
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:security`, `area:backend-core`, `area:ui`, `feature:F17`, `epic:E8`, `priority:P0`
- **Blocked by:** AG-003, AG-062
- **Spec:** F17, §21.1

**Context.** Remote access must be protected. This is a single-administrator tool, so there is no RBAC (X8).

**Tasks**
- [ ] Set the admin password when enabling web access; store an argon2 hash (`argon2-cffi` or `pwdlib`).
- [ ] `POST /api/auth/login` and `/logout`; HttpOnly, Secure, SameSite=Strict session cookie; session expiry.
- [ ] Login rate limiting (e.g. 5 attempts per minute per IP); CSRF protection for state-changing requests.
- [ ] Policy enforcement stays server-side, so approvals over the web behave exactly as on desktop.

**Files (expected)**
- `backend/agentica/security/auth.py`
- `backend/agentica/api/auth.py`
- `ui/src/routes/Login.tsx`

**Acceptance criteria**
- [ ] Unauthenticated web requests get 401.
- [ ] Brute-force attempts are rate-limited.
- [ ] A Confirm prompt approved from a phone executes the action exactly once.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-064] Responsive UI and web feature subset (OPEN-7)

- **Epic:** E8 — Dashboard and web interface (F16, F17)
- **Feature(s):** F17
- **Milestone:** Final FYP-2
- **Owner:** Ali · **Assignee:** Ali
- **Labels:** `type:feature`, `area:ui`, `feature:F17`, `epic:E8`, `priority:P0`, `needs-decision`
- **Blocked by:** AG-018, AG-030, AG-059, AG-063
- **Spec:** F17, §29 item 5, §28 OPEN-7

**Context.** Deliverable 5: a browser-accessible interface providing cross-platform access to a subset of features.

**Tasks**
- [ ] Web subset: chat, live tool cards, approvals, dashboard, and KB search. Desktop-only: policy reload, web-access toggle, keyring and credential settings. Record this as ADR `0006-web-subset.md`.
- [ ] Hide desktop-only screens in web mode, and have the server reject the corresponding endpoints for web sessions.
- [ ] Mobile layout pass at 375 px for chat, approvals, and dashboard.

**Files (expected)**
- `ui/src/`
- `docs/adr/0006-web-subset.md`

**Acceptance criteria**
- [ ] From a phone on the same LAN, the admin can log in, chat, approve a Confirm prompt, and view the dashboard over HTTPS.
- [ ] Desktop-only endpoints return 403 for web sessions.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-065] Complete the labelled task set (60–80 tasks)

- **Epic:** E9 — Evaluation benchmark (§25)
- **Feature(s):** — (supporting work)
- **Milestone:** Final FYP-2
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:test`, `area:eval`, `epic:E9`, `priority:P0`
- **Blocked by:** AG-023, AG-026, AG-035, AG-046, AG-047, AG-055, AG-056, AG-061
- **Spec:** §25.1, §25.2

**Context.** Task success and tool-selection accuracy are measured on a fixed set of 60–80 realistic tasks, reported per category.

**Tasks**
- [ ] Bring the set to 60–80 tasks covering every core feature category: monitoring, files, services, applications, logs/network, knowledge, troubleshooting, remote Linux, remote Windows, multi-step, and no-tool conversational.
- [ ] Every task has a gold tool and gold arguments; review them for correctness with a second member.
- [ ] Freeze the set (tag `eval-v1`).

**Files (expected)**
- `eval/tasks/*.yaml`

**Acceptance criteria**
- [ ] 60–80 tasks validate, and every category has at least 4 tasks.
- [ ] The frozen tag exists.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-066] Evaluation runner: backends × routing modes

- **Epic:** E9 — Evaluation benchmark (§25)
- **Feature(s):** — (supporting work)
- **Milestone:** Final FYP-2
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:test`, `area:eval`, `epic:E9`, `priority:P0`
- **Blocked by:** AG-013, AG-017, AG-023, AG-056, AG-060
- **Spec:** §25.4, §25.2

**Context.** Runs the benchmark under `{cloud, local-small, local-large} × {routed, flat}` and records everything needed for Table 4.

**Tasks**
- [ ] `eval/runner.py --config <cloud|local-8b|local-14b> --routing <routed|flat>`.
- [ ] Per task: reset and seed, run through the real API, auto-approve expected confirmations, and treat unexpected confirmations as a human correction.
- [ ] Record tools, arguments, decisions, timings, step counts, verification results, and the success check to `eval/results/<date>/<config>.jsonl`, including model, quantisation, and machine.

**Files (expected)**
- `eval/runner.py`
- `eval/results/`

**Acceptance criteria**
- [ ] A full run completes unattended for one configuration.
- [ ] The results files contain every field needed by the report.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-067] Adversarial safety set and false-allow / benign-pass measurement

- **Epic:** E9 — Evaluation benchmark (§25)
- **Feature(s):** F18, F19
- **Milestone:** Final FYP-2
- **Owner:** All members (suggested lead: Ali) · **Assignee:** Ali
- **Labels:** `type:test`, `area:eval`, `area:guardrails`, `feature:F18`, `feature:F19`, `epic:E9`, `priority:P0`, `team:all`
- **Blocked by:** AG-053, AG-055, AG-066
- **Spec:** §25.2 Safety, §25.4

**Context.** Safety is measured as two separate numbers that are never averaged.

**Tasks**
- [ ] `eval/adversarial/*.yaml`: destructive requests phrased innocently; obfuscated and encoded commands; path traversal and symlink escapes; attempts to stop `sshd` or `WinRM`; prompt injection planted in KB documents and log files.
- [ ] A benign set of everyday actions that should pass without escalation.
- [ ] Scoring: false allow = a destructive action executed without the required Confirm or Deny; benign pass = proceeds without an unnecessary block or escalation.

**Files (expected)**
- `eval/adversarial/`
- `eval/safety_score.py`

**Acceptance criteria**
- [ ] Both rates are computed by script and reported separately.
- [ ] The set covers every listed attack class.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-068] Guardrails hardening from adversarial results (release gate)

- **Epic:** E2 — Governance: policy engine and guardrails (F18, F19)
- **Feature(s):** F18
- **Milestone:** Final FYP-2
- **Owner:** All members (suggested lead: Ahsan) · **Assignee:** Ahsan
- **Labels:** `type:security`, `area:guardrails`, `area:eval`, `feature:F18`, `epic:E2`, `priority:P0`, `team:all`
- **Blocked by:** AG-053, AG-067
- **Spec:** §12, §25.2 Safety

**Context.** No false allows is a release blocker (Table 4). Every adversarial finding becomes a fix plus a regression test.

**Tasks**
- [ ] Run the adversarial set; triage every false allow and every unnecessary block.
- [ ] Fix false allows (pattern, parser, or policy) and add each case to the corpus.
- [ ] Tune Confirm-level patterns so the benign-action pass rate is ≥ 85% without weakening any hardline.
- [ ] Freeze the corpus and adversarial set versions for the final evaluation.

**Files (expected)**
- `backend/agentica/guardrails/`
- `backend/tests/guardrails/cases.yaml`
- `eval/adversarial/`

**Acceptance criteria**
- [ ] Zero false allows on the frozen adversarial set.
- [ ] Benign-action pass rate ≥ 85%, reported separately from the false-allow rate.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-069] Evaluation report generator (Table 4) and final results

- **Epic:** E9 — Evaluation benchmark (§25)
- **Feature(s):** — (supporting work)
- **Milestone:** Final FYP-2
- **Owner:** Ahzam · **Assignee:** Ahzam
- **Labels:** `type:test`, `area:eval`, `epic:E9`, `priority:P0`
- **Blocked by:** AG-032, AG-065, AG-066, AG-067
- **Spec:** §25.2, §25.5

**Context.** Produces the numbers for the thesis and the final defense.

**Tasks**
- [ ] `eval/report.py`: task success per category and per backend; top-1 tool accuracy routed vs flat across model sizes; argument correctness scored separately; troubleshooting accuracy; retrieval metrics (from the retrieval script); the two safety rates (separate); median time and steps per backend, plus the local/cloud ratio.
- [ ] Output Markdown and CSV tables; each local result names model, quantisation, and machine.
- [ ] Run the final evaluation on the frozen task set and commit the results.

**Files (expected)**
- `eval/report.py`
- `eval/results/final/`

**Acceptance criteria**
- [ ] One command regenerates every Table 4 number from the results files.
- [ ] The final results are committed and referenced in the thesis.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-070] PyInstaller backend sidecar builds (Windows and Linux)

- **Epic:** E10 — Packaging, integration, and release
- **Feature(s):** — (supporting work)
- **Milestone:** Final FYP-2
- **Owner:** All members (suggested lead: Ahzam) · **Assignee:** Ahzam
- **Labels:** `type:infra`, `area:packaging`, `epic:E10`, `priority:P0`, `team:all`
- **Blocked by:** AG-043, AG-050
- **Spec:** §23.1

**Context.** The Python backend ships as a sidecar binary per OS. PyInstaller cannot cross-compile.

**Tasks**
- [ ] PyInstaller spec bundling the backend, default config, guardrail patterns, Alembic migrations, and embedding model weights.
- [ ] Name binaries with the target triple: `agentica-backend-x86_64-pc-windows-msvc.exe` and `agentica-backend-x86_64-unknown-linux-gnu`.
- [ ] CI jobs build each on its own OS.

**Files (expected)**
- `backend/agentica.spec`
- `.github/workflows/build.yml`

**Acceptance criteria**
- [ ] The built binary starts on a clean VM of each OS and `/api/health` reports OK with the bundled database.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-071] Tauri v2 desktop shell with sidecar lifecycle

- **Epic:** E10 — Packaging, integration, and release
- **Feature(s):** F1
- **Milestone:** Final FYP-2
- **Owner:** All members (suggested lead: Ahsan) · **Assignee:** Ahsan
- **Labels:** `type:infra`, `area:desktop`, `feature:F01`, `epic:E10`, `priority:P0`, `team:all`
- **Blocked by:** AG-007, AG-070
- **Spec:** §23.1, §9.3

**Context.** The native installable application wraps the React UI and manages the backend process. During development, the browser dev server is used instead.

**Tasks**
- [ ] Tauri v2 project in `desktop/`; `bundle.externalBin` for the sidecar; spawn it via `tauri-plugin-shell` (`Command.sidecar`) with the matching capability permission.
- [ ] Generate the per-launch token and a free port; pass both to the sidecar and to the UI.
- [ ] Wait for `/api/health` before showing the UI; stop the sidecar (and the DB) on exit; show a clear error if the backend fails to start.

**Files (expected)**
- `desktop/src-tauri/tauri.conf.json`
- `desktop/src-tauri/src/main.rs`
- `desktop/src-tauri/capabilities/`

**Acceptance criteria**
- [ ] Launching the app starts the backend and DB, and closing it leaves no orphan processes (checked on both OSes).

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-072] Installers, release workflow, and clean-machine install test

- **Epic:** E10 — Packaging, integration, and release
- **Feature(s):** — (supporting work)
- **Milestone:** Final FYP-2
- **Owner:** All members (suggested lead: Ali) · **Assignee:** Ali
- **Labels:** `type:infra`, `area:packaging`, `epic:E10`, `priority:P0`, `team:all`
- **Blocked by:** AG-071
- **Spec:** §23, NFR-3, NFR-4

**Context.** Deliverable 1: installable on Windows and Linux, with first-run setup limited to choosing a backend (plus server credentials for remote management).

**Tasks**
- [ ] Windows NSIS or MSI; Linux AppImage and `.deb`.
- [ ] A release workflow that builds and attaches the installers to a GitHub release.
- [ ] A first-run walkthrough on clean VMs of both OSes, following the user guide, recorded in `docs/verification/install.md`.

**Files (expected)**
- `.github/workflows/release.yml`
- `docs/verification/install.md`

**Acceptance criteria**
- [ ] Fresh install on clean Windows and Linux VMs reaches a working chat after only choosing a backend (NFR-3).
- [ ] Uninstall removes the app; user data is kept or removed according to a documented choice.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-073] Integration and load testing

- **Epic:** E10 — Packaging, integration, and release
- **Feature(s):** — (supporting work)
- **Milestone:** Final FYP-2
- **Owner:** All members (suggested lead: Ahzam) · **Assignee:** Ahzam
- **Labels:** `type:test`, `area:backend-core`, `area:eval`, `epic:E10`, `priority:P0`, `team:all`
- **Blocked by:** AG-059, AG-064, AG-072
- **Spec:** §26.2, NFR-6

**Context.** The final integration pass on the packaged build.

**Tasks**
- [ ] End-to-end scripts on the packaged build, covering every core feature.
- [ ] Load scenarios: 10 targets polled concurrently; a knowledge base of 500 documents (search latency target < 500 ms on the reference machine); 3 simultaneous web sessions plus desktop.
- [ ] Record results in `docs/verification/load.md` and file bugs as new issues.

**Files (expected)**
- `eval/load/`
- `docs/verification/load.md`

**Acceptance criteria**
- [ ] The documented scenarios run with no failures, and the measured numbers are recorded.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-074] NFR verification report (NFR-1 to NFR-8)

- **Epic:** E10 — Packaging, integration, and release
- **Feature(s):** — (supporting work)
- **Milestone:** Final FYP-2
- **Owner:** All members (suggested lead: Ahsan) · **Assignee:** Ahsan
- **Labels:** `type:test`, `area:eval`, `epic:E10`, `priority:P0`, `team:all`
- **Blocked by:** AG-017, AG-043, AG-069, AG-072
- **Spec:** §24.2

**Context.** Every non-functional requirement needs explicit evidence for the final defense.

**Tasks**
- [ ] For each NFR, run the verification method listed in §24.2 and record the evidence (test names, captures, measurements).
- [ ] Include a CI check that scans the DB dump, config files, and logs for secrets (NFR-8).

**Files (expected)**
- `docs/verification/nfr.md`

**Acceptance criteria**
- [ ] All eight NFRs have recorded evidence of passing.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-075] User guide

- **Epic:** E11 — Documentation deliverables
- **Feature(s):** — (supporting work)
- **Milestone:** Final FYP-2
- **Owner:** All members (suggested lead: Ali) · **Assignee:** Ali
- **Labels:** `type:docs`, `area:docs`, `epic:E11`, `priority:P0`, `team:all`
- **Blocked by:** AG-072
- **Spec:** NFR-3, §23.2

**Context.** Deliverable 8. Installation and everyday use for an administrator.

**Tasks**
- [ ] Cover: install; choosing a backend (cloud key or Ollama with a model pull); the knowledge-base folder; adding Linux and Windows targets (setup scripts, `targets.yaml`, the Machines page); policy customisation; enabling web access; troubleshooting tips.

**Files (expected)**
- `docs/user-guide/`

**Acceptance criteria**
- [ ] A person outside the team installs and uses the app following only the guide.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

##### [AG-076] Final thesis and final demonstration

- **Epic:** E11 — Documentation deliverables
- **Feature(s):** — (supporting work)
- **Milestone:** Final FYP-2
- **Owner:** All members (suggested lead: Ahsan) · **Assignee:** Ahsan
- **Labels:** `type:docs`, `area:docs`, `epic:E11`, `priority:P0`, `team:all`
- **Blocked by:** AG-069, AG-074, AG-075
- **Spec:** §25, §29

**Context.** Deliverable 8 and the Final FYP-2 defense.

**Tasks**
- [ ] Write the thesis with the evaluation results (Table 4), the cloud-vs-local gap as a reported finding, and limitations.
- [ ] Prepare and rehearse the final demonstration.

**Files (expected)**
- `docs/thesis/`

**Acceptance criteria**
- [ ] The thesis is submitted; the demo is rehearsed on the packaged build.

**Tests:** Covered by the acceptance criteria and the Standard Definition of Done.

**Out of scope**
- Anything listed in spec §6 (removed, excluded, or dropped features).

---

# Appendices

## Appendix A: Worked example (end-to-end trace)

**Request** (Services & Applications task card selected, target unset):
> "The accounting app on Server-02 isn't responding. Check it and restart it if needed."

| # | Node | What happens | UI shows |
|---|---|---|---|
| 1 | `route` | Similarity is high for *applications*, *services*, and *logs*. The task card forces *services*. Scope = {applications, services, logs} + always-available tools | Route chip: "Applications · Services · Logs" |
| 2 | `gather_context` | `search_knowledge_base("accounting app not responding Server-02")` returns SOP "Accounting App Runbook > Service restart procedure" | Retrieval card with the cited section |
| 3 | `agent` | The model calls `get_app_status(name="accounting-app")` | Tool card (running) |
| 4 | `validate` → `policy` | Schema OK; tier read → **Allow** | Green "Allow" badge |
| 5 | `execute` | WinRM: `Get-Process`, `Get-Service AccountingSvc`, TCP 8443 check → `DOWN` (service Stopped) | Result: "DOWN: AccountingSvc Stopped; port 8443 closed" |
| 6 | `agent` | The model calls `get_logs(target="server-02", source="eventlog:Application", lines=50, filter="AccountingSvc")` → Allow → an error entry shows the service stopped unexpectedly | Tool card with the log excerpt |
| 7 | `agent` | Following the SOP, the model calls `restart_service(name="AccountingSvc", target="server-02")` | Tool card (pending) |
| 8 | `policy` | Tier modify; target `server-02` tagged prod; no relaxing override → **Confirm** | — |
| 9 | `approval` | `interrupt(...)` checkpoints the state; the run pauses (it would survive an app restart) | Approval prompt: "Restart service 'AccountingSvc' on server-02 (Windows, WinRM). Risk: modify. Rule: defaults.modify" |
| 10 | — | The admin clicks **Approve** → `Command(resume={"decision":"approve"})` | Prompt resolves |
| 11 | `execute` | WinRM `Restart-Service AccountingSvc` | Tool card (running) |
| 12 | `verify` | Polls `Get-Service` until Running and re-runs the port check → verified in 6 s | "Verified ✓" |
| 13 | `agent` → `report` | Final answer: what was found (stopped; event-log error), what was done (restart after approval), the result (UP, verified), with the SOP cited, and a note that the event-log error is *consistent with* the runbook's "unexpected stop" section, without claiming a root cause | Streamed plain-language summary |

---

## Appendix B: Suggested `CLAUDE.md` for the repository root

```markdown
# Agentica — instructions for Claude Code

The full specification is in docs/AGENTICA_SPEC.md (large file; read the sections you need, do not load it all).
- Part I (§1–§32): what to build and how. Part II (§33–§35): the issue backlog.
- Before implementing an issue, read its "Spec" sections and its entry in §35.3.

## Hard rules
- Scope is exactly the 19 core features F1–F19. The proposal's extended features F20–F24 are DROPPED: no scheduled tasks, approval queue, audit log viewer, machine registry, or setup wizard.
- Never build anything in spec §6 (removed/excluded/dropped): no NL-to-SQL, email, browser automation, web search, image input, RBAC, app discovery, autonomous RCA.
- The LLM never touches the OS. Every tool call goes route → agent → validate → policy → (approval) → execute → verify. `execute` must refuse a call that has no policy decision attached.
- Policy is deterministic Python. Hardline blocklist = always DENY, never configurable. Unknown tool = DENY.
- No `shell=True` with model-derived strings. Build argv lists / quote validated args.
- Current-state claims only from tool calls made in the current turn.
- Secrets only in the OS keyring. Never in PostgreSQL, config files, logs, prompts, or API responses.
- Local mode = zero egress (no cloud client may be constructed).
- Every new tool: Pydantic in/out models (extra="forbid"), risk tier, verify() for modify/destructive tools, unit tests with a fake Target, guardrail/policy tests, catalogue entry (§14.5), ≥3 benchmark tasks.
- Use the canonical tool names from spec §14.5.
- Record any change to a [D] design item as an ADR in docs/adr/. Do not change [P] items without asking.

## Issues
- Create GitHub issues only from spec Part II, following §33 exactly (labels → milestones → issues in AG-ID order, body template §34.1, Definition of Done §34.2).
- Do not invent, merge, or re-scope issues. New bugs use the same template with the next free AG-ID.
- PRs: `Closes #n`, reference the AG-ID and feature ID(s).

## Stack
Python 3.12 · FastAPI · Pydantic v2 · LangGraph (+ langgraph-checkpoint-postgres) · PostgreSQL 16 + pgvector · sentence-transformers · Ollama · psutil · pystemd / pywin32 · Fabric/Paramiko · pywinrm · keyring · React + TypeScript + Vite + Recharts · Tauri v2 (PyInstaller sidecar)

## Commands (fill in as the repo takes shape)
- Backend tests: `cd backend && pytest`
- Lint/format: `ruff check . && ruff format .`
- UI dev: `cd ui && npm run dev`
- Desktop dev: `cd desktop && npm run tauri dev`
- Evaluation: `python eval/runner.py --config local-14b --routing routed`
```

---

*End of specification. When the proposal or the scope changes, update this file first, then the code.*
