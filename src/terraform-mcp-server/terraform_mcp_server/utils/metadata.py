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

from datetime import datetime
from typing import Dict, Any, Optional
import os


def generate_base_metadata(source_path: str, loader_name: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Generate standardized base metadata for a document or chunk.
    """
    metadata = {
        "source_path": source_path,
        "file_name": os.path.basename(source_path),
        "loader": loader_name,
        "ingested_at": datetime.utcnow().isoformat(),
    }
    if extra:
        metadata.update(extra)
    return metadata


def merge_metadata(parent: Dict[str, Any], child: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Merge parent and child metadata, with child values taking precedence.
    """
    merged = parent.copy()
    if child:
        merged.update(child)
    return merged


def validate_metadata(metadata: Dict[str, Any], required_fields: Optional[list] = None) -> bool:
    """
    Validate that required metadata fields are present.
    """
    if not required_fields:
        required_fields = ["source_path", "loader", "ingested_at"]
    return all(field in metadata for field in required_fields) 