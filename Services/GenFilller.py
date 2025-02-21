import asyncio
import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from PyPDF2 import PdfReader
from fillpdf import fillpdfs
from pydantic import BaseModel, field_validator
from pydantic_ai import Agent
from pydantic_ai.models.gemini import GeminiModel
from Common.constants import  *


class PDFField(BaseModel):
    name: str
    type: str
    editable: bool
    options: Optional[List[str]] = None
    required: bool = False
    rect: Optional[List[float]] = None
    page: Optional[int] = None


class FieldMatch(BaseModel):
    json_field: str
    pdf_field: str
    confidence: float
    suggested_value: Any
    field_type: str
    editable: bool
    reasoning: str

    @field_validator('confidence')
    def validate_confidence(cls, v):
        if not (0 <= v <= 1):
            raise ValueError("Confidence must be between 0 and 1")
        return float(v)


class ProcessingResult(BaseModel):
    status: str
    matches: List[FieldMatch]
    unmatched_fields: List[str]
    success_rate: float
    execution_time: float
    non_editable_fields: List[str]


class FormProcessingError(Exception):
    """Custom exception for form processing errors"""
    pass


class IntelligentFormFiller:
    def __init__(self, api_key: str):
        self.agent = Agent(
            model=GeminiModel("gemini-1.5-flash", api_key=api_key),
            system_prompt="""You are an expert at intelligent form field matching, focusing on semantic understanding and context. 
            Pay special attention to field types, positions, and relationships between fields."""
        )
        self.processing_history = []

    def extract_pdf_fields(self, pdf_path: str) -> List[PDFField]:
        fields = []
        reader = PdfReader(pdf_path)

        for page_num, page in enumerate(reader.pages):
            if '/Annots' in page:
                for annot in page['/Annots']:
                    if isinstance(annot, dict):
                        obj = annot
                    else:
                        obj = annot.get_object()

                    if obj.get('/Subtype') == '/Widget':
                        field = self._process_pdf_field(obj, page_num)
                        if field:
                            fields.append(field)
        return fields

    def _process_pdf_field(self, field_obj: Dict, page_num: int) -> Optional[PDFField]:
        try:
            field_name = field_obj.get('/T', '')
            if not field_name:
                field_name = field_obj.get('/TU', '')
            if not field_name:
                return None

            field_type = field_obj.get('/FT', '/Tx')
            appearance = field_obj.get('/AP', {})
            flags = field_obj.get('/Ff', 0)

            mapped_type = self._determine_field_type(field_type, appearance, flags)
            rect = field_obj.get('/Rect', [0, 0, 0, 0])
            editable = not bool(flags & 1)
            required = bool(flags & 2)

            options = None
            if mapped_type in ('select', 'radio', 'checkbox'):
                opt = field_obj.get('/Opt', [])
                options = [o if isinstance(o, str) else o[1] for o in opt]

            return PDFField(
                name=field_name,
                type=mapped_type,
                editable=editable,
                options=options,
                required=required,
                rect=rect,
                page=page_num
            )
        except Exception as e:
            print(f"Error processing field {field_obj.get('/T', 'unknown')}: {str(e)}")
            return None

    def _determine_field_type(self, field_type: str, appearance: Dict, flags: int) -> str:
        base_type = {
            '/Tx': 'text',
            '/Btn': 'checkbox',
            '/Ch': 'select',
            '/Sig': 'signature'
        }.get(field_type, 'text')

        if base_type == 'text':
            if flags & (1 << 12):
                return 'textarea'
            if flags & (1 << 13):
                return 'password'
            return 'text'

        if base_type == 'checkbox':
            if flags & (1 << 15):
                return 'radio'
            return 'checkbox'

        return base_type

    def flatten_json(self, data: Dict[str, Any], prefix: str = '') -> Dict[str, Any]:
        items = {}
        for key, value in data.items():
            new_key = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                items.update(self.flatten_json(value, new_key))
            elif isinstance(value, (list, tuple)):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        items.update(self.flatten_json(item, f"{new_key}[{i}]"))
                    else:
                        items[f"{new_key}[{i}]"] = item
            else:
                items[new_key] = value
        return items

    def _clean_agent_response(self, response: str) -> str:
        """Clean up the agent's response to ensure valid JSON"""
        response = response.strip()

        if "```json" in response:
            response = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            response = response.split("```")[1]

        response = response.strip()

        start_idx = response.find('{')
        if start_idx != -1:
            response = response[start_idx:]

        end_idx = response.rfind('}')
        if end_idx != -1:
            response = response[:end_idx + 1]

        return response

    def preprocess_value(self, value: Any, field_type: str, options: Optional[List[str]] = None) -> str:
        if value is None:
            return ""

        if field_type == 'checkbox':
            return "Yes" if str(value).lower() in ('true', 'yes', '1', 'on') else "Off"

        if field_type == 'radio' and options:
            value_str = str(value).lower()
            for option in options:
                if option.lower() == value_str:
                    return option
            return options[0] if options else ""

        if field_type == 'select' and options:
            value_str = str(value).lower()
            matches = [opt for opt in options if opt.lower() == value_str]
            return matches[0] if matches else options[0] if options else ""

        if isinstance(value, (int, float)):
            return f"{value:,}"

        return str(value).strip()

    async def match_fields(self, json_data: Dict[str, Any], pdf_fields: List[PDFField]) -> Dict[str, Any]:
        flat_json = self.flatten_json(json_data)

        # Prepare detailed field information for the agent
        pdf_fields_data = [{
            'name': f.name,
            'type': f.type,
            'editable': f.editable,
            'options': f.options,
            'required': f.required,
            'page': f.page,
            'position': f.rect,
            'metadata': {
                'is_signature_field': f.type == 'signature',
                'has_options': bool(f.options),
                'field_length': len(f.name)
            }
        } for f in pdf_fields]

        try:
            response = await self.agent.run(
                FIELD_MATCHING_PROMPT1.format(
                    json_data=json.dumps(flat_json, indent=2),
                    pdf_fields=json.dumps(pdf_fields_data, indent=2)
                )
            )

            clean_response = self._clean_agent_response(response.data)
            result = json.loads(clean_response)

            return self._validate_matches(result, pdf_fields, flat_json)

        except Exception as e:
            print(f"Error in field matching: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return {"matches": []}

    def _validate_matches(self, result: Dict[str, Any], pdf_fields: List[PDFField], json_data: Dict[str, Any]) -> Dict[
        str, Any]:
        pdf_field_dict = {f.name: f for f in pdf_fields}
        valid_matches = []

        # Include all fields from PDF that don't have matches
        pdf_field_names = set(pdf_field_dict.keys())
        matched_pdf_fields = {match.get("pdf_field") for match in result.get("matches", [])}
        unmatched_pdf_fields = pdf_field_names - matched_pdf_fields

        # Add empty matches for unmatched PDF fields
        for unmatched_field in unmatched_pdf_fields:
            pdf_field = pdf_field_dict[unmatched_field]
            valid_matches.append({
                "json_field": "",
                "pdf_field": unmatched_field,
                "confidence": 0.0,
                "suggested_value": "",
                "field_type": pdf_field.type,
                "editable": pdf_field.editable,
                "reasoning": "Unmatched PDF field"
            })

        # Process existing matches
        for match in result.get("matches", []):
            try:
                pdf_field_name = match.get("pdf_field")
                if pdf_field_name in pdf_field_dict:
                    pdf_field = pdf_field_dict[pdf_field_name]

                    suggested_value = match.get("suggested_value")
                    if suggested_value is not None:
                        match["suggested_value"] = self.preprocess_value(
                            suggested_value,
                            pdf_field.type,
                            pdf_field.options
                        )

                    valid_matches.append(match)
            except Exception as e:
                print(f"Validation error: {str(e)}")
                continue

        result["matches"] = valid_matches
        return result

    async def process_form(self, template_pdf: str, json_data: Dict[str, Any], output_pdf: str) -> ProcessingResult:
        start_time = datetime.now()

        try:
            print(f"\n📄 Processing PDF: {template_pdf}")
            pdf_fields = self.extract_pdf_fields(template_pdf)

            print("\n🤖 AI Field Matching...")
            result = await self.match_fields(json_data, pdf_fields)

            valid_matches = [FieldMatch(**match) for match in result["matches"]]

            # Sort matches by confidence, but include all
            valid_matches.sort(key=lambda x: x.confidence, reverse=True)

            fill_data = {}
            non_editable = []

            # Process all matches, regardless of confidence
            for match in valid_matches:
                if match.editable:
                    # Include empty values as well
                    fill_data[match.pdf_field] = match.suggested_value or ""
                else:
                    non_editable.append(match.pdf_field)

            if fill_data:
                print(f"\n📝 Filling {len(fill_data)} fields...")
                fillpdfs.write_fillable_pdf(template_pdf, output_pdf, fill_data)

            flat_json = self.flatten_json(json_data)
            matched_fields = {match.json_field for match in valid_matches if match.json_field}
            unmatched = [f for f in flat_json.keys() if f not in matched_fields]

            # Calculate success rate based on matched JSON fields
            success_rate = (len(matched_fields) / len(flat_json)) * 100 if flat_json else 0

            result = ProcessingResult(
                status="success",
                matches=valid_matches,
                unmatched_fields=unmatched,
                success_rate=success_rate,
                execution_time=(datetime.now() - start_time).total_seconds(),
                non_editable_fields=non_editable
            )

            self.processing_history.append(result)
            return result

        except Exception as e:
            print(f"Processing error: {str(e)}")
            return ProcessingResult(
                status="error",
                matches=[],
                unmatched_fields=list(self.flatten_json(json_data).keys()),
                success_rate=0,
                execution_time=(datetime.now() - start_time).total_seconds(),
                non_editable_fields=[]
            )

    async def run(self, template_pdf: str, json_path: str, output_pdf: str) -> Optional[ProcessingResult]:
        try:
            print("\n🚀 Starting Form Processing...")

            if not os.path.exists(template_pdf):
                raise FileNotFoundError(f"Template PDF not found: {template_pdf}")
            if not os.path.exists(json_path):
                raise FileNotFoundError(f"JSON file not found: {json_path}")

            with open(json_path, 'r') as f:
                json_data = json.load(f)

            result = await self.process_form(template_pdf, json_data, output_pdf)

            print(f"\n📊 Results Summary:")
            print(f"Status: {result.status}")
            print(f"Success Rate: {result.success_rate:.1f}%")
            print(f"Processing Time: {result.execution_time:.2f}s")

            # Group matches by confidence level
            high_confidence = []
            medium_confidence = []
            low_confidence = []
            unmatched = []

            for match in result.matches:
                if match.confidence >= 0.8:
                    high_confidence.append(match)
                elif match.confidence >= 0.5:
                    medium_confidence.append(match)
                elif match.confidence > 0:
                    low_confidence.append(match)
                else:
                    unmatched.append(match)

            print("\n✅ High Confidence Matches:")
            for match in high_confidence:
                print(f"\n• {match.pdf_field}")
                print(f"  Value: {match.suggested_value}")
                print(f"  Confidence: {match.confidence:.2f}")

            print("\n📋 Medium Confidence Matches:")
            for match in medium_confidence:
                print(f"\n• {match.pdf_field}")
                print(f"  Value: {match.suggested_value}")
                print(f"  Confidence: {match.confidence:.2f}")

            print("\n⚠️ Low Confidence Matches:")
            for match in low_confidence:
                print(f"\n• {match.pdf_field}")
                print(f"  Value: {match.suggested_value}")
                print(f"  Confidence: {match.confidence:.2f}")

            print("\n❌ Unmatched Fields:")
            for match in unmatched:
                print(f"• {match.pdf_field}")

            if result.non_editable_fields:
                print("\n🔒 Non-Editable Fields:")
                for field in result.non_editable_fields:
                    print(f"• {field}")

            print(f"\n💾 Output: {output_pdf}")
            return result

        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return None

async def main():
      # Replace with your actual API key
    form_filler = IntelligentFormFiller(API_KEY)

    template_pdf = "D:\\demo\\Services\\California_LLC.pdf"
    json_path = "D:\\demo\\Services\\form_data.json"
    output_pdf = "D:\\demo\\Services\\filled_form6.pdf"

    try:
        result = await form_filler.run(template_pdf, json_path, output_pdf)
        print(f"\nTotal forms processed: {len(form_filler.processing_history)}")
        return result
    except Exception as e:
        print(f"Error in main: {str(e)}")
        return None


if __name__ == "__main__":
    asyncio.run(main())