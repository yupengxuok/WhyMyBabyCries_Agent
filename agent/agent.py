# agent/agent.py
"""
WMBC Agent - Minimal Continual Learning Agent
Core loop: Observe → Decide → Act → Observe Outcome → Learn
"""

import json
import os
import time
from datetime import datetime

# ====== Tool Interfaces (stub for hackathon) ======

def composio_execute(action: dict):
    """
    All real-world actions go through Composio.
    """
    print(f"[Composio] Executing action: {action}")
    return {"status": "success"}


def plivo_speak(message: str):
    """
    Voice output channel.
    """
    print(f"[Plivo Voice] {message}")


def you_search(query: str) -> str:
    """
    External grounding via You.com (stub).
    """
    print(f"[You.com] Searching: {query}")
    return "General caregiving best practices for night-time crying."


# ====== Agent Memory ======

MEMORY_FILE = "agent/memory.json"


def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return []
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)


def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)


# ====== Agent Core ======

class CryFlowAgent:
    def __init__(self):
        self.memory = load_memory()

    def observe(self, signal: dict) -> dict:
        """
        Observe raw environment signal.
        """
        return {
            "time": datetime.now().strftime("%H:%M"),
            "cry_intensity": signal.get("cry_intensity", "high"),
            "last_feed_hours": signal.get("last_feed_hours", 3),
        }

    def interpret(self, context: dict) -> dict:
        """
        Make sense of what the agent finds.
        """
        external_knowledge = you_search(
            "baby crying night feeding vs soothing"
        )

        likely_need = "feeding" if context["last_feed_hours"] >= 3 else "comfort"

        return {
            "context": context,
            "likely_need": likely_need,
            "knowledge": external_knowledge,
        }

    def decide(self, understanding: dict) -> dict:
        """
        Decide what action to take based on memory & understanding.
        """
        action_type = understanding["likely_need"]

        # simple policy: prefer historically successful actions
        confidence = 0.7
        for record in self.memory:
            if record["action"] == action_type:
                confidence = max(confidence, record["confidence"])

        return {
            "action": action_type,
            "confidence": confidence,
        }

    def act(self, decision: dict):
        """
        Execute action through Composio & optional voice.
        """
        composio_execute(decision)

        if decision["confidence"] > 0.75:
            plivo_speak(
                f"Suggested action: {decision['action']}. Please try now."
            )

    def observe_outcome(self) -> dict:
        """
        Observe outcome (simulated for demo).
        """
        # In real life: time-to-calm, sensor feedback, etc.
        return {
            "cry_stopped_minutes": 4
        }

    def learn(self, understanding, decision, outcome):
        """
        Continual learning: update internal memory.
        """
        success = outcome["cry_stopped_minutes"] <= 5
        new_confidence = (
            decision["confidence"] + 0.05 if success else decision["confidence"] - 0.05
        )

        record = {
            "timestamp": datetime.now().isoformat(),
            "context": understanding["context"],
            "action": decision["action"],
            "outcome": outcome,
            "confidence": round(new_confidence, 2),
        }

        self.memory.append(record)
        save_memory(self.memory)

    def run(self, signal: dict):
        """
        Full autonomous agent loop.
        """
        context = self.observe(signal)
        understanding = self.interpret(context)
        decision = self.decide(understanding)
        self.act(decision)
        outcome = self.observe_outcome()
        self.learn(understanding, decision, outcome)


# ====== CLI Entry ======

if __name__ == "__main__":
    agent = CryFlowAgent()

    # Simulated input signal
    input_signal = {
        "cry_intensity": "high",
        "last_feed_hours": 3
    }

    agent.run(input_signal)
    print("Agent cycle complete.")
