#!/usr/bin/env python3
"""CLI entry point for terraform-cost-predictor."""

from __future__ import annotations

import argparse
import json
import sys

from cost_estimator import build_cost_report
from llm import LLMClient


SYSTEM_PROMPT = (
    "You are a cloud cost analyst. Given a Terraform cost report in JSON, "
    "explain the costs in plain English. Highlight the most expensive resources, "
    "suggest cost-saving opportunities, and flag anything that looks unusually "
    "expensive. Be concise and actionable."
)


def format_report_text(report) -> str:
    """Format a CostReport as human-readable text."""
    lines = [
        "=" * 60,
        "  TERRAFORM COST ESTIMATE REPORT",
        "=" * 60,
        f"  Total Monthly Cost: ${report.total_monthly:,.2f}",
        f"  Total Annual Cost:  ${report.total_annual:,.2f}",
        f"  Resources:          {report.resource_count}",
        "=" * 60,
        "",
    ]

    if not report.estimates:
        lines.append("  No billable resources found.")
        return "\n".join(lines)

    lines.append("  TOP EXPENSIVE RESOURCES:")
    lines.append("-" * 60)
    for i, e in enumerate(report.top_expensive(10), 1):
        lines.append(
            f"  {i}. {e.resource_type} ({e.resource_name}): "
            f"${e.monthly_cost:,.2f}/mo"
        )
        if e.notes:
            lines.append(f"     Note: {e.notes}")

    lines.append("")
    lines.append("  COSTS BY TYPE:")
    lines.append("-" * 60)
    for rtype, cost in sorted(
        report.by_type().items(), key=lambda kv: kv[1], reverse=True
    ):
        lines.append(f"  {rtype:<40s} ${cost:>10,.2f}/mo")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Estimate monthly cloud costs from a Terraform plan JSON."
    )
    parser.add_argument(
        "plan_file",
        help="Path to Terraform plan JSON file (use 'terraform plan -out=plan && terraform show -json plan > plan.json')",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Use LLM to generate a plain-English explanation of costs",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output report as JSON instead of text",
    )

    args = parser.parse_args(argv)

    # Read the plan file
    try:
        with open(args.plan_file, "r") as f:
            plan_json = f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {args.plan_file}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error reading file: {exc}", file=sys.stderr)
        return 1

    # Build the cost report
    try:
        report = build_cost_report(plan_json)
    except (json.JSONDecodeError, KeyError) as exc:
        print(f"Error parsing Terraform plan: {exc}", file=sys.stderr)
        return 1

    if args.json_output:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report_text(report))

    # LLM explanation
    if args.explain:
        llm = LLMClient()
        report_json = json.dumps(report.to_dict(), indent=2)
        prompt = f"Here is the Terraform cost report:\n\n```json\n{report_json}\n```\n\nPlease explain this cost breakdown and suggest optimizations."

        print("\n" + "=" * 60)
        print("  AI COST ANALYSIS")
        print("=" * 60)
        try:
            explanation = llm.chat(prompt, system=SYSTEM_PROMPT)
            print(explanation)
        except Exception as exc:
            print(f"  LLM unavailable: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
