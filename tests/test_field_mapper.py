"""Unit tests for field mapper JSON parsing and rule-based fallback."""

import json

import pytest

from seejob.browser.field_mapper import (
    MockFieldMapper,
    parse_mapping_json,
    rule_based_field_map,
)


def test_parse_mapping_json_plain() -> None:
    raw = json.dumps({"#email": "a@b.com", "#name": "Jane Doe"})
    assert parse_mapping_json(raw) == {"#email": "a@b.com", "#name": "Jane Doe"}


def test_parse_mapping_json_strips_markdown_fence() -> None:
    raw = '```json\n{"#email": "a@b.com"}\n```'
    assert parse_mapping_json(raw) == {"#email": "a@b.com"}


def test_parse_mapping_json_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        parse_mapping_json('["not", "a", "dict"]')


def test_rule_based_field_map_matches_keywords() -> None:
    dom = """
FORM FIELDS DETECTED:

[1] <input> | type="email" | label="Email" | name="email" | selector="#email"
[2] <input> | type="text" | label="Full Name" | name="name" | selector="#name"
[3] <input> | type="tel" | label="Phone" | name="phone" | selector="#phone"
"""
    profile = {
        "email": "jane@example.com",
        "full_name": "Jane Doe",
        "phone": "+1-555-0100",
    }
    mapping = rule_based_field_map(dom, profile)

    assert mapping["#email"] == "jane@example.com"
    assert mapping["#name"] == "Jane Doe"
    assert mapping["#phone"] == "+1-555-0100"


@pytest.mark.asyncio
async def test_mock_field_mapper_uses_rule_based() -> None:
    dom = '[1] <input> | type="email" | label="Email" | selector="#email"'
    profile = {"email": "test@example.com"}
    mapper = MockFieldMapper()
    result = await mapper.map_fields(dom, profile)
    assert result["#email"] == "test@example.com"
