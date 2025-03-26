import asyncio
import json
import os
import re
import shutil
import hashlib
from typing import Dict, Any, List, Tuple

import fitz
import numpy as np
import cv2
from paddleocr import PaddleOCR
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, BooleanObject, ArrayObject
from difflib import SequenceMatcher

from pydantic_ai import Agent
from pydantic_ai.models.gemini import GeminiModel
from pydantic import BaseModel, field_validator


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


class MultiAgentFormFiller:
    def __init__(self):
        self.agent = Agent(
            model=GeminiModel("gemini-1.5-flash", api_key=API_KEYS["field_matcher"]),
            system_prompt="You are an expert at mapping PDF fields to JSON keys and filling them immediately."
        )

        self.ocr_reader = PaddleOCR(use_angle_cls=True, lang='en')
        self.matched_fields = {}

    def extract_template_info(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract comprehensive template information including fields and OCR text.

        Args:
            pdf_path (str): Path to the PDF template

        Returns:
            Dict[str, Any]: Extracted template information
        """
        print(f"🔍 Extracting template information for: {pdf_path}")
        doc = fitz.open(pdf_path)

        # Extract fillable fields
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

        # Extract OCR text
        ocr_results = []
        ocr_reader = PaddleOCR(use_angle_cls=True, lang='en')

        for page_num in range(len(doc)):
            pix = doc[page_num].get_pixmap(alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)

            if img.shape[2] == 4:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)

            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                           cv2.THRESH_BINARY_INV, 11, 2)

            results = ocr_reader.ocr(binary, cls=True)

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

        template_info = {
            "pdf_path": pdf_path,
            "pdf_fields": fields,
            "ocr_text_elements": ocr_results
        }

        print(f"✅ Extracted {len(fields)} fields and {len(ocr_results)} OCR elements")
        return template_info

    async def extract_pdf_fields(self, pdf_path: str) -> Dict[str, Dict[str, Any]]:
        """Extracts all fillable fields from a multi-page PDF with additional metadata."""
        print("🔍 Extracting all fillable fields...")

        # Extract template information
        template_info = self.extract_template_info(pdf_path)
        pdf_fields = template_info['pdf_fields']

        print(f"✅ Extracted {len(pdf_fields)} fields.")
        for field, info in pdf_fields.items():
            readonly_status = "READ-ONLY" if info["is_readonly"] else "EDITABLE"
            print(f" - Field: '{field}' (Page {info['page_num'] + 1}) [{readonly_status}]")

        return pdf_fields

    async def extract_ocr_text(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Extract text from PDF using OCR."""
        print("🔍 Extracting text using OCR...")

        # Extract template information
        template_info = self.extract_template_info(pdf_path)
        ocr_results = template_info['ocr_text_elements']

        print(f"✅ Extracted {len(ocr_results)} text elements using OCR.")
        return ocr_results

    async def match_and_fill_fields(self, pdf_path: str, json_data: Dict[str, Any], output_pdf: str,
                                    max_retries: int = 3):
        """Matches fields using AI and fills them immediately across multiple pages, ensuring OCR text is mapped to UUIDs properly."""

        backup_pdf = f"{pdf_path}.backup"
        shutil.copy2(pdf_path, backup_pdf)
        print(f"Created backup of original PDF: {backup_pdf}")

        pdf_fields = await self.extract_pdf_fields(pdf_path)
        ocr_text_elements = await self.extract_ocr_text(pdf_path)
        flat_json = self.flatten_json(json_data)
        field_context = await self.analyze_field_context(pdf_fields, ocr_text_elements)

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

        temp_output = f"{output_pdf}.temp"
        shutil.copy2(pdf_path, temp_output)

        try:
            print("Filling form fields and OCR-detected fields together with UUID-based matching...")
            combined_matches = matches + [
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

    async def analyze_field_context(self, pdf_fields: Dict[str, Dict[str, Any]],
                              ocr_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyze context around form fields using an AI-powered approach for improved understanding.

        Args:
            pdf_fields (Dict[str, Dict[str, Any]]): Dictionary of PDF form fields
            ocr_elements (List[Dict[str, Any]]): List of OCR text elements

        Returns:
            List[Dict[str, Any]]: Enhanced context for each form field
        """
        field_context = []

        # Prepare context data for AI analysis
        context_data = {
            "pdf_fields": [],
            "ocr_elements": []
        }

        # Process PDF fields
        for field_name, field_info in pdf_fields.items():
            field_context_entry = {
                "field_name": field_name,
                "page": field_info["page_num"] + 1,
                "rect": field_info["rect"],
                "nearby_elements": []
            }

            # Find nearby OCR text elements
            nearby_text = []
            for ocr_elem in ocr_elements:
                if ocr_elem["page_num"] != field_info["page_num"]:
                    continue

                ocr_pos = ocr_elem["position"]

                # Proximity calculation with more advanced logic
                horizontal_proximity = abs(field_info["rect"][0] - ocr_pos["x2"])
                vertical_proximity = abs(field_info["rect"][1] - ocr_pos["y2"])

                # More sophisticated proximity conditions
                is_nearby = (
                        (ocr_pos["x2"] < field_info["rect"][0] and horizontal_proximity < 250 and
                         abs(field_info["rect"][1] - ocr_pos["y1"]) < 50) or
                        (ocr_pos["y2"] < field_info["rect"][1] and vertical_proximity < 100 and
                         abs(field_info["rect"][0] - ocr_pos["x1"]) < 250)
                )

                if is_nearby:
                    nearby_text.append({
                        "text": ocr_elem["text"],
                        "position": {
                            "x1": ocr_pos["x1"],
                            "y1": ocr_pos["y1"],
                            "x2": ocr_pos["x2"],
                            "y2": ocr_pos["y2"]
                        },
                        "horizontal_distance": horizontal_proximity,
                        "vertical_distance": vertical_proximity
                    })

            # Sort nearby text by combined proximity
            nearby_text.sort(key=lambda x: x["horizontal_distance"] + x["vertical_distance"])
            field_context_entry["nearby_elements"] = nearby_text[:5]  # Keep top 5 nearby elements

            # Prepare context for AI analysis
            context_data["pdf_fields"].append({
                "field_name": field_name,
                "page": field_info["page_num"] + 1,
                "rect": field_info["rect"]
            })
            context_data["ocr_elements"].extend(nearby_text)

        # If AI agent is available, enhance context further
        try:
            context_prompt = f"""
            Analyze the following PDF form field context:

            PDF Fields: {json.dumps(context_data['pdf_fields'], indent=2)}

            Nearby OCR Text Elements: {json.dumps(context_data['ocr_elements'], indent=2)}

            For each PDF field, provide:
            1. Likely field type/purpose
            2. Potential default or expected value
            3. Any suggestions for field interpretation

            Respond in a structured JSON format with detailed insights.
            """

            # Use the existing AI agent to get enhanced context
            response = await self.agent.run(context_prompt)

            # Parse AI response and integrate additional insights
            ai_context = json.loads(response.data)

            # Merge AI insights with existing context
            for field_context_entry in field_context:
                field_name = field_context_entry["field_name"]
                ai_field_insights = next((item for item in ai_context.get('field_insights', [])
                                          if item.get('field_name') == field_name), None)

                if ai_field_insights:
                    field_context_entry.update({
                        "ai_suggested_type": ai_field_insights.get('suggested_type'),
                        "ai_suggested_value": ai_field_insights.get('suggested_value'),
                        "ai_interpretation_notes": ai_field_insights.get('interpretation_notes')
                    })

        except Exception as e:
            print(f"⚠️ AI context enhancement failed: {e}")

        return field_context

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
        """Fills PDF form fields using PyMuPDF (fitz) with improved handling of readonly fields."""
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
                updates.append((page_num, match.pdf_field, match.suggested_value))

        for page_num, field_name, value in updates:
            page = doc[page_num]
            for widget in page.widgets():
                if widget.field_name == field_name:
                    print(f"✍️ Filling: '{value}' → '{field_name}' (Page {page_num + 1})")
                    try:
                        widget.field_value = str(value)
                        widget.update()
                        filled_fields.append(field_name)
                    except Exception as e:
                        print(f"⚠️ Error filling {field_name}: {e}")
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
    template_pdf = "D:\\demo\\Services\\Wisconsin.pdf"
    json_path = "D:\\demo\\Services\\form_data.json"
    output_pdf = "D:\\demo\\Services\\fill_smart5.pdf"

    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    success = await form_filler.match_and_fill_fields(template_pdf, json_data, output_pdf)

    if success:
        print(f"✅ PDF successfully processed: {output_pdf}")
    else:
        print(f"❌ PDF processing failed. Please check the output file and logs.")


if __name__ == "__main__":
    asyncio.run(main())