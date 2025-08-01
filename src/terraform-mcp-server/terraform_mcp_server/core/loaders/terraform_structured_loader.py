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

import re
from .base import BaseDocumentLoader
from .registry import register_loader
from typing import List, Any, Dict
import os

class TerraformMarkdownStructuredLoader(BaseDocumentLoader):
    """
    Loader for extracting structured data from Terraform AWS provider Markdown documentation.
    Extracts: name, type, service, description, arguments, attributes, examples, notes.
    """
    def __init__(self, source_path: str):
        super().__init__(source_path)
        self.source_path = source_path
        self.structured_data = None
        self._raw_markdown = self._read_raw_markdown()
        self._lines = self._raw_markdown.splitlines()

    def load(self) -> List[Any]:
        """
        Load and parse the Markdown file, returning a single structured document.
        """
        return [self._extract_structured_data()]

    def _extract_structured_data(self) -> Dict[str, Any]:
        """
        Extract all structured fields from the Markdown content.
        """
        return {
            "name": self._extract_name(),
            "type": self._extract_type(),
            "service": self._extract_service(),
            "description": self._extract_description(),
            "arguments": self._extract_arguments(),  # TODO
            "attributes": self._extract_attributes(),  # TODO
            "examples": self._extract_examples(),  # TODO
            "notes": self._extract_notes()
        }

    def _read_raw_markdown(self) -> str:
        if not os.path.isfile(self.source_path):
            return ""
        with open(self.source_path, "r", encoding="utf-8") as f:
            return f.read()

    def _extract_name(self) -> str:
        # Look for the first level-1 heading (e.g., '# Resource: aws_s3_bucket')
        for line in self._lines:
            m = re.match(r'^# (Resource|Data Source): (aws_[a-zA-Z0-9_]+)', line)
            if m:
                return m.group(2)
        # Fallback: look for any heading with aws_...
        for line in self._lines:
            m = re.match(r'^# .*?(aws_[a-zA-Z0-9_]+)', line)
            if m:
                return m.group(1)
        return ""

    def _extract_type(self) -> str:
        # Infer from heading
        for line in self._lines:
            if line.startswith('# Resource:'):
                return "resource"
            if line.startswith('# Data Source:'):
                return "data_source"
        # Fallback: infer from file path
        if "/r/" in self.source_path:
            return "resource"
        if "/d/" in self.source_path:
            return "data_source"
        return ""

    def _extract_service(self) -> str:
        # Try to extract from frontmatter (subcategory: ...)
        subcat_re = re.compile(r'^---.*?subcategory:\s*"([^"]+)"', re.DOTALL)
        m = subcat_re.search(self._raw_markdown)
        if m:
            return m.group(1)
        # Fallback: look for subcategory in YAML frontmatter
        for line in self._lines[:10]:
            m = re.match(r'subcategory:\s*"?([^"]+)"?', line)
            if m:
                return m.group(1)
        # Fallback: infer from file path (e.g., .../r/s3_bucket.html.markdown -> S3)
        parts = self.source_path.split(os.sep)
        for i, part in enumerate(parts):
            if part == 'r' or part == 'd':
                if i > 0:
                    return parts[i-1].upper()
        return ""

    def _extract_description(self) -> str:
        # Extract text after the main heading, up to the next heading
        desc_lines = []
        in_desc = False
        for i, line in enumerate(self._lines):
            if re.match(r'^# (Resource|Data Source): ', line):
                in_desc = True
                continue
            if in_desc:
                if re.match(r'^#|^##', line):
                    break
                if line.strip() == '':
                    continue
                desc_lines.append(line.strip())
        return ' '.join(desc_lines)

    def _extract_notes(self) -> List[str]:
        # Extract all blockquotes with Note/Warning/Tip, including ~> style notes
        notes = []
        for line in self._lines:
            # Support both '>' and '~>' as note markers
            if line.strip().startswith('>') or line.strip().startswith('~>'):
                content = line.lstrip('>~ ').strip()
                if any(kw in content for kw in ["**NOTE:**", "**Note:**", "**Warning:**", "**Tip:**"]):
                    notes.append(content)
        return notes

    def _extract_arguments(self) -> List[Dict[str, Any]]:
        # Extract arguments from the '## Argument Reference' section (bullet style, multi-line, table style)
        # Support both '-' and '*' as bullet markers and both argument bullet styles
        args = []
        in_args = False
        current_arg = None
        section_lines = []
        for i, line in enumerate(self._lines):
            if re.match(r'^##+\s*Argument Reference', line, re.IGNORECASE):
                in_args = True
                continue
            if in_args:
                # Only break on # or ## (not ### or deeper)
                if re.match(r'^#{1,2} ', line):
                    if current_arg:
                        args.append(current_arg)
                        current_arg = None
                    break
                section_lines.append(line)
                # Bullet point style: - or * `name` (Required) - Description
                m = re.match(r'[-*]\s+`([a-zA-Z0-9_]+)`\s*\((Required|Optional)\)\s*-\s*(.+)', line)
                # Bullet point style: - or * `name` - (Required) Description
                m2 = re.match(r'[-*]\s+`([a-zA-Z0-9_]+)`\s*-\s*\((Required|Optional)[^)]*\)\s*(.+)', line)
                if m or m2:
                    if current_arg:
                        args.append(current_arg)
                    if m:
                        name = m.group(1)
                        required = m.group(2).lower() == 'required'
                        description = m.group(3).strip()
                    else:
                        name = m2.group(1)
                        required = m2.group(2).lower() == 'required'
                        description = m2.group(3).strip()
                    current_arg = {
                        'name': name,
                        'required': required,
                        'description': description
                    }
                    continue
                # Multi-line description: indented or not a new bullet/heading
                if current_arg and (line.startswith('  ') or (line.strip() and not line.strip().startswith('-') and not line.strip().startswith('*') and not re.match(r'^#|^##', line))):
                    current_arg['description'] += ' ' + line.strip()
        if current_arg:
            args.append(current_arg)
        # If no bullet arguments found, try table-style extraction
        if not args:
            # Find table header and rows
            table_start = None
            for idx, l in enumerate(section_lines):
                if '|' in l and '---' in l:
                    table_start = idx - 1  # header is before separator
                    break
            if table_start is not None and table_start >= 0:
                header = [h.strip().lower() for h in section_lines[table_start].split('|')]
                # Find column indices
                name_idx = next((i for i, h in enumerate(header) if 'name' in h), None)
                req_idx = next((i for i, h in enumerate(header) if 'required' in h), None)
                desc_idx = next((i for i, h in enumerate(header) if 'description' in h), None)
                # Parse table rows
                for row in section_lines[table_start+2:]:
                    if not row.strip() or not ('|' in row):
                        break
                    cols = [c.strip() for c in row.split('|')]
                    if len(cols) < max(name_idx, req_idx, desc_idx) + 1:
                        continue
                    name = cols[name_idx]
                    required = (cols[req_idx].lower() == 'yes') if req_idx is not None else False
                    description = cols[desc_idx] if desc_idx is not None else ''
                    args.append({
                        'name': name,
                        'required': required,
                        'description': description
                    })
        return args

    def _extract_attributes(self) -> List[Dict[str, Any]]:
        # Extract attributes from the '## Attribute Reference' section (bullet style, multi-line, table style)
        # Support both '-' and '*' as bullet markers
        attrs = []
        in_attrs = False
        current_attr = None
        section_lines = []
        for i, line in enumerate(self._lines):
            if re.match(r'^##+\s*Attribute Reference', line, re.IGNORECASE):
                in_attrs = True
                continue
            if in_attrs:
                # Stop at next heading
                if re.match(r'^#|^##', line):
                    if current_attr:
                        attrs.append(current_attr)
                        current_attr = None
                    break
                section_lines.append(line)
                # Bullet point style: - or * `name` - Description
                m = re.match(r'[-*]\s+`([a-zA-Z0-9_]+)`\s*-\s*(.+)', line)
                if m:
                    if current_attr:
                        attrs.append(current_attr)
                    name = m.group(1)
                    description = m.group(2).strip()
                    current_attr = {
                        'name': name,
                        'description': description
                    }
                    continue
                # Multi-line description: indented or not a new bullet/heading
                if current_attr and (line.startswith('  ') or (line.strip() and not line.strip().startswith('-') and not line.strip().startswith('*') and not re.match(r'^#|^##', line))):
                    current_attr['description'] += ' ' + line.strip()
        if current_attr:
            attrs.append(current_attr)
        # If no bullet attributes found, try table-style extraction
        if not attrs:
            # Find table header and rows
            table_start = None
            for idx, l in enumerate(section_lines):
                if '|' in l and '---' in l:
                    table_start = idx - 1  # header is before separator
                    break
            if table_start is not None and table_start >= 0:
                header = [h.strip().lower() for h in section_lines[table_start].split('|')]
                name_idx = next((i for i, h in enumerate(header) if 'name' in h), None)
                desc_idx = next((i for i, h in enumerate(header) if 'description' in h), None)
                for row in section_lines[table_start+2:]:
                    if not row.strip() or not ('|' in row):
                        break
                    cols = [c.strip() for c in row.split('|')]
                    if len(cols) < max(name_idx, desc_idx) + 1:
                        continue
                    name = cols[name_idx]
                    description = cols[desc_idx] if desc_idx is not None else ''
                    attrs.append({
                        'name': name,
                        'description': description
                    })
        return attrs

    def _extract_examples(self) -> List[str]:
        # Extract code blocks from the '## Example Usage' section
        examples = []
        in_examples = False
        in_code_block = False
        code_block_lines = []
        found_fenced = False
        for i, line in enumerate(self._lines):
            if re.match(r'^##+\s*Example Usage', line, re.IGNORECASE):
                in_examples = True
                continue
            if in_examples:
                # Only break on # or ## (not ### or deeper)
                if re.match(r'^#{1,2} ', line):
                    break
                # Fenced code block
                if line.strip().startswith('```'):
                    found_fenced = True
                    if not in_code_block:
                        in_code_block = True
                        code_block_lines = []
                        continue
                    else:
                        # End of code block
                        in_code_block = False
                        examples.append('\n'.join(code_block_lines))
                        code_block_lines = []
                        continue
                if in_code_block:
                    code_block_lines.append(line)
        # If no fenced code blocks found, try indented code blocks
        if not examples:
            in_indented = False
            indented_lines = []
            for i, line in enumerate(self._lines):
                if re.match(r'^##+\s*Example Usage', line, re.IGNORECASE):
                    in_examples = True
                    continue
                if in_examples:
                    if re.match(r'^#{1,2} ', line):
                        if in_indented and indented_lines:
                            examples.append('\n'.join(indented_lines))
                        break
                    if (line.startswith('    ') or line.startswith('\t')):
                        if not in_indented:
                            in_indented = True
                            indented_lines = []
                        indented_lines.append(line.lstrip())
                    else:
                        if in_indented and indented_lines:
                            examples.append('\n'.join(indented_lines))
                            indented_lines = []
                        in_indented = False
            if in_indented and indented_lines:
                examples.append('\n'.join(indented_lines))
        return examples

    def extract_metadata(self, *args, **kwargs):
        """
        Stub implementation to satisfy the abstract base class.
        """
        return {}

# Register the loader for .html.markdown files (or a custom type)
register_loader("terraform_structured", TerraformMarkdownStructuredLoader) 