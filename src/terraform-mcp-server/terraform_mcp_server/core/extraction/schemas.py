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

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class Argument(BaseModel):
    """
    Represents a Terraform resource argument (input parameter).
    """
    name: str = Field(..., description="Argument name")
    type: str = Field(..., description="Argument type (string, number, etc.)")
    required: bool = Field(..., description="Is this argument required?")
    description: Optional[str] = Field(None, description="Argument description")

class Attribute(BaseModel):
    """
    Represents a Terraform resource attribute (output property).
    """
    name: str = Field(..., description="Attribute name")
    type: str = Field(..., description="Attribute type (string, number, etc.)")
    description: Optional[str] = Field(None, description="Attribute description")

class TFResourceSchema(BaseModel):
    """
    Schema for a Terraform resource entity extracted from documentation.
    Includes a confidence score (0.0-1.0) for LLM self-assessment and optional provenance metadata.
    """
    resource_type: str = Field(..., description="Terraform resource type (e.g., aws_s3_bucket)")
    service: Optional[str] = Field(None, description="Service category (e.g., AWS S3)")
    description: Optional[str] = Field(None, description="Resource description")
    arguments: List[Argument] = Field(default_factory=list, description="List of arguments")
    attributes: List[Attribute] = Field(default_factory=list, description="List of attributes")
    examples: Optional[List[str]] = Field(default_factory=list, description="Usage examples")
    notes: Optional[List[str]] = Field(default_factory=list, description="Additional notes")
    confidence: float = Field(..., description="LLM self-assessed confidence score (0.0-1.0)")
    provenance: Optional[Dict[str, Any]] = Field(None, description="Provenance metadata for auditability and traceability.")

class BestPracticeSchema(BaseModel):
    """
    Schema for best practice and security recommendations for a Terraform resource.
    Includes a required, unique 'title' field, a confidence score (0.0-1.0) for LLM self-assessment, and optional provenance metadata.
    """
    title: str = Field(..., description="A concise, descriptive title for this best practice (required, unique)")
    resource_type: str = Field(..., description="Terraform resource type")
    best_practices: List[str] = Field(default_factory=list, description="Best practice recommendations")
    security: Optional[List[str]] = Field(default_factory=list, description="Security recommendations")
    compliance: Optional[List[str]] = Field(default_factory=list, description="Compliance requirements")
    pitfalls: Optional[List[str]] = Field(default_factory=list, description="Common pitfalls to avoid")
    confidence: float = Field(..., description="LLM self-assessed confidence score (0.0-1.0)")
    provenance: Optional[Dict[str, Any]] = Field(None, description="Provenance metadata for auditability and traceability.") 