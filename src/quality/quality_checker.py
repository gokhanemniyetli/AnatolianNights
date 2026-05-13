"""
QualityChecker — orchestrates rule-based + LLM quality checks.
Returns a structured result dict.
"""

import logging

from src.agents.quality_agent import QualityAgent
from src.config.settings import settings
from src.quality.rules import run_all_checks

logger = logging.getLogger(__name__)


class QualityChecker:
    def __init__(self):
        self._agent = QualityAgent()

    def check(self, lyrics: str, city_name: str, concept: dict) -> dict:
        """
        Returns:
        {
            "is_approved": bool,
            "score": float,
            "issues": list[str],
            "rejected_reason": str | None,
            "positive_notes": list[str],
            "reviewer_model": str,
            "rule_failed": bool,
        }
        """
        # Layer 1: fast rule checks
        rules_passed, rule_issues = run_all_checks(lyrics)
        if not rules_passed:
            logger.info("Rule check failed for city=%s: %s", city_name, rule_issues)
            return {
                "is_approved": False,
                "score": 0.0,
                "issues": rule_issues,
                "rejected_reason": "Rule-based filter failed: " + "; ".join(rule_issues),
                "positive_notes": [],
                "reviewer_model": "rules",
                "rule_failed": True,
            }

        # Layer 2: LLM quality review
        result = self._agent.review(lyrics, city_name, concept)
        result["rule_failed"] = False

        threshold = settings.pipeline.quality_threshold
        score = float(result.get("score", 0.0))
        result["is_approved"] = score >= threshold

        if not result["is_approved"] and not result.get("rejected_reason"):
            result["rejected_reason"] = f"Score {score:.1f} below threshold {threshold}"

        logger.info(
            "Quality check city=%s score=%.1f approved=%s",
            city_name,
            score,
            result["is_approved"],
        )
        return result
