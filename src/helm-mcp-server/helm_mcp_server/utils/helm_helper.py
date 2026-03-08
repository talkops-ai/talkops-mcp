"""Helm utility functions for safety checks and validation."""

import re
import shutil
from typing import List, Optional

# Patterns that can appear as substrings in legitimate words (e.g., "registry", "network", "dashboard")
# Use word-boundary matching to avoid false positives
WORD_BOUNDARY_PATTERNS = {'reg', 'net', 'sc', 'su', 'sh'}


def get_dangerous_patterns() -> List[str]:
    """Get a list of dangerous patterns for command injection detection.

    Returns:
        List of dangerous patterns to check for
    """
    patterns = [
        '|', ';', '&', '&&', '||',  # Command chaining
        '>', '>>', '<',  # Redirection
        '`', '$(',  # Command substitution
        '--',  # Double dash options
        '/bin/', '/usr/bin/',  # Path references
        '../', './',  # Directory traversal
        # Unix/Linux specific dangerous patterns
        'sudo', 'chmod', 'chown', 'su', 'bash', 'sh', 'zsh',
        'curl', 'wget', 'ssh', 'scp', 'eval', 'source',
        # Windows specific dangerous patterns
        'cmd', 'powershell', 'pwsh', 'net', 'reg', 'runas',
        'del', 'rmdir', 'taskkill', 'sc', 'schtasks', 'wmic',
        '%SYSTEMROOT%', '%WINDIR%', '.bat', '.cmd', '.ps1',
    ]
    return patterns


def is_helm_installed() -> bool:
    """Check if the helm binary is available in the system PATH.

    Returns:
        True if helm is found, False otherwise
    """
    return shutil.which('helm') is not None


def check_for_dangerous_patterns(args: List[str], log_prefix: Optional[str] = None) -> Optional[str]:
    """Check a list of command arguments for dangerous patterns.
    
    Args:
        args: List of command arguments to check
        log_prefix: Optional prefix for log messages
    
    Returns:
        The dangerous pattern found, or None if no dangerous patterns detected
    """
    patterns = get_dangerous_patterns()
    
    for arg in args:
        for pattern in patterns:
            if pattern == '--':
                # Only flag if the argument is exactly '--'
                if arg == '--':
                    return pattern
            elif pattern in WORD_BOUNDARY_PATTERNS:
                # Use word boundary to avoid false positives (e.g., "registry" in OCI URLs)
                if re.search(rf'\b{re.escape(pattern)}\b', arg):
                    return pattern
            else:
                if pattern in arg:
                    return pattern
    return None
