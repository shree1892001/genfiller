import asyncio
import json
import os
import re
import shutil
import time
import logging
from typing import Dict, Any, List, Tuple, Optional

import fitz
import numpy as np
import cv2
from paddleocr import PaddleOCR
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, BooleanObject, ArrayObject
from difflib import SequenceMatcher

from pydantic_ai import Agent
from pydantic_ai.models.gemini import GeminiModel
import google.generativeai as genai
from pydantic import BaseModel, field_validator

from Common.constants import *

# Setup logger
logger = logging.getLogger(__name__)

API_KEYS = {
    "field_matcher": API_KEY_3,
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
    pdf_field: str  # or = None if you update the validator
    confidence: float
    suggested_value: Any
    reasoning: str
    is_checkbox: bool = False  # Added flag to identify checkboxes

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
    pdf_field: str  # or = None if you update the validator
    suggested_value: Any
    reasoning: str
    is_checkbox: bool = False  # Added flag to identify checkboxes

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

        self.checkbox_agent = Agent(
            model=GeminiModel("gemini-1.5-flash", api_key=API_KEYS["field_matcher"]),
            system_prompt="You are an expert at identifying checkbox fields in forms and determining if they should be checked based on user data."
        )

        self.ocr_reader = PaddleOCR(use_angle_cls=True, lang='en')
        self.matched_fields = {}
        self.model_name = "gemini-1.5-pro"  # Model for the extract_labels feature
        self.max_retries = 3  # Maximum number of retries for API calls

    def _get_page_image(self, page):
        """Convert a PDF page to an image for Gemini processing."""
        pix = page.get_pixmap(alpha=False)
        img_data = pix.tobytes("png")
        return img_data

    async def extract_pdf_fields(self, pdf_path: str) -> Dict[str, Dict[str, Any]]:
        """Extracts all fillable fields from a multi-page PDF with additional metadata and their labels."""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        logger.info(f"Extracting labels for existing fields from: {pdf_path}")
        print("🔍 Extracting all fillable fields and their labels...")

        try:
            doc = fitz.open(pdf_path)

            # First, extract basic fields using PyMuPDF
            pymupdf_fields = {}

            for page_num, page in enumerate(doc):
                try:
                    for widget in page.widgets():
                        if not widget.field_name:
                            continue

                        field_name = widget.field_name.strip()
                        field_type = widget.field_type
                        field_rect = widget.rect
                        field_flags = widget.field_flags

                        # Check if the field is a checkbox
                        is_checkbox = field_type == 4  # Checkbox type in PyMuPDF

                        pymupdf_fields[field_name] = {
                            "page_num": page_num,
                            "rect": [field_rect.x0, field_rect.y0, field_rect.x1, field_rect.y1],
                            "field_type": field_type,
                            "flags": field_flags,
                            "is_readonly": bool(field_flags & 1),
                            "current_value": widget.field_value,
                            "is_checkbox": is_checkbox
                        }
                except Exception as e:
                    logger.error(f"Error extracting basic fields from page {page_num}: {e}")
                    print(f"⚠️ Error extracting fields from page {page_num}: {e}")

            # Now use Gemini to identify labels for these fields
            field_labels = {}

            for page_num in range(len(doc)):
                page_fields = {k: v for k, v in pymupdf_fields.items() if v["page_num"] == page_num}

                if not page_fields:
                    continue

                # Get page image
                img = self._get_page_image(doc[page_num])

                # Initialize Gemini model
                model = genai.GenerativeModel(self.model_name)

                # Prepare data for the prompt
                fields_info = []
                for field_name, info in page_fields.items():
                    fields_info.append({
                        "name": field_name,
                        "rect": info["rect"],
                        "type": info["field_type"],
                        "is_checkbox": info["is_checkbox"]
                    })

                # Create prompt focusing on identifying labels
                prompt = f"""
                I have a PDF form with the following form fields on this page:
                {json.dumps(fields_info, indent=2)}

                For each form field listed above, identify the associated label or descriptive text near the field.
                Consider proximity, alignment, and visual relationships to determine which text is meant to label each field.

                For checkboxes (field type 4), pay special attention to the text that describes what checking the box means.

                Return a JSON object where:
                - Each key is the original field name
                - Each value is the text of the label associated with that field

                Example:
                {{
                  "firstName": "First Name:",
                  "lastName": "Last Name:",
                  "dob": "Date of Birth",
                  "checkField1": "I agree to the terms and conditions",
                  "checkbox2": "Include me in the mailing list"
                }}

                Return valid JSON only.
                """

                # Make request to Gemini
                for attempt in range(self.max_retries):
                    try:
                        response = model.generate_content([prompt, img])
                        response_text = response.text

                        # Try to extract JSON
                        try:
                            labels_data = json.loads(response_text)
                            # Update the field_labels dictionary
                            field_labels.update(labels_data)
                            break
                        except json.JSONDecodeError:
                            # Try to find JSON in the response
                            import re
                            json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
                            if json_match:
                                try:
                                    labels_data = json.loads(json_match.group(1))
                                    field_labels.update(labels_data)
                                    break
                                except json.JSONDecodeError:
                                    pass

                            # One more attempt with any JSON-like structure
                            json_match = re.search(r'(\{.*\})', response_text, re.DOTALL)
                            if json_match:
                                try:
                                    labels_data = json.loads(json_match.group(1))
                                    field_labels.update(labels_data)
                                    break
                                except json.JSONDecodeError:
                                    pass

                            logger.warning(f"Could not extract valid JSON for labels on attempt {attempt + 1}")

                    except Exception as e:
                        logger.warning(f"Gemini API error on labels attempt {attempt + 1}: {e}")

                    # Wait before retry
                    if attempt < self.max_retries - 1:
                        time.sleep(2 * (attempt + 1))

            # Update the pymupdf_fields with the labels
            for field_name, label in field_labels.items():
                if field_name in pymupdf_fields:
                    pymupdf_fields[field_name]["label"] = label
                    logger.info(f"Field: '{field_name}' - Label: '{label}'")
                    print(f" - Field: '{field_name}' - Label: '{label}'")

            # Print summary
            print(f"✅ Extracted {len(pymupdf_fields)} fields across {len(doc)} pages.")
            for field_name, info in pymupdf_fields.items():
               # Check if the field is a checkbox - improve detection
               field_type = info.get("field_type")
               is_checkbox = field_type == 4  # Standard checkbox type

            # Additional detection based on field name
               if not is_checkbox and "check" in field_name.lower():
                print(f"✓ Detected checkbox by name: {field_name}")
                is_checkbox = True

            pymupdf_fields[field_name]["is_checkbox"] = is_checkbox
            doc.close()
            return pymupdf_fields

        except Exception as e:
            logger.error(f"Failed to extract labels for existing fields: {e}")
            print(f"❌ Error extracting fields: {e}")
            raise

    async def extract_ocr_text(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Extract text from PDF using OCR with position information."""
        print("🔍 Extracting text using OCR...")
        doc = fitz.open(pdf_path)
        ocr_results = []

        for page_num in range(len(doc)):
            print(f"Processing OCR for page {page_num + 1}/{len(doc)}...")
            pix = doc[page_num].get_pixmap(alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)

            if img.shape[2] == 4:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)

            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

            binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                           cv2.THRESH_BINARY_INV, 11, 2)

            results = self.ocr_reader.ocr(binary, cls=True)

            if not results[0]:
                _, threshold = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
                additional_results = self.ocr_reader.ocr(threshold, cls=True)

                if additional_results[0]:
                    results = additional_results

            if results[0]:
                unique_results = []
                seen_texts = set()

                for line in results[0]:
                    bbox, (text, prob) = line

                    text = text.strip().lower()
                    if text and text not in seen_texts and prob >= 0.4:
                        seen_texts.add(text)
                        unique_results.append((bbox, text, prob))

                for (bbox, text, prob) in unique_results:
                    if prob < 0.4 or not text.strip():
                        continue

                    # PaddleOCR format: [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                    x1, y1 = bbox[0]
                    x2, y2 = bbox[2]

                    cleaned_text = text.strip()
                    cleaned_text = ''.join(c for c in cleaned_text if c.isprintable())

                    ocr_results.append({
                        "page_num": page_num,
                        "text": cleaned_text,
                        "raw_text": text,
                        "confidence": float(prob),
                        "position": {
                            "x1": float(x1),
                            "y1": float(y1),
                            "x2": float(x2),
                            "y2": float(y2)
                        }
                    })

        doc.close()
        print(f"✅ Extracted {len(ocr_results)} text elements using OCR.")
        return ocr_results

    async def detect_checkboxes(self, pdf_path: str, json_data: Dict[str, Any],
                                pdf_fields: Dict[str, Dict[str, Any]]) -> List[FieldMatch]:
        """Detect checkboxes and determine if they should be checked based on JSON data."""
        print("🔍 Analyzing checkboxes in the form...")

        # Filter for checkbox fields with improved detection
        checkbox_fields = {k: v for k, v in pdf_fields.items() if
                           v.get("is_checkbox", False) or
                           "check" in k.lower() or
                           "box" in k.lower() or
                           (v.get("field_type") == 4)}

        print(f"Found {len(checkbox_fields)} checkbox fields:")
        for field_name, info in checkbox_fields.items():
            label = info.get("label", "Unknown")
            print(f" - Found checkbox: {field_name} (Label: {label})")

        if not checkbox_fields:
            print("No checkbox fields found in the PDF.")
            return []

        # Flatten the JSON data for easier reference
        flat_json = self.flatten_json(json_data)

        # Prepare data for the AI prompt
        checkbox_info = []
        for field_name, info in checkbox_fields.items():
            checkbox_info.append({
                "field_name": field_name,
                "label": info.get("label", "Unknown"),
                "page_num": info["page_num"] + 1,
                "rect": info["rect"]
            })

        # Create a more specific prompt focused on member/manager and registered agent checkboxes
        prompt = f"""
        I need to determine which checkboxes in a PDF form should be checked based on specific conditions:

        1. If the JSON data indicates a "member" or "manager" is present, check the corresponding checkbox
        2. If the JSON data shows a "registered agent" or "commercial registered agent" is specified, check the corresponding checkbox

        Here are the checkboxes in the form:
        {json.dumps(checkbox_info, indent=2)}

        Here is the user data:
        {json.dumps(flat_json, indent=2, cls=NumpyEncoder)}

        Focus specifically on:
        - Any checkbox with labels containing "member", "manager", "managing member", or similar terms
        - Any checkbox with labels containing "registered agent", "commercial registered agent", or similar terms

        For each checkbox, check if it should be marked based on these rules:
        - If the JSON has keys like "member", "manager", "managingMember", or contains these words in any field, mark the corresponding checkbox
        - If the JSON has keys like "registeredAgent", "commercialRegisteredAgent", or contains these terms in any field, mark the corresponding checkbox
        - Check for both the presence of these fields and their values (e.g., if "isManager" is true, mark the manager checkbox)

        Return a JSON object with the following structure:
        {{
            "checkbox_matches": [
                {{
                    "json_field": "[relevant JSON field that determined this choice]",
                    "pdf_field": "[checkbox field name in PDF]",
                    "confidence": 0.95,
                    "suggested_value": true,
                    "reasoning": "User data indicates this checkbox should be checked because...",
                    "is_checkbox": true
                }},
                ...
            ]
        }}

        Only include checkboxes that should be checked based on the data. If there's no clear match in the data, don't include that checkbox.
        Return valid JSON only.
        """

        # Send to AI and process response
        response = await self.checkbox_agent.run(prompt)
        result = self.parse_checkbox_response(response.data)

        if not result:
            print("⚠️ No checkbox matches were found.")
            return []

        checkbox_matches = []
        for match in result.get("checkbox_matches", []):
            try:
                validated_match = FieldMatch(
                    json_field=match.get("json_field", ""),
                    pdf_field=match.get("pdf_field", ""),
                    confidence=match.get("confidence", 1.0),
                    suggested_value=match.get("suggested_value", True),
                    reasoning=match.get("reasoning", ""),
                    is_checkbox=True
                )
                checkbox_matches.append(validated_match)
                print(f"✅ Found checkbox match: {match.get('pdf_field')} → {match.get('suggested_value')}")

                # Immediately check the checkbox after detection (NEW)
                success = self.check_checkbox_immediately(pdf_path, match.get('pdf_field'), pdf_fields)
                if not success:
                    print(f"⚠️ Failed to immediately check checkbox: {match.get('pdf_field')}")

            except Exception as e:
                print(f"⚠️ Error processing checkbox match: {e}")

        return checkbox_matches

    def check_checkbox_immediately(self, pdf_path: str, field_name: str, pdf_fields: Dict[str, Dict[str, Any]]) -> bool:
        """Immediately checks a checkbox in the PDF once detected."""
        try:
            if not field_name or field_name not in pdf_fields:
                print(f"⚠️ Checkbox field '{field_name}' not found in PDF")
                return False

            field_info = pdf_fields.get(field_name)
            if not field_info:
                print(f"⚠️ Field info for '{field_name}' not found")
                return False

            # Better checkbox detection
            is_checkbox = (field_info.get("is_checkbox", False) or
                           field_info.get("field_type") == 4 or
                           "check" in field_name.lower())

            if not is_checkbox:
                print(f"⚠️ Field '{field_name}' is not a checkbox")
                return False

            page_num = field_info["page_num"]

            doc = fitz.open(pdf_path)
            page = doc[page_num]

            checkbox_checked = False
            for widget in page.widgets():
                if widget.field_name == field_name:
                    print(f"🔳 Immediately checking checkbox: '{field_name}' on page {page_num + 1}")

                    # Try different checkbox value options for better compatibility
                    try:
                        # First try with choice values if available
                        if hasattr(widget, 'choice_values') and widget.choice_values:
                            widget.field_value = widget.choice_values[0]
                        else:
                            # Try standard values for checkboxes
                            widget.field_value = "Yes"

                        widget.update()
                        checkbox_checked = True
                    except Exception as e1:
                        print(f"⚠️ First attempt failed: {e1}")
                        try:
                            # Alternative checkbox values
                            alternative_values = ["On", "Checked", "True", "X", "1"]
                            for val in alternative_values:
                                try:
                                    widget.field_value = val
                                    widget.update()
                                    checkbox_checked = True
                                    print(f"✅ Checkbox checked with value: {val}")
                                    break
                                except:
                                    continue
                        except Exception as e2:
                            print(f"⚠️ Alternative values failed: {e2}")

                    break

            if checkbox_checked:
                # Save with clean=True to avoid PDF corruption
                doc.save(pdf_path, deflate=True, clean=True)
                print(f"✅ Checkbox '{field_name}' successfully checked")
                doc.close()
                return True
            else:
                print(f"⚠️ Checkbox widget for '{field_name}' not found on page {page_num}")
                doc.close()
                return False

        except Exception as e:
            print(f"❌ Error checking checkbox immediately: {e}")
            return False


    def parse_checkbox_response(self, response_text: str) -> Dict[str, List]:
        """Parse the AI response specific to checkbox detection."""
        json_patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
            r'(\{[\s\S]*\})'
        ]

        for pattern in json_patterns:
            json_match = re.search(pattern, response_text)
            if json_match:
                response_text = json_match.group(1)
                break

        response_text = response_text.strip()

        try:
            data = json.loads(response_text)
            return data
        except json.JSONDecodeError as e:
            print(f"❌ AI returned invalid JSON for checkboxes: {e}")
            print(f"Failed text: {response_text[:100]}...")
            return {}

    async def match_and_fill_fields(self, pdf_path: str, json_data: Dict[str, Any], output_pdf: str,
                                    max_retries: int = 3):
        """Matches fields using AI and fills them immediately across multiple pages, ensuring OCR text is mapped to UUIDs properly."""

        backup_pdf = f"{pdf_path}.backup"
        shutil.copy2(pdf_path, backup_pdf)
        print(f"Created backup of original PDF: {backup_pdf}")

        pdf_fields = await self.extract_pdf_fields(pdf_path)
        ocr_text_elements = await self.extract_ocr_text(pdf_path)
        flat_json = self.flatten_json(json_data)
        field_context = self.analyze_field_context(pdf_fields, ocr_text_elements)

        # Print available JSON fields for debugging
        print("Available JSON fields:")
        for key in flat_json.keys():

            print(f" - {key}: {flat_json[key]}")

        prompt = FIELD_MATCHING_PROMPT_UPDATED1.format(
            json_data=json.dumps(flat_json, indent=2, cls=NumpyEncoder),
            pdf_fields=json.dumps([{"uuid": k, "info": v} for k, v in pdf_fields.items()], indent=2, cls=NumpyEncoder),
            ocr_elements=json.dumps(ocr_text_elements, indent=2, cls=NumpyEncoder),
            field_context=json.dumps(field_context, indent=2, cls=NumpyEncoder)
        )

        matches, ocr_matches = [], []
        for attempt in range(max_retries):
            response = await self.agent.run(prompt)
            result = self.parse_ai_response(response.data)

            if result:
                matches = result.get("field_matches", [])
                ocr_matches = result.get("ocr_matches", [])
                if matches or ocr_matches:
                    break

            print(f"Attempt {attempt + 1}/{max_retries} failed to get valid matches. Retrying...")

        if not matches and not ocr_matches:
            print("⚠️ No valid field matches were found after all attempts.")
            return False

        # Detect and add checkboxes that should be checked
        checkbox_matches = await self.detect_checkboxes(pdf_path, json_data, pdf_fields)

        temp_output = f"{output_pdf}.temp"
        shutil.copy2(pdf_path, temp_output)

        try:
            print("Filling form fields, checkboxes, and OCR-detected fields together with UUID-based matching...")
            combined_matches = matches + checkbox_matches + [
                FieldMatch(
                    json_field=m.json_field,
                    pdf_field=m.pdf_field,  # Ensuring OCR text maps correctly to UUID
                    confidence=m.confidence,
                    suggested_value=m.suggested_value,
                    reasoning=m.reasoning
                ) for m in ocr_matches
            ]

            success = self.fill_pdf_immediately(temp_output, combined_matches, pdf_fields)

            if not success:
                print("⚠️ Some fields may not have been filled correctly.")
        except Exception as e:
            print(f"❌ Error during filling: {e}")
            return False

        try:
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

    def analyze_field_context(self, pdf_fields: Dict[str, Dict[str, Any]],
                              ocr_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Analyze context around form fields to improve field understanding."""
        field_context = []

        for field_name, field_info in pdf_fields.items():
            page_num = field_info["page_num"]
            rect = field_info["rect"]

            nearby_text = []
            for ocr_elem in ocr_elements:
                if ocr_elem["page_num"] != page_num:
                    continue

                ocr_pos = ocr_elem["position"]

                distance_x = abs(rect[0] - ocr_pos["x2"])
                distance_y = abs(rect[1] - ocr_pos["y2"])

                if (ocr_pos["x2"] < rect[0] and distance_x < 200 and abs(rect[1] - ocr_pos["y1"]) < 30) or \
                        (ocr_pos["y2"] < rect[1] and distance_y < 50 and abs(rect[0] - ocr_pos["x1"]) < 200):
                    nearby_text.append({
                        "text": ocr_elem["text"],
                        "distance_x": distance_x,
                        "distance_y": distance_y,
                        "position": "left" if ocr_pos["x2"] < rect[0] else "above"
                    })

            nearby_text.sort(key=lambda x: x["distance_x"] + x["distance_y"])

            field_context.append({
                "field_name": field_name,
                "page": page_num + 1,
                "nearby_text": nearby_text[:3]
            })

        return field_context

    def create_label_field_map(self, ocr_elements: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Create a map of potential form labels to nearby fields."""
        label_map = {}

        by_page = {}
        for elem in ocr_elements:
            page = elem["page_num"]
            if page not in by_page:
                by_page[page] = []
            by_page[page].append(elem)

        for page, elements in by_page.items():

            elements.sort(key=lambda x: x["position"]["y1"])

            for i, elem in enumerate(elements):
                if len(elem["text"]) > 30:
                    continue

                potential_fields = []
                for j, other in enumerate(elements):
                    if i == j:
                        continue

                    if (other["position"]["x1"] > elem["position"]["x2"] and
                            abs(other["position"]["y1"] - elem["position"]["y1"]) < 20):
                        potential_fields.append({
                            "text": other["text"],
                            "position": other["position"],
                            "relation": "right",
                            "distance": other["position"]["x1"] - elem["position"]["x2"]
                        })

                    elif (other["position"]["y1"] > elem["position"]["y2"] and
                          abs(other["position"]["x1"] - elem["position"]["x1"]) < 40 and
                          other["position"]["y1"] - elem["position"]["y2"] < 40):
                        potential_fields.append({
                            "text": other["text"],
                            "position": other["position"],
                            "relation": "below",
                            "distance": other["position"]["y1"] - elem["position"]["y2"]
                        })

                if potential_fields:
                    potential_fields.sort(key=lambda x: x["distance"])
                    label_map[elem["text"]] = potential_fields[:2]

        return label_map

    def parse_ai_response(self, response_text: str) -> Dict[str, List]:
        """Parses AI response and extracts valid JSON matches for both form fields and OCR text."""
        json_patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
            r'(\{[\s\S]*\})'
        ]

        for pattern in json_patterns:
            json_match = re.search(pattern, response_text)
            if json_match:
                response_text = json_match.group(1)
                break

        response_text = response_text.strip()

        try:
            data = json.loads(response_text)
            result = {
                "field_matches": [],
                "ocr_matches": []
            }

            for match in data.get("matches", []):
                match.setdefault("confidence", 1.0)
                match.setdefault("reasoning", "No reasoning provided.")
                match.setdefault("is_checkbox", False)

                try:
                    validated_match = FieldMatch(**match)
                    result["field_matches"].append(validated_match)
                except Exception as e:
                    print(f"⚠️ Skipping malformed field match: {match} | Error: {e}")

            for match in data.get("ocr_matches", []):
                match.setdefault("confidence", 1.0)
                match.setdefault("reasoning", "No reasoning provided.")
                match.setdefault("page_num", 0)
                match.setdefault("x1", 100)
                match.setdefault("y1", 100)
                match.setdefault("x2", 300)
                match.setdefault("y2", 120)
                match.setdefault("is_checkbox", False)

                try:
                    validated_match = OCRFieldMatch(**match)
                    result["ocr_matches"].append(validated_match)
                except Exception as e:
                    print(f"⚠️ Skipping malformed OCR match: {match} | Error: {e}")

            return result
        except json.JSONDecodeError as e:
            print(f"❌ AI returned invalid JSON: {e}")
            print(f"Failed text: {response_text[:100]}...")
            return {}

    def adjust_text_field(self, widget, value: str, field_info: Dict[str, Any]) -> str:
        """
        Adjusts text to properly fit within PDF form fields based on field size and content length.

        Args:
            widget: The PDF form widget
            value: The text value to be inserted
            field_info: Dictionary containing field information including dimensions

        Returns:
            Adjusted text value that will fit appropriately in the field
        """
        if not value or not isinstance(value, str):
            return str(value) if value is not None else ""

        # Get field dimensions
        rect = field_info.get("rect", [0, 0, 0, 0])
        field_width = rect[2] - rect[0]  # x2 - x0
        field_height = rect[3] - rect[1]  # y2 - y0

        # If field is too narrow, we need to be more aggressive with formatting
        is_narrow_field = field_width < 100

        # Calculate approximate characters per line based on field width
        # Average character width in points (assuming 10pt font)
        avg_char_width = 6
        chars_per_line = max(int(field_width / avg_char_width), 1)

        # Split text into words
        words = value.strip().split()

        # For very small fields, return abbreviated version
        if chars_per_line < 5 and len(value) > chars_per_line:
            abbreviated = value[:chars_per_line - 1] + "…"
            return abbreviated

        # Simple approach: if text is short enough, return as is
        if len(value) <= chars_per_line:
            return value

        # For longer content, format with line breaks
        formatted_text = ""
        current_line = ""

        for word in words:
            # Test if adding this word exceeds the line width
            test_line = current_line + " " + word if current_line else word

            if len(test_line) <= chars_per_line:
                current_line = test_line
            else:
                # Add current line to formatted text with line break
                formatted_text += current_line + "\n"
                current_line = word

        # Add the last line
        if current_line:
            formatted_text += current_line

        # Check if resulting text height fits in field
        # Approximate line height in points (assuming 10pt font with 1.2 line spacing)
        line_height = 12
        num_lines = formatted_text.count('\n') + 1
        text_height = num_lines * line_height

        # If text is too tall for field, truncate lines
        if text_height > field_height:
            max_lines = max(int(field_height / line_height), 1)
            lines = formatted_text.split('\n')

            if len(lines) > max_lines:
                # Keep only as many lines as will fit
                truncated_lines = lines[:max_lines - 1]
                # Add ellipsis to last line to indicate truncation
                truncated_lines.append(lines[max_lines - 1] + "…")
                formatted_text = '\n'.join(truncated_lines)

        # Log adjustment for debugging
        print(
            f"Adjusted text field: {len(value)} chars → {len(formatted_text)} chars, {formatted_text.count(chr(10)) + 1} lines")

        return formatted_text

    def fill_pdf_immediately(self, output_pdf: str, matches: List[FieldMatch],
                             pdf_fields: Dict[str, Dict[str, Any]]) -> bool:
        """Fills PDF form fields using PyMuPDF (fitz) with improved handling of readonly fields, checkboxes, and text field sizing."""
        doc = fitz.open(output_pdf)
        filled_fields = []

        updates = []
        for match in matches:
            if match.pdf_field and match.suggested_value is not None:
                field_info = pdf_fields.get(match.pdf_field)

                if not field_info:
                    print(f"⚠️ Field '{match.pdf_field}' not found in PDF")
                    continue

                if field_info["is_readonly"]:
                    print(f"⚠️ Skipping readonly field '{match.pdf_field}' - will handle via OCR")
                    continue

                page_num = field_info["page_num"]

                # Special handling for checkbox values
                if field_info.get("is_checkbox", False) or match.is_checkbox:
                    # Convert various true/false values to appropriate checkbox value
                    value = match.suggested_value
                    if isinstance(value, bool):
                        checkbox_value = "Yes" if value else "No"
                    elif isinstance(value, str):
                        value_lower = value.lower()
                        checkbox_value = "Yes" if value_lower in ["yes", "true", "1", "checked", "selected"] else "No"
                    elif isinstance(value, (int, float)):
                        checkbox_value = "Yes" if value in [1, 1.0] else "No"
                    else:
                        checkbox_value = "No"

                    updates.append((page_num, match.pdf_field, checkbox_value))
                    print(f"🔳 Will check checkbox: '{match.pdf_field}' → {checkbox_value}")
                else:
                    updates.append((page_num, match.pdf_field, match.suggested_value))

        for page_num, field_name, value in updates:
            page = doc[page_num]
            for widget in page.widgets():
                if widget.field_name == field_name:
                    # Handle different field types correctly
                    field_type = widget.field_type
                    field_info = pdf_fields.get(field_name, {})
                    is_checkbox = field_info.get("is_checkbox", False) or field_type == 4

                    if is_checkbox:
                        # Handle checkbox specifically
                        checkbox_val = str(value).lower()
                        if checkbox_val in ["yes", "true", "1", "checked", "selected"]:
                            print(f"✅ Checking checkbox: '{field_name}' (Page {page_num + 1})")
                            widget.field_value = widget.choice_values[0] if hasattr(widget,
                                                                                    'choice_values') and widget.choice_values else "Yes"
                        else:
                            print(f"❌ Leaving checkbox unchecked: '{field_name}' (Page {page_num + 1})")
                            widget.field_value = "Off"  # Standard value for unchecked boxes
                    else:
                        # Handle regular text fields with proper adjustment
                        adjusted_value = self.adjust_text_field(widget, str(value), field_info)
                        print(f"✍️ Filling: '{adjusted_value}' → '{field_name}' (Page {page_num + 1})")
                        widget.field_value = adjusted_value

                    widget.update()
                    filled_fields.append(field_name)
                    break

        try:
            # Remove garbage and incremental parameters to fix the error
            doc.save(output_pdf, deflate=True, clean=True)
            print(f"✅ Saved PDF with {len(filled_fields)} filled fields")
            doc.close()
            return len(filled_fields) > 0
        except Exception as e:
            print(f"❌ Error saving PDF: {e}")

            try:
                temp_path = f"{output_pdf}.tmp"
                doc.save(temp_path, deflate=True, clean=True)
                doc.close()
                shutil.move(temp_path, output_pdf)
                print(f"✅ Saved PDF using alternative method")
                return len(filled_fields) > 0
            except Exception as e2:
                print(f"❌ Alternative save also failed: {e2}")
                doc.close()
                return False

    def fill_ocr_fields(self, pdf_path: str, ocr_matches: List[OCRFieldMatch],
                        ocr_elements: List[Dict[str, Any]]) -> bool:
        """Fills OCR-detected areas with text for readonly fields with improved text fitting."""
        doc = fitz.open(pdf_path)
        annotations_added = 0

        for match in ocr_matches:
            if match.suggested_value is not None:
                try:
                    page = doc[match.page_num]

                    position = None
                    if match.ocr_text:
                        position = self.find_text_position(match.ocr_text, ocr_elements, match.page_num)

                    if position:
                        x1, y1, x2, y2 = position["x1"], position["y1"], position["x2"], position["y2"]

                        x1 = x2 + 10
                        x2 = x1 + 150

                        y2 = y1 + (y2 - y1)
                    else:
                        x1, y1, x2, y2 = match.x1, match.y1, match.x2, match.y2

                    rect = fitz.Rect(x1, y1, x2, y2)

                    # Use adjusted text based on field dimensions
                    field_info = {
                        "rect": [x1, y1, x2, y2]
                    }
                    adjusted_value = self.adjust_text_field(None, str(match.suggested_value), field_info)

                    print(
                        f"✍️ Filling OCR field: '{adjusted_value}' → near '{match.ocr_text}' (Page {match.page_num + 1})")

                    annotation_added = False

                    try:
                        annot = page.add_freetext_annot(
                            rect=rect,
                            text=adjusted_value,
                            fontsize=10,
                            fill_color=(0.95, 0.95, 0.95),
                            text_color=(0, 0, 0)
                        )
                        annotations_added += 1
                        annotation_added = True
                    except Exception as e1:
                        print(f"⚠️ Free text annotation failed: {e1}")

                    if not annotation_added:
                        try:
                            page.draw_rect(rect, color=(0.95, 0.95, 0.95), fill=(0.95, 0.95, 0.95))

                            # Split adjusted text into lines and insert each line separately
                            lines = adjusted_value.split('\n')
                            line_height = 12  # approximate line height in points

                            for i, line in enumerate(lines):
                                page.insert_text(
                                    point=(x1 + 2, y1 + 10 + (i * line_height)),
                                    text=line,
                                    fontsize=10
                                )

                            annotations_added += 1
                            annotation_added = True
                        except Exception as e2:
                            print(f"⚠️ Text insertion failed: {e2}")

                    if not annotation_added:
                        try:
                            annot = page.add_text_annot(
                                point=(x1, y1),
                                text=adjusted_value
                            )
                            annotations_added += 1
                        except Exception as e3:
                            print(f"⚠️ All text methods failed: {e3}")
                except Exception as e:
                    print(f"⚠️ Error processing OCR match: {e}")

        if annotations_added > 0:
            try:
                # Remove incremental parameter to fix the error
                doc.save(pdf_path, deflate=True, clean=True)
                print(f"✅ Added {annotations_added} OCR text fields")
                doc.close()
                return True
            except Exception as e:
                print(f"❌ Error saving PDF with OCR annotations: {e}")
                try:
                    temp_path = f"{pdf_path}.temp"
                    doc.save(temp_path)
                    doc.close()
                    shutil.move(temp_path, pdf_path)
                    print(f"✅ Saved OCR annotations using alternative method")
                    return True
                except Exception as e2:
                    print(f"❌ Alternative save method also failed: {e2}")
                    doc.close()
                    return False
        else:
            doc.close()
            return False

    def check_checkbox_immediately(self, pdf_path: str, field_name: str, pdf_fields: Dict[str, Dict[str, Any]]) -> bool:
        """Immediately checks a checkbox in the PDF once detected."""
        try:
            if not field_name or field_name not in pdf_fields:
                print(f"⚠️ Checkbox field '{field_name}' not found in PDF")
                return False

            field_info = pdf_fields.get(field_name)
            if not field_info or not field_info.get("is_checkbox", False):
                print(f"⚠️ Field '{field_name}' is not a checkbox")
                return False

            page_num = field_info["page_num"]

            doc = fitz.open(pdf_path)
            page = doc[page_num]

            checkbox_checked = False
            for widget in page.widgets():
                if widget.field_name == field_name:
                    print(f"🔳 Immediately checking checkbox: '{field_name}' on page {page_num + 1}")
                    widget.field_value = "Yes"  # Standard value for checked boxes
                    widget.update()
                    checkbox_checked = True
                    break

            if checkbox_checked:
                # Save with clean=True to avoid PDF corruption
                doc.save(pdf_path, deflate=True, clean=True)
                print(f"✅ Checkbox '{field_name}' successfully checked")
                doc.close()
                return True
            else:
                print(f"⚠️ Checkbox widget for '{field_name}' not found on page {page_num}")
                doc.close()
                return False

        except Exception as e:
            print(f"❌ Error checking checkbox immediately: {e}")
            return False

    def find_text_position(self, text: str, ocr_elements: List[Dict[str, Any]], page_num: int) -> Dict[str, float]:
        """Find the position of a text element in the OCR results with improved fuzzy matching."""
        if not text or not ocr_elements:
            return None

        search_text = text.strip().lower()

        for element in ocr_elements:
            if element["page_num"] == page_num and element["text"].strip().lower() == search_text:
                return element["position"]

        for element in ocr_elements:
            if element["page_num"] == page_num and search_text in element["text"].strip().lower():
                return element["position"]

        best_match = None
        best_ratio = 0.7

        for element in ocr_elements:
            if element["page_num"] == page_num:
                element_text = element["text"].strip().lower()

                ratio = SequenceMatcher(None, search_text, element_text).ratio()

                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = element["position"]

                words_in_search = set(search_text.split())
                words_in_element = set(element_text.split())
                common_words = words_in_search.intersection(words_in_element)
                if common_words:
                    word_ratio = len(common_words) / max(len(words_in_search), 1)
                    if word_ratio > 0.5 and word_ratio > best_ratio:
                        best_ratio = word_ratio
                        best_match = element["position"]

        return best_match

    def finalize_pdf(self, input_pdf: str, output_pdf: str) -> None:
        """Finalizes the PDF using PyPDF to avoid incremental save issues."""
        try:
            reader = PdfReader(input_pdf)
            writer = PdfWriter()

            for page in reader.pages:
                writer.add_page(page)

            if reader.get_fields():
                writer.clone_reader_document_root(reader)

            with open(output_pdf, "wb") as f:
                writer.write(f)
        except Exception as e:
            print(f"❌ Error in finalize_pdf: {e}")
            # Simply copy the file as a fallback
            shutil.copy2(input_pdf, output_pdf)
            print(f"✅ Used direct file copy as fallback for finalization")

    def verify_pdf_filled(self, pdf_path: str) -> bool:
        """Verifies that the PDF has been filled correctly or has annotations."""
        try:
            reader = PdfReader(pdf_path)
            fields = reader.get_fields()

            filled_fields = {}
            if fields:
                filled_fields = {k: v.get("/V") for k, v in fields.items() if v.get("/V")}
                print(f"✅ Found {len(filled_fields)} filled form fields")

            doc = fitz.open(pdf_path)
            annotation_count = 0

            for page in doc:
                annotations = list(page.annots())
                annotation_count += len(annotations)

            doc.close()
            print(f"✅ Found {annotation_count} annotations in the PDF")

            return bool(filled_fields) or annotation_count > 0

        except Exception as e:
            print(f"❌ Error verifying PDF: {e}")
            return False

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
    template_pdf = "D:\\demo\\Services\\Maine.pdf"
    json_path = "D:\\demo\\Services\\form_data.json"
    output_pdf = "D:\\demo\\Services\\fill_smart8.pdf"

    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    success = await form_filler.match_and_fill_fields(template_pdf, json_data, output_pdf)

    if success:
        print(f"✅ PDF successfully processed: {output_pdf}")
    else:
        print(f"❌ PDF processing failed. Please check the output file and logs.")


if __name__ == "__main__":
    asyncio.run(main())