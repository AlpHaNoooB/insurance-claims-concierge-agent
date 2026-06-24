# 🏥 Insurance Claims Concierge Agent

> An AI-powered concierge that helps individuals navigate the complex process of making cashless health insurance claims — translating corporate jargon, identifying hidden financial traps, and initiating claims securely.

---

## 🎯 Problem Statement

Health insurance claims are notoriously opaque. Policyholders face:
- **Jargon overload** (co-pay, sub-limits, deductibles, domiciliary)
- **Hidden financial traps** (10% co-payments, room-rent sub-limits) only discovered post-treatment
- **Coverage gaps** (excluded treatments, non-network hospitals)
- **Stressful, multi-step initiation** processes during already difficult medical situations

This agent acts as a **personal claims expert in your pocket** — available 24/7 to guide users from claim initiation to resolution.

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🔍 **Claim Extraction** | Parses natural language requests to extract policy ID, hospital, treatment, and cost |
| 🏥 **Network Verification** | Checks if the hospital is in the insurer's cashless network |
| 📋 **Coverage Analysis** | Retrieves real policy terms including co-pays, exclusions, and room-rent limits |
| ⚠️ **Trap Detection** | Uses an AI auditor to identify hidden co-payments, sub-limits, and exclusions |
| 🗣️ **Lingo Translation** | Converts corporate insurance jargon into plain English |
| 🔁 **Human-in-the-Loop** | Pauses for user confirmation when financial traps are detected |
| 📄 **Claim Form Generation** | Outputs a formatted cashless claim request document |
| 🔒 **Zero-Trust Security** | Input validation to prevent prompt injection attacks |

---

## 🏗️ Architecture

```
User Request (Natural Language)
         │
         ▼
  ┌─────────────────┐
  │ Extraction Agent │  ← Gemini 3.5 Flash (structured output)
  │ (parse_request)  │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────────────────┐
  │   verify_eligibility (node) │  ← check_hospital_network() + get_policy_coverage()
  └────────────┬────────────────┘
               │
               ▼
  ┌──────────────────────┐
  │ Risk Analysis Agent  │  ← Gemini 3.5 Flash (LLM-as-auditor)
  │ (analyze_traps)      │
  └────────┬─────────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────────┐
  │                   route_claim (Decision Node)           │
  │  ┌──────────┐  ┌───────────────┐  ┌──────────────────┐ │
  │  │ Approve  │  │ Human Gate ⚡ │  │  Reject          │ │
  │  │          │  │ (traps found) │  │  (non-network or │ │
  │  │          │  │               │  │   exclusion)     │ │
  │  └────┬─────┘  └──────┬────────┘  └──────────────────┘ │
  └───────┼───────────────┼─────────────────────────────────┘
          │               │
          ▼               ▼
  ┌──────────────┐  ┌────────────────────────┐
  │ Claims Form  │  │  Human Approval Gate   │
  │ Generated ✅ │  │  (user decides)        │
  └──────────────┘  └──────────┬─────────────┘
                               │ proceed / cancel
                               ▼
                        ┌──────────────┐
                        │ Claims Form  │
                        │   or Cancel  │
                        └──────────────┘
```

**Tech Stack:**
- **ADK 2.0 Graph Workflow** — Stateful multi-node workflow with conditional routing
- **Gemini 3.5 Flash** — LLM agents for extraction and risk analysis
- **Python + uv** — Dependency management
- **Google agents-cli** — Local dev playground + eval framework
- **pytest** — Unit and integration tests

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- `uv` package manager: `pip install uv`
- `agents-cli`: `uv tool install google-agents-cli`
- A Gemini API key from [Google AI Studio](https://aistudio.google.com)

### Setup

```bash
# Clone and enter the project
cd claims-agent

# Set your API key
echo 'GEMINI_API_KEY="your-api-key-here"' > .env

# Install dependencies
agents-cli install

# Launch the interactive playground
agents-cli playground
```

### Example Prompts to Try

```
✅ Approved path:
"I need a cashless claim for policy POL999 at Apollo Hospital for knee surgery, estimated $2000."

⚠️ Trap detected (10% co-pay + room-rent limit):
"I want to admit at Max Hospital for an appendix operation under policy POL123, cost around $3000."

❌ Non-network rejection:
"Please initiate a claim for POL123 at City Care Hospital for a check-up."

🚫 Excluded treatment:
"I want a cashless claim for Dental Cleaning at Fortis Hospital under POL123."
```

---

## 🧪 Testing

```bash
# Run unit tests (tool-level validation)
uv run pytest tests/unit/ -v

# Run all tests
uv run pytest tests/ -v

# Generate eval traces
agents-cli eval generate

# Grade the agent (LLM-as-judge)
agents-cli eval grade

# View analysis report
agents-cli eval analyze
```

---

## 📁 Project Structure

```
claims-agent/
├── app/
│   ├── agent.py              # ADK 2.0 Workflow: 9-node graph agent
│   ├── tools.py              # Tool functions: network check, policy lookup, lingo explain
│   ├── agent_runtime_app.py  # Agent Runtime deployment wrapper
│   └── app_utils/            # Utilities and helpers
├── data/
│   └── claims_db.json        # Mock insurance database (hospitals + policies)
├── tests/
│   ├── unit/
│   │   └── test_agent_tools.py   # 6 unit tests, all passing ✅
│   └── eval/
│       ├── eval_config.yaml      # LLM-as-judge rubrics (claims quality + trap accuracy)
│       └── datasets/
│           └── basic-dataset.json  # 5 real-world claim scenarios
├── specs/                    # BDD Gherkin specifications (SDD approach)
├── deployment/               # Cloud Run / Agent Runtime config
├── GEMINI.md                 # AI-assisted development context
├── pyproject.toml            # Project dependencies
└── README.md                 # This file
```

---

## 🔒 Security

This agent implements **Zero-Trust security principles**:
- Input sanitization prevents prompt injection attacks
- Policy data is fetched from a controlled JSON database (not user-controlled)
- No hardcoded credentials (API key loaded from `.env`)
- Human-in-the-loop gate for high-stakes decisions (traps detected)

---

## ☁️ Deployment

```bash
# Configure your Google Cloud project
gcloud config set project <your-project-id>
gcloud auth application-default login

# Deploy to Agent Runtime
agents-cli deploy
```

---

## 📊 Evaluation Metrics

The agent is evaluated using **two LLM-as-judge metrics**:

| Metric | Description | Target |
|--------|-------------|--------|
| `claims_evaluation_quality` | Overall accuracy, routing, and user guidance quality | ≥ 4.0/5.0 |
| `trap_identification_accuracy` | Accuracy of detecting co-pays, sub-limits, and exclusions | ≥ 4.0/5.0 |

---

## 🏆 Capstone Project

Built for the **Kaggle: AI Agents Intensive Vibe Coding Capstone Project** — demonstrating:
- ✅ Spec-Driven Development (BDD Gherkin specs in `specs/`)
- ✅ ADK 2.0 multi-node Graph Workflow
- ✅ Multi-agent pipeline (extraction + risk analysis LLM agents)
- ✅ Human-in-the-Loop with `RequestInput`
- ✅ Evaluation-Driven Development (LLM-as-judge rubrics)
- ✅ Zero-Trust security gating
- ✅ Agent Runtime deployment readiness
