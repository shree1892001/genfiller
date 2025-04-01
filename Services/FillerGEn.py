import asyncio
import json
import os
import re
import numpy as np
import cv2
import fitz
import time
from typing import Dict, Any, List, Tuple, Optional
import traceback
import shutil
from paddleocr import PaddleOCR
from pdf2image import convert_from_path

from pydantic_ai import Agent
from pydantic_ai.models.gemini import GeminiModel
from pydantic import BaseModel, field_validator, ConfigDict, ValidationError
from Common.constants import *

# Add timeout constants
API_TIMEOUT = 30  # seconds
OCR_TIMEOUT = 60  # seconds

API_KEYS = {
    "field_matcher":API_KEY_3,  # Replace with your actual API key
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
        print("Initializing OCR processor...")
        self.ocr_readers = {}
        for lang in languages:
            try:
                self.ocr_readers[lang] = PaddleOCR(
                    use_angle_cls=True,
                    lang=lang,
                    use_gpu=use_gpu,
                    show_log=False
                )
                print(f"Initialized OCR reader for language: {lang}")
            except Exception as e:
                print(f"Failed to initialize OCR reader for language {lang}: {e}")

    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Advanced image preprocessing for improved OCR accuracy

        Args:
            image (np.ndarray): Input image

        Returns:
            np.ndarray: Preprocessed image
        """
        print("Preprocessing image...")
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
        print("Image preprocessing complete")

        return denoised

    def extract_text_multilingual(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        Extract text using multiple language OCR with advanced preprocessing

        Args:
            image (np.ndarray): Input image

        Returns:
            List[Dict[str, Any]]: Extracted text with details
        """
        print("Starting OCR text extraction...")
        start_time = time.time()

        preprocessed_image = self.preprocess_image(image)

        all_results = []
        for lang, ocr_reader in self.ocr_readers.items():
            try:
                print(f"Running OCR for language: {lang}")
                # Add timeout check
                if time.time() - start_time > OCR_TIMEOUT:
                    print(f"OCR timeout after {OCR_TIMEOUT} seconds. Returning partial results.")
                    break

                results = ocr_reader.ocr(preprocessed_image, cls=True)
                # Convert generator to list if needed
                if hasattr(results, '__iter__') and not hasattr(results, '__len__'):
                    results = list(results)

                print(f"OCR completed for language {lang}")
                if results:
                    for result in results:
                        # Convert inner result to list if it's a generator
                        if hasattr(result, '__iter__') and not hasattr(result, '__len__'):
                            result = list(result)

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
        results = sorted(all_results, key=lambda x: x['confidence'], reverse=True)
        print(f"Extracted {len(results)} text elements in {time.time() - start_time:.2f} seconds")
        return results


class PlaceholderDetector:
    """Class to detect and parse placeholders in parentheses"""

    @staticmethod
    def extract_placeholders(ocr_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract placeholders in parentheses from OCR results

        Args:
            ocr_results (List[Dict[str, Any]]): OCR text elements

        Returns:
            List[Dict[str, Any]]: Extracted placeholders with position info
        """
        print("Extracting placeholders from OCR results...")
        placeholders = []

        # Regular expression to match text in parentheses
        placeholder_pattern = r'\((.*?)\)'

        for result in ocr_results:
            text = result.get('text', '')
            matches = re.findall(placeholder_pattern, text)

            if matches:
                for match in matches:
                    # Ensure we have coordinates from the bounding box
                    if 'bbox' in result:
                        # Create a placeholder entry with necessary info
                        placeholder = {
                            'placeholder_text': match.strip(),
                            'original_text': text,
                            'page': result.get('page', 0),
                            'bbox': result['bbox'],
                            'confidence': result.get('confidence', 0)
                        }
                        placeholders.append(placeholder)
                        print(f"Found placeholder: '{match.strip()}' on page {result.get('page', 0)}")

        print(f"Extracted {len(placeholders)} placeholders in total")
        return placeholders


class FieldMatchingAgent:
    def __init__(self, model_name="gemini-1.5-flash"):
        """
        Initialize AI agent for intelligent field matching with enhanced error handling

        Args:
            model_name (str): AI model to use
        """
        print(f"Initializing Field Matching Agent with model: {model_name}")
        try:
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
            print("Field Matching Agent initialized successfully")
        except Exception as e:
            print(f"Failed to initialize Field Matching Agent: {e}")
            raise

    async def intelligent_field_mapping(
            self,
            json_data: Dict[str, Any],
            ocr_results: List[Dict[str, Any]],
            placeholders: List[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Advanced field mapping using AI with comprehensive context and robust error handling
        Now with enhanced placeholder support

        Args:
            json_data (Dict[str, Any]): Input JSON data
            ocr_results (List[Dict[str, Any]]): OCR extracted text
            placeholders (List[Dict[str, Any]]): Extracted placeholders in parentheses

        Returns:
            List[Dict[str, Any]]: Intelligent field mappings
        """
        print("Starting intelligent field mapping...")
        start_time = time.time()

        # Use a truncated version of OCR results to avoid overwhelming the model
        max_ocr_results = 100
        truncated_ocr = ocr_results[:max_ocr_results] if len(ocr_results) > max_ocr_results else ocr_results
        print(f"Using {len(truncated_ocr)} OCR results out of {len(ocr_results)}")

        # Prepare comprehensive mapping prompt with placeholder information
        prompt_data = {
            "json_data": json_data,
            "ocr_results": truncated_ocr,
            "mapping_instructions": {
                "prioritize_semantic_matching": True,
                "handle_nested_structures": True,
                "suggest_value_transformations": True,
                "focus_on_placeholders": True
            }
        }

        # Add placeholders if available
        if placeholders:
            max_placeholders = 50
            truncated_placeholders = placeholders[:max_placeholders] if len(
                placeholders) > max_placeholders else placeholders
            prompt_data["placeholders"] = truncated_placeholders
            prompt_data["mapping_instructions"]["prioritize_placeholder_matching"] = True
            print(f"Including {len(truncated_placeholders)} placeholders in mapping prompt")

        prompt = json.dumps(prompt_data, indent=2)

        try:
            print("Sending request to AI model...")
            # Add timeout to the API call
            response_future = self.agent.run(prompt)
            response = await asyncio.wait_for(response_future, timeout=API_TIMEOUT)
            print(f"Received AI response in {time.time() - start_time:.2f} seconds")
            return self._parse_and_validate_matches(response.data)

        except asyncio.TimeoutError:
            print(f"AI request timed out after {API_TIMEOUT} seconds")
            return []
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

            print(f"Cleaned response length: {len(clean_response)} characters")
            print(f"Response preview: {clean_response[:100]}...")

            # Attempt to parse JSON
            try:
                parsed_matches = json.loads(clean_response)
            except json.JSONDecodeError as json_err:
                print(f"JSON Decoding Error: {json_err}")
                print(f"First 200 chars of problematic response: {clean_response[:200]}")
                raise AIResponseValidationError("Invalid JSON structure")

            # Validate parsed matches
            validated_matches = []
            match_count = len(parsed_matches.get('matches', []))
            print(f"Found {match_count} raw matches to validate")

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
                    'reasoning': str(match.get('reasoning', 'No specific reasoning')),
                    'is_placeholder': bool(match.get('is_placeholder', False))
                }

                validated_matches.append(validated_match)

            print(f"Parsed {len(validated_matches)} valid field matches")
            return validated_matches

        except Exception as e:
            print(f"Comprehensive parsing error: {e}")
            print(f"First 200 chars of original response: {raw_response[:200]}")
            raise AIResponseValidationError(f"Failed to parse AI response: {e}")


class PlaceholderFieldMatchingAgent:
    """Specialized agent for matching placeholders to JSON fields"""

    def __init__(self, model_name="gemini-1.5-flash"):
        """Initialize the placeholder matching agent"""
        print(f"Initializing Placeholder Matching Agent with model: {model_name}")
        try:
            self.agent = Agent(
                model=GeminiModel(model_name, api_key=API_KEYS.get("field_matcher")),
                system_prompt="""
                You are an AI specialized in matching PDF form placeholders to JSON data fields.

                Your task is to examine placeholders found in a PDF form (text in parentheses like "(name)" or 
                "(address)") and determine which JSON field they correspond to.

                CRITICAL OUTPUT REQUIREMENTS:
                ALWAYS return a VALID JSON with this EXACT structure:
                {
                    "placeholder_matches": [
                        {
                            "placeholder": "name",  // The placeholder text (without parentheses)
                            "json_field": "person.fullName",  // The corresponding JSON field path
                            "suggested_value": "John Smith",  // The value from the JSON to insert
                            "confidence": 0.9,  // Your confidence in this match (0.0-1.0)
                            "reasoning": "The placeholder requests a name which matches the person.fullName field"
                        }
                    ]
                }

                DO NOT include code blocks, comments, or additional text outside the JSON structure.
                """
            )
            print("Placeholder Matching Agent initialized successfully")
        except Exception as e:
            print(f"Failed to initialize Placeholder Matching Agent: {e}")
            raise

    async def match_placeholders(
            self,
            json_data: Dict[str, Any],
            placeholders: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Match placeholders to JSON fields

        Args:
            json_data: The JSON data with values to insert
            placeholders: List of extracted placeholders with position info

        Returns:
            List of placeholder matches with suggested values
        """
        print(f"Matching {len(placeholders)} placeholders to JSON fields...")
        start_time = time.time()

        # Prepare the placeholder matching prompt
        prompt = json.dumps({
            "json_data": json_data,
            "placeholders": [
                {
                    "placeholder_text": p["placeholder_text"],
                    "page": p.get("page", 0)
                } for p in placeholders
            ],
            "instructions": "Match each placeholder to the most appropriate JSON field. Consider both semantic matching and likely field types. For example, '(name)' might match to 'person.name' or 'company.name' depending on context."
        }, indent=2)

        try:
            print("Sending request to AI model for placeholder matching...")
            response_future = self.agent.run(prompt)
            response = await asyncio.wait_for(response_future, timeout=API_TIMEOUT)
            print(f"Received AI placeholder matching response in {time.time() - start_time:.2f} seconds")
            return self._parse_and_validate_placeholder_matches(response.data)
        except asyncio.TimeoutError:
            print(f"AI request timed out after {API_TIMEOUT} seconds")
            return []
        except Exception as e:
            print(f"Placeholder matching error: {e}")
            return []

    def _parse_and_validate_placeholder_matches(self, raw_response: str) -> List[Dict[str, Any]]:
        """Parse and validate the placeholder matches from AI response"""
        print("Parsing placeholder matching response...")

        try:
            # Clean response
            clean_response = re.sub(r'```(json)?', '', raw_response).strip()

            # Parse JSON
            try:
                parsed_matches = json.loads(clean_response)
            except json.JSONDecodeError as json_err:
                print(f"JSON Decoding Error: {json_err}")
                print(f"First 200 chars of problematic response: {clean_response[:200]}")
                return []

            # Extract and validate matches
            matches = []
            match_count = len(parsed_matches.get('placeholder_matches', []))
            print(f"Found {match_count} raw placeholder matches to validate")

            for match in parsed_matches.get('placeholder_matches', []):
                if not all(key in match for key in ['placeholder', 'json_field', 'suggested_value']):
                    print(f"Incomplete placeholder match: {match}")
                    continue

                matches.append({
                    'placeholder': str(match['placeholder']),
                    'json_field': str(match['json_field']),
                    'suggested_value': str(match['suggested_value']),
                    'confidence': float(match.get('confidence', 0.7)),
                    'reasoning': str(match.get('reasoning', 'No reasoning provided'))
                })

            print(f"Parsed {len(matches)} valid placeholder matches")
            return matches

        except Exception as e:
            print(f"Placeholder match parsing error: {e}")
            return []


class FormFieldAnalyzer:
    def __init__(self, model_name="gemini-1.5-flash"):
        """
        Initialize AI agent for form field analysis and placement

        Args:
            model_name (str): AI model to use
        """
        print(f"Initializing Form Field Analyzer with model: {model_name}")
        try:
            self.agent = Agent(
                model=GeminiModel(model_name, api_key=API_KEYS.get("field_matcher")),
                system_prompt="""
                You are an AI specialized in analyzing PDF forms and determining the exact positions 
                where field values should be placed.

                For each form field, you need to identify:
                1. The page number where the field is located
                2. The precise coordinates where text should be inserted
                3. Any special formatting requirements

                CRITICAL OUTPUT REQUIREMENTS:
                ALWAYS return a VALID JSON with this EXACT structure:
                {
                    "field_positions": [
                        {
                            "field_name": "Field name as it appears in PDF",
                            "page": 0,  // 0-indexed page number
                            "coordinates": {
                                "x": 150.5,  // x-coordinate for text insertion
                                "y": 225.3   // y-coordinate for text insertion
                            },
                            "max_width": 200,  // maximum width allowed for inserted text
                            "formatting": {
                                "alignment": "left",  // left, center, right
                                "font_size": 10
                            }
                        }
                    ]
                }

                DO NOT include code blocks, comments, or additional text outside the JSON structure.
                """
            )
            print("Form Field Analyzer initialized successfully")
        except Exception as e:
            print(f"Failed to initialize Form Field Analyzer: {e}")
            raise

    async def analyze_form_structure(
            self,
            ocr_results: List[Dict[str, Any]],
            pdf_width: int,
            pdf_height: int,
            field_matches: List[Dict[str, Any]],
            placeholders: List[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyze form structure to determine optimal field placement,
        now with enhanced placeholder support

        Args:
            ocr_results: OCR results from the PDF
            pdf_width: Width of the PDF in points
            pdf_height: Height of the PDF in points
            field_matches: List of field matches to place in the PDF
            placeholders: List of extracted placeholders (optional)

        Returns:
            List of field position mappings with exact coordinates
        """
        print("Starting form structure analysis...")
        start_time = time.time()

        # Use a truncated version of OCR results to avoid overwhelming the model
        max_ocr_results = 100
        truncated_ocr = ocr_results[:max_ocr_results] if len(ocr_results) > max_ocr_results else ocr_results
        print(f"Using {len(truncated_ocr)} OCR results out of {len(ocr_results)}")

        # Prepare the fields to place - limit to 20 fields max to avoid overwhelming the model
        fields_to_place = [match['pdf_field'] for match in field_matches][:20]
        print(f"Analyzing placement for {len(fields_to_place)} fields")

        # Prepare the analysis prompt
        prompt_data = {
            "ocr_results": truncated_ocr,
            "pdf_dimensions": {
                "width": pdf_width,
                "height": pdf_height
            },
            "fields_to_place": fields_to_place,
            "instructions": "Analyze the document structure and determine the exact positions where each field value should be placed. Look for form labels, underscores, boxes, or other indicators of field positions."
        }

        # Add placeholder information if available
        if placeholders:
            max_placeholders = 50
            truncated_placeholders = placeholders[:max_placeholders] if len(
                placeholders) > max_placeholders else placeholders
            prompt_data["placeholders"] = truncated_placeholders
            prompt_data[
                "instructions"] += " Pay special attention to text in parentheses, which are placeholders that need to be replaced."
            print(f"Including {len(truncated_placeholders)} placeholders in form analysis prompt")

        prompt = json.dumps(prompt_data, indent=2)

        try:
            print("Sending request to AI model for form analysis...")
            # Add timeout to the API call
            response_future = self.agent.run(prompt)
            response = await asyncio.wait_for(response_future, timeout=API_TIMEOUT)
            print(f"Received AI form analysis response in {time.time() - start_time:.2f} seconds")
            return self._parse_and_validate_positions(response.data)
        except asyncio.TimeoutError:
            print(f"AI request timed out after {API_TIMEOUT} seconds")
            return []
        except Exception as e:
            print(f"Form structure analysis error: {e}")
            return []

    def _parse_and_validate_positions(self, raw_response: str) -> List[Dict[str, Any]]:
        """
        Parse and validate the AI response for field positions

        Args:
            raw_response: Raw AI response

        Returns:
            List of validated field positions
        """
        print("Parsing field position analysis...")

        try:
            # Clean response
            clean_response = re.sub(r'```(json)?', '', raw_response).strip()
            print(f"Cleaned response length: {len(clean_response)} characters")
            print(f"Response preview: {clean_response[:100]}...")

            # Parse JSON
            try:
                parsed_positions = json.loads(clean_response)
            except json.JSONDecodeError as json_err:
                print(f"JSON Decoding Error: {json_err}")
                print(f"First 200 chars of problematic response: {clean_response[:200]}")
                return []

            # Extract and validate field positions
            field_positions = []
            position_count = len(parsed_positions.get('field_positions', []))
            print(f"Found {position_count} raw positions to validate")

            for position in parsed_positions.get('field_positions', []):
                if not all(key in position for key in ['field_name', 'page', 'coordinates']):
                    print(f"Incomplete position data: {position}")
                    continue

                field_positions.append(position)

            print(f"Parsed {len(field_positions)} valid field positions")
            return field_positions

        except Exception as e:
            print(f"Position parsing error: {e}")
            return []


class PDFSmartFiller:
    def __init__(self):
        print("Initializing PDF Smart Filler...")
        self.ocr_processor = AdvancedOCRProcessor()
        self.field_matcher = FieldMatchingAgent()
        self.placeholder_detector = PlaceholderDetector()
        self.placeholder_matcher = PlaceholderFieldMatchingAgent()
        self.field_analyzer = FormFieldAnalyzer()
        print("PDF Smart Filler initialized")

    async def process_pdf(
            self,
            input_pdf_path: str,
            json_data: Dict[str, Any],
            output_pdf_path: str
    ):
        """
        Comprehensive PDF processing with advanced OCR, AI mapping,
        and placeholder detection/replacement

        Args:
            input_pdf_path (str): Input PDF file path
            json_data (Dict[str, Any]): Data to fill in PDF
            output_pdf_path (str): Output filled PDF path
        """
        print(f"Starting PDF processing for: {input_pdf_path}")
        overall_start_time = time.time()

        try:
            # Verify input file exists
            if not os.path.exists(input_pdf_path):
                print(f"Error: Input PDF not found at {input_pdf_path}")
                return

            # Verify output directory exists
            output_dir = os.path.dirname(output_pdf_path)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                print(f"Created output directory: {output_dir}")

            # Convert PDF to images with progress reporting
            print(f"Converting PDF to images: {input_pdf_path}")
            pdf_conversion_start = time.time()
            pdf_images = convert_from_path(input_pdf_path)
            # Convert to list if it's a generator
            if hasattr(pdf_images, '__iter__') and not hasattr(pdf_images, '__len__'):
                pdf_images = list(pdf_images)
            pdf_conversion_time = time.time() - pdf_conversion_start
            print(f"PDF conversion completed in {pdf_conversion_time:.2f} seconds. Found {len(pdf_images)} pages.")

            # Extract text from images with progress reporting
            print("Starting OCR text extraction...")
            ocr_start_time = time.time()

            all_ocr_results = []
            for page_num, image in enumerate(pdf_images):
                page_start_time = time.time()
                print(f"Processing page {page_num + 1}/{len(pdf_images)}")

                img_array = np.array(image)
                page_results = self.ocr_processor.extract_text_multilingual(img_array)

                # Add page number to results
                for result in page_results:
                    result['page'] = page_num

                all_ocr_results.extend(page_results)

                page_time = time.time() - page_start_time
                print(
                    f"Page {page_num + 1} processed in {page_time:.2f} seconds. Found {len(page_results)} text elements.")

                # Break early if processing is taking too long


            ocr_time = time.time() - ocr_start_time
            print(f"OCR completed in {ocr_time:.2f} seconds. Found {len(all_ocr_results)} total text elements.")

            # NEW: Detect placeholders in parentheses
            print("Detecting plac                             eholders in parentheses...")
            placeholder_start_time = time.time()
            placeholders = self.placeholder_detector.extract_placeholders(all_ocr_results)
            placeholder_time = time.time() - placeholder_start_time
            print(
                f"Placeholder detection completed in {placeholder_time:.2f} seconds. Found {len(placeholders)} placeholders.")

            # NEW: Match placeholders to JSON fields
            print("Matching placeholders to JSON fields...")
            if placeholders:
                placeholder_match_start_time = time.time()
                placeholder_matches = await self.placeholder_matcher.match_placeholders(
                    json_data,
                    placeholders
                )
                placeholder_match_time = time.time() - placeholder_match_start_time
                print(
                    f"Placeholder matching completed in {placeholder_match_time:.2f} seconds. Found {len(placeholder_matches)} matches.")
            else:
                placeholder_matches = []
                print("No placeholders found to match.")

            # Intelligent field mapping
            try:
                print("Starting field mapping...")
                mapping_start_time = time.time()

                field_matches = await self.field_matcher.intelligent_field_mapping(
                    json_data,
                    all_ocr_results,
                    placeholders
                )

                # Add placeholder matches to field matches
                for p_match in placeholder_matches:
                    # Convert placeholder match to field match format
                    field_match = {
                        'json_field': p_match['json_field'],
                        'pdf_field': f"({p_match['placeholder']})",  # Add parentheses to match OCR text
                        'suggested_value': p_match['suggested_value'],
                        'confidence': p_match['confidence'],
                        'reasoning': p_match['reasoning'],
                        'is_placeholder': True
                    }

                    # Check if this placeholder is already matched
                    if not any(m['pdf_field'] == field_match['pdf_field'] for m in field_matches):
                        field_matches.append(field_match)
                        print(
                            f"Added placeholder match: {field_match['pdf_field']} -> {field_match['suggested_value']}")

                mapping_time = time.time() - mapping_start_time
                print(f"Field mapping completed in {mapping_time:.2f} seconds. Found {len(field_matches)} matches.")

                # Ensure we have matches before proceeding
                if not field_matches:
                    print("No field matches found. Skipping PDF filling.")
                    return

                # Get PDF dimensions for AI analysis
                print("Analyzing PDF structure...")
                doc = fitz.open(input_pdf_path)
                first_page = doc[0]
                pdf_width, pdf_height = first_page.rect.width, first_page.rect.height
                print(f"PDF dimensions: {pdf_width}x{pdf_height}")

                # Analyze form structure to determine field positions
                analysis_start_time = time.time()
                field_positions = await self.field_analyzer.analyze_form_structure(
                    all_ocr_results,
                    pdf_width,
                    pdf_height,
                    field_matches,
                    placeholders
                )

                analysis_time = time.time() - analysis_start_time
                print(
                    f"Form structure analysis completed in {analysis_time:.2f} seconds. Found {len(field_positions)} field positions.")

                # Fill PDF using the determined positions
                filling_start_time = time.time()# Fill PDF using the determined

                await self._fill_pdf_with_ai_positions(
                    input_pdf_path,
                    output_pdf_path,
                    field_matches,
                    field_positions
                )
                filling_time = time.time() - filling_start_time
                print(f"PDF filling completed in {filling_time:.2f} seconds.")

                total_time = time.time() - overall_start_time
                print(f"Overall processing completed in {total_time:.2f} seconds.")
                print(f"Output PDF saved to: {output_pdf_path}")

            except Exception as e:
                print(f"Error during intelligent field mapping: {e}")
                print("Processing could not be completed.")

        except Exception as e:
            print(f"Error during PDF processing: {e}")
            print(f"Processing failed for {input_pdf_path}")

    async def _fill_pdf_with_ai_positions(
            self,
            input_pdf_path: str,
            output_pdf_path: str,
            field_matches: List[Dict[str, Any]],
            field_positions: List[Dict[str, Any]]
    ):
        """
        Replace placeholders in PDF with values from field_matches using positions from field_positions.
        """
        print(f"Starting PDF placeholder replacement with {len(field_matches)} values...")

        try:

            input_pdf_path = os.path.abspath(input_pdf_path)
            output_pdf_path = os.path.abspath(output_pdf_path)

            # Create a temporary path in a different location (not derived from input_path)
            temp_dir = os.path.dirname(output_pdf_path)
            temp_filename = f"temp_{os.path.basename(input_pdf_path)}"
            temp_path = os.path.join(temp_dir, temp_filename)
            if temp_path == input_pdf_path or temp_path == output_pdf_path:
                temp_path = os.path.join(temp_dir, f"temp2_{os.path.basename(input_pdf_path)}")

                # Copy the input PDF to the temp file
            shutil.copy(input_pdf_path, temp_path)

            doc = fitz.open(temp_path)
            print(f"Opened PDF with {len(doc)} pages")

            replacement_map = {}
            for match in field_matches:
                pdf_field = match['pdf_field']
                value = match['suggested_value']
                replacement_map[pdf_field] = value

                if not (pdf_field.startswith('(') and pdf_field.endswith(')')):
                    placeholder = f"({pdf_field})"
                    replacement_map[placeholder] = value
                    print(f"Created mapping for: {placeholder} -> {value}")
                else:
                    print(f"Mapping placeholder: {pdf_field} -> {value}")

            replacement_count = 0

            all_replacements = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                print(f"First pass - analyzing page {page_num + 1}")

                text_instances = page.get_text("dict")

                page_replacements = []

                for block in text_instances.get("blocks", []):
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            original_text = span["text"]
                            rect = fitz.Rect(span["bbox"])

                            if rect.width < 2 or rect.height < 2:
                                continue

                            placeholder_found = False
                            replacement_text = original_text

                            for pattern, replacement in replacement_map.items():
                                if pattern in original_text:
                                    replacement_text = replacement_text.replace(pattern, replacement)
                                    placeholder_found = True

                            if not placeholder_found:
                                placeholder_pattern = r'\((.*?)\)'
                                matches = re.findall(placeholder_pattern, original_text)
                                for match in matches:
                                    placeholder = f"({match})"
                                    if placeholder in replacement_map:
                                        replacement_text = replacement_text.replace(
                                            placeholder, replacement_map[placeholder]
                                        )
                                        placeholder_found = True

                            if placeholder_found and replacement_text != original_text:
                                padding = 8
                                redact_rect = fitz.Rect(
                                    rect.x0 - padding,
                                    rect.y0 - padding,
                                    rect.x1 + padding,
                                    rect.y1 + padding
                                )

                                page_replacements.append({
                                    'rect': redact_rect,
                                    'new_text': replacement_text,
                                    'font_size': span.get("size", 11),
                                    'text_origin': (rect.x0, rect.y0),
                                    'original_text': original_text
                                })
                                print(f"Found text to replace: '{original_text}' -> '{replacement_text}'")

                for position in field_positions:
                    field_name = position.get('field_name')
                    pos_page_num = position.get('page', 0)

                    if pos_page_num == page_num:
                        matching_field = next((m for m in field_matches if m['pdf_field'] == field_name), None)

                        if matching_field:
                            value = matching_field['suggested_value']
                            coords = position.get('coordinates', {})
                            x = coords.get('x', 0)
                            y = coords.get('y', 0)
                            formatting = position.get('formatting', {})
                            font_size = formatting.get('font_size', 11)
                            alignment = formatting.get('alignment', 'left')
                            max_width = position.get('max_width', 200)

                            position_rect = fitz.Rect(
                                x - 5,
                                y - font_size - 5,
                                x + max_width + 5,
                                y + 5
                            )

                            page_replacements.append({
                                'rect': position_rect,
                                'new_text': value,
                                'font_size': font_size,
                                'text_origin': (x, y),
                                'alignment': alignment,
                                'max_width': max_width,
                                'is_position': True
                            })
                            print(f"Found position for field '{field_name}' at ({x}, {y})")

                if page_replacements:
                    all_replacements.append({
                        'page_num': page_num,
                        'replacements': page_replacements
                    })

            for page_data in all_replacements:
                page_num = page_data['page_num']
                page = doc[page_num]
                print(f"Second pass - processing page {page_num + 1}")

                new_page = doc.new_page(page_num + 1, width=page.rect.width, height=page.rect.height)
                new_page.show_pdf_page(new_page.rect, doc, page_num)

                doc.delete_page(page_num)

                page = doc[page_num]

                replacements = page_data['replacements']

                grouped_rects = []
                for repl in replacements:
                    rect = repl['rect']
                    added_to_group = False

                    for group in grouped_rects:

                        for existing_rect in group:
                            if (rect.x0 < existing_rect.x1 and rect.x1 > existing_rect.x0 and
                                    rect.y0 < existing_rect.y1 and rect.y1 > existing_rect.y0):
                                group.append(rect)
                                added_to_group = True
                                break
                        if added_to_group:
                            break

                    if not added_to_group:
                        grouped_rects.append([rect])

                merged_rects = []
                for group in grouped_rects:
                    if len(group) == 1:
                        merged_rects.append(group[0])
                    else:

                        x0 = min(r.x0 for r in group)
                        y0 = min(r.y0 for r in group)
                        x1 = max(r.x1 for r in group)
                        y1 = max(r.y1 for r in group)
                        merged_rects.append(fitz.Rect(x0, y0, x1, y1))

                for rect in merged_rects:
                    page.add_redact_annot(rect, fill=(1, 1, 1))

                page.apply_redactions()
                print(f"Applied {len(merged_rects)} redaction areas on page {page_num + 1}")

                for repl in replacements:
                    if repl.get('is_position', False):

                        value = repl['new_text']
                        x = repl['text_origin'][0]
                        y = repl['text_origin'][1]
                        font_size = repl['font_size']
                        alignment = repl.get('alignment', 'left')
                        max_width = repl.get('max_width', 200)

                        if alignment == 'center':
                            page.insert_text(
                                (x + max_width / 2, y),
                                value,
                                fontname="helv",
                                fontsize=font_size,
                                align=1
                            )
                        elif alignment == 'right':
                            page.insert_text(
                                (x + max_width, y),
                                value,
                                fontname="helv",
                                fontsize=font_size,
                                align=2
                            )
                        else:
                            page.insert_text(
                                (x, y),
                                value,
                                fontsize=font_size,
                                fontname="helv"
                            )
                    else:

                        x, y = repl['text_origin']
                        new_text = repl['new_text']
                        font_size = repl['font_size']

                        page.insert_text(
                            point=(x, y + font_size * 0.8),
                            text=new_text,
                            fontname="helv",
                            fontsize=font_size
                        )

                    replacement_count += 1

            doc.save(output_pdf_path)
            doc.close()

            # Remove the temporary file
            try:
                os.remove(temp_path)
            except Exception as e:
                print(f"Warning: Could not remove temp file {temp_path}: {e}")

            print(f"Successfully replaced {replacement_count} placeholders")
            print(f"Filled PDF saved to: {output_pdf_path}")

        except Exception as e:
            print(f"Error during PDF placeholder replacement: {e}")
            traceback.print_exc()
            raise

    def _detect_form_fields(self, page):
        """
        Detect form fields on a page based on visual characteristics.

        Args:
            page: PDF page object

        Returns:
            List of rectangles representing form fields
        """
        form_fields = []

        # Method 1: Look for underscores that might indicate input fields
        text = page.get_text("dict")
        for block in text.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text_content = span["text"]
                    # Check for form field indicators
                    if "_" * 3 in text_content or "□" in text_content or "■" in text_content:
                        form_fields.append(fitz.Rect(span["bbox"]))
                    # Check for placeholders in parentheses
                    if "(" in text_content and ")" in text_content:
                        placeholder_pattern = r'\((.*?)\)'
                        if re.search(placeholder_pattern, text_content):
                            form_fields.append(fitz.Rect(span["bbox"]))

        # Method 2: Look for rectangles that might be form field boxes
        # This uses the page's drawing content to identify boxes
        paths = page.get_drawings()
        for path in paths:
            for item in path["items"]:
                if item[0] == "re":  # Rectangle
                    rect = item[1]  # Rectangle coordinates
                    # Filter for rectangles that are likely to be form fields
                    # These are usually wider than they are tall and not too big
                    width = rect[2] - rect[0]
                    height = rect[3] - rect[1]
                    if 20 < width < 300 and 5 < height < 40:
                        form_fields.append(fitz.Rect(rect))

        # Method 3: Look for areas around placeholder text
        for block in text.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text_content = span["text"]
                    if "(" in text_content and ")" in text_content:
                        span_rect = fitz.Rect(span["bbox"])
                        # Expand the rectangle a bit to ensure we cover the full field
                        expanded_rect = fitz.Rect(
                            span_rect.x0 - 5,
                            span_rect.y0 - 2,
                            span_rect.x1 + 5,
                            span_rect.y1 + 2
                        )
                        form_fields.append(expanded_rect)

        return form_fields

    def _rect_overlap(self, rect1, rect2):
        """
        Check if two rectangles overlap.

        Args:
            rect1: First rectangle
            rect2: Second rectangle

        Returns:
            Boolean indicating if the rectangles overlap
        """
        # Two rectangles overlap if one rectangle's left edge is to the left of the other's right edge,
        # and one rectangle's top edge is above the other's bottom edge.
        return (
                rect1.x0 < rect2.x1 and
                rect1.x1 > rect2.x0 and
                rect1.y0 < rect2.y1 and
                rect1.y1 > rect2.y0
        )


class ImportantOutputInfo(BaseModel):
    """Defines the expected structure for output information"""
    model_config = ConfigDict(extra='forbid')

    filled_fields: List[Dict[str, Any]] = []
    failed_fields: List[Dict[str, Any]] = []
    processing_time: float = 0.0
    ocr_results_count: int = 0
    field_matches_count: int = 0
    placeholder_count: int = 0

    @field_validator('filled_fields', 'failed_fields')
    def validate_fields(cls, v):
        """Validate field lists"""
        for field in v:
            if not isinstance(field, dict):
                raise ValueError("Each field must be a dictionary")
        return v


async def main():
    """
    Main function for PDF filling workflow with detailed logging
    """
    print("Starting FillerGEN workflow...")

    try:
        # Example usage paths
        input_pdf_path = "D:\\demo\\Services\\MIchiganCorp.pdf"
        output_pdf_path = "D:\\demo\\Services\\fill_smart5.pdf"
        json_data_path = "D:\\demo\\Services\\form_data.json"

        # Check files exist
        if not os.path.exists(input_pdf_path):
            print(f"Error: Input PDF not found at {input_pdf_path}")
            return

        if not os.path.exists(json_data_path):
            print(f"Error: JSON data not found at {json_data_path}")
            return

        # Load JSON data
        with open(json_data_path, 'r') as f:
            json_data = json.load(f)

        # Initialize filler
        filler = PDFSmartFiller()

        # Process PDF
        await filler.process_pdf(
            input_pdf_path=input_pdf_path,
            json_data=json_data,
            output_pdf_path=output_pdf_path
        )

        print("FillerGEN workflow completed successfully")

    except Exception as e:
        print(f"Error in FillerGEN workflow: {e}")


if __name__ == "__main__":
    asyncio.run(main())