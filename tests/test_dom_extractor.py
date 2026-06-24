"""Unit tests for DOM extractor on HTML fixtures."""

from seejob.browser.dom_extractor import (
    extract_fields_from_html,
    format_fields_for_llm,
    screening_textareas,
)

SIMPLE_FORM_HTML = """
<html><body>
<form id="application-form">
  <label for="email">Email Address</label>
  <input type="email" id="email" name="email" required placeholder="you@example.com" />
  <label for="name">Full Name</label>
  <input type="text" id="name" name="name" required />
  <input type="hidden" name="csrf" value="abc" />
  <select name="country" id="country">
    <option value="">Select</option>
    <option value="US">United States</option>
    <option value="DE">Germany</option>
  </select>
  <label for="cover">Why do you want to work here?</label>
  <textarea id="cover" name="cover"></textarea>
</form>
<div id="newsletter-signup-modal">
  <input type="email" name="subscribe" id="subscribe" />
</div>
</body></html>
"""


def test_extract_visible_fields_skips_hidden_and_newsletter() -> None:
    fields = extract_fields_from_html(SIMPLE_FORM_HTML)
    selectors = {f.selector for f in fields}
    names = {f.name for f in fields}

    assert "#email" in selectors
    assert "#name" in selectors
    assert "select[name=\"country\"]" in selectors or "#country" in selectors
    assert "csrf" not in names
    assert "subscribe" not in names


def test_format_fields_for_llm_includes_selectors() -> None:
    fields = extract_fields_from_html(SIMPLE_FORM_HTML)
    text = format_fields_for_llm(fields)

    assert "FORM FIELDS DETECTED" in text
    assert 'selector="#email"' in text
    assert "[REQUIRED]" in text
    assert "United States" in text


def test_screening_textareas_filters_by_label_length() -> None:
    fields = extract_fields_from_html(SIMPLE_FORM_HTML)
    screening = screening_textareas(fields)

    assert len(screening) == 1
    assert screening[0].name == "cover"
    assert screening[0].label is not None
    assert len(screening[0].label) > 10


def test_empty_html_returns_no_fields_message() -> None:
    assert "No interactive" in format_fields_for_llm([])
