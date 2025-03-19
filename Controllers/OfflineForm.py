import asyncio
import json
import os
import shutil
from typing import Dict, Any, List
import fitz
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from Services.GenericFiller import MultiAgentFormFiller as StandardFormFiller
from Services.GenFiler import MultiAgentFormFiller as OCRFormFiller

app = FastAPI(title="Smart PDF Form Filler API",
              description="API for intelligent PDF form filling with automatic OCR detection")

class FieldMatch(BaseModel):
    json_field: str
    pdf_field: str
    confidence: float
    suggested_value: Any
    reasoning: str

class FormResponse(BaseModel):
    status: str
    message: str
    requires_ocr: bool
    field_matches: List[FieldMatch]

async def analyze_form_fields(pdf_path: str) -> tuple[bool, list]:
    """Analyze PDF form fields and determine if OCR is needed"""
    try:
        doc = fitz.open(pdf_path)
        fields = []

        for page in doc:
            for widget in page.widgets():
                if widget.field_name:
                    # Check if field name is a UUID-like string
                    if len(widget.field_name) > 30:
                        doc.close()
                        return True, []  # Needs OCR if field names are UUID-like
                    fields.append({
                        'name': widget.field_name,
                        'type': widget.field_type,
                        'value': widget.field_value
                    })

        doc.close()
        # Need OCR if no fields found or very few fields
        needs_ocr = len(fields) < 3
        return needs_ocr, fields
    except Exception as e:
        print(f"Error analyzing form fields: {e}")
        return True, []  # Default to OCR on error

def cleanup_temp_file(file_path: str):
    """Function to clean up temporary files after response is sent"""
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            print(f"Cleaned up temporary file: {file_path}")
        except Exception as e:
            print(f"Error cleaning up file {file_path}: {e}")

def cleanup_temp_files(input_path: str, output_path: str):
    """Clean up temporary files in case of errors"""
    for path in [input_path, output_path]:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

@app.post("/api/process-form")
async def process_form(
    pdf_file: UploadFile = File(...),
    form_data: str = Form(...),
    force_ocr: bool = Form(False),
    return_json: bool = Form(False),  # Optional parameter to return JSON instead of PDF
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Process PDF form with intelligent OCR detection and return the filled PDF"""
    temp_path = f"temp_{pdf_file.filename}"
    output_path = f"filled_{pdf_file.filename}"

    try:
        # Save uploaded PDF temporarily
        with open(temp_path, "wb") as f:
            content = await pdf_file.read()
            f.write(content)

        # Parse form data
        json_data = json.loads(form_data)

        # Analyze form structure
        needs_ocr, fields = await analyze_form_fields(temp_path)
        needs_ocr = needs_ocr or force_ocr

        # Select appropriate service
        form_filler = OCRFormFiller() if needs_ocr else StandardFormFiller()

        # Process form and get field matches
        result = await form_filler.match_and_fill_fields(temp_path, json_data, output_path)

        # Create field matches response
        field_matches = [
            FieldMatch(
                json_field="form_processed",
                pdf_field="system",
                confidence=1.0,
                suggested_value=True,
                reasoning="Form processed successfully"
            )
        ]

        # Ensure the output file exists by checking if our direct methods failed
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            # If there was an error during saving, the fallback might have created a different file
            # Try to find a file that matches our output pattern
            fallback_path = None
            directory = os.path.dirname(output_path) if os.path.dirname(output_path) else "."
            for file in os.listdir(directory):
                if file.startswith("filled_") and pdf_file.filename in file:
                    fallback_path = os.path.join(directory, file)
                    break

            if fallback_path and os.path.exists(fallback_path):
                # Copy the fallback file to our expected output path
                shutil.copy2(fallback_path, output_path)
                # Clean up the fallback file
                os.remove(fallback_path)

        # If the file still doesn't exist or is empty, raise an exception
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception("Failed to generate filled PDF")

        # Create permanent copy of the output in a separate directory for long-term storage
        os.makedirs("filled_forms", exist_ok=True)
        permanent_path = os.path.join("filled_forms", f"filled_{pdf_file.filename}")
        shutil.copy2(output_path, permanent_path)

        # Clean up temporary input file
        if os.path.exists(temp_path):
            os.remove(temp_path)

        # Return JSON response if requested, otherwise return the PDF file
        if return_json:
            # Schedule cleanup of output file
            background_tasks.add_task(cleanup_temp_file, output_path)

            return FormResponse(
                status="success",
                message=f"Form processed successfully. PDF saved at {permanent_path}",
                requires_ocr=needs_ocr,
                field_matches=field_matches
            )
        else:
            # Return the PDF file directly and schedule cleanup for later
            # FastAPI will handle this properly and clean up after download
            background_tasks.add_task(cleanup_temp_file, output_path)

            return FileResponse(
                path=output_path,
                filename=f"filled_{pdf_file.filename}",
                media_type="application/pdf"
            )

    except json.JSONDecodeError:
        cleanup_temp_files(temp_path, output_path)
        raise HTTPException(status_code=400, detail="Invalid JSON in form_data")
    except Exception as e:
        cleanup_temp_files(temp_path, output_path)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)