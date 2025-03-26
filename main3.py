import fitz  # PyMuPDF
import google.generativeai as genai
from PIL import Image
import io
from Common.constants import API_KEY_2  # Assuming you have your API key here

# Configure the GenAI API key
genai.configure(api_key=API_KEY_2)

def extract_text_from_image_pdf(pdf_path, dpi=300):
    """Extracts text from a PDF containing images using Gemini Pro Vision."""
    doc = fitz.open(pdf_path)
    full_text = ""

    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72)) #increase dpi for better results

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()

        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content([
                "Extract all the text from this image.",
                Image.open(io.BytesIO(img_byte_arr))
            ])
            full_text += response.text + "\n"
        except Exception as e:
            print(f"Error processing page {page_num + 1}: {e}")

    return full_text

def main():
    pdf_path = "D:\\demo\\Services\\Connecitcuit.pdf"  # Replace with your PDF path
    extracted_text = extract_text_from_image_pdf(pdf_path)

    if extracted_text:
        print("Extracted Text:")
        print(extracted_text)
    else:
        print("Failed to extract text from PDF.")

if __name__ == "__main__":
    main()