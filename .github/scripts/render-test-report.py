#!/usr/bin/env python3
"""Render pytest JUnit XML and coverage.py XML into CI HTML reports."""

from __future__ import annotations

import argparse
import datetime as dt
import html
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def pct(value: int | float, total: int | float) -> float:
    return 0.0 if float(total) == 0.0 else (float(value) / float(total)) * 100.0


def fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}%"


def duration(value: Any) -> str:
    try:
        return f"{float(value):.2f}s"
    except (TypeError, ValueError):
        return "-"


def status_label(status: str) -> str:
    return {
        "pass": "Passed",
        "fail": "Failed",
        "skip": "Skipped",
        "unknown": "Unknown",
    }.get(status, status.title())


def status_class(status: str) -> str:
    return {
        "pass": "status-pass",
        "fail": "status-fail",
        "skip": "status-skip",
    }.get(status, "status-unknown")


def testcase_status(testcase: ET.Element) -> tuple[str, str]:
    failure = testcase.find("failure")
    if failure is not None:
        return "fail", failure.get("message") or (failure.text or "")
    error = testcase.find("error")
    if error is not None:
        return "fail", error.get("message") or (error.text or "")
    skipped = testcase.find("skipped")
    if skipped is not None:
        return "skip", skipped.get("message") or (skipped.text or "")
    return "pass", ""


def parse_junit(path: Path) -> dict[str, Any]:
    packages: dict[str, dict[str, Any]] = {}
    tests: list[dict[str, Any]] = []

    if not path.exists():
        return {"packages": packages, "tests": tests}

    root = ET.parse(path).getroot()
    for testcase in root.iter("testcase"):
        classname = testcase.get("classname") or "unknown"
        name = testcase.get("name") or "unknown"
        elapsed = testcase.get("time")
        status, message = testcase_status(testcase)
        package_name = classname.rsplit(".", 1)[0] if "." in classname else classname

        package = packages.setdefault(
            package_name,
            {
                "name": package_name,
                "tests": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "elapsed": 0.0,
                "status": "pass",
            },
        )
        package["tests"] += 1
        package["elapsed"] += float(elapsed or 0.0)
        if status == "fail":
            package["failed"] += 1
            package["status"] = "fail"
        elif status == "skip":
            package["skipped"] += 1
            if package["status"] != "fail":
                package["status"] = "skip"
        else:
            package["passed"] += 1

        tests.append(
            {
                "package": package_name,
                "classname": classname,
                "name": name,
                "status": status,
                "elapsed": elapsed,
                "message": message.strip(),
            }
        )

    return {
        "packages": dict(sorted(packages.items())),
        "tests": sorted(tests, key=lambda item: (item["package"], item["name"])),
    }


def parse_coverage_xml(path: Path) -> dict[str, Any]:
    coverage: dict[str, Any] = {"percent": None, "files": {}, "packages": {}}
    if not path.exists():
        return coverage

    root = ET.parse(path).getroot()
    line_rate = root.get("line-rate")
    if line_rate is not None:
        coverage["percent"] = float(line_rate) * 100.0

    for package in root.findall(".//package"):
        package_name = package.get("name") or "unknown"
        rate = package.get("line-rate")
        coverage["packages"][package_name] = float(rate) * 100.0 if rate is not None else None

    for cls in root.findall(".//class"):
        filename = cls.get("filename") or cls.get("name") or "unknown"
        rate = cls.get("line-rate")
        coverage["files"][filename] = float(rate) * 100.0 if rate is not None else None

    return coverage


def coverage_for_package(package_name: str, coverage: dict[str, Any]) -> float | None:
    coverage_packages: dict[str, float | None] = coverage["packages"]
    candidates = [
        package_name,
        package_name.replace(".", "/"),
        package_name.split(".", 1)[0],
    ]
    for candidate in candidates:
        if candidate in coverage_packages:
            return coverage_packages[candidate]
    if package_name.startswith("tests"):
        return None
    return coverage["percent"]


def render_package_rows(report: dict[str, Any], coverage: dict[str, Any]) -> str:
    rows: list[str] = []
    for package in report["packages"].values():
        coverage_percent = coverage_for_package(package["name"], coverage)
        rows.append(
            "<tr>"
            f"<td><span class=\"pill {status_class(package['status'])}\">"
            f"{esc(status_label(package['status']))}</span></td>"
            f"<td>{esc(package['name'])}</td>"
            f"<td>{package['tests']}</td>"
            f"<td>{package['passed']}</td>"
            f"<td>{package['failed']}</td>"
            f"<td>{package['skipped']}</td>"
            f"<td>{duration(package['elapsed'])}</td>"
            f"<td>{fmt_pct(coverage_percent)}</td>"
            "</tr>"
        )
    return "\n".join(rows) or '<tr><td colspan="8">No package data found.</td></tr>'


def render_failures(report: dict[str, Any]) -> str:
    failures = [test for test in report["tests"] if test["status"] == "fail"]
    if not failures:
        return '<div class="panel empty">No failing tests were reported.</div>'
    blocks = []
    for test in failures:
        blocks.append(
            '<div class="panel failure">'
            f"<h3>{esc(test['package'])} / {esc(test['name'])}</h3>"
            f"<pre>{esc(test['message'] or 'No failure message recorded.')}</pre>"
            "</div>"
        )
    return "\n".join(blocks)


def render_test_details(report: dict[str, Any]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for test in report["tests"]:
        grouped.setdefault(test["package"], []).append(test)

    sections: list[str] = []
    for package, tests in grouped.items():
        rows = "\n".join(
            "<tr>"
            f"<td><span class=\"pill {status_class(test['status'])}\">"
            f"{esc(status_label(test['status']))}</span></td>"
            f"<td>{esc(test['name'])}</td>"
            f"<td>{duration(test['elapsed'])}</td>"
            "</tr>"
            for test in tests
        )
        passed = sum(1 for test in tests if test["status"] == "pass")
        failed = sum(1 for test in tests if test["status"] == "fail")
        skipped = sum(1 for test in tests if test["status"] == "skip")
        sections.append(
            "<details>"
            f"<summary><strong>{esc(package)}</strong>"
            f"<span>{passed} pass / {failed} fail / {skipped} skip</span></summary>"
            "<table><thead><tr><th>Status</th><th>Test</th><th>Time</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            "</details>"
        )
    return "\n".join(sections) or '<div class="panel empty">No test cases were parsed.</div>'


def render_coverage_rows(coverage: dict[str, Any]) -> str:
    files: dict[str, float | None] = coverage["files"]
    if not files:
        return '<tr><td colspan="2">No coverage file details found.</td></tr>'
    return "\n".join(
        f"<tr><td>{esc(filename)}</td><td>{fmt_pct(percent)}</td></tr>"
        for filename, percent in sorted(files.items())
    )


def render_html(report: dict[str, Any], coverage: dict[str, Any], output_path: Path) -> None:
    tests = report["tests"]
    total = len(tests)
    passed = sum(1 for test in tests if test["status"] == "pass")
    failed = sum(1 for test in tests if test["status"] == "fail")
    skipped = sum(1 for test in tests if test["status"] == "skip")
    overall_status = "Failed" if failed else "Passed"
    overall_class = "status-fail" if failed else "status-pass"
    pass_width = pct(passed, total)
    fail_width = pct(failed, total)
    skip_width = pct(skipped, total)
    generated_at = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NUS Resource Service Test Report</title>
  <style>
    :root {{
      --bg: #f6f8fb;
      --panel: #ffffff;
      --ink: #101820;
      --muted: #60707f;
      --line: #dce3ea;
      --pass: #1f8f5f;
      --fail: #c43d3d;
      --skip: #6b7280;
      --shadow: 0 18px 42px rgba(16, 24, 32, 0.10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: #f6f8fb;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    main {{ width: min(100% - 20px, 1180px); margin: 0 auto; padding: 28px 0 48px; }}
    header, .panel, table, details {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 24px;
    }}
    h1 {{ margin: 0; font-size: 30px; letter-spacing: 0; }}
    h2 {{ margin: 34px 0 14px; font-size: 20px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 10px; font-size: 16px; letter-spacing: 0; }}
    p {{ margin: 6px 0 0; color: var(--muted); }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 14px;
      margin-top: 18px;
    }}
    .metric {{ padding: 18px; }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      font-weight: 800;
    }}
    .metric strong {{ display: block; margin-top: 6px; font-size: 30px; line-height: 1.1; }}
    .bar {{
      display: flex;
      height: 14px;
      overflow: hidden;
      border-radius: 8px;
      margin: 18px 0 0;
      background: #e5e7eb;
    }}
    .bar-pass {{ width: {pass_width:.2f}%; background: var(--pass); }}
    .bar-fail {{ width: {fail_width:.2f}%; background: var(--fail); }}
    .bar-skip {{ width: {skip_width:.2f}%; background: var(--skip); }}
    .pill {{
      display: inline-flex;
      align-items: center;
      border-radius: 8px;
      padding: 5px 10px;
      color: #ffffff;
      font-weight: 800;
      font-size: 12px;
    }}
    .status-pass {{ background: var(--pass); }}
    .status-fail {{ background: var(--fail); }}
    .status-skip {{ background: var(--skip); }}
    .status-unknown {{ background: #7c8490; }}
    table {{ width: 100%; border-collapse: collapse; overflow: hidden; }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
      background: #f2f6fa;
    }}
    tr:last-child td {{ border-bottom: 0; }}
    details {{ margin-bottom: 12px; overflow: hidden; }}
    summary {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      cursor: pointer;
      padding: 14px 16px;
    }}
    details table {{ border: 0; border-top: 1px solid var(--line); border-radius: 0; box-shadow: none; }}
    .failure {{ margin-bottom: 14px; padding: 18px; }}
    .empty {{ padding: 18px; color: var(--muted); }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      margin: 0;
      padding: 12px;
      border-radius: 8px;
      background: #f7f9fb;
      border: 1px solid var(--line);
    }}
    footer {{ margin-top: 24px; color: var(--muted); }}
    @media (max-width: 900px) {{
      header, summary {{ flex-direction: column; align-items: flex-start; }}
      .metric-grid {{ grid-template-columns: 1fr; }}
      th, td {{ padding: 10px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>NUS Resource Service Test Report</h1>
        <p>{esc(generated_at)}</p>
      </div>
      <span class="pill {overall_class}">{overall_status}</span>
    </header>
    <section class="metric-grid" aria-label="Test run metrics">
      <div class="panel metric"><span>Total tests</span><strong>{total}</strong></div>
      <div class="panel metric"><span>Passed</span><strong>{passed}</strong></div>
      <div class="panel metric"><span>Failed</span><strong>{failed}</strong></div>
      <div class="panel metric"><span>Skipped</span><strong>{skipped}</strong></div>
      <div class="panel metric"><span>Coverage</span><strong>{fmt_pct(coverage["percent"])}</strong></div>
    </section>
    <div class="bar" aria-label="Test status distribution">
      <div class="bar-pass" title="Passed"></div>
      <div class="bar-fail" title="Failed"></div>
      <div class="bar-skip" title="Skipped"></div>
    </div>
    <h2>Package Health</h2>
    <table>
      <thead>
        <tr><th>Status</th><th>Package</th><th>Tests</th><th>Pass</th><th>Fail</th><th>Skip</th><th>Time</th><th>Coverage</th></tr>
      </thead>
      <tbody>{render_package_rows(report, coverage)}</tbody>
    </table>
    <h2>Failures</h2>
    {render_failures(report)}
    <h2>Test Cases</h2>
    {render_test_details(report)}
    <h2>Coverage Files</h2>
    <table>
      <thead><tr><th>File</th><th>Coverage</th></tr></thead>
      <tbody>{render_coverage_rows(coverage)}</tbody>
    </table>
    <footer>Parsed {len(report["packages"])} packages and {total} tests.</footer>
  </main>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")


def render_markdown_summary(report: dict[str, Any], coverage: dict[str, Any], output_path: Path) -> None:
    tests = report["tests"]
    total = len(tests)
    passed = sum(1 for test in tests if test["status"] == "pass")
    failed = sum(1 for test in tests if test["status"] == "fail")
    skipped = sum(1 for test in tests if test["status"] == "skip")
    failures = [test for test in tests if test["status"] == "fail"]

    lines = [
        "## Unit Test Report",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Tests | {total} |",
        f"| Passed | {passed} |",
        f"| Failed | {failed} |",
        f"| Skipped | {skipped} |",
        f"| Packages | {len(report['packages'])} |",
        f"| Coverage | {fmt_pct(coverage['percent'])} |",
        "",
        "Artifacts: `test-report.html`, `coverage.xml`, `htmlcov/`, and `test-report.xml`.",
    ]

    if failures:
        lines.extend(["", "### Failing Tests", ""])
        for test in failures[:10]:
            lines.append(f"- `{test['package']}` / `{test['name']}`")
    elif total == 0:
        lines.extend(["", "No test cases were parsed. Check `test-report.xml`."])
    else:
        lines.extend(["", "All reported tests passed."])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", required=True, type=Path, help="Path to pytest JUnit XML")
    parser.add_argument("--coverage-xml", required=True, type=Path, help="Path to coverage.py XML")
    parser.add_argument("--html", required=True, type=Path, help="Output HTML report path")
    parser.add_argument("--summary", required=True, type=Path, help="Output GitHub summary Markdown path")
    args = parser.parse_args()

    report = parse_junit(args.junit)
    coverage = parse_coverage_xml(args.coverage_xml)
    render_html(report, coverage, args.html)
    render_markdown_summary(report, coverage, args.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
