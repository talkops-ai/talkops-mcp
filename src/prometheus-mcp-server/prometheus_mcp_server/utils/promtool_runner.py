"""Promtool subprocess wrapper.

Provides utilities for running promtool check rules and
promtool test rules with graceful fallback when promtool
is not available.
"""

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def find_promtool() -> Optional[str]:
    """Find promtool binary in PATH or configured location."""
    path = shutil.which("promtool")
    return path


def is_promtool_available() -> bool:
    """Check if promtool is available."""
    return find_promtool() is not None


async def run_promtool_command(
    args: List[str], input_yaml: Optional[str] = None
) -> Tuple[int, str, str]:
    """Run a promtool command asynchronously.

    Args:
        args: Command arguments (e.g. ['check', 'rules', '/path/to/file.yml'])
        input_yaml: Optional YAML content to write to a temp file

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    promtool = find_promtool()
    if not promtool:
        return (-1, "", "promtool not found in PATH. Install from Prometheus releases.")

    temp_file = None
    try:
        if input_yaml:
            temp_file = tempfile.NamedTemporaryFile(
                mode='w', suffix='.yml', delete=False
            )
            temp_file.write(input_yaml)
            temp_file.flush()
            temp_file.close()
            # Replace placeholder path in args
            args = [temp_file.name if arg == "__TEMP_FILE__" else arg for arg in args]

        cmd = [promtool] + args
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=30
        )
        return (
            process.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )
    except asyncio.TimeoutError:
        return (-1, "", "promtool command timed out after 30 seconds")
    except Exception as e:
        return (-1, "", f"promtool execution failed: {e}")
    finally:
        if temp_file:
            try:
                Path(temp_file.name).unlink(missing_ok=True)
            except Exception:
                pass


async def check_rules(rules_yaml: str) -> Dict[str, Any]:
    """Run promtool check rules on a YAML string.

    Args:
        rules_yaml: YAML content containing rule groups

    Returns:
        Dict with valid, errors, warnings, and rules_checked
    """
    if not is_promtool_available():
        return {
            "valid": False,
            "errors": ["promtool not available. Install from https://prometheus.io/download/"],
            "warnings": [],
            "rules_checked": 0,
            "promtool_available": False,
        }

    return_code, stdout, stderr = await run_promtool_command(
        ["check", "rules", "__TEMP_FILE__"],
        input_yaml=rules_yaml,
    )

    errors = []
    warnings = []
    rules_checked = 0

    if return_code != 0:
        # Parse errors from stderr/stdout
        output = stderr or stdout
        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if "WARNING" in line.upper():
                warnings.append(line)
            else:
                errors.append(line)
    else:
        # Parse success output
        for line in stdout.strip().split("\n"):
            if "SUCCESS" in line.upper() or "rule" in line.lower():
                # Try to extract count
                import re
                match = re.search(r'(\d+)\s+rule', line)
                if match:
                    rules_checked = int(match.group(1))

    return {
        "valid": return_code == 0,
        "errors": errors,
        "warnings": warnings,
        "rules_checked": rules_checked,
        "promtool_available": True,
    }


async def test_rules(rules_yaml: str, test_yaml: str) -> Dict[str, Any]:
    """Run promtool test rules with test YAML.

    Args:
        rules_yaml: YAML content containing rule groups
        test_yaml: YAML content containing test scenarios

    Returns:
        Dict with passed, total_tests, failed_tests, errors, output
    """
    if not is_promtool_available():
        return {
            "passed": False,
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "errors": ["promtool not available. Install from https://prometheus.io/download/"],
            "output": "",
            "promtool_available": False,
        }

    # Write both files
    rules_file = tempfile.NamedTemporaryFile(
        mode='w', suffix='_rules.yml', delete=False
    )
    rules_file.write(rules_yaml)
    rules_file.flush()
    rules_file.close()

    test_file = tempfile.NamedTemporaryFile(
        mode='w', suffix='_test.yml', delete=False
    )
    # Inject rules file reference into test YAML
    test_content = test_yaml.replace("__RULES_FILE__", rules_file.name)
    test_file.write(test_content)
    test_file.flush()
    test_file.close()

    try:
        return_code, stdout, stderr = await run_promtool_command(
            ["test", "rules", test_file.name]
        )

        errors = []
        total_tests = 0
        passed_tests = 0
        failed_tests = 0

        output = stdout or stderr
        if return_code != 0:
            for line in (stderr or stdout).strip().split("\n"):
                if line.strip():
                    errors.append(line.strip())

        # Parse test results
        for line in output.split("\n"):
            if "PASSED" in line.upper():
                passed_tests += 1
                total_tests += 1
            elif "FAILED" in line.upper():
                failed_tests += 1
                total_tests += 1

        return {
            "passed": return_code == 0,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "errors": errors,
            "output": output,
            "promtool_available": True,
        }
    finally:
        Path(rules_file.name).unlink(missing_ok=True)
        Path(test_file.name).unlink(missing_ok=True)
