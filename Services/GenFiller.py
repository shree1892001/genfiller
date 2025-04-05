import asyncio
import json
import os
import re
import shutil
from typing import Dict, Any, List, Tuple, Optional

import fitz
import numpy as np
import cv2
import pytesseract
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, BooleanObject, ArrayObject
from difflib import SequenceMatcher

from pydantic_ai import Agent
from pydantic_ai.models.gemini import GeminiModel
from pydantic import BaseModel, field_validator

from Common.constants import *

API_KEYS = {
    "field_matcher": API_KEY_1,
}


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NumpyEncoder, self).default(obj)


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


class OCRFieldMatch(BaseModel):
    json_field: str
    ocr_text: str
    page_num: int
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    pdf_field: str
    suggested_value: Any
    reasoning: str

    @field_validator("confidence")
    def validate_confidence(cls, v):
        if not (0 <= v <= 1):
            raise ValueError("Confidence must be between 0 and 1")
        return float(v)


class EnhancedFormFiller:
    def __init__(self):
        self.agent = Agent(
            model=GeminiModel("gemini-1.5-flash", api_key=API_KEYS["field_matcher"]),
            system_prompt="You are an expert at mapping PDF form fields to JSON data and filling them accurately. You analyze both field names and surrounding context to make precise matches."
        )
        self.matched_fields = {}

    async def extract_pdf_fields(self, pdf_path: str) -> Dict[str, Dict[str, Any]]:
        """Extracts all fillable fields from a multi-page PDF with additional metadata."""
        print("🔍 Extracting all fillable fields...")
        doc = fitz.open(pdf_path)
        fields = {}

        for page_num, page in enumerate(doc, start=0):
            for widget in page.widgets():
                if widget.field_name:
                    field_name = widget.field_name.strip()
                    field_type = widget.field_type
                    field_rect = widget.rect
                    field_flags = widget.field_flags

                    fields[field_name] = {
                        "page_num": page_num,
                        "type": field_type,
                        "rect": [field_rect.x0, field_rect.y0, field_rect.x1, field_rect.y1],
                        "flags": field_flags,
                        "is_readonly": bool(field_flags & 1),
                        "current_value": widget.field_value
                    }

        print(f"✅ Extracted {len(fields)} fields across {len(doc)} pages.")
        for field, info in fields.items():
            readonly_status = "READ-ONLY" if info["is_readonly"] else "EDITABLE"
            print(f" - Field: '{field}' (Page {info['page_num'] + 1}) [{readonly_status}]")

        doc.close()
        return fields

    async def extract_ocr_text(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Extract text from PDF using pytesseract OCR with position information."""
        print("🔍 Extracting text using OCR...")
        doc = fitz.open(pdf_path)
        ocr_results = []

        for page_num in range(len(doc)):
            print(f"Processing OCR for page {page_num + 1}/{len(doc)}...")
            pix = doc[page_num].get_pixmap(alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)

            if img.shape[2] == 4:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)

            # Enhanced preprocessing for better OCR results
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

            # Try multiple preprocessing techniques
            preprocessing_methods = [
                # Adaptive threshold
                lambda: cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                              cv2.THRESH_BINARY_INV, 11, 2),
                # Regular threshold
                lambda: cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)[1],
                # Otsu's threshold
                lambda: cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1],
                # Original grayscale
                lambda: gray
            ]

            # Try various OCR configurations
            configs = [
                r'--oem 3 --psm 11',  # Full page with default OCR engine
                r'--oem 3 --psm 6',  # Assume a single uniform block of text
                r'--oem 3 --psm 4'  # Assume a single column of text
            ]

            best_results = []
            best_count = 0

            # Try combinations of preprocessing and config
            for preprocess in preprocessing_methods:
                processed_img = preprocess()

                for config in configs:
                    data = pytesseract.image_to_data(processed_img, config=config,
                                                     output_type=pytesseract.Output.DICT)

                    valid_texts = [text for i, text in enumerate(data['text'])
                                   if text.strip() and data['conf'][i] >= 40]

                    if len(valid_texts) > best_count:
                        best_count = len(valid_texts)
                        best_results = data

            # If we found results, process them
            if best_count > 0:
                seen_texts = set()
                for i in range(len(best_results['text'])):
                    text = best_results['text'][i].strip().lower()
                    if not text or text in seen_texts or best_results['conf'][i] < 40:
                        continue

                    seen_texts.add(text)
                    x, y, w, h = (best_results['left'][i], best_results['top'][i],
                                  best_results['width'][i], best_results['height'][i])

                    cleaned_text = ''.join(c for c in text if c.isprintable())

                    ocr_results.append({
                        "page_num": page_num,
                        "text": cleaned_text,
                        "raw_text": text,
                        "confidence": float(best_results['conf'][i]) / 100,
                        "position": {
                            "x1": float(x),
                            "y1": float(y),
                            "x2": float(x + w),
                            "y2": float(y + h)
                        }
                    })

        doc.close()
        print(f"✅ Extracted {len(ocr_results)} text elements using OCR.")
        return ocr_results

    async def match_and_fill_fields(self, pdf_path: str, json_data: Dict[str, Any], output_pdf: str,
                                    max_retries: int = 3):
        """Matches fields using AI and fills them immediately across multiple pages."""

        # Create backup of original PDF
        backup_pdf = f"{pdf_path}.backup"
        shutil.copy2(pdf_path, backup_pdf)
        print(f"Created backup of original PDF: {backup_pdf}")

        print("Processing JSON data...")
        print(json_data)

        # Extract fields and OCR text
        pdf_fields = await self.extract_pdf_fields(pdf_path)
        ocr_text_elements = await self.extract_ocr_text(pdf_path)
        flat_json = self.flatten_json(json_data)
        field_context = await self.analyze_field_context(pdf_fields, ocr_text_elements)

        # Enhanced prompt with field context analysis
        prompt = self.create_enhanced_matching_prompt(flat_json, pdf_fields, ocr_text_elements, field_context)

        # Multiple retry attempts to get good matches
        matches, ocr_matches = [], []
        for attempt in range(max_retries):
            print(f"🤖 AI Matching Attempt {attempt + 1}/{max_retries}...")
            response = await self.agent.run(prompt)
            print(f"AI Response: {response.data[:500]}...")  # Print just first part for debugging

            result = self.parse_ai_response(response.data)

            if result:
                matches = result.get("field_matches", [])
                ocr_matches = result.get("ocr_matches", [])
                if matches or ocr_matches:
                    print(f"✅ Found {len(matches)} direct field matches and {len(ocr_matches)} OCR-based matches.")
                    break

            print(f"⚠️ Attempt {attempt + 1}/{max_retries} failed to get valid matches. Retrying...")

        if not matches and not ocr_matches:
            print("❌ No valid field matches were found after all attempts.")
            return False

        # Create temporary output file
        temp_output = f"{output_pdf}.temp"
        shutil.copy2(pdf_path, temp_output)

        try:
            print("🖋️ Filling form fields...")
            # Combine direct matches and OCR matches
            combined_matches = matches + [
                FieldMatch(
                    json_field=m.json_field,
                    pdf_field=m.pdf_field,
                    confidence=m.confidence,
                    suggested_value=m.suggested_value,
                    reasoning=m.reasoning
                ) for m in ocr_matches if m.pdf_field
            ]

            # Fill PDF fields
            success = self.fill_pdf_immediately(temp_output, combined_matches, pdf_fields)
            if not success:
                print("⚠️ Some fields may not have been filled correctly.")

        except Exception as e:
            print(f"❌ Error during filling: {e}")
            return False

        try:
            # Finalize PDF
            self.finalize_pdf(temp_output, output_pdf)
            print(f"✅ Finalized PDF saved to: {output_pdf}")
            return self.verify_pdf_filled(output_pdf)
        except Exception as e:
            print(f"❌ Error during finalization: {e}")
            print("Trying alternative finalization method...")

            try:
                shutil.copy2(temp_output, output_pdf)
                print(f"✅ Alternative save successful: {output_pdf}")
                return self.verify_pdf_filled(output_pdf)
            except Exception as e2:
                print(f"❌ Alternative save also failed: {e2}")
                return False

    def create_enhanced_matching_prompt(self, flat_json, pdf_fields, ocr_text_elements, field_context):
        """Create an enhanced prompt for the AI to match fields more accurately."""
        return f"""
        You are an expert at mapping JSON data to PDF form fields. Your task is to analyze the PDF fields,
        OCR text elements, and JSON data to create accurate mappings.

        # JSON Data (Flattened)
        ```json
        {json.dumps(flat_json, indent=2, cls=NumpyEncoder)}
        ```

        # PDF Form Fields
        ```json
        {json.dumps([{"uuid": k, "info": v} for k, v in pdf_fields.items()], indent=2, cls=NumpyEncoder)}
        ```

        # OCR Text Elements
        ```json
        {json.dumps(ocr_text_elements, indent=2, cls=NumpyEncoder)}
        ```

        # Field Context Analysis
        ```json
        {json.dumps(field_context, indent=2, cls=NumpyEncoder)}
        ```

        ## Instructions
        1. Match each field in the PDF form to the most appropriate JSON data field.
        2. For each match, provide:
           - The JSON field key
           - The PDF field ID
           - A confidence score (0.0-1.0)
           - The suggested value to insert
           - Reasoning for the match
        3. For OCR-detected text that should be matched:
           - Identify JSON fields that correspond to labels near form fields
           - Provide coordinates for potential text insertion

        ## Special Considerations
        - Format dates, addresses, and phone numbers appropriately
        - Be attentive to field types (text, checkbox, radio button)
        - For checkbox fields, determine if they should be checked based on JSON data
        - For multi-line fields, format the text appropriately

        Provide your response in the following JSON format:
        ```json
        {{
          "matches": [
            {{
              "json_field": "string",
              "pdf_field": "string",
              "confidence": 0.0-1.0,
              "suggested_value": "any",
              "reasoning": "string"
            }}
          ],
          "ocr_matches": [
            {{
              "json_field": "string",
              "ocr_text": "string",
              "page_num": 0,
              "x1": 0.0,
              "y1": 0.0,
              "x2": 0.0,
              "y2": 0.0,
              "confidence": 0.0-1.0,
              "pdf_field": "string",
              "suggested_value": "any",
              "reasoning": "string"
            }}
          ]
        }}
        ```

        Ensure your response contains ONLY valid JSON and no additional text.
        """

    async def analyze_field_context(self, pdf_fields: Dict[str, Dict[str, Any]],
                                    ocr_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Analyze context around form fields to improve understanding of field purpose."""
        print("🔍 Analyzing field context...")
        field_context = []

        # Enhanced context analysis
        for field_name, field_info in pdf_fields.items():
            page_num = field_info["page_num"]
            rect = field_info["rect"]
            nearby_text = []

            # Find nearby text elements
            for ocr_elem in ocr_elements:
                if ocr_elem["page_num"] != page_num:
                    continue

                ocr_pos = ocr_elem["position"]

                # Calculate distance from field
                center_x_field = (rect[0] + rect[2]) / 2
                center_y_field = (rect[1] + rect[3]) / 2
                center_x_ocr = (ocr_pos["x1"] + ocr_pos["x2"]) / 2
                center_y_ocr = (ocr_pos["y1"] + ocr_pos["y2"]) / 2

                distance = ((center_x_field - center_x_ocr) ** 2 +
                            (center_y_field - center_y_ocr) ** 2) ** 0.5

                # Determine relative position
                position = "unknown"
                if ocr_pos["x2"] < rect[0]:
                    position = "left"
                elif ocr_pos["x1"] > rect[2]:
                    position = "right"
                elif ocr_pos["y2"] < rect[1]:
                    position = "above"
                elif ocr_pos["y1"] > rect[3]:
                    position = "below"

                # Use a threshold to decide if text is nearby
                if distance < 200:  # Adjust threshold as needed
                    # Calculate relevance score based on distance and position
                    # Text above or to the left is often a label
                    position_factor = 1.0
                    if position in ["above", "left"]:
                        position_factor = 2.0  # Prioritize labels

                    relevance_score = (1.0 - min(distance, 200) / 200) * position_factor

                    nearby_text.append({
                        "text": ocr_elem["text"],
                        "position": position,
                        "distance": distance,
                        "relevance_score": round(relevance_score, 2)
                    })

            # Sort by relevance and keep top 5
            nearby_text.sort(key=lambda x: x["relevance_score"], reverse=True)
            top_nearby = nearby_text[:5]

            field_context.append({
                "field_name": field_name,
                "page": page_num + 1,
                "field_type": field_info["type"],
                "nearby_text": top_nearby
            })

        return field_context

    def parse_ai_response(self, response_text: str) -> Dict[str, List]:
        """Parse AI response with improved handling of malformed JSON."""
        # Try to extract JSON from various formats
        json_patterns = [
            r'```json\s*([\s\S]*?)\s*```',  # JSON in code block
            r'```\s*([\s\S]*?)\s*```',  # Generic code block
            r'(\{[\s\S]*\})'  # Raw JSON object
        ]

        for pattern in json_patterns:
            json_match = re.search(pattern, response_text)
            if json_match:
                response_text = json_match.group(1).strip()
                break

        # Handle common JSON syntax errors
        response_text = response_text.replace("'", '"')  # Replace single quotes with double quotes
        response_text = re.sub(r',\s*}', '}', response_text)  # Remove trailing commas in objects
        response_text = re.sub(r',\s*]', ']', response_text)  # Remove trailing commas in arrays

        try:
            # Fix for the specific error: Properly handle the original JSON structure
            # The error seems to be with the expected JSON key names
            data = json.loads(response_text)
            result = {
                "field_matches": [],
                "ocr_matches": []
            }

            # Process field matches - Fix: Check for both "matches" and "field_matches" keys
            match_list = data.get("matches", []) or data.get("field_matches", [])
            for match in match_list:
                # Set default values if missing
                match.setdefault("confidence", 0.8)
                match.setdefault("reasoning", "Matched by AI")

                # Validate match data
                try:
                    # Convert None to empty string for suggested_value if needed
                    if match.get("suggested_value") is None:
                        match["suggested_value"] = ""

                    validated_match = FieldMatch(**match)
                    result["field_matches"].append(validated_match)
                except Exception as e:
                    print(f"⚠️ Invalid field match: {e} - {match}")

            # Process OCR matches
            ocr_match_list = data.get("ocr_matches", [])
            for match in ocr_match_list:
                # Set default values if missing
                match.setdefault("confidence", 0.7)
                match.setdefault("reasoning", "Matched by OCR")
                match.setdefault("page_num", 0)
                match.setdefault("x1", 0)
                match.setdefault("y1", 0)
                match.setdefault("x2", 0)
                match.setdefault("y2", 0)

                # Validate match data
                try:
                    # Convert None to empty string for suggested_value if needed
                    if match.get("suggested_value") is None:
                        match["suggested_value"] = ""

                    validated_match = OCRFieldMatch(**match)
                    result["ocr_matches"].append(validated_match)
                except Exception as e:
                    print(f"⚠️ Invalid OCR match: {e} - {match}")

            return result
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse AI response as JSON: {e}")
            print(f"Response text: {response_text[:200]}...")

            # Additional fallback: Try to fix common JSON syntax issues
            try:
                # Remove any non-JSON text before the opening brace
                clean_text = re.sub(r'^[^{]*', '', response_text)
                # Remove any non-JSON text after the closing brace
                clean_text = re.sub(r'[^}]*$', '', clean_text)

                data = json.loads(clean_text)
                return self.parse_ai_response(json.dumps(data))
            except:
                pass

            return {}

    def fill_pdf_immediately(self, output_pdf: str, matches: List[FieldMatch],
                             pdf_fields: Dict[str, Dict[str, Any]]) -> bool:
        """Fill PDF form fields with improved error handling."""
        try:
            doc = fitz.open(output_pdf)
            filled_fields = []

            # Process all matches
            for match in matches:
                if not match.pdf_field or match.suggested_value is None:
                    continue

                field_info = pdf_fields.get(match.pdf_field)
                if not field_info:
                    print(f"⚠️ Field '{match.pdf_field}' not found in PDF")
                    continue

                if field_info["is_readonly"]:
                    print(f"⚠️ Skipping readonly field '{match.pdf_field}'")
                    continue

                page_num = field_info["page_num"]
                page = doc[page_num]

                # Find and fill the widget
                for widget in page.widgets():
                    if widget.field_name == match.pdf_field:
                        value = match.suggested_value
                        print(f"✍️ Filling: '{value}' → '{match.pdf_field}' (Page {page_num + 1})")

                        try:
                            # Convert value to appropriate type based on field type
                            field_type = field_info["type"]

                            # Handle checkbox fields
                            if field_type == 4:  # Checkbox
                                value = self.convert_to_boolean(value)

                            # Handle text fields
                            elif field_type == 3:  # Text
                                value = str(value)

                            # Set field value and update widget
                            widget.field_value = value
                            widget.update()
                            filled_fields.append(match.pdf_field)

                        except Exception as e:
                            print(f"⚠️ Error filling {match.pdf_field}: {e}")
                        break

            # Save PDF with filled fields
            doc.save(output_pdf, deflate=True, clean=True, garbage=4, pretty=False)
            print(f"✅ Successfully filled {len(filled_fields)} fields")
            doc.close()
            return len(filled_fields) > 0

        except Exception as e:
            print(f"❌ Error filling PDF: {e}")
            return False

    def convert_to_boolean(self, value):
        """Convert various value formats to boolean for checkboxes."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            value = value.lower()
            return value in ['true', 'yes', 'y', '1', 'checked', 'selected']
        if isinstance(value, (int, float)):
            return bool(value)
        return False

    def finalize_pdf(self, input_pdf: str, output_pdf: str) -> None:
        """Finalize the PDF to ensure all changes are saved correctly."""
        try:
            # Method 1: Use PyPDF
            reader = PdfReader(input_pdf)
            writer = PdfWriter()

            # Copy all pages
            for page in reader.pages:
                writer.add_page(page)

            # Copy form fields if any
            if reader.get_fields():
                writer.clone_reader_document_root(reader)

            # Ensure all necessary dictionaries are present
            if "/AcroForm" in reader.trailer["/Root"]:
                acro_form = reader.trailer["/Root"]["/AcroForm"].get_object()
                if acro_form:
                    writer.add_object(acro_form)

            # Write to output file
            with open(output_pdf, "wb") as f:
                writer.write(f)

            print("✅ PDF finalized using PyPDF")

        except Exception as e:
            print(f"⚠️ PyPDF finalization failed: {e}")

            try:
                # Method 2: Use PyMuPDF
                doc = fitz.open(input_pdf)
                doc.save(output_pdf, deflate=True, clean=True, garbage=4, pretty=False)
                doc.close()
                print("✅ PDF finalized using PyMuPDF")

            except Exception as e2:
                print(f"⚠️ PyMuPDF finalization failed: {e2}")

                # Method 3: Simple file copy
                shutil.copy2(input_pdf, output_pdf)
                print("✅ PDF finalized using direct copy")

    def verify_pdf_filled(self, pdf_path: str) -> bool:
        """Verify that the PDF has been filled correctly."""
        try:
            reader = PdfReader(pdf_path)
            fields = reader.get_fields()

            filled_fields = {}
            if fields:
                filled_fields = {k: v.get("/V") for k, v in fields.items() if v.get("/V") is not None}
                print(f"✅ Verified {len(filled_fields)} filled form fields")

                # Print a sample of filled fields
                if filled_fields:
                    sample = list(filled_fields.items())[:5]
                    print("Sample filled fields:")
                    for name, value in sample:
                        print(f"  - {name}: {value}")

            # Also check for annotations
            doc = fitz.open(pdf_path)
            annotation_count = 0
            for page in doc:
                annotations = list(page.annots())
                annotation_count += len(annotations)
            doc.close()

            return bool(filled_fields) or annotation_count > 0

        except Exception as e:
            print(f"❌ Error verifying PDF: {e}")
            return False

    def flatten_json(self, data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        """Flatten nested JSON objects for easier matching."""
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
                # Clean and normalize values
                if isinstance(value, str):
                    value = value.strip()
                items[new_key] = value

        return items


async def main():
    form_filler = EnhancedFormFiller()
    template_pdf = "D:\\demo\\Services\\WisconsinCorp.pdf"
    json_path = "D:\\demo\\Services\\form_data.json"
    output_pdf = "D:\\demo\\Services\\filled_form_output.pdf"

    # Load JSON data
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    # Process PDF with AI matching
    print(f"🚀 Processing PDF: {template_pdf}")
    print(f"📄 Using JSON data from: {json_path}")
    print(f"💾 Output will be saved to: {output_pdf}")

    success = await form_filler.match_and_fill_fields(template_pdf, json_data, output_pdf)

    if success:
        print(f"✅ PDF successfully processed and saved to: {output_pdf}")
    else:
        print(f"❌ PDF processing failed. Please check the logs for details.")


if __name__ == "__main__":
    asyncio.run(main())