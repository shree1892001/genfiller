import fitz  # PyMuPDF
import pytesseract
from pdf2image import convert_from_path
import cv2
import numpy as np


def extract_text_from_images(input_pdf_path):
    """Converts PDF pages to images and extracts text using OCR."""
    images = convert_from_path(input_pdf_path)
    pdf_text_data = {}

    for page_num, img in enumerate(images, start=1):
        # Convert image to OpenCV format
        img_cv = np.array(img)
        img_cv = cv2.cvtColor(img_cv, cv2.COLOR_RGB2GRAY)  # Convert to grayscale for better OCR

        # Extract text using Tesseract OCR
        text = pytesseract.image_to_string(img_cv)

        # Store text per page
        pdf_text_data[page_num] = text.split("\n")  # Store as lines

    return pdf_text_data


# Step 2: Use AI to extract fields (Simulated AI Output)
fillable_fields = {
    "The name of the limited liability company is:": "Acme LLC",
    "Later effective date (specified here):": "2024-10-26",
    "CRA Public Number:": "1234567",
    "(Name of commercial registered agent)": "Registered Agent Corp",
    "(Name of noncommercial registered agent)": "John Smith",
    "(physical location, not P.O. Box â€“ street, city, state and zip code)": "123 Main St, Anytown, ME 04000",
    "(mailing address if different from above)": "PO Box 123, Anytown, ME 04000",
    "(Type of professional services)": "Law",
    "Dated": "2024-10-26",
    "(original written signature of authorized person)": "[Signature]",
    "(type or print name and title of signer)": "John Smith, CEO",
    "(Name of contact person)": "Jane Doe",
    "(Daytime telephone number)": "555-123-4567",
    "(Contact email address for this filing)": "jane.doe@example.com",
    "(Email address to use for annual report reminders)": "jane.doe@example.com",
    "(Name of attested copy recipient)": "Jane Doe",
    "(Firm or Company)": "Acme LLC",
    "(Mailing Address)": "123 Main St, Anytown, ME 04000",
    "(City, State & Zip)": "Anytown, ME 04000"
}


# Step 3: Locate keys in the PDF and fill values
def fill_pdf_fields(input_pdf_path, output_pdf_path, fields_data):
    """Annotates only the identified fields in the PDF with extracted values."""
    doc = fitz.open(input_pdf_path)
    pdf_text_data = extract_text_from_images(input_pdf_path)  # Extract text from images

    for page_num, lines in pdf_text_data.items():
        used_rects = set()  # **Track used placeholder positions**

        for key, value in fields_data.items():
            for i, line in enumerate(lines):
                if key in line:  # If the field name is found
                    matches = doc[page_num - 1].search_for("___________________")  # Locate placeholder
                    if matches:  # Ensure match is found
                        for rect in matches:
                            if rect in used_rects:
                                continue  # **Skip if already used**

                            x0, y0, x1, y1 = rect

                            # **Erase the placeholder**
                            doc[page_num - 1].insert_text((x0, y0), " " * 15, fontsize=10, color=(1, 1, 1))

                            # **Insert the value inside the text box**
                            doc[page_num - 1].insert_text((x0 + 5, y0 + 8), value, fontsize=10, color=(0, 0, 0))

                            used_rects.add(rect)  # **Mark this placeholder as used**
                            break

    doc.save(output_pdf_path)
    print(f"Annotated PDF saved as: {output_pdf_path}")


# Usage

input_pdf = "D:\\demo\\Services\\Maine.pdf"
output_pdf = "D:\\demo\\Services\\fill_smart13.pdf"


# Step 3: Fill the PDF fields
fill_pdf_fields(input_pdf, output_pdf, fillable_fields)
