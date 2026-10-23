# ✈️ TripMate AI — Multi-Agent Travel Planner

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-v1.2.2-purple.svg)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-v0.136.3-green.svg)](https://fastapi.tiangolo.com/)
[![MCP Protocol](https://img.shields.io/badge/MCP-MultiServer-orange.svg)](https://modelcontextprotocol.io/)
[![Google Cloud Run](https://img.shields.io/badge/Deployed-Cloud%20Run-4285F4.svg)](https://cloud.google.com/run)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Live Deployment:** [https://tripmate-ai.cloud.run](https://tripmate-ai.cloud.run) *(Canonical Cloud Run Instance: [https://tripmate-ai-63094329383.asia-south1.run.app](https://tripmate-ai-63094329383.asia-south1.run.app))*  
> **Health Check:** `GET /health` → `{"status":"ok","features":["supervisor_agent","input_guardrail","human_in_the_loop"]}`

---

## 📖 Table of Contents
1. [Overview & Problem Statement](#1-overview--problem-statement)
2. [Core Engineering Differentiators](#2-core-engineering-differentiators)
3. [Agent System Architecture](#3-agent-system-architecture)
4. [Tool Integration Layer (Model Context Protocol - MCP)](#4-tool-integration-layer-model-context-protocol---mcp)
5. [Technology Stack](#5-technology-stack)
6. [API Reference & Workflow Contracts](#6-api-reference--workflow-contracts)
7. [Local Development & Setup](#7-local-development--setup)
8. [Production Deployment Guide](#8-production-deployment-guide)
9. [Repository Structure](#9-repository-structure)
10. [Roadmap & Production Hardening](#10-roadmap--production-hardening)

---

## 1. Overview & Problem Statement

Planning an international or multi-city itinerary requires manually cross-referencing information across multiple disconnected tools: flight status monitors, lodging aggregators, meteorological forecasts, and budget tracking sheets.

**TripMate AI** solves this fragmentation through an autonomous, stateful **Multi-Agent AI Travel System**. Ingesting a single natural-language user query (e.g., *"Plan a 5-day budget trip to Tokyo for 2 adults under $1500"*), the system:
- Decomposes the request into travel constraints (destination, dates, budget limit, travel style).
- Validates user intent via semantic input guardrails.
- Dynamically selects and activates specialized domain agents.
- Queries live external tools using the **Model Context Protocol (MCP)**.
- Compiles an interactive draft travel plan and halts execution at a **Human-in-the-Loop (HITL)** checkpoint.
- Resumes execution upon receiving user approval or revision notes, synthesizing a polished 7-part final itinerary.

---

## 2. Core Engineering Differentiators

Unlike simple single-prompt LLM wrappers, TripMate AI implements production-grade agentic design patterns:

- **Stateful Human-in-the-Loop (HITL) Interruption:** Uses LangGraph's native `interrupt()` and `Command(resume=...)` primitives to suspend execution state directly into an external **PostgreSQL** checkpointer (`PostgresSaver`), enabling asynchronous human approval across stateless HTTP cycles.
- **Model Context Protocol (MCP) Multi-Server Client:** Implements `langchain-mcp-adapters` and `FastMCP` to standardize tool execution across distinct transport mechanisms (`streamable_http` and `stdio`), isolating agent reasoning from third-party vendor APIs.
- **Dynamic Supervisor & Intent Guardrailing:** Employs a supervisor agent that evaluates query safety/domain relevance and dynamically chooses the minimal subset of specialist agents required, reducing token costs and execution latency.
- **Fault-Tolerant Fallback Policies:** Every agent node encapsulates tool execution with isolated exception handling, allowing the pipeline to degrade gracefully to non-live guidelines if external APIs fail.

---

## 3. Agent System Architecture

The workflow is constructed as a directed **LangGraph StateGraph** backed by a shared, typed state container ([`TravelState`](backend.py)).

### Architecture Diagram

```mermaid
graph TD
    Start([START]) --> Supervisor[supervisor_agent<br/>Guardrail & Decomposition]
    
    Supervisor -->|Violates Guardrail| Blocked[guardrail_blocked_agent]
    Blocked --> EndNode([END])
    
    Supervisor -->|Valid Request| Flight[flight_agent*<br/>AviationStack MCP]
    Flight --> Hotel[hotel_agent*<br/>Tavily Search MCP]
    Hotel --> Weather[weather_agent*<br/>Custom FastMCP Weather]
    Weather --> Budget[budget_agent*<br/>Financial Analysis]
    Budget --> Itinerary[itinerary_agent<br/>Draft Plan Assembly]
    
    Itinerary --> HITL[human_approval_agent<br/>LangGraph interrupt barrier]
    
    HITL -->|POST /api/travel/approve<br/>Command resume| Final[final_agent<br/>Feedback Polish & Structure]
    Final --> EndNode
    
    classDef conditional fill:#fff3cd,stroke:#ffecb5,stroke-width:2px;
    class Flight,Hotel,Weather,Budget conditional;
```
*\*Conditionally activated: Inactive specialist agents are automatically bypassed by dynamic conditional routing edges.*

### Agent Roles & Specifications

| Node Name | Source Function | Primary Model / Engine | External Tools & APIs | Responsibility |
| :--- | :--- | :--- | :--- | :--- |
| **`supervisor`** | `supervisor_agent` | Groq `openai/gpt-oss-120b` | None (Structured LLM parsing) | Evaluates safety guardrails, decomposes query into `trip_constraints`, and selects required specialist agents. |
| **`guardrail_blocked`** | `guardrail_blocked_agent` | Deterministic Logic | None | Returns a clean explanation for queries blocked by safety or off-topic travel filters. |
| **`flight_agent`** | `flight_agent` | Groq `openai/gpt-oss-120b` | AviationStack MCP (`list_airports`, `list_airlines`) | Resolves likely origin/destination hubs, route schedules, peak pricing warnings, and booking guidance. |
| **`hotel_agent`** | `hotel_agent` | Tool Execution | Tavily Search MCP (`tavily_search`) | Performs live search queries for top accommodations, neighborhood safety, and proximity to attractions. |
| **`weather_agent`** | `weather_agent` | Groq + FastMCP Microservice | OpenWeatherMap via Custom FastMCP | Extracts destination city, queries current temperatures, and compiles a 5-step meteorological forecast. |
| **`budget_agent`** | `budget_agent` | Groq `openai/gpt-oss-120b` | None (Multi-domain synthesis) | Assesses financial feasibility against constraints, identifies budget risks, and suggests money-saving strategies. |
| **`itinerary_agent`** | `itinerary_agent` | Groq `openai/gpt-oss-120b` | None (Aggregation) | Merges accumulated domain outputs into a structured draft itinerary ready for human inspection. |
| **`human_approval`** | `human_approval_agent` | LangGraph `interrupt()` | PostgreSQL Checkpointer | Suspends thread execution, returning the draft to the client and awaiting human review. |
| **`final_agent`** | `final_agent` | Groq `openai/gpt-oss-120b` | None (Synthesis) | Incorporates human revision feedback and formats the final polished 7-section travel plan. |

---

## 4. Tool Integration Layer (Model Context Protocol - MCP)

TripMate AI adopts the open **Model Context Protocol (MCP)** specification via [`mcp_client.py`](mcp_client.py) and [`custom_weather_mcp_server.py`](custom_weather_mcp_server.py).

```
   ┌─────────────────────────────────────────────────────────────┐
   │                  LangGraph Travel Workflow                  │
   └──────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │               MultiServerMCPClient Interface                │
   └───────────────┬──────────────┬──────────────┬───────────────┘
                   │              │              │
        streamable_http         stdio          stdio
                   │              │              │
                   ▼              ▼              ▼
           ┌──────────────┐┌──────────────┐┌──────────────┐
           │  Tavily MCP  ││AviationStack ││Custom FastMCP│
           │ Search Server││  MCP (uvx)   ││Weather Server│
           └──────────────┘└──────────────┘└──────┬───────┘
                                                  │ REST
                                                  ▼
                                          ┌──────────────┐
                                          │OpenWeatherMap│
                                          └──────────────┘
```

1. **Tavily MCP Server:** Connected over `streamable_http` transport (`https://mcp.tavily.com/mcp/?tavilyApiKey=...`). Used for contextual hotel and lodging research.
2. **AviationStack MCP Server:** Spawned as an isolated subprocess via `stdio` transport using `uvx aviationstack-mcp`. Supplies live airline and airport registry metadata.
3. **Custom FastMCP Weather Server:** Standalone Python microservice ([`custom_weather_mcp_server.py`](custom_weather_mcp_server.py)) built with the `FastMCP` SDK, exposing `get_current_weather` and `get_forecast` tools over `stdio`.

---

## 5. Technology Stack

- **Agent & LLM Frameworks:**
  - `langgraph` (v1.2.2) — Graph-based agent orchestration, checkpointing, and interruption.
  - `langchain` (v1.3.2) & `langchain-groq` (v1.1.3) — LLM interface to Groq Cloud (`openai/gpt-oss-120b`).
  - `langchain-mcp-adapters` (v0.3.0) & `mcp` (v1.28.1) — FastMCP and multi-server MCP client.
- **Backend Infrastructure:**
  - `fastapi` (v0.136.3) — High-performance asynchronous API framework.
  - `uvicorn` (v0.48.0) — ASGI production web server.
  - `pydantic` — API payload schema validation.
- **Database & Persistence:**
  - `psycopg` (v3.3.4, binary) & `psycopg-pool` — Modern PostgreSQL driver with connection pooling.
  - `langgraph-checkpoint-postgres` (v3.1.0) — State checkpointer for conversation threads.
- **Frontend & UI:**
  - Responsive vanilla HTML5, CSS3 (glassmorphic dark UI), and JavaScript.
  - Jinja2 template rendering.
  - Client-side markdown formatting (`marked.js`) and client-side PDF export (`html2pdf.js`).
- **Cloud & Containerization:**
  - Docker container running `python:3.11-slim`.
  - Google Cloud Run (Region: `asia-south1`, Mumbai).

---

## 6. API Reference & Workflow Contracts

### 1. Health Check
```http
GET /health
```
**Response:**
```json
{
  "status": "ok",
  "message": "TripMate AI API is running",
  "features": ["supervisor_agent", "input_guardrail", "human_in_the_loop"]
}
```

---

### 2. Submit Travel Request (Initiates Run)
```http
POST /api/travel
Content-Type: application/json
```
**Request Body:**
```json
{
  "message": "Plan a 4-day trip to Singapore with a budget of $1000",
  "thread_id": "optional-custom-uuid"
}
```
**Response (`requires_approval: true`):**
```json
{
  "success": true,
  "thread_id": "user_a1b2c3d4e5",
  "answer": "### 4-Day Singapore Draft Itinerary\n...",
  "requires_approval": true,
  "approval_request": "Please review the generated draft itinerary. Approve it to create the final polished plan, or provide feedback for revision.",
  "selected_agents": ["flight_agent", "hotel_agent", "weather_agent", "budget_agent", "itinerary_agent"],
  "guardrail_allowed": true,
  "trip_constraints": {
    "destination": "Singapore",
    "budget": "$1000",
    "duration": "4 days"
  }
}
```

---

### 3. Human Approval & Workflow Resumption
```http
POST /api/travel/approve
Content-Type: application/json
```
**Request Body:**
```json
{
  "thread_id": "user_a1b2c3d4e5",
  "approved": false,
  "feedback": "Please swap out fine-dining options for affordable street food and hawker centers."
}
```
**Response (`requires_approval: false`):**
```json
{
  "success": true,
  "thread_id": "user_a1b2c3d4e5",
  "answer": "# ✈️ Complete Singapore Travel Plan\n\n### 1. Trip Summary\n...",
  "requires_approval": false,
  "approved": false,
  "human_feedback": "Please swap out fine-dining options for affordable street food and hawker centers."
}
```

---

## 7. Local Development & Setup

### Prerequisites
- Python 3.10+ installed
- PostgreSQL instance running locally or hosted (e.g., Supabase / Neon / Render)
- API Keys:
  - [Groq Console](https://console.groq.com/)
  - [Tavily AI](https://tavily.com/)
  - [OpenWeatherMap](https://openweathermap.org/api)
  - [AviationStack](https://aviationstack.com/) *(optional)*
- `uv` installed (`pip install uv`) for running MCP stdio servers

### Step 1: Clone Repository & Create Virtual Environment
```bash
git clone https://github.com/jeyaseelan6/TripMate-AI---A-Multi-Agent-Travel-Planner.git
cd TripMate-AI---A-Multi-Agent-Travel-Planner

python -m venv .venv
# On Linux/macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate
```

### Step 2: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables
Create a `.env` file in the project root:
```ini
# PostgreSQL Checkpointer
DATABASE_URL=postgresql://postgres:password@localhost:5432/tripmate_db?sslmode=require

# LLM Inference
GROQ_API_KEY=gsk_your_groq_key_here
GROQ_MODEL=openai/gpt-oss-120b

# MCP External Data Providers
TAVILY_API_KEY=tvly-your_tavily_key_here
OPENWEATHER_API_KEY=your_openweather_key_here
AVIATION_STACK_API_KEY=your_aviationstack_key_here

# Default Departure Hub (IATA Code)
DEFAULT_ORIGIN_IATA=DAC
```

### Step 4: Run the Application
```bash
python app.py
```
Open your browser at `http://127.0.0.1:8000/`.

---

## 8. Production Deployment Guide

TripMate AI is packaged as a containerized microservice optimized for **Google Cloud Run**.

### Option A: Automated PowerShell Deployment (Cloud Run)
The included script [`deploy-cloudrun.ps1`](deploy-cloudrun.ps1) generates a clean environment file and deploys the container to the Mumbai region:
```powershell
.\deploy-cloudrun.ps1
```

### Option B: Manual Container Build & Run
```bash
# Build Docker image
docker build -t tripmate-ai .

# Run container locally
docker run -p 8080:8080 --env-file .env tripmate-ai
```

---

## 9. Repository Structure

```text
.
├── app.py                         # FastAPI web application, route handlers, and static mounting
├── backend.py                     # LangGraph StateGraph, supervisor routing, and agent definitions
├── custom_weather_mcp_server.py   # Standalone FastMCP server wrapping OpenWeatherMap API
├── mcp_client.py                  # MultiServerMCPClient manager for Tavily, AviationStack, & Weather
├── requirements.txt               # Locked production dependencies
├── Dockerfile                     # Optimized Python 3.11 container manifest
├── deploy-cloudrun.ps1            # Automated Google Cloud Run deployment script
├── DEPLOYMENT.md                  # Detailed GCP Cloud Run and Secret Manager setup guide
├── static/                        # Frontend UI assets
│   ├── script.js                  # Asynchronous client logic, Markdown rendering, & HITL UI flow
│   └── style.css                  # Responsive glassmorphism stylesheet
└── templates/
    └── index.html                 # Jinja2 HTML5 single-page application template
```

---

## 10. Roadmap & Production Hardening

Planned engineering improvements for subsequent releases:
- [ ] **Async Graph Execution:** Transition graph nodes to native `async def` to eliminate synchronous `asyncio.run()` wrappers inside LangGraph.
- [ ] **Strict Pydantic Output Enforcement:** Upgrade `_json_from_llm` to `ChatGroq.with_structured_output` for validated schema decoding.
- [ ] **Database Connection Pooling:** Replace the module-level `psycopg.connect` with `psycopg_pool.ConnectionPool` for serverless lifecycle management.
- [ ] **Automated Test Coverage:** Implement a `pytest` test suite with mock fixtures for all MCP servers and agent transitions.
- [ ] **OpenTelemetry & LangSmith Integration:** Add trace observability for LLM token usage, latency metrics, and error tracking.

---

## 📄 License
This project is open-source and distributed under the [MIT License](LICENSE).