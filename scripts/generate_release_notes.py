#!/usr/bin/env python3
"""Generate industry-standard, monorepo-scoped GitHub Release notes for TalkOps MCP servers.

Features:
- Strictly scopes git commit history to ``src/<server-name>/`` so monorepo sibling
  commits never pollute a package's release notes.
- Supports curated ``src/<server-name>/CHANGELOG.md`` entries (Keep a Changelog format)
  when present, with automatic Conventional Commits categorization as fallback.
- Reads live introspected capability counts (MCP Tools, MCP Resources, Agent Skills)
  produced during the build step instead of fragile regex scraping.
- Emits full 64-character SHA-256 checksums for built sdist/wheel artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s*(?P<desc>.+)$"
)
PR_REF_RE = re.compile(r"\(#(\d+)\)")
VERSION_BUMP_NOISE_RE = re.compile(
    r"^(?:bump|chore)?[:\s]*(?:bump\s+versions?|release\s+v?\d+\.\d+)", re.IGNORECASE
)

CATEGORY_ORDER: list[tuple[str, str]] = [
    ("breaking", "### ⚠️ Breaking Changes"),
    ("feat", "### ✨ Features"),
    ("fix", "### 🐛 Bug Fixes"),
    ("perf_refactor", "### ⚡ Refactoring & Performance"),
    ("docs", "### 📖 Documentation & Agent Skills"),
    ("test", "### 🧪 Tests & Verification"),
    ("other", "### 🧰 Maintenance"),
]


def _run_git(repo_root: Path, args: list[str]) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _find_previous_tag(repo_root: Path, server_name: str, current_tag: str) -> str | None:
    raw = _run_git(
        repo_root,
        ["tag", "--list", f"{server_name}/v*", "--sort=-version:refname"],
    )
    for line in raw.splitlines():
        tag = line.strip()
        if tag and tag != current_tag:
            return tag
    return None


def _extract_curated_changelog(server_dir: Path, version: str) -> str | None:
    changelog_path = server_dir / "CHANGELOG.md"
    if not changelog_path.is_file():
        return None
    text = changelog_path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^##\s+\[?v?{re.escape(version)}\]?(?:\s+-\s+.*|\s*\(.*\))?\s*$",
        re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return None
    rest = text[match.end() :]
    next_heading = re.search(r"^##\s+\[?v?\d+\.\d+", rest, re.MULTILINE)
    section = rest[: next_heading.start()] if next_heading else rest
    cleaned = section.strip()
    return cleaned or None


def _linkify_prs(text: str, repo_url: str) -> str:
    return PR_REF_RE.sub(rf"([#\1]({repo_url}/pull/\1))", text)


def _capitalize_first(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]


def _collect_scoped_commits(
    repo_root: Path,
    server_rel_dir: str,
    prev_tag: str | None,
    end_ref: str,
    repo_url: str,
) -> tuple[dict[str, list[str]], list[str]]:
    rev_range = f"{prev_tag}..{end_ref}" if prev_tag else end_ref
    fmt = "%H%x1f%h%x1f%s%x1f%b%x1f%an%x1e"
    raw = _run_git(
        repo_root,
        ["log", "--no-merges", f"--format={fmt}", rev_range, "--", server_rel_dir],
    )

    buckets: dict[str, list[str]] = {k: [] for k, _ in CATEGORY_ORDER}
    authors: list[str] = []
    parsed_records: list[tuple[str, str, bool]] = []

    for record in raw.split("\x1e"):
        record = record.strip()
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) < 5:
            continue
        full_sha, short_sha, subject, body, author = (p.strip() for p in parts[:5])
        if author and author not in authors and "bot" not in author.lower():
            authors.append(author)

        is_noise = bool(VERSION_BUMP_NOISE_RE.search(subject))
        m = CONVENTIONAL_RE.match(subject)
        has_breaking_footer = "BREAKING CHANGE:" in body or "BREAKING-CHANGE:" in body

        if m:
            ctype = m.group("type").lower()
            scope = (m.group("scope") or "").strip()
            is_breaking = bool(m.group("breaking")) or has_breaking_footer
            desc = m.group("desc").strip()
            if scope and scope.lower() not in server_rel_dir.lower():
                formatted_desc = f"**{scope}:** {_capitalize_first(desc)}"
            else:
                formatted_desc = _capitalize_first(desc)

            if is_breaking:
                cat = "breaking"
            elif ctype == "feat":
                cat = "feat"
            elif ctype in ("fix", "security"):
                cat = "fix"
            elif ctype in ("perf", "refactor"):
                cat = "perf_refactor"
            elif ctype == "docs":
                cat = "docs"
            elif ctype == "test":
                cat = "test"
            else:
                cat = "other"
        else:
            cat = "breaking" if has_breaking_footer else "other"
            formatted_desc = _capitalize_first(subject)

        formatted_desc = _linkify_prs(formatted_desc, repo_url)
        bullet = f"- {formatted_desc} ([`{short_sha}`]({repo_url}/commit/{full_sha}))"
        parsed_records.append((cat, bullet, is_noise))

    has_substantive = any(not noise for _, _, noise in parsed_records)
    for cat, bullet, is_noise in parsed_records:
        if has_substantive and is_noise and cat == "other":
            continue
        if bullet not in buckets[cat]:
            buckets[cat].append(bullet)

    return buckets, authors


def _discover_skills(server_dir: Path) -> list[str]:
    skills_dir = server_dir / "skills"
    if not skills_dir.is_dir():
        return []
    return sorted(
        p.name
        for p in skills_dir.iterdir()
        if p.is_dir() and (p / "SKILL.md").is_file()
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_release_notes(
    repo_root: Path,
    server_name: str,
    version: str,
    pypi_name: str,
    github_repo: str,
    dist_dir: Path,
    meta_file: Path | None = None,
    tag_name: str | None = None,
    end_ref: str = "HEAD",
) -> str:
    server_rel_dir = f"src/{server_name}"
    server_dir = repo_root / server_rel_dir
    current_tag = tag_name or f"{server_name}/v{version}"
    repo_url = f"https://github.com/{github_repo}"

    pyproject = tomllib.loads((server_dir / "pyproject.toml").read_text(encoding="utf-8"))
    project_meta: dict[str, Any] = pyproject.get("project", {})
    description = str(project_meta.get("description", "")).strip()
    requires_python = str(project_meta.get("requires-python", ">=3.12")).strip()
    license_field = project_meta.get("license", "Apache-2.0")
    license_name = (
        license_field.get("text", "Apache-2.0")
        if isinstance(license_field, dict)
        else str(license_field)
    )

    live_meta: dict[str, Any] = {}
    if meta_file and meta_file.is_file():
        live_meta = json.loads(meta_file.read_text(encoding="utf-8"))

    skills = live_meta.get("skills") or _discover_skills(server_dir)
    tool_count = live_meta.get("tool_count")
    resource_count = live_meta.get("resource_count")

    # Build capability summary pills
    surface_parts: list[str] = []
    if isinstance(tool_count, int) and tool_count > 0:
        surface_parts.append(f"`{tool_count}` MCP Tools")
    if isinstance(resource_count, int) and resource_count > 0:
        surface_parts.append(f"`{resource_count}` Live Resources")
    if skills:
        surface_parts.append(f"`{len(skills)}` Bundled Agent Skills")

    py_badge_val = requires_python.replace(">=", "%3E%3D").replace(" ", "")
    lic_badge_val = license_name.replace("-", "--").replace(" ", "_")
    doc_ref = current_tag if _run_git(repo_root, ["rev-parse", "-q", "--verify", f"refs/tags/{current_tag}"]) else "main"
    docs_url = f"{repo_url}/tree/{doc_ref}/{server_rel_dir}#readme"
    pypi_url = f"https://pypi.org/project/{pypi_name}/{version}/"

    lines: list[str] = [
        (
            f"[![PyPI](https://img.shields.io/pypi/v/{pypi_name}/{version}?label=PyPI&logo=pypi&logoColor=white)]({pypi_url}) "
            f"[![Python](https://img.shields.io/badge/Python-{py_badge_val}-3776AB?logo=python&logoColor=white)]({pypi_url}) "
            f"[![License](https://img.shields.io/badge/License-{lic_badge_val}-blue)]({repo_url}/blob/main/LICENSE)"
        ),
        "",
        description,
    ]
    if surface_parts:
        lines.extend(["", f"**Capabilities:** {' · '.join(surface_parts)} · [Documentation]({docs_url})"])

    # ── Section 1: What's Changed ──
    lines.extend(["", "## What's Changed", ""])
    prev_tag = _find_previous_tag(repo_root, server_name, current_tag)
    curated = _extract_curated_changelog(server_dir, version)

    if curated:
        lines.append(curated)
    else:
        buckets, _ = _collect_scoped_commits(
            repo_root=repo_root,
            server_rel_dir=server_rel_dir,
            prev_tag=prev_tag,
            end_ref=end_ref,
            repo_url=repo_url,
        )
        rendered_any = False
        for key, heading in CATEGORY_ORDER:
            items = buckets[key]
            if not items:
                continue
            rendered_any = True
            lines.append(heading)
            if key == "breaking":
                lines.extend(
                    [
                        "> [!IMPORTANT]",
                        f"> Review the migration notes in the [server README]({docs_url}) before upgrading.",
                        "",
                    ]
                )
            lines.extend(items)
            lines.append("")

        if not rendered_any:
            if prev_tag:
                lines.append(
                    f"- Package release `{pypi_name}` `v{version}` incorporating latest MCP execution server and bundled Agent Skills updates."
                )
            else:
                lines.append(f"- Initial PyPI release of `{pypi_name}` (`v{version}`).")
            lines.append("")

    if skills and (not prev_tag or version.endswith(".0")):
        skill_list = ", ".join(f"`{s}`" for s in skills)
        lines.extend(
            [
                "### 🧠 Bundled Agent Skills (`skills/`)",
                f"- Ships **{len(skills)}** progressive-disclosure Agent Skills (`Agent Plugins v1.0.0`): {skill_list}.",
                "",
            ]
        )

    if prev_tag:
        compare_target = current_tag if doc_ref == current_tag else end_ref
        lines.append(
            f"**Full Changelog:** [`{prev_tag}...{current_tag}`]({repo_url}/compare/{prev_tag}...{compare_target}) *(scoped to `{server_rel_dir}`)*"
        )
    else:
        lines.append(f"**Release Tree:** [`{current_tag}`]({docs_url})")

    # ── Section 2: Installation ──
    lines.extend(
        [
            "",
            "## Installation",
            "",
            "```bash",
            "# Run directly without installing (recommended)",
            f"uvx {pypi_name}@{version}",
            "",
            "# Install with uv or pip",
            f"uv pip install {pypi_name}=={version}",
            f"pip install {pypi_name}=={version}",
            "```",
            "",
            f"For MCP client wiring (`mcp.json`), CLI flags, environment variables, and Docker deployment, see the [{server_name} README]({docs_url}).",
        ]
    )

    # ── Section 3: Full Cryptographic Checksums ──
    artifacts = (
        sorted(
            p
            for p in dist_dir.iterdir()
            if p.is_file() and (p.name.endswith(".whl") or p.name.endswith(".tar.gz"))
        )
        if dist_dir.is_dir()
        else []
    )
    if artifacts:
        lines.extend(
            [
                "",
                "## Artifact Checksums (SHA-256)",
                "",
                "| Artifact | SHA-256 |",
                "| :--- | :--- |",
            ]
        )
        for art in artifacts:
            digest = _sha256_file(art)
            lines.append(f"| `{art.name}` | `{digest}` |")
        lines.extend(
            [
                "",
                "Verify downloaded artifacts locally with `sha256sum --check SHA256SUMS.txt`.",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--server-name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--pypi-name", required=True)
    parser.add_argument("--github-repo", default="talkops-ai/talkops-mcp")
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--meta-file", type=Path, default=None)
    parser.add_argument("--tag-name", default=None)
    parser.add_argument("--end-ref", default="HEAD")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    body = generate_release_notes(
        repo_root=args.repo_root.resolve(),
        server_name=args.server_name,
        version=args.version,
        pypi_name=args.pypi_name,
        github_repo=args.github_repo,
        dist_dir=args.dist_dir,
        meta_file=args.meta_file,
        tag_name=args.tag_name,
        end_ref=args.end_ref,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(body, encoding="utf-8")


if __name__ == "__main__":
    main()
