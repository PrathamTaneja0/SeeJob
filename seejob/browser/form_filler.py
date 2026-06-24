"""Deterministic Playwright form fill by field type."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FIELD_DELAY_MS = 150


@dataclass
class FillOptions:
    """Paths for heuristic file uploads."""

    resume_path: Path | None = None
    cover_letter_path: Path | None = None


@dataclass
class FillFormResult:
    """Summary of a fill operation."""

    filled: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def fields_filled(self) -> int:
        return len(self.filled)


async def fill_form(
    page: Any,
    mapping: dict[str, str],
    *,
    options: FillOptions | None = None,
) -> FillFormResult:
    """Fill form fields using selector→value mapping with 150ms inter-field delay."""
    opts = options or FillOptions()
    results = FillFormResult()

    for selector, value in mapping.items():
        try:
            element = await page.query_selector(selector)
            if element is None:
                results.skipped.append(selector)
                continue

            tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
            input_type = await element.evaluate("el => el.getAttribute('type') || ''")

            if tag_name == "select":
                await _fill_select(page, selector, value)
            elif tag_name == "textarea":
                await _fill_textarea(page, selector, value)
            elif tag_name == "input":
                if input_type in ("checkbox", "radio"):
                    await _fill_checkbox_or_radio(page, selector, value, input_type)
                elif input_type == "file":
                    uploaded = await _upload_file_for_input(page, selector, opts)
                    if uploaded:
                        results.filled.append(selector)
                    else:
                        results.skipped.append(selector)
                    await page.wait_for_timeout(FIELD_DELAY_MS)
                    continue
                else:
                    await _fill_text_input(page, selector, value)
            else:
                await _fill_text_input(page, selector, value)

            results.filled.append(selector)
            await page.wait_for_timeout(FIELD_DELAY_MS)
        except Exception as exc:
            logger.debug("Failed to fill %s: %s", selector, exc)
            results.failed.append(selector)

    await _upload_unmapped_file_inputs(page, mapping, opts, results)
    return results


async def _fill_text_input(page: Any, selector: str, value: str) -> None:
    await page.click(selector, timeout=5000)
    await page.fill(selector, "")
    await page.fill(selector, str(value))


async def _fill_textarea(page: Any, selector: str, value: str) -> None:
    await page.click(selector, timeout=5000)
    await page.fill(selector, "")
    await page.fill(selector, str(value))


async def _fill_select(page: Any, selector: str, value: str) -> None:
    try:
        await page.select_option(selector, value, timeout=5000)
    except Exception:
        await page.select_option(selector, label=value, timeout=5000)


async def _fill_checkbox_or_radio(page: Any, selector: str, value: str, input_type: str) -> None:
    should_check = value.lower() == "true"
    if input_type == "checkbox":
        if should_check:
            await page.check(selector, timeout=5000)
        else:
            await page.uncheck(selector, timeout=5000)
    else:
        await page.check(selector, timeout=5000)

async def _get_file_input_context(page: Any, selector: str) -> str:
    return await page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          if (!el) return '';
          const id = el.id || '';
          let label = '';
          if (id) {
            const labelEl = document.querySelector(`label[for="${id}"]`);
            if (labelEl) label = labelEl.textContent || '';
          }
          if (!label) {
            const parent = el.closest('label');
            if (parent) label = parent.textContent || '';
          }
          const aria = el.getAttribute('aria-label') || '';
          const name = el.getAttribute('name') || '';
          return `${label} ${aria} ${name}`.toLowerCase();
        }""",
        selector,
    )


async def _upload_file_for_input(page: Any, selector: str, options: FillOptions) -> bool:
    context = await _get_file_input_context(page, selector)
    file_path: Path | None = None

    if re.search(r"resume|cv|curriculum", context):
        file_path = options.resume_path
    elif re.search(r"cover|letter", context):
        file_path = options.cover_letter_path
    elif options.resume_path and options.resume_path.exists():
        file_path = options.resume_path

    if file_path is None or not file_path.exists():
        return False

    await page.set_input_files(selector, str(file_path))
    return True


async def _upload_unmapped_file_inputs(
    page: Any,
    mapping: dict[str, str],
    options: FillOptions,
    results: FillFormResult,
) -> None:
    mapped = set(mapping.keys())
    handles = await page.query_selector_all('input[type="file"]')

    for handle in handles:
        selector = await handle.evaluate(
            """el => {
              if (el.id) return `#${CSS.escape(el.id)}`;
              if (el.name) return `input[type="file"][name="${el.name}"]`;
              return null;
            }"""
        )
        if not selector or selector in mapped:
            continue
        try:
            if await _upload_file_for_input(page, selector, options):
                results.filled.append(selector)
        except Exception:
            results.failed.append(selector)


async def submit_form(page: Any) -> bool:
    """Try common submit button patterns. Returns True if a click was attempted."""
    selectors = [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Submit")',
        'button:has-text("Apply")',
        'input[value="Submit"]',
        'input[value="Apply"]',
    ]
    for selector in selectors:
        el = await page.query_selector(selector)
        if el is not None:
            await el.click(timeout=5000)
            return True
    return False
