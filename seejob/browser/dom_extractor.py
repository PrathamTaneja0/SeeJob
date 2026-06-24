"""DOM extraction for ATS forms — StockFish domReducer port."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from bs4 import BeautifulSoup, Tag

from seejob.browser.interfaces import FormField

_SKIP_PATTERN = re.compile(
    r"dead-link|newsletter|subscribe|cookie|report-modal|signup-modal",
    re.IGNORECASE,
)

EXTRACT_FORM_FIELDS_JS = """
() => {
  const selectors = ['input', 'select', 'textarea'];
  const results = [];

  function buildSelector(el) {
    if (el.id) {
      return `#${CSS.escape(el.id)}`;
    }
    if (el.name) {
      const tag = el.tagName.toLowerCase();
      const nameSelector = `${tag}[name="${el.name}"]`;
      if (document.querySelectorAll(nameSelector).length === 1) {
        return nameSelector;
      }
    }
    const parts = [];
    let current = el;
    while (current && current !== document.body) {
      const parent = current.parentElement;
      if (!parent) break;
      const siblings = Array.from(parent.children);
      const index = siblings.indexOf(current) + 1;
      parts.unshift(`${current.tagName.toLowerCase()}:nth-child(${index})`);
      current = parent;
    }
    return parts.join(' > ');
  }

  for (const tag of selectors) {
    const elements = document.querySelectorAll(tag);
    for (const el of elements) {
      const style = window.getComputedStyle(el);
      if (
        style.display === 'none' ||
        style.visibility === 'hidden' ||
        el.type === 'hidden' ||
        el.getAttribute('aria-hidden') === 'true'
      ) {
        continue;
      }

      const rect = el.getBoundingClientRect();
      if (rect.width < 2 || rect.height < 2) {
        continue;
      }

      const idName = `${el.id || ''} ${el.name || ''}`.toLowerCase();
      const formId = (el.closest('form')?.id || el.closest('[role="dialog"]')?.id || '').toLowerCase();
      if (/dead-link|newsletter|subscribe|cookie|report-modal|signup-modal/.test(`${idName} ${formId}`)) {
        continue;
      }

      const descriptor = {
        tag: el.tagName.toLowerCase(),
        type: el.getAttribute('type') || null,
        name: el.getAttribute('name') || null,
        id: el.getAttribute('id') || null,
        placeholder: el.getAttribute('placeholder') || null,
        ariaLabel: el.getAttribute('aria-label') || null,
        required: el.hasAttribute('required'),
        options: [],
        label: null,
        selector: null,
        currentValue: el.value || null
      };

      if (el.id) {
        const labelEl = document.querySelector(`label[for="${el.id}"]`);
        if (labelEl) {
          descriptor.label = labelEl.textContent.trim();
        }
      }

      if (!descriptor.label) {
        const parentLabel = el.closest('label');
        if (parentLabel) {
          const clone = parentLabel.cloneNode(true);
          const nested = clone.querySelector(tag);
          if (nested) nested.remove();
          descriptor.label = clone.textContent.trim();
        }
      }

      if (el.tagName.toLowerCase() === 'select') {
        const options = el.querySelectorAll('option');
        descriptor.options = Array.from(options).map((opt) => ({
          value: opt.value,
          text: opt.textContent.trim()
        }));
      }

      descriptor.selector = buildSelector(el);
      results.push(descriptor);
    }
  }

  return results;
}
"""


@dataclass
class FieldDescriptor:
    """Raw extracted form field metadata."""

    tag: str
    selector: str
    name: str | None = None
    field_type: str | None = None
    field_id: str | None = None
    placeholder: str | None = None
    aria_label: str | None = None
    label: str | None = None
    required: bool = False
    options: list[dict[str, str]] = field(default_factory=list)
    current_value: str | None = None

    def to_form_field(self) -> FormField:
        return FormField(
            selector=self.selector,
            name=self.name or "",
            field_type=self.field_type or self.tag,
            label=self.label,
            required=self.required,
            options=[o.get("text", o.get("value", "")) for o in self.options],
        )


class _FrameLike(Protocol):
    async def evaluate(self, expression: str) -> Any: ...


def _should_skip_element(el: Tag) -> bool:
    if el.get("type") == "hidden" or el.get("aria-hidden") == "true":
        return True
    style = el.get("style", "")
    if "display:none" in style.replace(" ", "") or "visibility:hidden" in style.replace(" ", ""):
        return True
    id_name = f"{el.get('id', '')} {el.get('name', '')}".lower()
    form = el.find_parent("form")
    form_id = (form.get("id", "") if form else "").lower()
    return bool(_SKIP_PATTERN.search(f"{id_name} {form_id}"))


def _build_selector(el: Tag, soup: BeautifulSoup) -> str:
    if el.get("id"):
        return f"#{el['id']}"
    if el.get("name"):
        tag = el.name
        name_selector = f'{tag}[name="{el["name"]}"]'
        if len(soup.select(name_selector)) == 1:
            return name_selector
    parts: list[str] = []
    current: Tag | None = el
    while current and current.name != "[document]" and current.name != "body":
        parent = current.parent
        if not parent or not hasattr(parent, "children"):
            break
        siblings = [c for c in parent.children if isinstance(c, Tag)]
        index = siblings.index(current) + 1
        parts.insert(0, f"{current.name}:nth-child({index})")
        current = parent if isinstance(parent, Tag) else None
    return " > ".join(parts)


def _resolve_label(el: Tag, soup: BeautifulSoup) -> str | None:
    field_id = el.get("id")
    if field_id:
        label_el = soup.find("label", attrs={"for": field_id})
        if label_el:
            return label_el.get_text(strip=True)
    parent_label = el.find_parent("label")
    if parent_label:
        clone = BeautifulSoup(str(parent_label), "html.parser").find("label")
        if clone:
            nested = clone.find(el.name)
            if nested:
                nested.decompose()
            text = clone.get_text(strip=True)
            return text or None
    return None


def extract_fields_from_html(html: str) -> list[FieldDescriptor]:
    """Extract visible form fields from static HTML (for unit tests)."""
    soup = BeautifulSoup(html, "html.parser")
    results: list[FieldDescriptor] = []

    for tag_name in ("input", "select", "textarea"):
        for el in soup.find_all(tag_name):
            if not isinstance(el, Tag) or _should_skip_element(el):
                continue

            options: list[dict[str, str]] = []
            if tag_name == "select":
                for opt in el.find_all("option"):
                    options.append(
                        {
                            "value": opt.get("value", ""),
                            "text": opt.get_text(strip=True),
                        }
                    )

            results.append(
                FieldDescriptor(
                    tag=tag_name,
                    field_type=el.get("type"),
                    name=el.get("name"),
                    field_id=el.get("id"),
                    placeholder=el.get("placeholder"),
                    aria_label=el.get("aria-label"),
                    required=el.has_attr("required"),
                    label=_resolve_label(el, soup),
                    options=options,
                    current_value=el.get("value"),
                    selector=_build_selector(el, soup),
                )
            )

    return results


def format_fields_for_llm(fields: list[FieldDescriptor]) -> str:
    """Format field descriptors into minimized LLM text."""
    if not fields:
        return "No interactive form fields found on this page."

    lines = ["FORM FIELDS DETECTED:", ""]
    for i, f in enumerate(fields, start=1):
        parts = [f"[{i}] <{f.tag}>"]
        if f.field_type:
            parts.append(f'type="{f.field_type}"')
        if f.label:
            parts.append(f'label="{f.label}"')
        if f.placeholder:
            parts.append(f'placeholder="{f.placeholder}"')
        if f.aria_label:
            parts.append(f'aria-label="{f.aria_label}"')
        if f.name:
            parts.append(f'name="{f.name}"')
        if f.required:
            parts.append("[REQUIRED]")
        parts.append(f'selector="{f.selector}"')
        lines.append(" | ".join(parts))

        if f.options:
            option_texts = [
                f'"{o["text"]}" (value: {o["value"]})'
                for o in f.options
                if o.get("value", "") != ""
            ]
            if option_texts:
                lines.append(f"    Options: {', '.join(option_texts)}")
        if f.current_value:
            lines.append(f'    Current value: "{f.current_value}"')

    return "\n".join(lines)


async def extract_form_fields(context: _FrameLike) -> list[FieldDescriptor]:
    """Extract form fields from a Playwright page or frame via evaluate."""
    raw = await context.evaluate(EXTRACT_FORM_FIELDS_JS)
    return [
        FieldDescriptor(
            tag=item["tag"],
            field_type=item.get("type"),
            name=item.get("name"),
            field_id=item.get("id"),
            placeholder=item.get("placeholder"),
            aria_label=item.get("ariaLabel"),
            required=bool(item.get("required")),
            label=item.get("label"),
            options=item.get("options") or [],
            current_value=item.get("currentValue"),
            selector=item["selector"],
        )
        for item in raw
    ]


@dataclass
class ReduceDOMResult:
    """DOM reduction output with optional iframe context."""

    fields: list[FieldDescriptor]
    formatted: str
    form_context: Any = None


async def reduce_dom(page: Any) -> ReduceDOMResult:
    """Extract fields from page, falling back to iframe with most fields."""
    fields = await extract_form_fields(page)
    form_context: Any = page

    if not fields:
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                frame_fields = await extract_form_fields(frame)
                if len(frame_fields) > len(fields):
                    fields = frame_fields
                    form_context = frame
            except Exception:
                continue

    return ReduceDOMResult(
        fields=fields,
        formatted=format_fields_for_llm(fields),
        form_context=form_context,
    )


def screening_textareas(fields: list[FieldDescriptor]) -> list[FieldDescriptor]:
    """Return screening question textareas (label > 10 chars)."""
    return [
        f
        for f in fields
        if f.tag == "textarea"
        and f.label
        and len(f.label) > 10
        and f.field_type != "file"
    ]
