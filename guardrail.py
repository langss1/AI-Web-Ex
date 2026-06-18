"""
=============================================================
ANTI-LOOPING GUARDRAIL
=============================================================
Intercepts duplicate or previously-failed payloads before
they reach the Action Layer.
Operates at Orchestrator level — checks against PCB history.
=============================================================
"""

import logging
from memory_system import MemorySystem

log = logging.getLogger(__name__)


class AntiLoopingGuardrail:
    def __init__(self, memory: MemorySystem):
        self.memory = memory
        self._blocked_count = 0

    def is_duplicate(self, vuln_type: str, payload: str) -> bool:
        """
        Returns True (BLOCK) if:
          1. Exact payload already in PCB, OR
          2. Payload is a close variant (trimmed match)
        """
        if not payload or not payload.strip():
            return False

        existing = self.memory.get_all_payloads(vuln_type)
        payload_normalized = payload.strip().lower()

        for past in existing:
            if past.strip().lower() == payload_normalized:
                self._blocked_count += 1
                log.warning(
                    f"[Block] GUARDRAIL #{self._blocked_count}: "
                    f"Duplicate payload detected → '{payload[:60]}'"
                )
                return True

        return False

    def is_blocked(self, vuln_type: str, payload: str, strategy_category: str) -> bool:
        if self.is_duplicate(vuln_type, payload):
            return True
            
        history = self.memory.get_pcb(vuln_type)
        if len(history) >= 3:
            recent_strategies = [entry.get("strategy_category", "") for entry in history[-3:]]
            recent_behaviors = [entry.get("behavior", {}).get("outcome", "") for entry in history[-3:]]
            
            if all(s == strategy_category for s in recent_strategies) and all(b in ("failed", "blocked") for b in recent_behaviors):
                self._blocked_count += 1
                log.warning(f"[Block] GUARDRAIL #{self._blocked_count}: Stagnation detected on strategy '{strategy_category}'. Forcing new strategy.")
                return True
                
        return False

    def get_untried_strategies(self, vuln_type: str) -> list:
        all_sqli_strategies = ["union_based", "error_based", "boolean_blind", "time_blind", "auth_bypass"]
        all_xss_strategies = ["reflected_basic", "stored_xss", "event_handler_bypass", "case_variation_bypass", "encoding_bypass"]
        
        target_list = all_sqli_strategies if vuln_type == "sqli" else all_xss_strategies
        
        history = self.memory.get_pcb(vuln_type)
        tried_strategies = set(entry.get("strategy_category", "") for entry in history)
        
        untried = [s for s in target_list if s not in tried_strategies]
        if not untried:
            return target_list
        return untried

    @property
    def blocked_count(self) -> int:
        return self._blocked_count
