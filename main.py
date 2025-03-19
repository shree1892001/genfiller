import fitz  # PyMuPDF
import ocrmypdf
import json
import os
import shutil
import logging
from typing import Dict, Any, List, Tuple
import asyncio
from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent
from pydantic_ai.models.gemini import GeminiModel
from concurrent.futures import ThreadPoolExecutor
from Common.constants import *

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('form_filler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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

class PDFEncoder(json.JSONEncoder):
    """Custom JSON encoder for PDF-specific objects."""
    def default(self, obj):
        if hasattr(obj, 'tolist'):
            return obj.tolist()
        elif isinstance(obj, fitz.Rect):
            return [obj.x0, obj.y0, x1, y1] = list(obj)
            return [x0, y0, x1, y1]
        return super().default(obj)

class MultiAgentFormFiller:
    def __init__(self):
        self.ai_agent = Agent(
            model=GeminiModel("gemini-1.5-flash", api_key=API_KEY_3),
            system_prompt="""You are an expert at PDF form processing and field matching.
            Focus on matching fields accurately based on field names, types, and context.
            Only provide high-confidence matches with clear reasoning."""
        )
        self.thread_pool = ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 1) * 4))

    def __del__(self):
        if hasattr(self, 'thread_pool'):
            self.thread_pool.shutdown(wait=True)

    async def process_pdf(self, pdf_path: str, json_data: Dict[str, Any], output_pdf: str) -> bool:
        """Process PDF form using AI-driven analysis and filling."""
        try:
            logger.info(f"Starting PDF processing: {pdf_path}")
            
            # Create backup
            backup_pdf = f"{pdf_path}.backup"
            shutil.copy2(pdf_path, backup_pdf)
            logger.info(f"Created backup: {backup_pdf}")

            # Extract PDF fields
            pdf_fields = await self.extract_pdf_fields(pdf_path)
            if not pdf_fields:
                logger.error("No PDF fields found")
                return False

            # Process fields in batches
            all_matches = []
            field_batches = self.create_field_batches(pdf_fields, json_data, batch_size=5)
            
            for batch_num, (pdf_batch, json_batch) in enumerate(field_batches, 1):
                logger.info(f"Processing batch {batch_num}")
                batch_matches = await self.process_field_batch(pdf_batch, json_batch)
                if batch_matches:
                    all_matches.extend(batch_matches)

            if not all_matches:
                logger.warning("No valid matches found in any batch")
                return False

            logger.info(f"Found {len(all_matches)} total matches")

            # Fill the form
            success = await self.fill_form(pdf_path, output_pdf, all_matches)
            return success

        except Exception as e:
            logger.error(f"Error in process_pdf: {str(e)}", exc_info=True)
            return False

    async def extract_pdf_fields(self, pdf_path: str) -> Dict[str, Dict]:
        """Extract fields from PDF with error handling."""
        try:
        doc = fitz.open(pdf_path)
        fields = {}

            for page_num in range(len(doc)):
                page = doc[page_num]
            for widget in page.widgets():
                if widget.field_name:
                        fields[widget.field_name] = {
                            "page_num": page_num,
                            "type": widget.field_type,
                            "rect": list(widget.rect),
                            "value": widget.field_value
                        }
            
            doc.close()
            logger.info(f"Extracted {len(fields)} fields from PDF")
            return fields
            
        except Exception as e:
            logger.error(f"Error extracting PDF fields: {str(e)}", exc_info=True)
            return {}

    def create_field_batches(self, pdf_fields: Dict, json_data: Dict, batch_size: int) -> List[Tuple[Dict, Dict]]:
        """Create batches of fields for processing."""
        batches = []
        pdf_items = list(pdf_fields.items())
        json_items = list(json_data.items())
        
        for i in range(0, len(pdf_items), batch_size):
            pdf_batch = dict(pdf_items[i:i + batch_size])
            json_batch = dict(json_items[i:i + batch_size])
            batches.append((pdf_batch, json_batch))
        
        return batches

    async def process_field_batch(self, pdf_fields: Dict, json_data: Dict) -> List[Dict]:
        """Process a batch of fields."""
        try:
            prompt = f"""Analyze and match these PDF form fields with JSON data.
            
PDF FIELDS:
{json.dumps(pdf_fields, indent=2)}

        JSON DATA:
{json.dumps(json_data, indent=2)}

Match fields based on:
1. Field name similarity
2. Field type compatibility
3. Expected value format

Respond with ONLY a JSON array of matches in this format:
[
    {{
        "json_field": "exact_json_field_name",
        "pdf_field": "exact_pdf_field_name",
        "value": "formatted_value",
                    "confidence": 0.95,
        "reasoning": "brief_explanation"
    }}
]"""

            logger.info("Requesting AI analysis for batch")
            response = await self.ai_agent.run(prompt)
            matches = self.parse_ai_response(response.data)
            
            if not matches:
                return []
                
            # Validate matches
            valid_matches = []
            for match in matches:
                if self.validate_match(match, pdf_fields, json_data):
                    valid_matches.append(match)
            
            logger.info(f"Found {len(valid_matches)} valid matches in batch")
            return valid_matches
            
        except Exception as e:
            logger.error(f"Error processing field batch: {str(e)}", exc_info=True)
            return []

    def validate_match(self, match: Dict, pdf_fields: Dict, json_data: Dict) -> bool:
        """Validate a single field match."""
        try:
            required_keys = ["json_field", "pdf_field", "value", "confidence", "reasoning"]
            if not all(key in match for key in required_keys):
                return False
                
            if not (0 <= match["confidence"] <= 1):
                return False

            if match["json_field"] not in json_data:
                return False
                
            if match["pdf_field"] not in pdf_fields:
                return False
                
            return True
            
        except Exception:
            return False

    def parse_ai_response(self, response: str) -> List[Dict]:
        """Parse AI response with enhanced error handling."""
        try:
            # Clean up response
            json_str = response.strip()
            
            # Extract JSON array
            start_idx = json_str.find("[")
            end_idx = json_str.rfind("]")
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = json_str[start_idx:end_idx + 1]
                
            # Remove markdown and parse
            json_str = json_str.replace("```json", "").replace("```", "")
            return json.loads(json_str)
            
        except Exception as e:
            logger.error(f"Error parsing AI response: {str(e)}")
            logger.debug(f"Raw response: {response[:200]}")
            return []

    async def fill_form(self, pdf_path: str, output_pdf: str, matches: List[Dict]) -> bool:
        """Fill PDF form with enhanced error handling."""
        temp_pdf = None
        doc = None
        
        try:
            # Create temporary output
            temp_pdf = f"{output_pdf}.temp"
            shutil.copy2(pdf_path, temp_pdf)
            
            doc = fitz.open(temp_pdf)
            filled_count = 0
            
            for match in matches:
                if match["confidence"] >= 0.85:
                    success = await self.fill_single_field(doc, match)
                    if success:
                        filled_count += 1
            
            if filled_count > 0:
                # Save with careful error handling
                try:
                    doc.save(temp_pdf, garbage=4, deflate=True, clean=True)
                    doc.close()
                    doc = None
                    shutil.move(temp_pdf, output_pdf)
                    logger.info(f"Successfully filled {filled_count} fields")
                    return True
                except Exception as e:
                    logger.error(f"Error saving PDF: {str(e)}", exc_info=True)
                    return False
            else:
                logger.warning("No fields were filled")
                return False

        except Exception as e:
            logger.error(f"Error filling form: {str(e)}", exc_info=True)
            return False
            
        finally:
            # Cleanup
            if doc:
                try:
                    doc.close()
                except:
                    pass
            if temp_pdf and os.path.exists(temp_pdf):
                try:
                    os.remove(temp_pdf)
                except:
                    pass

    async def fill_single_field(self, doc: fitz.Document, match: Dict) -> bool:
        """Fill a single form field with error handling."""
        try:
            for page in doc:
                for widget in page.widgets():
                    if widget.field_name == match["pdf_field"]:
                        widget.field_value = match["value"]
                        widget.update()
                        logger.info(f"Filled field {match['pdf_field']} = {match['value']}")
                        return True
            return False
        except Exception as e:
            logger.error(f"Error filling field {match['pdf_field']}: {str(e)}")
            return False

async def main():
    form_filler = MultiAgentFormFiller()
    template_pdf = "D:\\demo\\Services\\WisconsinLLC.pdf"
    json_path = "D:\\demo\\Services\\form_data.json"
    output_pdf = "D:\\demo\\Services\\fill_smart2.pdf"

    try:
        # Load JSON data
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)

        # Process the form
        success = await form_filler.process_pdf(template_pdf, json_data, output_pdf)

    if success:
            logger.info(f"PDF successfully processed: {output_pdf}")
    else:
            logger.error("PDF processing failed")

    except Exception as e:
        logger.error(f"Error during processing: {str(e)}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
