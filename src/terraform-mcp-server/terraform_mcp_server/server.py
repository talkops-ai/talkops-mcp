# Copyright (C) 2025 StructBinary
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
DEPRECATED: This module is retained for backward compatibility only.

The monolithic server has been replaced by a layered architecture:
- Entry: terraform_mcp_server.main
- Bootstrap: terraform_mcp_server.server.bootstrap
- Tools: terraform_mcp_server.tools
- Resources: terraform_mcp_server.resources

Scheduled for removal in v0.3.0.
"""

import warnings

warnings.warn(
    "terraform_mcp_server.server is deprecated. "
    "Use terraform_mcp_server.main:main instead. "
    "Scheduled for removal in v0.3.0.",
    DeprecationWarning,
    stacklevel=2,
)

from terraform_mcp_server.main import main  # noqa: F401, E402