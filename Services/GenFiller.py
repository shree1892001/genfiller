import asyncio
import json
import os
import re
from typing import Dict, Any, List, Tuple, Optional

import fitz
from pypdf import PdfReader, PdfWriter
from pydantic import BaseModel, field_validator

from pydantic_ai import Agent
from pydantic_ai.models.gemini import GeminiModel
from Common.constants import *
# Constants would be imported from your Common.constants
# API_KEY_3 = "your-api-key-here"  # Replace with your actual key
API_KEYS = {"field_matcher": API_KEY_3}

# Improved prompt template
PDF_FIELD_MATCHING_PROMPT = """
You are an expert at mapping JSON data to PDF form fields.

The extracted text fields from a PDF form are:
{pdf_fields}

The JSON data to be filled into the form is:
{json_data}

For each PDF field, determine the most appropriate JSON field to map it to. Then provide a suggested value based on the JSON data.

Return your response in the following JSON format:
```json
{{
  "matches": [
    {{
      "json_field": "The full path to the JSON field",
      "pdf_field": "The exact PDF field name",
      "confidence": 0.95,
      "suggested_value": "The value to fill in the PDF field",
      "reasoning": "Brief explanation of why this is a good match"
    }},
    ...more matches...
  ]
}}
```

Be precise and ensure your response can be parsed as valid JSON.
"""


class FieldMatch(BaseModel):
    json_field: str
    pdf_field: str
    confidence: float
    suggested_value: Any
    reasoning: str

    @field_validator("confidence")
    def validate_confidence(cls, v):
        if not (0 <= v <= 1):
            raise ValueError("Confidence must be between 0 and 1")
        return float(v)


class ExtractedField(BaseModel):
    field_name: str
    page_num: int
    field_type: str = "text"  # Could be "text", "checkbox", etc.
    context_before: str = ""
    context_after: str = ""


class ImprovedFormFiller:
    def __init__(self):
        self.agent = Agent(
            model=GeminiModel("gemini-1.5-flash", api_key=API_KEYS["field_matcher"]),
            system_prompt="You are an expert at mapping PDF fields to JSON keys and filling forms accurately."
        )

    async def extract_pdf_fields(self, pdf_path: str) -> Dict[str, ExtractedField]:
        """Enhanced extraction of form fields from PDF text."""
        print("🔍 Extracting all fillable fields...")
        doc = fitz.open(pdf_path)
        fields = {}

        # First try to get actual form fields
        for page_num, page in enumerate(doc):
            widgets_found = False
            for widget in page.widgets():
                widgets_found = True
                if widget.field_name:
                    field_name = widget.field_name.strip()
                    fields[field_name] = ExtractedField(
                        field_name=field_name,
                        page_num=page_num,
                        field_type=widget.field_type_string
                    )
                    print(
                        f"✅ Extracted form field: '{field_name}' (Type: {widget.field_type_string}) on page {page_num + 1}")

            # If no widgets found on this page, try text extraction
            if not widgets_found:
                self._extract_text_based_fields(page, page_num, fields)

        # If no form fields found at all, use text analysis on all pages
        if not fields:
            print("⚠️ No form fields found. Attempting text-based extraction on all pages...")
            for page_num, page in enumerate(doc):
                self._extract_text_based_fields(page, page_num, fields)

        print(f"✅ Extracted {len(fields)} fields across {len(doc)} pages.")
        doc.close()
        return fields

    def _extract_text_based_fields(self, page, page_num, fields):
        """Extract potential form fields from text on a page."""
        text = page.get_text("text")
        blocks = page.get_text("blocks")  # Get text blocks for better context
        lines = text.split('\n')

        # Various patterns that might indicate form fields
        patterns = [
            r"([\w\s,]+)[:]\s*",  # Label followed by colon
            r"([\w\s,]+)(?:_+|\[\s*\]|\(\s*\))",  # Label followed by underscores or brackets
            r"([\w\s\-,]+)(?:\s*□\s*|\s*■\s*)",  # Label followed by checkbox symbol
        ]

        for i, line in enumerate(lines):
            for pattern in patterns:
                matches = re.findall(pattern, line)
                for match in matches:
                    field_name = match.strip()
                    if field_name and len(field_name) > 2:
                        # Get context before and after
                        context_before = lines[i - 1] if i > 0 else ""
                        context_after = lines[i + 1] if i < len(lines) - 1 else ""

                        # Skip if already found as actual form field
                        if field_name in fields:
                            continue

                        fields[field_name] = ExtractedField(
                            field_name=field_name,
                            page_num=page_num,
                            field_type="text",
                            context_before=context_before,
                            context_after=context_after
                        )
                        print(f"✅ Extracted text field: '{field_name}' on page {page_num + 1}")

    def prepare_field_matching_prompt(self, fields: Dict[str, ExtractedField], json_data: Dict[str, Any]) -> str:
        """Create a more informative prompt for the AI model."""
        flat_json = self.flatten_json(json_data)

        # Create richer field descriptions with context
        field_descriptions = []
        for field_name, info in fields.items():
            context = f"Type: {info.field_type}"
            if info.context_before:
                context += f", Context before: '{info.context_before}'"
            if info.context_after:
                context += f", Context after: '{info.context_after}'"

            field_descriptions.append({
                "name": field_name,
                "page": info.page_num + 1,
                "context": context
            })

        return PDF_FIELD_MATCHING_PROMPT.format(
            json_data=json.dumps(flat_json, indent=2),
            pdf_fields=json.dumps(field_descriptions, indent=2)
        )

    async def match_and_fill_fields(self, pdf_path: str, json_data: Dict[str, Any], output_pdf: str,
                                    max_retries: int = 3):
        """Enhanced matching and filling logic."""
        fields = await self.extract_pdf_fields(pdf_path)

        prompt = self.prepare_field_matching_prompt(fields, json_data)

        matches = []
        for attempt in range(max_retries):
            try:
                print(f"🤖 Attempt {attempt + 1}/{max_retries} to match fields...")
                response = await self.agent.run(prompt)
                matches = self.parse_ai_response(response.data)

                if matches:
                    print(f"✅ Successfully matched {len(matches)} fields.")
                    break

            except Exception as e:
                print(f"❌ Error in AI matching: {e}")

            print(f"Attempt {attempt + 1}/{max_retries} failed. Retrying...")

        if not matches:
            print("⚠️ No valid field matches were found after all attempts.")
            return False

        filled_fields = self.fill_pdf_fields(pdf_path, output_pdf, matches, fields)
        return filled_fields

    def parse_ai_response(self, response_text: str) -> List[FieldMatch]:
        """Parse AI response with better error handling."""
        # Extract JSON from code blocks if present
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
        if json_match:
            response_text = json_match.group(1).strip()
        else:
            response_text = response_text.strip()

        try:
            data = json.loads(response_text)
            matches = []

            for match in data.get("matches", []):
                try:
                    # Set defaults for missing fields
                    match.setdefault("confidence", 0.8)
                    match.setdefault("reasoning", "No reasoning provided.")
                    match.setdefault("suggested_value", "")

                    validated_match = FieldMatch(**match)
                    matches.append(validated_match)
                    print(f"✓ Matched: {match['pdf_field']} → {match['json_field']} ({match['confidence']:.2f})")

                except Exception as e:
                    print(f"⚠️ Skipping malformed match: {match} | Error: {e}")

            return matches

        except json.JSONDecodeError as e:
            print(f"❌ AI returned invalid JSON: {e}")
            print(f"Response text: {response_text[:200]}...")
            return []

    def fill_pdf_fields(self, template_pdf: str, output_pdf: str, matches: List[FieldMatch],
                        fields: Dict[str, ExtractedField]) -> Dict[str, Any]:
        """Fill PDF form fields using widgets when available, falling back to text insertion."""
        doc = fitz.open(template_pdf)
        filled_fields = {}

        for match in matches:
            if match.pdf_field and match.suggested_value is not None:
                field_info = fields.get(match.pdf_field)
                if not field_info:
                    print(f"⚠️ Field '{match.pdf_field}' not found in extracted fields.")
                    continue

                page_num = field_info.page_num
                page = doc[page_num]

                widget_filled = False

                # First try to fill using form widgets if they exist
                for widget in page.widgets():
                    if widget.field_name == match.pdf_field:
                        print(f"✍️ Filling: '{match.suggested_value}' → '{match.pdf_field}' (Page {page_num + 1})")
                        try:
                            # Update the field value
                            widget.field_value = str(match.suggested_value)
                            # Apply the changes to the widget
                            widget.update()
                            filled_fields[match.pdf_field] = match.suggested_value
                            widget_filled = True
                        except Exception as e:
                            print(f"⚠️ Error filling widget {match.pdf_field}: {e}")
                        break

                # If no widget was filled, try text insertion for text-extracted fields
                if not widget_filled and field_info.field_type == "text":
                    try:
                        # Find the text on the page
                        instances = page.search_for(match.pdf_field)
                        if instances:
                            # Define a position after or below the field label
                            rect = instances[0]
                            text_point = fitz.Point(rect[2] + 5, rect[1])  # To the right of field label

                            print(
                                f"✍️ Inserting text: '{match.suggested_value}' for '{match.pdf_field}' (Page {page_num + 1})")

                            page.insert_text(
                                text_point,
                                str(match.suggested_value),
                                fontsize=10,
                                color=(0, 0, 1)  # Blue color for inserted text
                            )
                            filled_fields[match.pdf_field] = match.suggested_value
                        else:
                            print(f"⚠️ Could not locate text field '{match.pdf_field}' on page {page_num + 1}")
                    except Exception as e:
                        print(f"⚠️ Error inserting text for {match.pdf_field}: {e}")

        doc.save(output_pdf)
        doc.close()

        print(f"✅ Successfully filled {len(filled_fields)} fields: {list(filled_fields.keys())[:5]}...")

        self.verify_pdf_filled(output_pdf)
        return filled_fields

    def verify_pdf_filled(self, pdf_path: str) -> bool:
        """Verifies that the PDF has been filled correctly."""
        reader = PdfReader(pdf_path)
        fields = reader.get_fields()

        if not fields:
            print("⚠️ No fillable form fields found in output PDF. PDF may be flattened or text-only.")
            return False

        filled_fields = {k: v.get("/V") for k, v in fields.items() if v.get("/V")}
        print(f"✓ Verification found {len(filled_fields)} filled form fields.")
        return bool(filled_fields)

    def flatten_json(self, data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        """Flattens nested JSON objects into a flat dictionary."""
        items = {}
        for key, value in data.items():
            new_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                items.update(self.flatten_json(value, new_key))
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        items.update(self.flatten_json(item, f"{new_key}[{i}]"))
                    else:
                        items[f"{new_key}[{i}]"] = item
            else:
                items[new_key] = value
        return items


async def main():
    form_filler = ImprovedFormFiller()
    template_pdf = "D:\\demo\\Services\\WisconsinLLC.pdf"
    json_path = "D:\\demo\\Services\\form_data.json"
    output_pdf = "D:\\demo\\Services\\filled_Wisconsin_LLC.pdf"

    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    filled_fields = await form_filler.match_and_fill_fields(template_pdf, json_data, output_pdf)

    if filled_fields:
        print(f"✅ PDF successfully processed: {output_pdf}")
    else:
        print(f"❌ PDF processing failed. Please check the output file and logs.")


if __name__ == "__main__":
    asyncio.run(main())