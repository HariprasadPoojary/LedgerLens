"""
Rules store — persistent categorization rules backed by data/rules.json.

Priority: data/rules.json (user customized) → const.py (defaults)

Any time the user edits rules via the UI, they're saved here.
The categorizer always reads from here, so changes take effect immediately
on the next analysis run without restarting the server.
"""

import json
import re
from pathlib import Path

from app.const import CATEGORY_RULES
from app.rule_patterns import pattern_to_regex

DATA_DIR = Path(__file__).parent.parent / "data"
RULES_FILE = DATA_DIR / "rules.json"


def get_rules() -> list[tuple[str, list[str], str]]:
    """
    Return current rules as list of (category, patterns, txn_type).
    Reads from rules.json if it exists, otherwise falls back to const.py.
    """
    if RULES_FILE.exists():
        try:
            raw = json.loads(RULES_FILE.read_text(encoding="utf-8"))
            return [(r["category"], r["patterns"], r["txn_type"]) for r in raw]
        except Exception as e:
            print(f"[rules_store] Failed to load rules.json, using defaults: {e}")
    return CATEGORY_RULES


def get_rules_as_dicts() -> list[dict]:
    """Return rules as list of dicts — for JSON API responses."""
    return [{"category": c, "patterns": p, "txn_type": t} for c, p, t in get_rules()]


def get_category_names() -> list[str]:
    """Return sorted list of unique category names."""
    return sorted({c for c, _, _ in get_rules()})


def save_rules(rules: list[dict]) -> None:
    """
    Persist rules to data/rules.json.
    rules: list of {"category": str, "patterns": [str], "txn_type": str}
    """
    if not isinstance(rules, list):
        raise ValueError("Rules must be a list.")

    normalized: list[dict[str, str | list[str]]] = []
    for index, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            raise ValueError(f"Rule {index} must be an object.")
        category = rule.get("category")
        if not isinstance(category, str) or not category.strip():
            raise ValueError(f"Rule {index} must have a non-empty category.")
        patterns = rule.get("patterns", [])
        if not isinstance(patterns, list) or any(not isinstance(p, str) for p in patterns):
            raise ValueError(f"Patterns for rule '{category}' must be a list of strings.")
        for pattern in patterns:
            try:
                pattern_to_regex(pattern)
            except (re.error, ValueError, TypeError) as error:
                raise ValueError(
                    f"Rule '{category}' has invalid pattern '{pattern}': {error}"
                ) from None
        txn_type = rule.get("txn_type", "both")
        if txn_type not in ("credit", "debit", "both"):
            txn_type = "both"
        normalized.append(
            {"category": category.strip(), "patterns": patterns, "txn_type": txn_type}
        )

    DATA_DIR.mkdir(exist_ok=True)
    RULES_FILE.write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def reset_to_defaults() -> None:
    """Delete rules.json, reverting to const.py defaults."""
    if RULES_FILE.exists():
        RULES_FILE.unlink()
