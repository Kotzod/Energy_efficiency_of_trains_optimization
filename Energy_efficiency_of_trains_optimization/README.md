# 🚆 Railway Resilience Framework

### Agent-Based Cascading Failure Simulation for Finnish Single-Track Railways

---

# Overview

The Railway Resilience Framework is a modular agent-based railway simulation platform focused on:

- cascading delay propagation
- infrastructure vulnerability analysis
- degraded-state railway operations
- adaptive dispatching
- ETCS-inspired movement authority abstraction
- resilience experimentation on single-track corridors

The primary research target is the **Tampere–Pori railway corridor** in Finland.

This project combines:

- agent-based modeling (ABM)
- graph-based infrastructure analysis
- railway dispatch simulation
- failure injection systems
- infrastructure criticality scoring
- optional reinforcement learning dispatch optimization

into a unified railway resilience laboratory.

---

# 🎯 Research Goal

The project investigates:

> How infrastructure degradation propagates operational disruption through single-track railway networks.

The framework evaluates:

- knock-on delays
- deadlock formation
- recovery time
- dispatcher response
- critical infrastructure dependencies

using deterministic replayable simulation scenarios.

---

# 🧠 Core Thesis Contribution

The main contribution is:

## Dynamic Infrastructure Vulnerability Scoring

The framework repeatedly injects failures into railway infrastructure components and measures network-wide operational impact.

Example:

| Infrastructure Element | Avg Delay | Deadlock Risk | Recovery Time |
| ---------------------- | --------- | ------------- | ------------- |
| Nokia Switch A         | 240 min   | High          | 8h            |
| Rural Passing Loop B   | 12 min    | Low           | 30m           |

This enables:

- resilience analysis
- operational bottleneck discovery
- dispatch strategy evaluation
- degraded-state experimentation

---

# 🏗️ System Architecture

```text
                    ┌──────────────────────┐
                    │ Gemini-Style Prompt  │
                    └──────────┬───────────┘
                               │
                               ▼
                   ┌─────────────────────┐
                   │ NLP Prompt Parser   │
                   └──────────┬──────────┘
                              │
                              ▼
                   ┌─────────────────────┐
                   │ JSON Scenario Model │
                   └──────────┬──────────┘
                              │
                              ▼
        ┌────────────────────────────────────────┐
        │ Railway Resilience Simulation Engine   │
        └────────────────────────────────────────┘
             │            │             │
             │            │             │
     ┌───────▼─────┐ ┌────▼─────┐ ┌─────▼──────┐
     │ Failures    │ │ Dispatch │ │ Analytics  │
     │ Engine      │ │ Engine   │ │ Engine     │
     └───────┬─────┘ └────┬─────┘ └─────┬──────┘
             │            │             │
             ▼            ▼             ▼
    Telecom Outage   RL Dispatcher   Vulnerability
    Switch Failure   Heuristic AI    Scoring
    Speed Restrict.  Conflict Mgmt   Delay Analysis
```

---

# ⚙️ Key Features

## 🚄 Agent-Based Railway Simulation

- train agents
- dispatcher agents
- timetable replay
- movement authorities
- single-track occupancy logic
- passing loop negotiation

---

## 🌐 Infrastructure Graph Modeling

The railway is represented as a graph:

- nodes → stations, switches, passing loops
- edges → track segments

Powered by:

- graph traversal
- centrality analysis
- network resilience metrics

---

## ⚠️ Failure Injection Engine

Simulate degraded operational states:

- switch failures
- occupied sections
- telecom degradation
- reduced speed zones
- delayed departures

The framework evaluates how disruption propagates through the network.

---

## 🧮 Vulnerability Scoring

Every infrastructure component can be evaluated based on:

- average delay created
- deadlock frequency
- recovery duration
- cascading disruption severity

This forms the primary research output.

---

## 🤖 Adaptive Dispatching

Two dispatching approaches can be compared:

### Heuristic Dispatcher

Rule-based prioritization:

- passenger priority
- freight yielding
- conflict resolution heuristics

### RL Dispatcher (Optional)

Experimental reinforcement learning dispatcher:

- delay minimization
- adaptive rerouting
- congestion reduction

---

## 📡 ETCS-Inspired Operational Abstraction

The project does NOT attempt full ETCS protocol emulation.

Instead, it models:

- movement authority constraints
- communication degradation states
- adaptive headway behavior
- degraded operational logic

The focus is operational impact rather than telecom packet realism.

---

# 💬 Gemini-Style Scenario Interface

The system includes a natural language scenario interface.

Example prompt:

```text
Simulate a switch failure near Nokia station during peak freight traffic
with degraded telecom conditions.
```

The NLP layer converts this into a structured JSON experiment schema:

```json
{
  "scenario": {
    "line": "tampere_pori",
    "failure": {
      "type": "switch_failure",
      "location": "Nokia"
    },
    "telecom_state": "degraded",
    "traffic_density": "high"
  }
}
```

The simulation then launches directly from the generated configuration.

---

# 🖥️ Visualization System

The visualization layer provides:

- live train movement
- railway topology rendering
- delay heatmaps
- deadlock visualization
- timeline replay
- vulnerability dashboards

---

# 📁 Project Structure

```text
railway-resilience-sim/
│
├── frontend/          # Gemini-style UI
├── api/               # FastAPI backend
├── core/              # simulation engine
├── infrastructure/    # railway graph
├── agents/            # train + dispatcher agents
├── simulation/        # movement logic
├── failures/          # degradation engine
├── dispatching/       # heuristic + RL dispatching
├── analytics/         # vulnerability scoring
├── visualization/     # rendering system
├── experiments/       # reproducible experiments
├── rl/                # reinforcement learning
└── tests/             # validation tests
```

---

# 🧪 Experiment Workflow

```text
User Prompt
    ↓
Scenario Parser
    ↓
Validated JSON Schema
    ↓
Simulation Execution
    ↓
Failure Propagation
    ↓
Metrics Collection
    ↓
Vulnerability Scoring
    ↓
Visualization & Reports
```

---

# 🛠️ Technology Stack

## Simulation

- Mesa
- SimPy
- NetworkX

## Backend

- FastAPI
- WebSockets
- Pydantic

## Frontend

- Streamlit
- Plotly
- PyVis

## AI / RL

- Stable-Baselines3
- Gymnasium
- PyTorch

## Analytics

- Pandas
- NumPy
- SciPy

---

# 🚀 Installation

## Clone Repository

```bash
git clone <repository-url>
cd railway-resilience-sim
```

## Create Environment

```bash
python -m venv .venv
```

### Windows

```bash
.venv\Scripts\activate
```

### Linux / macOS

```bash
source .venv/bin/activate
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

# ▶️ Running the System

## Launch Frontend

```bash
streamlit run frontend/app/main.py
```

---

# 🧪 Running Experiments

# 📊 Planned Research Experiments

## Infrastructure Failure Analysis

- switch failures
- passing loop degradation
- occupied sections

## Telecom Degradation

- increased movement authority latency
- adaptive headway changes
- degraded dispatch coordination

## Dispatch Optimization

- heuristic vs RL dispatcher
- congestion minimization
- deadlock reduction

## Cascading Delay Analysis

- delay propagation chains
- critical node discovery
- recovery-time analysis

---

# 🎓 Academic Focus

This project focuses on:

- railway resilience
- cascading operational disruption
- infrastructure vulnerability
- simulation-based experimentation
- degraded-state railway operation

The framework is intended for:

- applied software engineering research
- railway operations analysis
- transport resilience experimentation
- Finnish single-track corridor analysis

---

# ⚠️ Scope Boundaries

The framework intentionally does NOT attempt:

- full ETCS certification
- exact FRMCS protocol implementation
- real train physics simulation
- production railway control deployment
- nationwide scaling

The focus is:

> operational resilience analysis through high-level simulation abstraction.

---

# 🔮 Future Extensions

Potential future work:

- nationwide railway scaling
- digital twin integration
- predictive maintenance modules
- real Digitraffic live replay
- multi-corridor dispatch coordination
- weather-aware disruption modeling
- distributed simulation clusters

---

# 📚 Inspiration & Research Areas

Relevant domains:

- railway operations research
- complex network theory
- agent-based modeling
- transport resilience engineering
- reinforcement learning dispatching
- cascading failure analysis

---

# 👨‍💻 Author

Oliver Chandler

Software Engineering Thesis Project

Tampere University of Applied Sciences

Finland
