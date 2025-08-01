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

from typing import List, Dict, Any
from terraform_mcp_server.utils.logging import get_logger

logger = get_logger(__name__)

class StructuredChunker:
    """
    Creates semantically meaningful chunks from structured Terraform data
    while preserving provider, service, and name metadata.
    """
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def chunk_terraform_resource(self, structured_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Chunk a Terraform resource's structured data into meaningful segments.
        
        Args:
            structured_data: Output from TerraformMarkdownStructuredLoader
            
        Returns:
            List of chunks with preserved metadata
        """
        chunks = []
        
        # Extract base metadata
        provider = "aws"  # Default for AWS provider
        service = structured_data.get("service", "")
        name = structured_data.get("name", "")
        resource_type = structured_data.get("type", "resource")
        
        # Chunk 1: Resource Overview
        overview_content = self._create_overview_chunk(structured_data)
        if overview_content:
            chunks.append({
                "content": overview_content,
                "provider": provider,
                "service": service,
                "name": name,
                "type": resource_type,
                "chunk_type": "overview"
            })
        
        # Chunk 2: Arguments
        arguments_content = self._create_arguments_chunk(structured_data.get("arguments", []), structured_data)
        if arguments_content:
            chunks.append({
                "content": arguments_content,
                "provider": provider,
                "service": service,
                "name": name,
                "type": resource_type,
                "chunk_type": "arguments"
            })
        
        # Chunk 3: Attributes
        attributes_content = self._create_attributes_chunk(structured_data.get("attributes", []), structured_data)
        if attributes_content:
            chunks.append({
                "content": attributes_content,
                "provider": provider,
                "service": service,
                "name": name,
                "type": resource_type,
                "chunk_type": "attributes"
            })
        
        # Chunk 4: Examples
        examples_content = self._create_examples_chunk(structured_data.get("examples", []), structured_data)
        if examples_content:
            chunks.append({
                "content": examples_content,
                "provider": provider,
                "service": service,
                "name": name,
                "type": resource_type,
                "chunk_type": "examples"
            })
        
        # Chunk 5: Notes
        notes_content = self._create_notes_chunk(structured_data.get("notes", []), structured_data)
        if notes_content:
            chunks.append({
                "content": notes_content,
                "provider": provider,
                "service": service,
                "name": name,
                "type": resource_type,
                "chunk_type": "notes"
            })
        
        return chunks

    def chunk_best_practice(self, structured_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Chunk a best practice's structured data into meaningful segments.
        
        Args:
            structured_data: Output from ChunkExtractionPipeline (BestPracticeSchema)
            
        Returns:
            List of chunks with preserved metadata
        """
        chunks = []
        
        # Extract base metadata
        provider = "aws"  # Default for AWS provider
        title = structured_data.get("title", "")
        resource_type = structured_data.get("resource_type", "")
        
        # Chunk 1: Best Practice Overview
        overview_content = self._create_best_practice_overview_chunk(structured_data)
        if overview_content:
            chunks.append({
                "content": overview_content,
                "provider": provider,
                "service": "best_practice",
                "name": title,
                "type": "best_practice",
                "chunk_type": "overview"
            })
        
        # Chunk 2: Best Practice Recommendations
        best_practices_content = self._create_best_practices_chunk(structured_data.get("best_practices", []), structured_data)
        if best_practices_content:
            chunks.append({
                "content": best_practices_content,
                "provider": provider,
                "service": "best_practice",
                "name": title,
                "type": "best_practice",
                "chunk_type": "best_practices"
            })
        
        # Chunk 3: Security Recommendations
        security_content = self._create_security_chunk(structured_data.get("security", []), structured_data)
        if security_content:
            chunks.append({
                "content": security_content,
                "provider": provider,
                "service": "best_practice",
                "name": title,
                "type": "best_practice",
                "chunk_type": "security"
            })
        
        # Chunk 4: Compliance Requirements
        compliance_content = self._create_compliance_chunk(structured_data.get("compliance", []), structured_data)
        if compliance_content:
            chunks.append({
                "content": compliance_content,
                "provider": provider,
                "service": "best_practice",
                "name": title,
                "type": "best_practice",
                "chunk_type": "compliance"
            })
        
        # Chunk 5: Common Pitfalls
        pitfalls_content = self._create_pitfalls_chunk(structured_data.get("pitfalls", []), structured_data)
        if pitfalls_content:
            chunks.append({
                "content": pitfalls_content,
                "provider": provider,
                "service": "best_practice",
                "name": title,
                "type": "best_practice",
                "chunk_type": "pitfalls"
            })
        
        return chunks

    def _create_best_practice_overview_chunk(self, data: Dict[str, Any]) -> str:
        """Create overview chunk with best practice title, resource type, and confidence."""
        content_parts = []
        
        # Best practice header with all required metadata
        title = data.get("title", "")
        resource_type = data.get("resource_type", "")
        confidence = data.get("confidence", 0.0)
        provider = "aws"  # Default for AWS provider
        
        content_parts.append(f"Provider: {provider}")
        content_parts.append(f"Service: best_practice")
        content_parts.append(f"Name: {title}")
        content_parts.append(f"Type: best_practice")
        content_parts.append(f"Resource Type: {resource_type}")
        content_parts.append(f"Confidence: {confidence}")
        
        return "\n".join(content_parts)

    def _create_best_practices_chunk(self, best_practices: List[str], data: Dict[str, Any]) -> str:
        """Create chunk for best practice recommendations."""
        if not best_practices:
            return ""
        
        content_parts = []
        
        # Add metadata header
        provider = "aws"  # Default for AWS provider
        title = data.get("title", "")
        resource_type = data.get("resource_type", "")
        
        content_parts.append(f"Provider: {provider}")
        content_parts.append(f"Service: best_practice")
        content_parts.append(f"Name: {title}")
        content_parts.append(f"Type: best_practice")
        content_parts.append(f"Resource Type: {resource_type}")
        content_parts.append("")
        content_parts.append("Best Practice Recommendations:")
        
        for i, practice in enumerate(best_practices, 1):
            content_parts.append(f"{i}. {practice}")
        
        return "\n".join(content_parts)

    def _create_security_chunk(self, security: List[str], data: Dict[str, Any]) -> str:
        """Create chunk for security recommendations."""
        if not security:
            return ""
        
        content_parts = []
        
        # Add metadata header
        provider = "aws"  # Default for AWS provider
        title = data.get("title", "")
        resource_type = data.get("resource_type", "")
        
        content_parts.append(f"Provider: {provider}")
        content_parts.append(f"Service: best_practice")
        content_parts.append(f"Name: {title}")
        content_parts.append(f"Type: best_practice")
        content_parts.append(f"Resource Type: {resource_type}")
        content_parts.append("")
        content_parts.append("Security Recommendations:")
        
        for i, sec in enumerate(security, 1):
            content_parts.append(f"{i}. {sec}")
        
        return "\n".join(content_parts)

    def _create_compliance_chunk(self, compliance: List[str], data: Dict[str, Any]) -> str:
        """Create chunk for compliance requirements."""
        if not compliance:
            return ""
        
        content_parts = []
        
        # Add metadata header
        provider = "aws"  # Default for AWS provider
        title = data.get("title", "")
        resource_type = data.get("resource_type", "")
        
        content_parts.append(f"Provider: {provider}")
        content_parts.append(f"Service: best_practice")
        content_parts.append(f"Name: {title}")
        content_parts.append(f"Type: best_practice")
        content_parts.append(f"Resource Type: {resource_type}")
        content_parts.append("")
        content_parts.append("Compliance Requirements:")
        
        for i, comp in enumerate(compliance, 1):
            content_parts.append(f"{i}. {comp}")
        
        return "\n".join(content_parts)

    def _create_pitfalls_chunk(self, pitfalls: List[str], data: Dict[str, Any]) -> str:
        """Create chunk for common pitfalls."""
        if not pitfalls:
            return ""
        
        content_parts = []
        
        # Add metadata header
        provider = "aws"  # Default for AWS provider
        title = data.get("title", "")
        resource_type = data.get("resource_type", "")
        
        content_parts.append(f"Provider: {provider}")
        content_parts.append(f"Service: best_practice")
        content_parts.append(f"Name: {title}")
        content_parts.append(f"Type: best_practice")
        content_parts.append(f"Resource Type: {resource_type}")
        content_parts.append("")
        content_parts.append("Common Pitfalls to Avoid:")
        
        for i, pitfall in enumerate(pitfalls, 1):
            content_parts.append(f"{i}. {pitfall}")
        
        return "\n".join(content_parts)

    def _create_overview_chunk(self, data: Dict[str, Any]) -> str:
        """Create overview chunk with resource name, type, service, and description."""
        content_parts = []
        
        # Resource header with all required metadata
        resource_type = data.get("type", "resource")
        name = data.get("name", "")
        service = data.get("service", "")
        provider = "aws"  # Default for AWS provider
        
        content_parts.append(f"Provider: {provider}")
        content_parts.append(f"Service: {service}")
        content_parts.append(f"Name: {name}")
        content_parts.append(f"Type: {resource_type}")
        
        # Description
        description = data.get("description", "")
        if description:
            content_parts.append(f"Description: {description}")
        
        return "\n".join(content_parts)
    
    def _create_arguments_chunk(self, arguments: List[Dict[str, Any]], data: Dict[str, Any]) -> str:
        """Create chunk for resource arguments."""
        if not arguments:
            return ""
        
        content_parts = []
        
        # Add metadata header
        provider = "aws"  # Default for AWS provider
        service = data.get("service", "")
        name = data.get("name", "")
        resource_type = data.get("type", "resource")
        
        content_parts.append(f"Provider: {provider}")
        content_parts.append(f"Service: {service}")
        content_parts.append(f"Name: {name}")
        content_parts.append(f"Type: {resource_type}")
        content_parts.append("")
        content_parts.append("Arguments:")
        
        for arg in arguments:
            name = arg.get("name", "")
            required = arg.get("required", False)
            description = arg.get("description", "")
            arg_type = arg.get("type", "")
            
            arg_line = f"- {name}"
            if required:
                arg_line += " (required)"
            if arg_type:
                arg_line += f" - {arg_type}"
            if description:
                arg_line += f": {description}"
            
            content_parts.append(arg_line)
        
        return "\n".join(content_parts)
    
    def _create_attributes_chunk(self, attributes: List[Dict[str, Any]], data: Dict[str, Any]) -> str:
        """Create chunk for resource attributes."""
        if not attributes:
            return ""
        
        content_parts = []
        
        # Add metadata header
        provider = "aws"  # Default for AWS provider
        service = data.get("service", "")
        name = data.get("name", "")
        resource_type = data.get("type", "resource")
        
        content_parts.append(f"Provider: {provider}")
        content_parts.append(f"Service: {service}")
        content_parts.append(f"Name: {name}")
        content_parts.append(f"Type: {resource_type}")
        content_parts.append("")
        content_parts.append("Attributes:")
        
        for attr in attributes:
            name = attr.get("name", "")
            description = attr.get("description", "")
            attr_type = attr.get("type", "")
            
            attr_line = f"- {name}"
            if attr_type:
                attr_line += f" ({attr_type})"
            if description:
                attr_line += f": {description}"
            
            content_parts.append(attr_line)
        
        return "\n".join(content_parts)
    
    def _create_examples_chunk(self, examples: List[str], data: Dict[str, Any]) -> str:
        """Create chunk for resource examples."""
        if not examples:
            return ""
        
        content_parts = []
        
        # Add metadata header
        provider = "aws"  # Default for AWS provider
        service = data.get("service", "")
        name = data.get("name", "")
        resource_type = data.get("type", "resource")
        
        content_parts.append(f"Provider: {provider}")
        content_parts.append(f"Service: {service}")
        content_parts.append(f"Name: {name}")
        content_parts.append(f"Type: {resource_type}")
        content_parts.append("")
        content_parts.append("Examples:")
        
        for i, example in enumerate(examples, 1):
            content_parts.append(f"Example {i}:")
            content_parts.append(example)
            content_parts.append("")  # Empty line between examples
        
        return "\n".join(content_parts)
    
    def _create_notes_chunk(self, notes: List[str], data: Dict[str, Any]) -> str:
        """Create chunk for resource notes."""
        if not notes:
            return ""
        
        content_parts = []
        
        # Add metadata header
        provider = "aws"  # Default for AWS provider
        service = data.get("service", "")
        name = data.get("name", "")
        resource_type = data.get("type", "resource")
        
        content_parts.append(f"Provider: {provider}")
        content_parts.append(f"Service: {service}")
        content_parts.append(f"Name: {name}")
        content_parts.append(f"Type: {resource_type}")
        content_parts.append("")
        content_parts.append("Notes:")
        
        for note in notes:
            content_parts.append(f"- {note}")
        
        return "\n".join(content_parts) 