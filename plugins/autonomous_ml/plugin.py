"""
Autonomous ML Plugin — Reinforcement Learning for Continuous Self-Improvement.

Features:
  - Reinforcement learning from user interactions
  - Success/failure tracking and adaptation
  - Behavioral optimization based on feedback
  - Continuous model improvement through experience
"""

import json
import logging
import random
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.autonomous_ml")

EXPERIENCE_FILE = Path.home() / "NexusScripts" / "autonomous_ml_experience.json"
POLICY_FILE = Path.home() / "NexusScripts" / "autonomous_ml_policy.json"

class AutonomousMLPlugin(BasePlugin):
    name = "autonomous_ml"
    description = "Reinforcement learning system for continuous AI self-improvement"
    icon = "🧠"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._experience_buffer = []
        self._policy = self._load_policy()
        self._learning_rate = 0.1
        self._discount_factor = 0.9
        self._exploration_rate = 0.1

    def _load_policy(self) -> dict:
        """Load learned policy from disk."""
        if POLICY_FILE.exists():
            try:
                return json.loads(POLICY_FILE.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"Failed to load policy: {e}")
        return {
            "action_values": defaultdict(float),  # Q-values for action selection
            "state_action_counts": defaultdict(int),  # Visit counts for exploration
            "success_patterns": defaultdict(list),  # Successful interaction patterns
            "failure_patterns": defaultdict(list),  # Failed interaction patterns
            "adaptation_rules": {},  # Learned rules for behavior adaptation
            "last_updated": datetime.now().isoformat()
        }

    def _save_policy(self):
        """Save learned policy to disk."""
        try:
            POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
            self._policy["last_updated"] = datetime.now().isoformat()
            POLICY_FILE.write_text(json.dumps(dict(self._policy), indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save policy: {e}")

    async def connect(self) -> bool:
        """Initialize autonomous learning system."""
        self._connected = True
        self._status_message = f"Autonomous ML active - {len(self._policy['action_values'])} learned actions"
        return True

    def get_capabilities(self) -> list[dict]:
        return [
            {
                "action": "log_interaction",
                "description": "Log user interaction for reinforcement learning",
                "params": ["user_input", "ai_response", "user_feedback", "success_score", "context"]
            },
            {
                "action": "learn_from_experience",
                "description": "Process experience buffer and update policy",
                "params": []
            },
            {
                "action": "get_optimal_action",
                "description": "Get best action recommendation based on current state",
                "params": ["state", "available_actions"]
            },
            {
                "action": "analyze_performance",
                "description": "Analyze learning performance and adaptation patterns",
                "params": []
            },
            {
                "action": "reset_learning",
                "description": "Reset learning progress (use with caution)",
                "params": []
            }
        ]

    async def execute(self, action: str, params: dict) -> str:
        """Execute autonomous ML actions."""
        try:
            if action == "log_interaction":
                return self._log_interaction(params)
            elif action == "learn_from_experience":
                return await self._learn_from_experience()
            elif action == "get_optimal_action":
                return self._get_optimal_action(params)
            elif action == "analyze_performance":
                return self._analyze_performance()
            elif action == "reset_learning":
                return self._reset_learning()
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.error(f"Autonomous ML error: {e}")
            return f"Error in autonomous_ml.{action}: {e}"

    def _log_interaction(self, params: dict) -> str:
        """Log an interaction for later learning."""
        interaction = {
            "timestamp": datetime.now().isoformat(),
            "user_input": params.get("user_input", ""),
            "ai_response": params.get("ai_response", ""),
            "user_feedback": params.get("user_feedback", 0),  # -1 to 1 scale
            "success_score": params.get("success_score", 0.5),  # 0 to 1 scale
            "context": params.get("context", {}),
            "state_features": self._extract_state_features(params)
        }

        self._experience_buffer.append(interaction)

        # Keep buffer size manageable
        if len(self._experience_buffer) > 1000:
            self._experience_buffer = self._experience_buffer[-500:]

        # Save to disk periodically
        if len(self._experience_buffer) % 50 == 0:
            self._save_experience_buffer()

        return f"Interaction logged. Buffer size: {len(self._experience_buffer)}"

    def _extract_state_features(self, params: dict) -> dict:
        """Extract relevant features from interaction state."""
        user_input = params.get("user_input", "").lower()
        context = params.get("context", {})

        features = {
            "input_length": len(user_input),
            "has_question": "?" in user_input,
            "has_command": any(word in user_input for word in ["create", "build", "make", "do", "run", "start"]),
            "time_of_day": datetime.now().hour,
            "is_complex": len(user_input.split()) > 10,
            "has_code": any(char in user_input for char in ["{", "(", "[", "="]),
            "plugin_context": context.get("active_plugin", ""),
            "conversation_length": context.get("conversation_length", 0)
        }

        return features

    async def _learn_from_experience(self) -> str:
        """Process experience buffer and update policy using reinforcement learning."""
        if not self._experience_buffer:
            return "No experiences to learn from."

        updated_actions = 0
        successful_patterns = 0
        failed_patterns = 0

        for experience in self._experience_buffer[-100:]:  # Learn from recent experiences
            reward = self._calculate_reward(experience)
            state = self._get_state_key(experience["state_features"])
            action = self._infer_action_from_response(experience["ai_response"])

            if action:
                # Q-learning update
                old_value = self._policy["action_values"].get(f"{state}:{action}", 0.0)
                self._policy["state_action_counts"][f"{state}:{action}"] += 1

                # Temporal difference learning
                new_value = old_value + self._learning_rate * (reward + self._discount_factor * self._get_max_future_value(state) - old_value)
                self._policy["action_values"][f"{state}:{action}"] = new_value
                updated_actions += 1

                # Pattern learning
                if reward > 0.5:
                    self._policy["success_patterns"][state].append({
                        "action": action,
                        "reward": reward,
                        "features": experience["state_features"]
                    })
                    successful_patterns += 1
                elif reward < -0.2:
                    self._policy["failure_patterns"][state].append({
                        "action": action,
                        "reward": reward,
                        "features": experience["state_features"]
                    })
                    failed_patterns += 1

        # Learn adaptation rules
        self._learn_adaptation_rules()

        self._save_policy()
        self._experience_buffer = []  # Clear processed experiences

        return f"Learning complete: {updated_actions} actions updated, {successful_patterns} success patterns, {failed_patterns} failure patterns learned."

    def _calculate_reward(self, experience: dict) -> float:
        """Calculate reward from interaction experience."""
        feedback = experience.get("user_feedback", 0)
        success = experience.get("success_score", 0.5)

        # Base reward from explicit feedback
        reward = (feedback + success - 1.0)  # Normalize to -1 to 1 range

        # Bonus for complex successful interactions
        if success > 0.8 and experience["state_features"]["is_complex"]:
            reward += 0.2

        # Penalty for failed simple interactions
        if success < 0.3 and not experience["state_features"]["is_complex"]:
            reward -= 0.3

        return max(-1.0, min(1.0, reward))  # Clamp to [-1, 1]

    def _get_state_key(self, features: dict) -> str:
        """Create a state key from features for Q-learning."""
        # Discretize continuous features
        time_slot = features["time_of_day"] // 6  # 0-3 (4 time slots)
        length_cat = min(3, features["input_length"] // 50)  # 0-3 length categories

        return f"t{time_slot}_l{length_cat}_q{int(features['has_question'])}_c{int(features['has_command'])}_x{int(features['is_complex'])}"

    def _infer_action_from_response(self, response: str) -> str:
        """Infer the action taken from AI response."""
        response_lower = response.lower()

        # Map response patterns to actions
        if "action" in response_lower and "plugin" in response_lower:
            return "plugin_action"
        elif "conversation" in response_lower:
            return "conversation"
        elif "multi_action" in response_lower:
            return "multi_step"
        elif "schedule" in response_lower:
            return "schedule_task"
        elif any(word in response_lower for word in ["created", "built", "generated", "wrote"]):
            return "creation"
        elif any(word in response_lower for word in ["searched", "found", "looked up"]):
            return "research"
        else:
            return "general_response"

    def _get_max_future_value(self, state: str) -> float:
        """Get maximum Q-value for state (for Q-learning)."""
        max_value = 0.0
        for key, value in self._policy["action_values"].items():
            if key.startswith(f"{state}:"):
                max_value = max(max_value, value)
        return max_value

    def _learn_adaptation_rules(self):
        """Learn rules for adapting behavior based on patterns."""
        # Analyze success patterns to create adaptation rules
        rules = {}

        for state, patterns in self._policy["success_patterns"].items():
            if len(patterns) >= 3:  # Need multiple examples
                # Find common successful actions for this state
                action_counts = defaultdict(int)
                for pattern in patterns[-10:]:  # Recent patterns
                    action_counts[pattern["action"]] += 1

                best_action = max(action_counts.items(), key=lambda x: x[1])[0]
                rules[state] = {
                    "preferred_action": best_action,
                    "confidence": action_counts[best_action] / len(patterns[-10:]),
                    "last_updated": datetime.now().isoformat()
                }

        self._policy["adaptation_rules"] = rules

    def _get_optimal_action(self, params: dict) -> str:
        """Recommend optimal action based on learned policy."""
        state_features = params.get("state", {})
        available_actions = params.get("available_actions", [])

        if not available_actions:
            return json.dumps({"error": "No available actions provided"})

        state_key = self._get_state_key(state_features)

        # Check learned adaptation rules first
        if state_key in self._policy["adaptation_rules"]:
            rule = self._policy["adaptation_rules"][state_key]
            if rule["preferred_action"] in available_actions and rule["confidence"] > 0.6:
                return json.dumps({
                    "recommended_action": rule["preferred_action"],
                    "confidence": rule["confidence"],
                    "reason": "learned_preference",
                    "state": state_key
                })

        # Fallback to Q-learning values
        best_action = None
        best_value = float('-inf')

        for action in available_actions:
            # Exploration vs exploitation
            if random.random() < self._exploration_rate:
                # Explore: random action
                candidate = random.choice(available_actions)
            else:
                # Exploit: best known action
                candidate = action

            value = self._policy["action_values"].get(f"{state_key}:{candidate}", 0.0)
            if value > best_value:
                best_value = value
                best_action = candidate

        return json.dumps({
            "recommended_action": best_action or available_actions[0],
            "confidence": min(1.0, best_value + 0.5),  # Scale confidence
            "reason": "q_learning",
            "state": state_key
        })

    def _analyze_performance(self) -> str:
        """Analyze learning performance and patterns."""
        total_actions = len(self._policy["action_values"])
        total_states = len(set(key.split(":")[0] for key in self._policy["action_values"].keys()))
        adaptation_rules = len(self._policy["adaptation_rules"])

        success_patterns = sum(len(patterns) for patterns in self._policy["success_patterns"].values())
        failure_patterns = sum(len(patterns) for patterns in self._policy["failure_patterns"].values())

        # Calculate learning statistics
        q_values = list(self._policy["action_values"].values())
        avg_q_value = sum(q_values) / len(q_values) if q_values else 0

        analysis = {
            "total_learned_actions": total_actions,
            "unique_states": total_states,
            "adaptation_rules": adaptation_rules,
            "success_patterns": success_patterns,
            "failure_patterns": failure_patterns,
            "average_q_value": round(avg_q_value, 3),
            "learning_progress": "good" if total_actions > 50 else "developing",
            "last_updated": self._policy.get("last_updated", "never")
        }

        return json.dumps(analysis, indent=2)

    def _reset_learning(self) -> str:
        """Reset all learned knowledge."""
        self._policy = {
            "action_values": defaultdict(float),
            "state_action_counts": defaultdict(int),
            "success_patterns": defaultdict(list),
            "failure_patterns": defaultdict(list),
            "adaptation_rules": {},
            "last_updated": datetime.now().isoformat()
        }
        self._experience_buffer = []
        self._save_policy()

        # Remove experience file
        if EXPERIENCE_FILE.exists():
            EXPERIENCE_FILE.unlink()

        return "Learning progress reset. Starting fresh."

    def _save_experience_buffer(self):
        """Save experience buffer to disk."""
        try:
            EXPERIENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(EXPERIENCE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._experience_buffer, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save experience buffer: {e}")