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
        """Detect checkboxes specifically for registered agent and member/manager options using AI analysis."""
        print("🔍 Analyzing checkboxes using AI agent...")

        # Extract all form fields without filtering
        all_fields = {}
        for k, v in pdf_fields.items():
            field_info = {
                "field_name": k,
                "field_type": v.get("field_type", "Unknown"),
                "label": v.get("label", "Unknown"),
                "page_num": v["page_num"] + 1,
                "rect": v["rect"]
            }
            all_fields[k] = field_info

        # Get PDF metadata

        # Flatten the JSON data
        flat_json = self.flatten_json(json_data)

        # Create a comprehensive prompt for the AI agent
        prompt = f"""
        You are an expert AI agent specializing in legal form analysis. Your task is to determine which checkboxes need to be checked on an LLC formation document.

        I need you to find and mark checkboxes for TWO specific decisions:

        1. REGISTERED AGENT TYPE:
           - Common options: "commercial registered agent" vs "non-commercial registered agent"

        2. LLC MANAGEMENT STRUCTURE:
           - Common options: "member-managed LLC" vs "manager-managed LLC"

        Here is the form data from the user:
        {json.dumps(flat_json, indent=2, cls=NumpyEncoder)}

        Here are ALL form fields in the PDF (some may be checkboxes):
        {json.dumps(all_fields, indent=2)}

        

        INSTRUCTIONS:

        1. Analyze ALL form fields to identify potential checkboxes, even if they're not explicitly labeled as checkboxes.
        2. Look for fields that appear to be related to registered agent selection or LLC management structure.
        3. Use creative problem-solving to identify checkboxes - they might be buttons, radio buttons, or other field types.
        4. For fields with limited or missing labels, infer their purpose from their location, nearby fields, or form context.
        5. Determine which checkboxes should be checked based on the user's data.

        APPROACH THIS TASK COMPREHENSIVELY:
        - Don't limit yourself to obvious checkbox fields
        - Consider field names, labels, locations, and types
        - Think about what would make logical sense based on the form structure
        - Be thorough in your examination of all potential checkbox candidates

        Return a JSON object with the following structure:
        {{
        "checkbox_matches": [
                {{
                    "json_field": "[relevant JSON field that determined this choice]",
                    "pdf_field": "[field name in PDF that should be checked]",
                    "confidence": 0.0-1.0,
                    "suggested_value": true,
                    "reasoning": "Detailed explanation of why this checkbox should be checked...",
                    "category": "[REGISTERED_AGENT or MEMBER_MANAGER]",
                    "is_checkbox": true
                }},
                ...
            ]
        }}

        IMPORTANT: 
        - Be thorough and creative in identifying checkboxes
        - Provide detailed reasoning for each match
        - Return valid JSON only
        """

        # Send to AI and process response
        try:
            response = await self.checkbox_agent.run(prompt)
            result = self.parse_checkbox_response(response.data)

            if not result or not result.get("checkbox_matches"):
                print("⚠️ No checkbox matches were found by the AI.")
                print("Attempting secondary analysis with OCR data...")
                return await self.detect_checkboxes_with_ocr(pdf_path, json_data, pdf_fields)

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
                    print(
                        f"✅ AI identified {match.get('category', 'Unknown')} checkbox match: {match.get('pdf_field')} → {match.get('suggested_value')}")
                    print(f"   Reason: {match.get('reasoning', 'No reasoning provided')}")

                    # Check the checkbox
                    self.check_checkbox_immediately(pdf_path, match.get('pdf_field'), pdf_fields)
                except Exception as e:
                    print(f"⚠️ Error processing checkbox match: {str(e)}")

            return checkbox_matches

        except Exception as e:
            print(f"❌ Error in AI checkbox detection: {str(e)}")
            return []

    async def detect_checkboxes_with_ocr(self, pdf_path: str, json_data: Dict[str, Any],
                                         pdf_fields: Dict[str, Dict[str, Any]]) -> List[FieldMatch]:
        """Use OCR data to help the AI agent identify checkboxes when standard detection fails."""
        print("🔍 Using OCR data to help identify checkboxes...")

        try:
            # Extract OCR text from the PDF
            ocr_data = await self.extract_ocr_text(pdf_path)

            # Flatten the JSON data
            flat_json = self.flatten_json(json_data)

            # Create a prompt that includes OCR data
            prompt = f"""
            You are an expert AI agent specializing in legal form analysis. The standard checkbox detection on this form failed.
            I need you to use OCR text data to identify which checkboxes need to be checked.

            Focus on finding checkboxes related to:

            1. REGISTERED AGENT TYPE:
               - Common options: "commercial registered agent" vs "non-commercial registered agent"

            2. LLC MANAGEMENT STRUCTURE:
               - Common options: "member-managed LLC" vs "manager-managed LLC"

            Here is the OCR text extracted from the PDF:
            {json.dumps(ocr_data, indent=2)}

            Here is the form data from the user:
            {json.dumps(flat_json, indent=2, cls=NumpyEncoder)}

            Here are all form fields in the PDF:
            {json.dumps({k: {
                "field_type": v.get("field_type", "Unknown"),
                "label": v.get("label", "Unknown"),
                "page_num": v["page_num"] + 1,
                "rect": v["rect"]
            } for k, v in pdf_fields.items()}, indent=2)}

            INSTRUCTIONS:

            1. Analyze the OCR text to identify text that indicates checkbox options for registered agent or management structure
            2. Look at the PDF form fields and identify which ones might be checkboxes near these text elements
            3. Determine which checkboxes should be checked based on the user's data
            4. Be creative and flexible - form fields might be incorrectly labeled or categorized

            Return a JSON object with the following structure:
            {{
            "checkbox_matches": [
                    {{
                        "json_field": "[relevant JSON field that determined this choice]",
                        "pdf_field": "[field name in PDF that should be checked]",
                        "confidence": 0.0-1.0,
                        "suggested_value": true,
                        "reasoning": "Detailed explanation of why this checkbox should be checked...",
                        "category": "[REGISTERED_AGENT or MEMBER_MANAGER]",
                        "is_checkbox": true,
                        "related_ocr_text": "[relevant OCR text that helped identify this checkbox]"
                    }},
                    ...
                ]
            }}

            Return valid JSON only.
            """

            # Send to AI and process response
            response = await self.checkbox_agent.run(prompt)
            result = self.parse_checkbox_response(response.data)

            if not result or not result.get("checkbox_matches"):
                print("⚠️ No checkbox matches were found using OCR analysis.")
                print("Attempting final analysis using best-guess approach...")
                return await self.detect_checkboxes_best_guess(pdf_path, json_data, pdf_fields)

            checkbox_matches = []
            for match in result.get("checkbox_matches", []):
                try:
                    validated_match = FieldMatch(
                        json_field=match.get("json_field", ""),
                        pdf_field=match.get("pdf_field", ""),
                        confidence=match.get("confidence", 0.8),
                        suggested_value=match.get("suggested_value", True),
                        reasoning=match.get("reasoning", ""),
                        is_checkbox=True
                    )
                    checkbox_matches.append(validated_match)
                    print(
                        f"✅ OCR-aided detection found checkbox match: {match.get('pdf_field')} → {match.get('suggested_value')}")
                    print(f"   Reason: {match.get('reasoning', 'No reasoning provided')}")
                    print(f"   Related OCR text: {match.get('related_ocr_text', 'None')}")

                    # Check the checkbox
                    self.check_checkbox_immediately(pdf_path, match.get('pdf_field'), pdf_fields)
                except Exception as e:
                    print(f"⚠️ Error processing OCR checkbox match: {str(e)}")

            return checkbox_matches

        except Exception as e:
            print(f"❌ Error in OCR-based checkbox detection: {str(e)}")
            return []

    async def detect_checkboxes_best_guess(self, pdf_path: str, json_data: Dict[str, Any],
                                           pdf_fields: Dict[str, Dict[str, Any]]) -> List[FieldMatch]:
        """Final best-guess approach using AI agent when other methods fail."""
        print("🔍 Using best-guess approach to identify checkboxes...")

        try:
            # Flatten the JSON data
            flat_json = self.flatten_json(json_data)

            # Extract key information that will help with checkbox identification
            agent_info = {}
            management_info = {}

            for k, v in flat_json.items():
                k_lower = k.lower()
                if any(term in k_lower for term in ["agent", "registered", "commercial"]):
                    agent_info[k] = v
                elif any(term in k_lower for term in ["manage", "member", "manager", "structure"]):
                    management_info[k] = v

            # Create a prompt for best-guess analysis
            prompt = f"""
            You are an expert AI agent specializing in legal form analysis. Previous checkbox detection methods have failed.
            I need you to make your best guess about which form fields should be treated as checkboxes and checked.

            Focus on finding fields related to:

            1. REGISTERED AGENT TYPE:
               - Common options: "commercial registered agent" vs "non-commercial registered agent"

            2. LLC MANAGEMENT STRUCTURE:
               - Common options: "member-managed LLC" vs "manager-managed LLC"

            Key registered agent information from the user:
            {json.dumps(agent_info, indent=2, cls=NumpyEncoder)}

            Key management structure information from the user:
            {json.dumps(management_info, indent=2, cls=NumpyEncoder)}

            Form fields to consider (showing field type and label):
            {json.dumps({k: {
                "field_type": v.get("field_type", "Unknown"),
                "label": v.get("label", "Unknown")
            } for k, v in pdf_fields.items()}, indent=2)}

            INSTRUCTIONS:

            1. Make your BEST GUESS about which fields might be checkboxes for registered agent and management structure
            2. Consider ALL fields, not just those labeled as checkboxes - they might be buttons, text fields, or other types
            3. Use creative reasoning based on field names, labels, and types
            4. Determine which fields should be checked based on the user's data

            Return a JSON object with the following structure:
            {{
            "checkbox_matches": [
                    {{
                        "json_field": "[relevant JSON field that determined this choice]",
                        "pdf_field": "[field name in PDF that should be checked]",
                        "confidence": 0.0-1.0,
                        "suggested_value": true,
                        "reasoning": "Detailed explanation of why this field might be a checkbox...",
                        "category": "[REGISTERED_AGENT or MEMBER_MANAGER]",
                        "is_checkbox": true
                    }},
                    ...
                ]
            }}

            Return valid JSON only.
            """

            # Send to AI and process response
            response = await self.checkbox_agent.run(prompt)
            result = self.parse_checkbox_response(response.data)

            if not result or not result.get("checkbox_matches"):
                print("❌ All checkbox detection methods failed.")
                return []

            checkbox_matches = []
            for match in result.get("checkbox_matches", []):
                try:
                    validated_match = FieldMatch(
                        json_field=match.get("json_field", ""),
                        pdf_field=match.get("pdf_field", ""),
                        confidence=match.get("confidence", 0.6),  # Lower confidence for best-guess approach
                        suggested_value=match.get("suggested_value", True),
                        reasoning=match.get("reasoning", ""),
                        is_checkbox=True
                    )
                    checkbox_matches.append(validated_match)
                    print(
                        f"✅ Best-guess detection found potential checkbox: {match.get('pdf_field')} → {match.get('suggested_value')}")
                    print(f"   Reason: {match.get('reasoning', 'No reasoning provided')}")

                    # Check the checkbox
                    self.check_checkbox_immediately(pdf_path, match.get('pdf_field'), pdf_fields)
                except Exception as e:
                    print(f"⚠️ Error processing best-guess checkbox match: {str(e)}")

            return checkbox_matches

        except Exception as e:
            print(f"❌ Error in best-guess checkbox detection: {str(e)}")
            return []
    def retry_checkbox_with_alternatives(self, pdf_path: str, field_name: str,
                                         pdf_fields: Dict[str, Dict[str, Any]]) -> bool:
        """Try alternative approaches for stubborn checkboxes that resist standard methods."""
        try:
            field_info = pdf_fields.get(field_name)
            if not field_info:
                return False

            page_num = field_info["page_num"]
            doc = fitz.open(pdf_path)
            page = doc[page_num]

            # Try multiple approaches for stubborn checkboxes
            # Approach 1: Try setting a visual mark on the checkbox using annotations
            for widget in page.widgets():
                if widget.field_name == field_name:
                    rect = widget.rect

                    # First try adding a check mark using annotation
                    try:
                        # Add a visible X mark annotation over the checkbox
                        annot = page.add_freetext_annot(
                            rect=rect,
                            text="X",
                            fontsize=min(rect.width, rect.height) * 0.8,
                            text_color=(0, 0, 0),
                            align=fitz.TEXT_ALIGN_CENTER
                        )
                        doc.save(pdf_path, deflate=True, clean=True)
                        doc.close()
                        return True
                    except Exception as e:
                        print(f"Annotation approach failed: {e}")

                    # Approach 2: Try marking directly on the PDF using drawing functions
                    try:
                        # Draw an X mark
                        page.draw_line(rect.tl, rect.br, color=(0, 0, 0), width=2)
                        page.draw_line(rect.tr, rect.bl, color=(0, 0, 0), width=2)
                        doc.save(pdf_path, deflate=True, clean=True)
                        doc.close()
                        return True
                    except Exception as e:
                        print(f"Drawing approach failed: {e}")

            doc.close()
            return False

        except Exception as e:
            print(f"❌ All alternative checkbox methods failed: {e}")
            return False

    def check_checkbox_immediately(self, pdf_path: str, field_name: str, pdf_fields: Dict[str, Dict[str, Any]]) -> bool:
        """Immediately checks a checkbox in the PDF once detected with improved options for compatibility."""
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
                    print(f"🔳 Checking checkbox: '{field_name}' on page {page_num + 1}")

                    # Try different checkbox value options for better compatibility
                    checkbox_values = ["Yes", "On", "Checked", "True", "X", "1"]

                    if hasattr(widget, 'choice_values') and widget.choice_values:
                        # If the widget has predefined choice values, use the first one
                        try:
                            widget.field_value = widget.choice_values[0]
                            widget.update()
                            checkbox_checked = True
                            print(f"✅ Checkbox checked with choice value: {widget.choice_values[0]}")
                        except Exception as e:
                            print(f"⚠️ Failed with choice value: {e}")

                    if not checkbox_checked:
                        # Try standard values for checkboxes
                        for val in checkbox_values:
                            try:
                                widget.field_value = val
                                widget.update()
                                checkbox_checked = True
                                print(f"✅ Checkbox checked with value: {val}")
                                break
                            except Exception as e:
                                continue

                    break

            if checkbox_checked:
                # Save with clean=True to avoid PDF corruption
                doc.save(pdf_path, deflate=True, clean=True)
                print(f"✅ Checkbox '{field_name}' successfully checked")
                doc.close()
                return True
            else:
                print(f"⚠️ Checkbox widget for '{field_name}' not found or couldn't be checked on page {page_num}")
                doc.close()
                return False

        except Exception as e:
            print(f"❌ Error checking checkbox immediately: {e}")
            return False

    def parse_checkbox_response(self, response_text: str) -> Dict[str, List]:
        """Parse the AI response specific to checkbox detection with better JSON extraction."""
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

        # Try to extract JSON even if surrounded by extra text
        try:
            # Find the first { and last } to extract potential JSON
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1

            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                data = json.loads(json_str)
                return data
        except json.JSONDecodeError:
            pass

        # If the above failed, try the original response
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

    def fill_pdf_immediately(self, output_pdf: str, matches: List[FieldMatch],
                             pdf_fields: Dict[str, Dict[str, Any]]) -> bool:
        """Fills PDF form fields using PyMuPDF (fitz) with improved handling of readonly fields and checkboxes."""
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
                        # Handle regular fields
                        print(f"✍️ Filling: '{value}' → '{field_name}' (Page {page_num + 1})")
                        widget.field_value = str(value)

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
        """Fills OCR-detected areas with text for readonly fields."""
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

                    print(
                        f"✍️ Filling OCR field: '{match.suggested_value}' → near '{match.ocr_text}' (Page {match.page_num + 1})")

                    annotation_added = False

                    try:
                        annot = page.add_freetext_annot(
                            rect=rect,
                            text=str(match.suggested_value),
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

                            page.insert_text(
                                point=(x1 + 2, y1 + 10),
                                text=str(match.suggested_value),
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
                                text=str(match.suggested_value)
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