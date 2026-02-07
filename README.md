# WhyMyBabyCries_Agent
## How to Run

This project is implemented as an **agent-first backend system**.
No frontend or web server is required to run the agent.

### Prerequisites

- Python 3.9+
- No external services are required for the demo (all integrations are stubbed)

### Project Structure

WhyMyBabyCries_Agent/
├── agent/
│ ├── agent.py # Core autonomous agent
│ ├── memory.json # Persistent agent memory (continual learning)
│ └── prompt.txt # Agent behavior charter
└── README.md


### Running the Agent

From the project root directory:

```bash
python agent/agent.py
Each run executes one full autonomous agent cycle:

Observe → Interpret → Decide → Act → Learn

Running the agent multiple times demonstrates continual learning, as the agent updates its internal memory and confidence based on outcomes.

Expected Output
Example output:

[You.com] Searching: baby crying night feeding vs soothing
[Agent Belief] Likely cause: hunger (60%)
[Composio] Executing action: {'action': 'feeding', 'confidence': 0.68, 'reason': 'hunger'}
Agent cycle complete.
The output shows:

The agent’s inferred belief

The selected action

The confidence and reasoning behind the decision

Continual Learning Demonstration
Run the agent multiple times:

python agent/agent.py
python agent/agent.py
Then inspect agent/memory.json to observe how:

Action attempt counts increase

Success rates influence future decisions

Confidence evolves over time

This demonstrates outcome-driven continual learning without model retraining.

