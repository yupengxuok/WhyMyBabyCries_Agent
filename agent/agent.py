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
        return {
            "care_events": [],
            "belief_state": {},
            "action_stats": {}
        }

    try:
        with open(MEMORY_FILE, "r") as f:
            content = f.read().strip()
            if not content:
                return {
                    "care_events": [],
                    "belief_state": {},
                    "action_stats": {}
                }
            return json.loads(content)
    except json.JSONDecodeError:
        print("[Agent] Memory corrupted. Reinitializing.")
        return {
            "care_events": [],
            "belief_state": {},
            "action_stats": {}
        }



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
        action_type = understanding["likely_need"]

        stats = self.memory.get("action_stats", {})
        action_info = stats.get(action_type, {"attempts": 0, "success": 0})

        if action_info["attempts"] > 0:
            confidence = action_info["success"] / action_info["attempts"]
        else:
            confidence = 0.6  # default prior

        return {
            "action": action_type,
            "confidence": round(confidence, 2),
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
        success = outcome["cry_stopped_minutes"] <= 5

        stats = self.memory.setdefault("action_stats", {})
        action = decision["action"]
        if action not in stats:
            stats[action] = {"attempts": 0, "success": 0}
        stats[action]["attempts"] += 1
        if success:
            stats[action]["success"] += 1
        self.memory.setdefault("care_events", []).append({
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "outcome": outcome
        })
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
