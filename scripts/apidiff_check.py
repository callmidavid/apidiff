"""
Apidiff — API Contract Check.

Purpose:
    Compare two versions of an API contract and determine whether
    the candidate is safe to deploy.

Inputs:
    api/v1.json — Baseline contract (current behaviour).
    api/v2.json — Candidate contract (proposed behaviour).

Outputs:
    docs/result.json — Machine-readable result for the dashboard.
    docs/result.md   — Human-readable summary for the pull request.

Classification:
    Removed field      -> BREAKING. Existing clients will fail.
    Type changed       -> BREAKING. Clients expecting the original type will fail.
    Added field        -> SAFE. Existing clients may ignore it.

Exit codes:
    0 — Safe to deploy. No breaking changes detected.
    1 — Breaking change detected. Deployment should not proceed.
    2 — Input files missing or invalid. Check the file paths.

Language: en-GB. Spelling follows British English throughout.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# File locations. Relative to the repository root.
OLD_PATH = Path("api/v1.json")
NEW_PATH = Path("api/v2.json")
JSON_OUT = Path("docs/result.json")
MD_OUT = Path("docs/result.md")

def load_contract(path: Path) -> dict:
    """Load a JSON contract. Raise a clear error if it is missing or invalid."""
    if not path.exists():
        print(f"Error: Contract not found: {path}", file=sys.stderr)
        print("Expected api/v1.json (baseline) and api/v2.json (candidate).", file=sys.stderr)
        sys.exit(2)
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(2)
    # Support both a single object and a list of users.
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict) and "users" in data and isinstance(data["users"], list) and data["users"]:
        return data["users"][0]
    return data if isinstance(data, dict) else {}

def compare(old: dict, new: dict) -> list:
    """Compare two contracts field by field. Returns a list of changes."""
    changes = []

    # Removed or type-changed fields are breaking.
    for field in old:
        if field not in new:
            changes.append({
                "type": "removed",
                "field": field,
                "path": f"users[].{field}",
                "severity": "breaking",
                "breaking": True,
                "message": f"Removed field: {field} — BREAKING. Existing clients reading user.{field} will fail.",
                "suggestion": f"Restore {field}, or release as /v2/users with a migration note.",
            })
        elif type(old[field]) is not type(new[field]):
            # Note: bool is a subclass of int in Python, so compare type names explicitly.
            old_type = type(old[field]).__name__
            new_type = type(new[field]).__name__
            if old_type != new_type:
                changes.append({
                    "type": "type_changed",
                    "field": field,
                    "path": f"users[].{field}",
                    "severity": "breaking",
                    "breaking": True,
                    "old_type": old_type,
                    "new_type": new_type,
                    "message": f"Type changed: {field} — BREAKING. Changed from {old_type} to {new_type}. Clients expecting {old_type} will fail.",
                    "suggestion": f"Keep {field} as {old_type}, or coerce consistently across all clients before deployment.",
                })

    # Added fields are safe. Existing clients may ignore them.
    for field in new:
        if field not in old:
            changes.append({
                "type": "added",
                "field": field,
                "path": f"users[].{field}",
                "severity": "non-breaking",
                "breaking": False,
                "message": f"Added field: {field} — SAFE. Backwards compatible; existing clients may ignore it.",
                "suggestion": "No action required. This change is safe to deploy.",
            })

    return changes

def main() -> None:
    """Run the check, write the outputs, and exit with the correct code."""
    old = load_contract(OLD_PATH)
    new = load_contract(NEW_PATH)

    changes = compare(old, new)
    breaking_changes = [c for c in changes if c["breaking"]]
    is_breaking = len(breaking_changes) > 0

    verdict = (
        "⛔ BREAKING CHANGE — DO NOT DEPLOY v2 until all breaking changes are resolved, or release as /v2/users"
        if is_breaking
        else "✓ SAFE TO DEPLOY — Only non-breaking additions were detected."
    )

    result = {
        "title": "Apidiff — API Contract Check",
        "endpoint": "GET /v1/users",
        "old": "api/v1.json",
        "new": "api/v2.json",
        "old_label": "v1 — Baseline",
        "new_label": "v2 — Candidate",
        "checked_at": datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC"),
        "breaking": is_breaking,
        "summary": {
            "total": len(changes),
            "breaking": len(breaking_changes),
            "non_breaking": len(changes) - len(breaking_changes),
            "removed": sum(1 for c in changes if c["type"] == "removed"),
            "added": sum(1 for c in changes if c["type"] == "added"),
            "type_changed": sum(1 for c in changes if c["type"] == "type_changed"),
        },
        "changes": changes,
        "verdict": verdict,
        "contributor": "Temitope Abraham Olorunmola, Abuja — Fusion Contribution for github.com/callmidavid/apidiff",
    }

    # Ensure the output directory exists before writing.
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    # Markdown summary for the GitHub Actions job summary.
    lines = [
        "### Result",
        "",
        f"**Verdict:** {verdict}",
        "",
        f"**Total:** {len(changes)} • **Breaking:** {len(breaking_changes)} • **Safe:** {len(changes) - len(breaking_changes)}",
        "",
        "### Changes",
        "",
    ]
    if not changes:
        lines.append("No changes. The contracts match.")
    else:
        for c in changes:
            icon = "⛔" if c["breaking"] else "✓"
            lines.append(f"- {icon} **{c['field']}** — {c['message']}")
            lines.append(f"  - Suggestion: {c['suggestion']}")
    MD_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Print a concise log for the Actions console.
    print(f"Apidiff: {len(changes)} change(s), {len(breaking_changes)} breaking.")
    print(f"Verdict: {verdict}")
    print(f"Written: {JSON_OUT} and {MD_OUT}")

    # Exit code 1 fails the build. This is intentional.
    sys.exit(1 if is_breaking else 0)

if __name__ == "__main__":
    main()