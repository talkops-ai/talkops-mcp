"""Validation service for Helm charts and Kubernetes manifests."""

import json
import yaml
from typing import Dict, Any, Optional, List
from helm_mcp_server.config import ServerConfig
from helm_mcp_server.exceptions import HelmValidationError
from helm_mcp_server.utils.helm_helper import check_for_dangerous_patterns


class ValidationService:
    """Service for validating Helm charts and Kubernetes manifests."""
    
    def __init__(self, config: ServerConfig):
        """Initialize with configuration."""
        self.config = config
    
    def validate_values(
        self,
        chart_name: str,
        values: Dict[str, Any],
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Validate Helm chart values against schema.
        
        Args:
            chart_name: Chart name
            values: Values to validate
            schema: Optional JSON schema for validation
        
        Returns:
            Validation result with status and any errors
        
        Raises:
            HelmValidationError: If validation fails
        """
        # Safety check: Check for dangerous patterns in chart_name and values
        # Convert values to string representation for pattern checking
        values_str = json.dumps(values)
        chart_name_str = str(chart_name)
        
        # Check chart_name
        pattern = check_for_dangerous_patterns([chart_name_str], log_prefix='[validate_values] ')
        if pattern:
            raise HelmValidationError(
                f"Dangerous pattern detected in chart_name: '{pattern}'. Aborting validation for safety."
            )
        
        # Check values (convert dict to list of string representations)
        values_check_list = [values_str]
        pattern = check_for_dangerous_patterns(values_check_list, log_prefix='[validate_values] ')
        if pattern:
            raise HelmValidationError(
                f"Dangerous pattern detected in values: '{pattern}'. Aborting validation for safety."
            )
        
        errors = []
        warnings = []
        
        # Basic validation
        if not values:
            warnings.append('No values provided, using chart defaults')
        
        # Check for common issues
        if 'replicas' in values:
            replicas = values.get('replicas', 1)
            if not isinstance(replicas, int) or replicas < 1:
                errors.append(f'Invalid replicas value: {replicas} (must be positive integer)')
            elif replicas > 100:
                warnings.append(f'High replica count: {replicas} (may cause resource issues)')
        
        if 'imageTag' in values and values.get('imageTag') == 'latest':
            warnings.append("Using 'latest' tag is not recommended for production")
        
        # Schema validation if provided
        if schema:
            try:
                # Simplified schema validation - could use jsonschema library
                required_fields = schema.get('required', [])
                for field in required_fields:
                    if field not in values:
                        errors.append(f'Required field missing: {field}')
            except Exception as e:
                errors.append(f'Schema validation error: {str(e)}')
        
        if errors:
            raise HelmValidationError(f'Validation failed: {json.dumps(errors)}')
        
        return {
            'valid': True,
            'warnings': warnings,
            'errors': [],
            'chart_name': chart_name
        }
    
    def validate_manifests(self, manifests: str) -> Dict[str, Any]:
        """Validate Kubernetes manifests (basic YAML and structure validation).
        
        Args:
            manifests: Kubernetes manifests as YAML string
        
        Returns:
            Validation result with status and any errors
        
        Raises:
            HelmValidationError: If validation fails
        
        Note:
            Dangerous pattern checking is not performed on manifests as they legitimately
            contain shell references (e.g., 'sh', '/bin/sh') in container commands,
            init containers, and other Kubernetes resource definitions.
        """
        errors = []
        warnings = []
        
        # Check if manifests is empty
        if not manifests or not manifests.strip():
            raise HelmValidationError('Manifests string is empty')
        
        # Check manifest size (warn if very large)
        manifest_size = len(manifests)
        if manifest_size > 10_000_000:  # 10MB
            warnings.append(f'Manifests are very large ({manifest_size / 1_000_000:.1f}MB), validation may be slow')
        
        try:
            # Try parsing with safe_load_all first (handles multiple documents with --- separators)
            documents = []
            try:
                documents = list(yaml.safe_load_all(manifests))
            except yaml.YAMLError as parse_error:
                # If safe_load_all fails, try parsing documents individually
                # Split by document separator and parse each one
                warnings.append(f'Failed to parse as multi-document YAML, trying individual document parsing: {str(parse_error)[:200]}')
                
                # Split by document separator
                doc_parts = manifests.split('---')
                parsed_count = 0
                
                for i, doc_part in enumerate(doc_parts):
                    doc_part = doc_part.strip()
                    if not doc_part:
                        continue
                    
                    try:
                        doc = yaml.safe_load(doc_part)
                        if doc:
                            documents.append(doc)
                            parsed_count += 1
                    except yaml.YAMLError as doc_error:
                        # Log which document failed but continue parsing others
                        line_num = manifests[:manifests.find(doc_part)].count('\n') + 1
                        errors.append(f'Failed to parse document {i+1} (around line {line_num}): {str(doc_error)[:200]}')
                
                if parsed_count == 0:
                    # If we couldn't parse any documents, raise the original error
                    raise parse_error
            
            if not documents:
                errors.append('No valid YAML documents found')
            
            resource_count = 0
            resource_types = {}
            
            for doc in documents:
                if doc and isinstance(doc, dict):
                    resource_count += 1
                    kind = doc.get('kind', 'Unknown')
                    resource_types[kind] = resource_types.get(kind, 0) + 1
                    
                    # Basic structure validation
                    if 'apiVersion' not in doc:
                        warnings.append(f'Resource missing apiVersion: {kind}')
                    if 'metadata' not in doc:
                        errors.append(f'Resource missing metadata: {kind}')
            
            # If we have some valid documents but also errors, return partial success
            if errors and resource_count > 0:
                warnings.append(f'Validation completed with {len(errors)} error(s), but found {resource_count} valid resource(s)')
            
            if errors and resource_count == 0:
                # Only fail if we have errors AND no valid resources
                raise HelmValidationError(f'Manifest validation failed: {json.dumps(errors[:10])}')  # Limit error details
            
            return {
                'valid': True,
                'resource_count': resource_count,
                'resource_types': resource_types,
                'warnings': warnings,
                'errors': errors[:10] if errors else []  # Limit errors in response
            }
        
        except yaml.YAMLError as e:
            error_msg = str(e)
            # Provide more helpful error message for common issues
            if 'document start' in error_msg.lower():
                error_msg += (
                    '. This usually means the YAML is missing document separators (---) or contains invalid syntax. '
                    'Kubernetes manifests should be separated by "---" between documents.'
                )
            raise HelmValidationError(f'Invalid YAML: {error_msg}')
        except HelmValidationError:
            # Re-raise our own errors
            raise
        except Exception as e:
            raise HelmValidationError(f'Manifest validation error: {str(e)}')

