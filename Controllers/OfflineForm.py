import asyncio
import json
import os
import shutil
import uuid
from typing import Dict, Any, List, Optional
import fitz
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Custom Form Filler Services
from Services.GenericFiller import MultiAgentFormFiller as StandardFormFiller
from Services.GenFiler import MultiAgentFormFiller as OCRFormFiller


class FieldMatch(BaseModel):
    json_field: str = Field(..., description="Field from input JSON")
    pdf_field: str = Field(..., description="Corresponding PDF form field")
    confidence: float = Field(..., ge=0, le=1, description="Matching confidence")
    suggested_value: Any = Field(None, description="Value suggested for the field")
    reasoning: str = Field(None, description="Reasoning behind the match")


class FormResponse(BaseModel):
    status: str = Field(..., description="Processing status")
    message: str = Field(..., description="Detailed processing message")
    requires_ocr: bool = Field(False, description="Whether OCR was required")
    file_path: Optional[str] = Field(None, description="Path to processed file")
    field_matches: List[FieldMatch] = Field(default_factory=list, description="Field matching details")
    error_details: Optional[str] = Field(None, description="Error details if processing failed")


class PDFProcessingService:
    @staticmethod
    async def analyze_form_fields(pdf_path: str) -> tuple[bool, list]:
        """Advanced form field analysis with comprehensive detection"""
        try:
            doc = fitz.open(pdf_path)
            fields = []
            total_interactive_fields = 0

            for page in doc:
                for widget in page.widgets():
                    if widget.field_name:
                        total_interactive_fields += 1
                        fields.append({
                            'name': widget.field_name,
                            'type': widget.field_type,
                            'value': widget.field_value
                        })

            doc.close()

            # Sophisticated OCR need detection
            needs_ocr = (
                    total_interactive_fields < 3 or
                    any(len(field['name']) > 30 for field in fields)
            )

            return needs_ocr, fields

        except Exception as e:
            print(f"Field analysis error: {e}")
            return True, []


class TemporaryFileManager:
    @staticmethod
    def generate_unique_filename(prefix: str = "", extension: str = "") -> str:
        """Generate a unique filename with optional prefix and extension"""
        unique_id = str(uuid.uuid4())
        return f"{prefix}{unique_id}{extension}"

    @staticmethod
    def cleanup_file(file_path: str):
        """Safe file cleanup with error handling"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Cleaned up file: {file_path}")
        except Exception as e:
            print(f"File cleanup error for {file_path}: {e}")


class PDFFormFillerAPI:
    def __init__(self):
        self.app = FastAPI(
            title="Intelligent PDF Form Filler API",
            description="Advanced API for intelligent PDF form processing"
        )

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"]
        )

        self.setup_routes()

    def setup_routes(self):
        @self.app.post("/api/process-form", response_model=FormResponse)
        async def process_form(
                pdf_file: UploadFile = File(...),
                form_data: str = Form(...),
                force_ocr: bool = Form(False),
                return_json: bool = Form(False),
                background_tasks: BackgroundTasks = BackgroundTasks()
        ):
            temp_input_path = ""
            output_path = ""
            permanent_path = ""

            try:
                # Generate unique filenames
                temp_input_path = TemporaryFileManager.generate_unique_filename(
                    prefix="temp_input_", extension=".pdf"
                )
                output_path = TemporaryFileManager.generate_unique_filename(
                    prefix="filled_", extension=".pdf"
                )

                # Save input PDF
                with open(temp_input_path, "wb") as f:
                    content = await pdf_file.read()
                    f.write(content)

                # Parse form data
                json_data = json.loads(form_data)

                # Analyze form structure
                needs_ocr, fields = await PDFProcessingService.analyze_form_fields(temp_input_path)
                needs_ocr = needs_ocr or force_ocr

                # Select appropriate form filler
                form_filler = OCRFormFiller() if needs_ocr else StandardFormFiller()

                # Process form
                result = await form_filler.match_and_fill_fields(
                    temp_input_path, json_data, output_path
                )

                # Ensure output file exists
                if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                    raise ValueError("Failed to generate filled PDF")

                # Create permanent storage
                os.makedirs("filled_forms", exist_ok=True)
                permanent_path = os.path.join(
                    "filled_forms",
                    TemporaryFileManager.generate_unique_filename(
                        prefix="filled_", extension=".pdf"
                    )
                )
                shutil.copy2(output_path, permanent_path)

                # Prepare field matches
                field_matches = [
                    FieldMatch(
                        json_field="processed_form",
                        pdf_field="system_confirmation",
                        confidence=1.0,
                        suggested_value=True,
                        reasoning="Successful form processing"
                    )
                ]

                # Schedule cleanup tasks
                background_tasks.add_task(TemporaryFileManager.cleanup_file, temp_input_path)
                background_tasks.add_task(TemporaryFileManager.cleanup_file, output_path)

                # Return response based on return_json flag
                if return_json:
                    return FormResponse(
                        status="success",
                        message="Form processed successfully",
                        requires_ocr=needs_ocr,
                        file_path=permanent_path,
                        field_matches=field_matches
                    )
                else:
                    return FileResponse(
                        path=permanent_path,
                        filename=f"filled_{pdf_file.filename}",
                        media_type="application/pdf"
                    )

            except Exception as e:
                # Comprehensive error handling
                error_response = FormResponse(
                    status="error",
                    message=f"Processing failed: {str(e)}",
                    error_details=str(e),
                    requires_ocr=False
                )

                # Cleanup in case of error
                for path in [temp_input_path, output_path, permanent_path]:
                    TemporaryFileManager.cleanup_file(path)

                raise HTTPException(status_code=500, detail=error_response.dict())

    def get_app(self):
        return self.app


# API Initialization
pdf_form_filler_api = PDFFormFillerAPI()
app = pdf_form_filler_api.get_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)