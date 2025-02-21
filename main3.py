

from pypdf import PdfReader,PdfWriter

reader = PdfReader("D:\\demo\\Services\\filled_form4.pdf")

fields = reader.get_fields()
for key, field in fields.items():
    print(f"Field Name: {key}, Field Type: {field.field_type}, Options: {field.value}")