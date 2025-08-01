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

import json
from .schemas import TFResourceSchema, BestPracticeSchema

class PromptManager:
    """
    Manages prompt templates for LLM extraction tasks.
    """
    @staticmethod
    def get_test_prompt() -> str:
        """
        Returns a simple prompt for testing LLM connectivity and JSON output.
        """
        return (
            "Extract the main Terraform resource from this text and return it as JSON:\n\n"
            "Text: \"The aws_s3_bucket resource creates an S3 bucket in AWS. It supports versioning and encryption.\"\n\n"
            "Expected format:\n"
            "{\n  \"resource\": \"aws_s3_bucket\",\n  \"description\": \"creates an S3 bucket in AWS\"\n}"
        )

    @staticmethod
    def get_resource_prompt(text: str) -> str:
        """
        Returns a prompt for extracting a Terraform resource entity from documentation text.
        The prompt includes the TFResourceSchema JSON schema and explicit instructions.
        """
        schema = TFResourceSchema.model_json_schema()
        return (
            "You are an expert in Terraform documentation extraction.\n"
            "Extract the following information from the provided text and respond ONLY with a JSON object matching this schema.\n"
            "Include a field 'confidence' (float, 0.0-1.0) indicating how certain you are about the correctness of this extraction.\n"
            "A confidence of 1.0 means you are completely certain; 0.0 means you are guessing.\n"
            f"{json.dumps(schema, indent=2)}\n"
            "Text:\n"
            f"{text}\n"
        )

    @staticmethod
    def get_best_practice_prompt(text: str) -> str:
        """
        Returns a prompt for extracting best practices and security recommendations from documentation text.
        The prompt includes the BestPracticeSchema JSON schema and explicit instructions.
        """
        schema = BestPracticeSchema.model_json_schema()
        return (
            "You are an expert in Terraform security and best practices.\n"
            "For each best practice, extract:\n"
            "- 'title': A concise, descriptive title for the best practice (required, unique, 3-12 words).\n"
            "- 'resource_type': The Terraform resource or context this applies to.\n"
            "- 'best_practices': List of recommendations.\n"
            "- 'security', 'compliance', 'pitfalls', etc.\n"
            "Respond ONLY with a JSON object matching this schema.\n"
            "Include a field 'confidence' (float, 0.0-1.0) indicating how certain you are about the correctness of this extraction.\n"
            "A confidence of 1.0 means you are completely certain; 0.0 means you are guessing.\n"
            f"{json.dumps(schema, indent=2)}\n"
            "Text:\n"
            f"{text}\n"
        ) 