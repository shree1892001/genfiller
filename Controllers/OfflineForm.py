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

from Services.GenericFiller import MultiAgentFormFiller as StandardFormFiller
from Services.GenFiler import MultiAgentFormFiller as OCRFormFiller

app = FastAPI(title="Smart PDF Form Filler API",
              description="API for intelligent PDF form filling with automatic OCR detection")

origins = ['*']
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        """Advanced form field analysis with improved OCR detection logic"""
        try:
            doc = fitz.open(pdf_path)
            fields = []
            total_interactive_fields = 0
            total_pages = len(doc)

            filled_fields = 0
            empty_fields = 0

            for page in doc:
                for widget in page.widgets():
                    if widget.field_name:
                        total_interactive_fields += 1
                        field_value = widget.field_value

                        if field_value:
                            filled_fields += 1
                        else:
                            empty_fields += 1

                        fields.append({
                            'name': widget.field_name,
                            'type': widget.field_type,
                            'value': field_value
                        })

            doc.close()

            needs_ocr = (
                total_interactive_fields == 0 or
                (total_pages > 2 and total_interactive_fields < 3) or
                (total_interactive_fields > 0 and empty_fields == total_interactive_fields)
            )

            print(f"OCR Detection Analysis: pages={total_pages}, fields={total_interactive_fields}, "
                  f"filled={filled_fields}, empty={empty_fields}, needs_ocr={needs_ocr}")

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

                print(f"Processing form request: filename={pdf_file.filename}, force_ocr={force_ocr}")

                temp_input_path = TemporaryFileManager.generate_unique_filename(
                    prefix="temp_input_", extension=".pdf"
                )
                output_path = TemporaryFileManager.generate_unique_filename(
                    prefix="filled_", extension=".pdf"
                )

                with open(temp_input_path, "wb") as f:
                    content = await pdf_file.read()
                    f.write(content)

                json_data = json.loads(form_data)

                needs_ocr, fields = await PDFProcessingService.analyze_form_fields(temp_input_path)

                final_ocr_decision = needs_ocr or force_ocr

                print(f"Final OCR decision: auto_detect={needs_ocr}, force_ocr={force_ocr}, "
                      f"using_ocr={final_ocr_decision}, fields_count={len(fields)}")

                form_filler = OCRFormFiller() if final_ocr_decision else StandardFormFiller()

                print(f"Selected form filler: {'OCR' if final_ocr_decision else 'Standard'}")

                result = await form_filler.match_and_fill_fields(
                    temp_input_path, json_data, output_path
                )

                if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                    raise ValueError("Failed to generate filled PDF")

                os.makedirs("filled_forms", exist_ok=True)
                permanent_path = os.path.join(
                    "filled_forms",
                    TemporaryFileManager.generate_unique_filename(
                        prefix="filled_", extension=".pdf"
                    )
                )
                shutil.copy2(output_path, permanent_path)

                print(f"Form successfully filled: output={permanent_path}")

                field_matches = [
                    FieldMatch(
                        json_field="processed_form",
                        pdf_field="system_confirmation",
                        confidence=1.0,
                        suggested_value=True,
                        reasoning="Successful form processing"
                    )
                ]

                background_tasks.add_task(TemporaryFileManager.cleanup_file, temp_input_path)
                background_tasks.add_task(TemporaryFileManager.cleanup_file, output_path)

                if return_json:
                    return FormResponse(
                        status="success",
                        message="Form processed successfully",
                        requires_ocr=final_ocr_decision,
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

                error_msg = str(e)
                print(f"Form processing error: {error_msg}")

                error_response = FormResponse(
                    status="error",
                    message=f"Processing failed: {error_msg}",
                    error_details=error_msg,
                    requires_ocr=False
                )

                for path in [temp_input_path, output_path]:
                    if path and os.path.exists(path):
                        background_tasks.add_task(TemporaryFileManager.cleanup_file, path)

                raise HTTPException(status_code=500, detail=error_response.dict())

    def get_app(self):
        return self.app

pdf_form_filler_api = PDFFormFillerAPI()
app = pdf_form_filler_api.get_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)