import asyncio
import json
import os
import re
import numpy as np
import cv2
import fitz
from typing import Dict, Any, List, Tuple, Optional

from paddleocr import PaddleOCR
from pdf2image import convert_from_path

from pydantic_ai import Agent
from pydantic_ai.models.gemini import GeminiModel
from pydantic import BaseModel, field_validator, ConfigDict, ValidationError
from Common.constants import *

API_KEYS = {
    "field_matcher": API_KEY_3,
}

class AIResponseValidationError(Exception):
    """Custom exception for AI response validation failures."""
    pass


class AdvancedOCRProcessor:
    def __init__(self, languages=['en'], use_gpu=True):
        """
        Initialize advanced OCR processor with multi-language support and GPU acceleration

        Args:
            languages (List[str]): List of language codes to support
            use_gpu (bool): Enable GPU acceleration for OCR
        """
        self.ocr_readers = {
            lang: PaddleOCR(
                use_angle_cls=True,
                lang=lang,
                use_gpu=use_gpu,
                show_log=False
            ) for lang in languages
        }

    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Advanced image preprocessing for improved OCR accuracy

        Args:
            image (np.ndarray): Input image

        Returns:
            np.ndarray: Preprocessed image
        """
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )

        # Denoise
        denoised = cv2.fastNlMeansDenoising(thresh, None, 10, 7, 21)

        return denoised

    def extract_text_multilingual(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        Extract text using multiple language OCR with advanced preprocessing

        Args:
            image (np.ndarray): Input image

        Returns:
            List[Dict[str, Any]]: Extracted text with details
        """
        preprocessed_image = self.preprocess_image(image)

        all_results = []
        for lang, ocr_reader in self.ocr_readers.items():
            try:
                results = ocr_reader.ocr(preprocessed_image, cls=True)
                if results:
                    for result in results:
                        for text_info in result:
                            all_results.append({
                                'text': text_info[1][0],
                                'confidence': text_info[1][1],
                                'bbox': text_info[0],
                                'language': lang
                            })
            except Exception as e:
                print(f"OCR error for language {lang}: {e}")

        # Sort results by confidence
        return sorted(all_results, key=lambda x: x['confidence'], reverse=True)


class FieldMatchingAgent:
    def __init__(self, model_name="gemini-1.5-flash"):
        """
        Initialize AI agent for intelligent field matching with enhanced error handling

        Args:
            model_name (str): AI model to use
            temperature (float): Creativity/randomness of responses
        """
        self.agent = Agent(
            model=GeminiModel(model_name, api_key=API_KEYS.get("field_matcher")),
            system_prompt="""
            You are an advanced AI assistant for intelligent PDF form field mapping.

            CRITICAL OUTPUT REQUIREMENTS:
            1. ALWAYS return a VALID JSON with this EXACT structure:
            {
                "matches": [
                    {
                        "json_field": "exact_json_key",
                        "pdf_field": "PDF field label",
                        "suggested_value": "value to fill",
                        "confidence": 0.7,
                        "reasoning": "Mapping explanation"
                    }
                ]
            }

            2. If NO matches are found, return:
            {"matches": []}

            3. NEVER include code blocks, comments, or additional text
            """

        )

    async def intelligent_field_mapping(
            self,
            json_data: Dict[str, Any],
            ocr_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Advanced field mapping using AI with comprehensive context and robust error handling

        Args:
            json_data (Dict[str, Any]): Input JSON data
            ocr_results (List[Dict[str, Any]]): OCR extracted text

        Returns:
            List[Dict[str, Any]]: Intelligent field mappings
        """
        # Prepare comprehensive mapping prompt
        prompt = json.dumps({
            "json_data": json_data,
            "ocr_results": ocr_results,
            "mapping_instructions": {
                "prioritize_semantic_matching": True,
                "handle_nested_structures": True,
                "suggest_value_transformations": True
            }
        }, indent=2)

        try:
            response = await self.agent.run(prompt)
            return self._parse_and_validate_matches(response.data)

        except Exception as e:
            print(f"Field mapping error: {e}")
            return []

    def _parse_and_validate_matches(self, raw_response: str) -> List[Dict[str, Any]]:
        """
        Comprehensive parsing and validation of AI-generated field matches

        Args:
            raw_response (str): Raw AI response

        Returns:
            List[Dict[str, Any]]: Validated field matches

        Raises:
            AIResponseValidationError: If response cannot be parsed or validated
        """
        print("Parsing AI response...")

        # Extensive cleaning and preprocessing
        try:
            # Remove any code block markers, trim whitespace
            clean_response = re.sub(r'```(json)?', '', raw_response).strip()
            clean_response = clean_response.replace('\n', '').replace('\r', '')

            print(f"Cleaned response: {clean_response}")

            # Attempt to parse JSON
            try:
                parsed_matches = json.loads(clean_response)
            except json.JSONDecodeError as json_err:
                print(f"JSON Decoding Error: {json_err}")
                print(f"Problematic response: {clean_response}")
                raise AIResponseValidationError("Invalid JSON structure")

            # Validate parsed matches
            validated_matches = []
            for match in parsed_matches.get('matches', []):
                # Rigorous validation of match structure
                if not all(key in match for key in ['json_field', 'pdf_field', 'suggested_value']):
                    print(f"Incomplete match: {match}")
                    continue

                # Normalize and validate match
                validated_match = {
                    'json_field': str(match['json_field']),
                    'pdf_field': str(match['pdf_field']),
                    'suggested_value': str(match['suggested_value']),
                    'confidence': float(match.get('confidence', 0.7)),
                    'reasoning': str(match.get('reasoning', 'No specific reasoning'))
                }

                validated_matches.append(validated_match)

            print(f"Parsed {len(validated_matches)} valid field matches")
            return validated_matches

        except Exception as e:
            print(f"Comprehensive parsing error: {e}")
            print(f"Original response: {raw_response}")
            raise AIResponseValidationError(f"Failed to parse AI response: {e}")


class PDFSmartFiller:
    def __init__(self):
        self.ocr_processor = AdvancedOCRProcessor()
        self.field_matcher = FieldMatchingAgent()

    async def process_pdf(
            self,
            input_pdf_path: str,
            json_data: Dict[str, Any],
            output_pdf_path: str
    ):
        """
        Comprehensive PDF processing with advanced OCR and AI mapping

        Args:
            input_pdf_path (str): Input PDF file path
            json_data (Dict[str, Any]): Data to fill in PDF
            output_pdf_path (str): Output filled PDF path
        """
        try:
            # Convert PDF to images
            pdf_images = convert_from_path(input_pdf_path)

            # Extract text from images
            all_ocr_results = []
            for image in pdf_images:
                img_array = np.array(image)
                page_results = self.ocr_processor.extract_text_multilingual(img_array)
                all_ocr_results.extend(page_results)

            # Intelligent field mapping with enhanced error handling
            try:
                field_matches = await self.field_matcher.intelligent_field_mapping(
                    json_data,
                    all_ocr_results
                )

                # Ensure we have matches before filling
                if not field_matches:
                    print("No field matches found. Skipping PDF filling.")
                    return

                # Fill PDF with matched fields
                self._fill_pdf_intelligently(input_pdf_path, output_pdf_path, field_matches)

            except AIResponseValidationError as ave:
                print(f"AI Response Validation Failed: {ave}")
                # Optionally, you could fall back to a manual mapping strategy here

        except Exception as e:
            print(f"PDF processing failed: {e}")

    def _fill_pdf_intelligently(
            self,
            input_pdf_path: str,
            output_pdf_path: str,
            field_matches: List[Dict[str, Any]]
    ):
        """
        Intelligent PDF field filling with advanced placement

        Args:
            input_pdf_path (str): Input PDF path
            output_pdf_path (str): Output PDF path
            field_matches (List[Dict[str, Any]]): Field mappings
        """
        doc = fitz.open(input_pdf_path)

        for match in field_matches:
            for page in doc:
                # Advanced text and placeholder detection
                text_instances = page.search_for(match['pdf_field'])
                placeholder_instances = page.search_for("___________________")

                # Smart field placement logic
                for rect in text_instances + placeholder_instances:
                    page.insert_text(
                        (rect[0] + 5, rect[1] + 8),
                        str(match['suggested_value']),
                        fontsize=10
                    )

        doc.save(output_pdf_path)
        print(f"Intelligently filled PDF saved: {output_pdf_path}")


async def main():
    try:
        smart_filler = PDFSmartFiller()
        input_pdf = "D:\\demo\\Services\\Maine.pdf"
        json_path = "D:\\demo\\Services\\form_data.json"
        output_pdf = "D:\\demo\\Services\\fill_smart_fina2.pdf"

        # Load JSON data with error handling
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Failed to load JSON data: {e}")
            return

        # Process PDF
        await smart_filler.process_pdf(input_pdf, json_data, output_pdf)

    except Exception as e:
        print(f"Unexpected error in main process: {e}")


if __name__ == "__main__":
    asyncio.run(main())