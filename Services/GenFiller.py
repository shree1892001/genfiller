import asyncio
import json
import os
import re
from typing import Dict, Any, List, Tuple

import fitz
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, BooleanObject, ArrayObject

from pydantic_ai import Agent
from pydantic_ai.models.gemini import GeminiModel
from pydantic import BaseModel, field_validator

from Common.constants import *

API_KEYS = {
    "field_matcher": API_KEY_3,
}


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


class MultiAgentFormFiller:
    def __init__(self):
        self.agent = Agent(
            model=GeminiModel("gemini-1.5-flash", api_key=API_KEYS["field_matcher"]),
            system_prompt="You are an expert at mapping PDF fields to JSON keys and filling them immediately."
        )

    async def extract_pdf_fields(self, pdf_path: str) -> Dict[str, int]:
        """Extracts all fillable fields from a multi-page PDF, with enhanced detection for address fields."""
        print("🔍 Extracting all fillable fields...")
        doc = fitz.open(pdf_path)
        fields = {}
        address_components = {}
        address_pattern = r"Street\s+address|City|State|Zip\s+Code"

        # First pass: extract actual form fields from PDF
        for page_num, page in enumerate(doc, start=0):
            for widget in page.widgets():

                if widget.field_name:
                    field_name = widget.field_name.strip()
                    sanitized_field_name = field_name
                    fields[sanitized_field_name] = page_num

        # If few or no fields found, do text-based extraction with improved patterns
        if len(fields) < 5:
            print("⚠️ Few form fields found. Performing enhanced text-based extraction...")
            for page_num, page in enumerate(doc):
                text = page.get_text("text")

                # Address field detection
                address_matches = re.finditer(r"(Street\s+address|City|State|Zip\s+Code)", text)
                for match in address_matches:
                    address_component = match.group(1)
                    position = match.start()
                    address_components[address_component] = (page_num, position)
                    fields[address_component] = page_num
                    print(f"📍 Found address component: {address_component} on page {page_num + 1}")

                # General form field detection - improved patterns
                # Look for form fields with various indicators
                label_matches = re.findall(r"(\d+\.\s*[\w\s,]+)[:]\s*", text)  # Numbered fields like "1. Name:"
                form_matches = re.findall(r"([\w\s,]+)(?:_+|\[\s*\]|\(\s*\)|\s*:)",
                                          text)  # Fields with underscores, brackets
                checkbox_matches = re.findall(r"(?:□|☐|⬜)\s*([\w\s,]+)", text)  # Checkbox-style fields

                # Specific pattern for fields that might span multiple lines
                multiline_matches = re.findall(r"(\w[\w\s]+)[\s]*(?:\n|:)", text)

                all_matches = set(label_matches + form_matches + checkbox_matches + multiline_matches)

                for match in all_matches:
                    field_name = match.strip()
                    # Filter out very short field names and common false positives
                    if field_name and len(field_name) > 2 and not re.match(r"^(the|and|or|of|to|in|for|a|an)$",
                                                                           field_name.lower()):
                        sanitized_field_name = field_name
                        fields[sanitized_field_name] = page_num
                        print(f"✅ Extracted field: {sanitized_field_name} on page {page_num + 1}")

                # Special handling for address fields - detect columns and related fields
                address_section = re.search(r"(Street address\s+City\s+State\s+Zip Code)", text)
                if address_section:
                    print(f"📮 Found complete address section on page {page_num + 1}")
                    if "Street address" not in fields:
                        fields["Street address"] = page_num
                    if "City" not in fields:
                        fields["City"] = page_num
                    if "State" not in fields:
                        fields["State"] = page_num
                    if "Zip Code" not in fields:
                        fields["Zip Code"] = page_num

        print(f"✅ Extracted {len(fields)} fields across {len(doc)} pages.")
        doc.close()
        return fields

    async def match_and_fill_fields(self, pdf_path: str, json_data: Dict[str, Any], output_pdf: str,
                                    max_retries: int = 3):
        """Matches fields using AI and fills them immediately across multiple pages."""
        pdf_fields = await self.extract_pdf_fields(pdf_path)
        flat_json = self.flatten_json(json_data)

        # Enhanced prompt to handle address fields specifically
        prompt = """
You are an expert at matching JSON data to PDF form fields.

JSON DATA:
{json_data}

PDF FORM FIELDS:
{pdf_fields}

Special instructions:
1. For address fields, look for components like "Street address", "City", "State", and "Zip Code".
2. Match each JSON field to the most appropriate PDF field.
3. For fields that aren't explicitly matched, suggest reasonable defaults.
4. For address fields, separate the components properly.

Return a JSON object with "matches" array containing objects with these properties:
- "json_field": The original JSON field name
- "pdf_field": The matched PDF field name
- "suggested_value": The value to fill in
- "confidence": A number between 0-1 indicating confidence in the match
- "reasoning": Short explanation for the match

Example:
{{"matches": [
  {{"json_field": "company.address.street", "pdf_field": "Street address", "suggested_value": "123 Main St", "confidence": 0.95, "reasoning": "Direct match for street address"}}
]}}
        """.format(
            json_data=json.dumps(flat_json, indent=2),
            pdf_fields=json.dumps(list(pdf_fields.keys()), indent=2)
        )

        matches = []
        for attempt in range(max_retries):
            response = await self.agent.run(prompt)
            matches = self.parse_ai_response(response.data)

            if matches:
                break

            print(f"Attempt {attempt + 1}/{max_retries} failed to get valid matches. Retrying...")

        if not matches:
            print("⚠️ No valid field matches were found after all attempts.")

        # Add logic to break down address if needed
        enhanced_matches = self.enhance_address_matching(matches, flat_json, pdf_fields)

        self.fill_pdf_immediately(pdf_path, output_pdf, enhanced_matches, pdf_fields)

    def enhance_address_matching(self, matches: List[FieldMatch], json_data: Dict[str, Any],
                                 pdf_fields: Dict[str, int]) -> List[FieldMatch]:
        """Enhances address field matching by breaking down full addresses into components."""
        # Check if we have address components in the PDF fields
        address_components = ["Street address", "City", "State", "Zip Code"]
        has_address_components = any(component in pdf_fields for component in address_components)

        if not has_address_components:
            return matches

        # Look for address fields in the matches
        address_matches = [m for m in matches if 'address' in m.json_field.lower()]
        full_address_match = next((m for m in address_matches if 'full' in m.json_field.lower()
                                   or ('street' not in m.json_field.lower() and
                                       'city' not in m.json_field.lower() and
                                       'state' not in m.json_field.lower() and
                                       'zip' not in m.json_field.lower())), None)

        # If we found a full address but no component matches, break it down
        if full_address_match and full_address_match.suggested_value:
            full_address = str(full_address_match.suggested_value)
            components = self.parse_address(full_address)

            new_matches = []
            for match in matches:
                if match != full_address_match:  # Keep all non-full-address matches
                    new_matches.append(match)

            # Add component matches
            for component_name, component_value in components.items():
                if component_name in pdf_fields and component_value:
                    new_match = FieldMatch(
                        json_field=f"address.{component_name.lower().replace(' ', '_')}",
                        pdf_field=component_name,
                        suggested_value=component_value,
                        confidence=0.9,
                        reasoning=f"Extracted from full address: {full_address}"
                    )
                    new_matches.append(new_match)
                    print(f"📬 Extracted address component: {component_name} = {component_value}")

            return new_matches

        return matches

    def parse_address(self, address: str) -> Dict[str, str]:
        """Parse a full address into components."""
        # Simple address parser - can be enhanced with regex patterns
        components = {
            "Street address": "",
            "City": "",
            "State": "",
            "Zip Code": ""
        }

        # Try to parse based on common patterns
        address_parts = address.split(',')

        if len(address_parts) >= 2:
            components["Street address"] = address_parts[0].strip()

            # Try to extract city, state, zip from the last part
            city_state_zip = address_parts[-1].strip()
            match = re.search(r'([^0-9]+)\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)', city_state_zip)

            if match:
                components["City"] = match.group(1).strip()
                components["State"] = match.group(2).strip()
                components["Zip Code"] = match.group(3).strip()
            else:
                # If we couldn't parse the standard format, try other patterns
                state_zip = re.search(r'([A-Z]{2})\s+(\d{5}(?:-\d{4})?)', city_state_zip)
                if state_zip:
                    components["State"] = state_zip.group(1).strip()
                    components["Zip Code"] = state_zip.group(2).strip()
                    # Try to extract city
                    city_match = re.search(r'(.+?)\s+[A-Z]{2}', city_state_zip)
                    if city_match:
                        components["City"] = city_match.group(1).strip()

        return components

    def parse_ai_response(self, response_text: str) -> List[FieldMatch]:
        """Parses AI response and extracts valid JSON matches, handling missing fields."""
        response_text = re.sub(r"^```json", "", response_text).strip().rstrip("```")
        try:
            data = json.loads(response_text)
            matches = []

            for match in data.get("matches", []):
                match.setdefault("confidence", 1.0)
                match.setdefault("reasoning", "No reasoning provided.")

                try:
                    validated_match = FieldMatch(**match)
                    matches.append(validated_match)
                except Exception as e:
                    print(f"⚠️ Skipping malformed match: {match} | Error: {e}")

            return matches
        except json.JSONDecodeError:
            print("❌ AI returned invalid JSON. Retrying...")
            return []

    def fill_pdf_immediately(self, template_pdf: str, output_pdf: str, matches: List[FieldMatch],
                             pdf_fields: Dict[str, int]):
        """Fills PDF form fields using PyMuPDF (fitz) for better compatibility."""

        doc = fitz.open(template_pdf)
        filled_fields = {}

        # First, check if we need to handle address fields specially
        address_fields = {"Street address", "City", "State", "Zip Code"}
        address_matches = {m.pdf_field: m for m in matches if m.pdf_field in address_fields}

        # Process regular form fields first
        for match in matches:
            if match.pdf_field and match.suggested_value is not None:
                page_num = pdf_fields.get(match.pdf_field, 0)
                page = doc[page_num]

                field_found = False
                for widget in page.widgets():
                    if widget.field_name == match.pdf_field:
                        print(f"✍️ Filling: '{match.suggested_value}' → '{match.pdf_field}' (Page {page_num + 1})")
                        try:
                            # Update the field value
                            widget.field_value = str(match.suggested_value)
                            # Apply the changes to the widget
                            widget.update()
                            filled_fields[match.pdf_field] = match.suggested_value
                            field_found = True
                        except Exception as e:
                            print(f"⚠️ Error filling {match.pdf_field}: {e}")
                        break

                # If it's an address component and no widget was found, try annotation-based insertion
                if not field_found and match.pdf_field in address_fields:
                    # Look for text areas where we might need to insert the value
                    self.attempt_text_insertion(doc, page_num, match.pdf_field, str(match.suggested_value))

        doc.save(output_pdf)
        doc.close()

        print(f"✅ Successfully filled {len(filled_fields)} fields: {list(filled_fields.keys())[:5]}...")

        self.verify_pdf_filled(output_pdf)
        return filled_fields

    def attempt_text_insertion(self, doc, page_num, field_name, value):
        """Attempts to insert text at the appropriate position for non-widget fields."""
        page = doc[page_num]

        # Define search patterns for common field labels
        field_patterns = {
            "Street address": ["Street address", "Address", "Street"],
            "City": ["City"],
            "State": ["State"],
            "Zip Code": ["Zip Code", "Zip", "ZIP"]
        }

        # Get the patterns for this field
        patterns = field_patterns.get(field_name, [field_name])

        # Get page text and try to locate the field
        text = page.get_text("text")
        field_pos = None

        for pattern in patterns:
            match = re.search(f"{pattern}", text)
            if match:
                field_pos = match.end()
                break

        if field_pos is not None:
            # Calculate insertion position (approximate)
            # For a real implementation, you'd need to convert text position to page coordinates
            # This is simplified and might need adjustment based on the PDF structure
            print(f"🖋️ Attempting to insert '{value}' for field '{field_name}' at text position {field_pos}")

            # In a real implementation, you would:
            # 1. Convert text position to page coordinates
            # 2. Insert text annotation or form field at those coordinates
            # PyMuPDF provides insert_text() and add_freetext_annot() methods

    def verify_pdf_filled(self, pdf_path: str) -> bool:
        """Verifies that the PDF has been filled correctly."""
        reader = PdfReader(pdf_path)
        fields = reader.get_fields()

        if not fields:
            print("⚠️ No fillable fields found. PDF may be flattened.")
            return False

        filled_fields = {k: v.get("/V") for k, v in fields.items() if v.get("/V")}
        print(f"✅ Filled {len(filled_fields)} fields: {list(filled_fields.keys())[:5]}...")
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
    form_filler = MultiAgentFormFiller()
    template_pdf = "D:\\demo\\Services\\arizonallc.pdf"
    json_path = "D:\\demo\\Services\\form_data1.json"
    output_pdf = "D:\\demo\\Services\\fill_smart15.pdf"

    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    await form_filler.match_and_fill_fields(template_pdf, json_data, output_pdf)
    print(f"✅ PDF processing completed: {output_pdf}")


if __name__ == "__main__":
    asyncio.run(main())