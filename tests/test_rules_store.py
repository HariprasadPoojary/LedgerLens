"""
Tests for app/rules_store.py

Covers:
  - get_rules: fallback to const.py, load from json
  - get_rules_as_dicts: shape and types
  - get_category_names: sorted, unique
  - save_rules: persists to json, validates input
  - reset_to_defaults: deletes rules.json
"""

import json

import pytest

from app.const import CATEGORY_RULES
from app.rules_store import (
    get_category_names,
    get_rules,
    get_rules_as_dicts,
    reset_to_defaults,
    save_rules,
)

# ── get_rules ─────────────────────────────────────────────────────────────────


class TestGetRules:

    def test_returns_list_of_tuples(self, tmp_rules_file):
        rules = get_rules()
        assert isinstance(rules, list)
        assert all(isinstance(r, tuple) and len(r) == 3 for r in rules)

    def test_fallback_to_const_when_no_json(self, tmp_rules_file):
        # No rules.json exists → should return CATEGORY_RULES from const.py
        rules = get_rules()
        assert rules == CATEGORY_RULES

    def test_loads_from_json_when_exists(self, tmp_rules_file):
        custom = [{"category": "TestCat", "patterns": ["testpayee"], "txn_type": "debit"}]
        (tmp_rules_file / "rules.json").write_text(json.dumps(custom))
        rules = get_rules()
        assert len(rules) == 1
        assert rules[0][0] == "TestCat"
        assert rules[0][1] == ["testpayee"]
        assert rules[0][2] == "debit"

    def test_falls_back_on_corrupt_json(self, tmp_rules_file):
        (tmp_rules_file / "rules.json").write_text("not valid json {{")
        rules = get_rules()
        # Should fall back to const.py defaults without raising
        assert rules == CATEGORY_RULES


# ── get_rules_as_dicts ────────────────────────────────────────────────────────


class TestGetRulesAsDicts:

    def test_returns_list_of_dicts(self, tmp_rules_file):
        rules = get_rules_as_dicts()
        assert isinstance(rules, list)
        assert all(isinstance(r, dict) for r in rules)

    def test_dicts_have_required_keys(self, tmp_rules_file):
        for rule in get_rules_as_dicts():
            assert "category" in rule
            assert "patterns" in rule
            assert "txn_type" in rule

    def test_patterns_is_list(self, tmp_rules_file):
        for rule in get_rules_as_dicts():
            assert isinstance(rule["patterns"], list)

    def test_txn_type_valid_values(self, tmp_rules_file):
        valid = {"credit", "debit", "both"}
        for rule in get_rules_as_dicts():
            assert rule["txn_type"] in valid


# ── get_category_names ────────────────────────────────────────────────────────


class TestGetCategoryNames:

    def test_returns_sorted_list(self, tmp_rules_file):
        names = get_category_names()
        assert names == sorted(names)

    def test_no_duplicates(self, tmp_rules_file):
        names = get_category_names()
        assert len(names) == len(set(names))

    def test_returns_strings(self, tmp_rules_file):
        assert all(isinstance(n, str) for n in get_category_names())

    def test_reflects_custom_rules(self, tmp_rules_file):
        custom = [
            {"category": "Alpha", "patterns": [], "txn_type": "both"},
            {"category": "Beta", "patterns": [], "txn_type": "both"},
        ]
        save_rules(custom)
        names = get_category_names()
        assert "Alpha" in names
        assert "Beta" in names


# ── save_rules ────────────────────────────────────────────────────────────────


class TestSaveRules:

    def test_creates_rules_json(self, tmp_rules_file):
        save_rules([{"category": "Test", "patterns": ["foo"], "txn_type": "both"}])
        assert (tmp_rules_file / "rules.json").exists()

    def test_persisted_rules_loadable(self, tmp_rules_file):
        rules = [
            {"category": "Dining", "patterns": ["Zomato", "Swiggy"], "txn_type": "debit"},
            {"category": "Income", "patterns": ["salary"], "txn_type": "credit"},
        ]
        save_rules(rules)
        loaded = get_rules()
        assert len(loaded) == 2
        assert loaded[0][0] == "Dining"
        assert "Zomato" in loaded[0][1]

    def test_empty_patterns_allowed(self, tmp_rules_file):
        save_rules([{"category": "Empty", "patterns": [], "txn_type": "both"}])
        loaded = get_rules()
        assert loaded[0][1] == []

    def test_missing_category_raises(self, tmp_rules_file):
        with pytest.raises(ValueError, match="category"):
            save_rules([{"category": "", "patterns": [], "txn_type": "both"}])

    def test_invalid_patterns_type_raises(self, tmp_rules_file):
        with pytest.raises(ValueError, match="[Pp]attern"):
            save_rules([{"category": "X", "patterns": "not-a-list", "txn_type": "both"}])

    def test_non_string_pattern_raises_with_rule_name(self, tmp_rules_file):
        with pytest.raises(ValueError, match="Patterns for rule 'Dining'"):
            save_rules([{"category": "Dining", "patterns": [42], "txn_type": "debit"}])

    def test_invalid_regex_raises_with_rule_and_pattern(self, tmp_rules_file):
        with pytest.raises(ValueError, match="Dining.*re:\[invalid"):
            save_rules([{"category": "Dining", "patterns": ["re:[invalid"], "txn_type": "debit"}])

    def test_invalid_save_does_not_overwrite_existing_rules(self, tmp_rules_file):
        existing = [{"category": "Dining", "patterns": ["Cafe"], "txn_type": "debit"}]
        save_rules(existing)
        with pytest.raises(ValueError):
            save_rules([{"category": "Dining", "patterns": ["re:[invalid"], "txn_type": "debit"}])
        assert get_rules_as_dicts() == existing

    def test_invalid_txn_type_defaults_to_both(self, tmp_rules_file):
        save_rules([{"category": "X", "patterns": [], "txn_type": "invalid"}])
        loaded = get_rules()
        assert loaded[0][2] == "both"

    def test_json_is_human_readable(self, tmp_rules_file):
        save_rules([{"category": "Test", "patterns": ["foo"], "txn_type": "debit"}])
        raw = (tmp_rules_file / "rules.json").read_text()
        # Should be pretty-printed (indented)
        assert "\n" in raw

    def test_unicode_category_names(self, tmp_rules_file):
        save_rules([{"category": "食費", "patterns": ["スーパー"], "txn_type": "debit"}])
        loaded = get_rules()
        assert loaded[0][0] == "食費"


# ── reset_to_defaults ─────────────────────────────────────────────────────────


class TestResetToDefaults:

    def test_deletes_rules_json(self, tmp_rules_file):
        save_rules([{"category": "X", "patterns": [], "txn_type": "both"}])
        assert (tmp_rules_file / "rules.json").exists()
        reset_to_defaults()
        assert not (tmp_rules_file / "rules.json").exists()

    def test_after_reset_falls_back_to_const(self, tmp_rules_file):
        save_rules([{"category": "CustomOnly", "patterns": [], "txn_type": "both"}])
        reset_to_defaults()
        rules = get_rules()
        cats = [r[0] for r in rules]
        assert "CustomOnly" not in cats
        assert "Income" in cats  # from const.py

    def test_reset_when_no_file_is_noop(self, tmp_rules_file):
        # Should not raise if file doesn't exist
        reset_to_defaults()  # no error
