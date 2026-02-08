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
from tools.you_search import you_search

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


def you_search_summary(query: str) -> str:
    """
    External grounding via You.com Search API.
    """
    print(f"[You.com] Searching: {query}")
    try:
        results = you_search(query, count=3)
    except Exception as exc:
        return f"Search unavailable: {exc}"

    if not results:
        return "No search results found."

    top = results[0]
    title = top.get("title") or "Result"
    snippet = top.get("snippet") or ""
    return f"{title}: {snippet}".strip()


# ====== Agent Memory ======

MEMORY_FILE = "agent/memory.json"

def _iso_now():
    return datetime.utcnow().isoformat() + "Z"


def _new_event_id():
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    return f"evt_{stamp}"


def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {
            "events": [],
            "belief_state": {},
            "action_stats": {}
        }

    try:
        with open(MEMORY_FILE, "r") as f:
            content = f.read().strip()
            if not content:
                return {
                    "events": [],
                    "belief_state": {},
                    "action_stats": {}
                }
            data = json.loads(content)
            data.setdefault("events", [])
            data.setdefault("belief_state", {})
            data.setdefault("action_stats", {})
            return data
    except json.JSONDecodeError:
        print("[Agent] Memory corrupted. Reinitializing.")
        return {
            "events": [],
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
        external_knowledge = you_search_summary(
            "baby crying night feeding vs soothing"
        )
        print(f"[You.com] Top result: {external_knowledge}")

        likely_need = "feeding" if context["last_feed_hours"] >= 3 else "comfort"

        return {
            "context": context,
            "likely_need": likely_need,
            "knowledge": external_knowledge,
        }

    def decide(self, understanding: dict) -> dict:
    # 1. 从 belief_state 推断哭因
        belief = self.memory.get("belief_state", {}).get("night_cry", {})

        if belief:
            predicted_reason = max(belief, key=belief.get)
            base_confidence = belief[predicted_reason]
        else:
            predicted_reason = understanding["likely_need"]
            base_confidence = 0.5

    # 2. 原因 → 行为 映射（必须在函数内部）
        reason_to_action = {
            "hunger": "feeding",
            "emotional_comfort": "comfort",
            "discomfort": "diaper_check",
            "unknown": understanding["likely_need"]
        }

        action_type = reason_to_action.get(
            predicted_reason,
            understanding["likely_need"]
        )

        # 3. 结合历史 action 成功率
        stats = self.memory.get("action_stats", {})
        action_info = stats.get(action_type, {"attempts": 0, "success": 0})

        if action_info["attempts"] > 0:
            success_rate = action_info["success"] / action_info["attempts"]
            confidence = round((base_confidence + success_rate) / 2, 2)
        else:
            confidence = round(base_confidence, 2)

        # 4. 打印 agent 的“思考结果”（Demo 关键）
        print(
            f"[Agent Belief] Likely cause: {predicted_reason} "
            f"({int(base_confidence * 100)}%)"
        )

        return {
            "action": action_type,
            "confidence": confidence,
            "reason": predicted_reason
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
        event = {
            "id": _new_event_id(),
            "type": "manual",
            "occurred_at": _iso_now(),
            "source": "agent",
            "category": action,
            "payload": {
                "reason": decision["reason"],
                "confidence": decision["confidence"],
                "outcome": outcome
            },
            "tags": ["agent"],
            "created_at": _iso_now()
        }
        self.memory.setdefault("events", []).append(event)
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
