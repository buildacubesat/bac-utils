# SPDX-License-Identifier: MIT
"""Output formats.

``terminal``
    The BAC terminal profile: opening panel, one step line per rule, a
    rule-based summary table, a result block with the verdict.
``report``
    Plain text designed to be pasted into a review or an LLM session
    unchanged: one ``--- CHECK … --- END`` section per rule with
    ``path:line:text`` findings, then a summary and a verdict. This is the
    format the shell version produced.
``tsv``
    One row per finding: id, severity, path, line, text. Notes have empty
    path and line.

Hit counts are always the full count; ``max_hits`` only limits how many
lines are printed.
"""

from __future__ import annotations

from dataclasses import dataclass

from bac_common import ui

from .engine import RuleResult

MAX_COLS = 200


@dataclass(slots=True)
class RunMeta:
    tool: str
    version: str
    run_utc: str
    root: str
    files: int
    source: str
    rule_sets: list[str]


def blocking_count(results: list[RuleResult]) -> int:
    return sum(r.count for r in results if r.rule.severity == "blocking")


def advisory_count(results: list[RuleResult]) -> int:
    return sum(r.count for r in results if r.rule.severity == "advisory")


def error_count(results: list[RuleResult]) -> int:
    return sum(1 for r in results if r.error)


def verdict(results: list[RuleResult]) -> str:
    blocking = blocking_count(results)
    errors = error_count(results)
    parts: list[str] = []
    if blocking:
        parts.append(f"{blocking} blocking finding(s)")
    if errors:
        parts.append(f"{errors} rule error(s)")
    return ", ".join(parts) if parts else "clean, no blocking findings"


def _clip(text: str) -> str:
    return text if len(text) <= MAX_COLS else text[:MAX_COLS] + "…"


def _hit_lines(result: RuleResult, max_hits: int) -> list[str]:
    lines: list[str] = []
    for i, hit in enumerate(result.hits):
        if max_hits and i >= max_hits:
            lines.append(f"note: output truncated at {max_hits} hits ({result.count - max_hits} more)")
            break
        lines.append(_clip(f"{hit.path}:{hit.line}:{hit.text}"))
    return lines


# ---------------------------------------------------------------------------
# report (plain)
# ---------------------------------------------------------------------------


def render_report(results: list[RuleResult], meta: RunMeta, max_hits: int) -> str:
    out: list[str] = [
        f"=== {ui.header(meta.tool, meta.version)}",
        f"run_utc: {meta.run_utc}",
        f"root: {meta.root}",
        f"files: {meta.files} ({meta.source})",
        f"rules: {', '.join(meta.rule_sets)}",
        "format: one section per check, delimited by --- CHECK and --- END.",
        "        result lines are path:line:text. lines prefixed 'note:' are commentary,",
        "        not findings. 'hits: 0' means the check passed.",
        "",
    ]
    for r in results:
        out.append(f"--- CHECK {r.rule.id} | {r.rule.severity} | {r.rule.title}")
        out.append(f"hits: {r.count}")
        if r.error:
            out.append(f"note: rule error: {r.error}")
        out.extend(f"note: {n}" for n in r.notes)
        out.extend(_hit_lines(r, max_hits))
        out.append(f"--- END {r.rule.id}")
        out.append("")
    out.append("=== SUMMARY")
    out.append(f"{'ID':<4} {'SEVERITY':<9} {'HITS':<6} TITLE")
    for r in results:
        hits = "error" if r.error else str(r.count)
        out.append(f"{r.rule.id:<4} {r.rule.severity:<9} {hits:<6} {r.rule.title}")
    out.append("")
    out.append(f"verdict: {verdict(results)}")
    out.append("=== END")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# tsv
# ---------------------------------------------------------------------------


def render_tsv(results: list[RuleResult], max_hits: int) -> str:
    rows: list[str] = []
    for r in results:
        if r.error:
            rows.append(f"{r.rule.id}\t{r.rule.severity}\t\t\tnote: rule error: {r.error}")
        for n in r.notes:
            rows.append(f"{r.rule.id}\t{r.rule.severity}\t\t\tnote: {n}")
        for i, hit in enumerate(r.hits):
            if max_hits and i >= max_hits:
                rows.append(
                    f"{r.rule.id}\t{r.rule.severity}\t\t\tnote: output truncated at {max_hits} hits "
                    f"({r.count - max_hits} more)"
                )
                break
            text = hit.text.replace("\t", " ")
            rows.append(f"{r.rule.id}\t{r.rule.severity}\t{hit.path}\t{hit.line}\t{_clip(text)}")
    return ("\n".join(rows) + "\n") if rows else ""


# ---------------------------------------------------------------------------
# terminal (Rich)
# ---------------------------------------------------------------------------


def render_terminal(results: list[RuleResult], meta: RunMeta, max_hits: int) -> None:
    sets = ", ".join(meta.rule_sets)
    ui.opening(meta.tool, meta.version, f"Scanning {ui.path(meta.root)} against {len(results)} rules ({ui.esc(sets)}).")
    ui.dim(f"{meta.files} file(s) via {meta.source}.")

    for r in results:
        label = f"[bold]{ui.esc(r.rule.id)}[/]  {ui.esc(r.rule.title)}"
        if r.error:
            ui.fail(f"{label}  [dim]rule error[/]")
            ui.dim(f"      {ui.esc(r.error)}")
        elif r.count == 0:
            ui.dim(f"✓ {r.rule.id}  {ui.esc(r.rule.title)}")
        elif r.rule.severity == "blocking":
            ui.fail(f"{label}  {r.count} hit(s)")
        else:
            ui.warn(f"{label}  {r.count} hit(s)")
        for n in r.notes:
            ui.dim(f"      note: {ui.esc(n)}")
        if r.count and not r.error:
            for line in _hit_lines(r, max_hits):
                ui.dim(f"      {ui.esc(line)}")
            if r.rule.note:
                ui.dim(f"      → {ui.esc(r.rule.note)}")

    ui.rule("Summary")
    ui.table(
        None,
        [("ID", 0), ("Severity", 0), ("Hits", 0, "right"), ("Title", 1)],
        [
            [ui.esc(r.rule.id), r.rule.severity, "error" if r.error else str(r.count), ui.esc(r.rule.title)]
            for r in results
        ],
    )
    ui.summary(
        [
            ("Files", meta.files),
            ("Rules", len(results)),
            ("Blocking", blocking_count(results)),
            ("Advisory", advisory_count(results)),
            ("Errors", error_count(results)),
        ]
    )
    if blocking_count(results) or error_count(results):
        ui.fail(ui.esc(verdict(results)))
    else:
        ui.ok(ui.esc(verdict(results)))
