# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from .errors import LLMProviderError, LLMResponseError
from .models import BlockTarget, ExtractedDocument, ResourceDecision
from .utils import safe_filename

# Canonical system prompt used by every provider. Previously the OpenAI path
# inlined a detailed version and the Claude path used a 4-line stub, which made
# Claude's classifications materially weaker. Keep this as the single source of
# truth.
SYSTEM_PROMPT = """You are classifying technical resources for the CubeSat Resources MkDocs site.

Return only valid JSON matching this structure:

{
"title": "Human-readable document title",
"resource_type": "datasheet | user_guide | standard | paper | report | manual | presentation | repository | website | tool | dataset | documentation | other",
"publisher": "Publisher or organization, if known",
"author": "Author or person/team responsible, if known",
"year": 2026,
"suggested_filename": "slug-safe-filename-with-original-extension.pdf",
"placement_type": "existing_block | new_block_requested | new_page_requested",

"target_block_id": "existing-block-id-or-null",
"target_markdown_file": "docs/path/file.md",

"suggested_parent_file": "docs/path/existing-page.md",
"suggested_parent_heading": "Exact existing heading under which the new block should be inserted",
"suggested_heading": "Reusable category heading if requesting a new block, like Solar Cell Datasheets, or Linux SDR Software, or TVAC Testing Procedures, or EMC Simulation Tools, Open Source CubeSat Projects, or University CubeSat Missions",
"suggested_block_id": "slug-safe-block-id-if-requesting-new-block-or-page",

"suggested_path": "docs/path/new-page.md",
"suggested_nav_title": "Navigation title if requesting a new page",

"description": "Short description, 4 to 12 words",
"tags": ["tag1", "tag2"],
"confidence": 0.0,
"reason": "Brief reason for placement"
}

Rules:
- Prefer existing blocks when a good fit exists.
- For placement_type existing_block, use exactly one provided block_id and file.
- For placement_type new_block_requested, provide suggested_parent_file, suggested_heading, and suggested_block_id.
- For placement_type new_page_requested, provide suggested_path, suggested_nav_title, and suggested_block_id.
- Do not invent arbitrary filesystem paths.
- Use candidate_sections when suggesting new blocks or pages.
- Use publisher for organizations that publish or host the resource.
- Use author for named people, teams, or project maintainers, if known.
- Use slug-safe lowercase filenames.
- Preserve the original file extension in suggested_filename.
- Keep descriptions short, neutral, and useful.
- Use repository for GitHub, GitLab, Codeberg, or similar source-code/hardware repositories.
- Use website for general websites or landing pages.
- Use documentation for docs sites, wikis, or structured online documentation.
- Use tool for calculators, web apps, scripts, or utilities.
- Use dataset for downloadable or browsable data collections.
- Return JSON only. No Markdown. No explanation outside the JSON.
- suggested_block_id must describe the resource category, not the individual document.
- Never include publisher names, product names, part numbers, percentages, model numbers, or document titles in suggested_block_id.
- For datasheets, use broad category names such as solar-cell-datasheets, battery-datasheets, radio-module-datasheets, sensor-datasheets, or regulator-datasheets.
- When requesting a new block, choose the most relevant existing section as suggested_parent_file and suggested_heading.
- suggested_heading should be a reusable category heading, not the document title.
- For a new block under an existing H2 section, suggest an H3-style category heading.
- Never put a new block at the very end below the footnotes.
- For repository resources, resource_type may be repository, but suggested_heading and suggested_block_id should describe the broader reusable category, not merely "repositories".
- Prefer category names like tools, software, libraries, simulators, calculators, datasets, guides, or datasheets depending on what future related resources would share.
- If maintainer_hint is present, treat it as authoritative guidance from the site maintainer about type, publisher, or placement.
"""


# Number of LLM call attempts including the first. Two means: one initial
# attempt, then one retry with the validation error fed back to the model.
MAX_ATTEMPTS = 2


class LLMClassifier:
    def __init__(self, provider: str, model: str):
        self.provider = provider.lower()
        self.model = model
        if self.provider not in {"openai", "claude", "anthropic"}:
            raise LLMProviderError(f"Unsupported CSR_LLM_PROVIDER: {self.provider}")

    def classify(
        self,
        document: ExtractedDocument,
        blocks: list[BlockTarget],
        candidate_sections: list[dict[str, Any]],
        notify: Callable[[str], None] | None = None,
    ) -> ResourceDecision:
        """Classify a document, retrying once on JSON/schema validation failure.

        ``notify`` is an optional callback invoked on retry with a short human
        readable message. It exists so the classifier stays free of UI library
        dependencies while still allowing the CLI to surface retry events.
        """
        payload = self._payload(document, blocks, candidate_sections)
        last_error: str | None = None

        for attempt in range(MAX_ATTEMPTS):
            try:
                if self.provider == "openai":
                    raw = self._classify_openai(payload, retry_context=last_error)
                else:  # claude / anthropic (validated in __init__)
                    raw = self._classify_claude(payload, retry_context=last_error)

                decision = ResourceDecision.model_validate(raw)
                decision.suggested_filename = safe_filename(decision.suggested_filename, document.extension)
                return decision

            except (json.JSONDecodeError, ValidationError) as e:
                last_error = str(e)
                if attempt + 1 >= MAX_ATTEMPTS:
                    raise LLMResponseError(f"LLM returned invalid output after {MAX_ATTEMPTS} attempts: {e}") from e
                if notify is not None:
                    notify(
                        f"LLM returned invalid output (attempt {attempt + 1}/{MAX_ATTEMPTS}), "
                        "retrying with error feedback..."
                    )

        raise AssertionError("unreachable: retry loop returns or raises")

    def _payload(
        self,
        document: ExtractedDocument,
        blocks: list[BlockTarget],
        candidate_sections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "document": {
                "original": document.source.original,
                "source_url": document.source.source_url,
                "title_hint": document.title_hint,
                "extension": document.extension,
                "size_bytes": document.size_bytes,
                "sha256": document.sha256,
                "metadata": document.metadata,
                "content_excerpt": document.content_excerpt,
            },
            # Free-text nudge from the user (`--hint` or `:: hint` in a list file).
            "maintainer_hint": document.hint,
            "available_blocks": [b.model_dump() for b in blocks],
            "candidate_sections": candidate_sections[:250],
            "allowed_schema": {
                "placement_type": ["existing_block", "new_block_requested", "new_page_requested"],
                "notes": [
                    "existing_block requires target_block_id and target_markdown_file",
                    "new_block_requested requires suggested_parent_file, suggested_heading, suggested_block_id",
                    "new_page_requested requires suggested_path, suggested_nav_title, suggested_block_id",
                ],
            },
        }

    def _user_message(self, payload: dict[str, Any], retry_context: str | None) -> str:
        """Build the user message, optionally appending retry feedback."""
        body = json.dumps(payload, ensure_ascii=False)
        if retry_context is None:
            return body
        return (
            body
            + "\n\nYour previous response failed validation with this error:\n"
            + retry_context
            + "\n\nReturn strict JSON matching the schema. No prose, no Markdown."
        )

    def _classify_openai(self, payload: dict[str, Any], retry_context: str | None = None) -> dict[str, Any]:
        from openai import OpenAI

        if not os.getenv("OPENAI_API_KEY"):
            raise LLMProviderError("OPENAI_API_KEY is required for CSR_LLM_PROVIDER=openai")

        client = OpenAI()
        response = client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self._user_message(payload, retry_context)},
            ],
        )

        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    def _classify_claude(self, payload: dict[str, Any], retry_context: str | None = None) -> dict[str, Any]:
        import anthropic

        if not os.getenv("ANTHROPIC_API_KEY"):
            raise LLMProviderError("ANTHROPIC_API_KEY is required for CSR_LLM_PROVIDER=claude")

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=self.model,
            max_tokens=2000,
            temperature=0.2,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": self._user_message(payload, retry_context)},
            ],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        return json.loads(text)
