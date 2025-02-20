from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfform
from reportlab.lib.colors import black
from reportlab.pdfbase import pdfdoc
from reportlab.pdfbase.pdfmetrics import stringWidth
import io


def create_sample_form():
    """Create a sample fillable PDF form"""

    # Create PDF buffer
    buffer = io.BytesIO()

    # Create the canvas
    c = canvas.Canvas(buffer)
    c.setFont("Helvetica", 12)

    # Form title
    c.drawString(50, 800, "Sample Employee Information Form")
    c.setFont("Helvetica", 10)

    # Personal Information Section
    c.drawString(50, 750, "Personal Information")
    c.line(50, 745, 550, 745)

    # Full Name field
    c.drawString(50, 720, "Full Name:")
    form = c.acroForm
    form.textfield(
        name='full_name',
        tooltip='Enter full name',
        x=150,
        y=715,
        width=200,
        height=20,
        borderStyle='solid',
        borderWidth=1
    )

    # Email field
    c.drawString(50, 680, "Email Address:")
    form.textfield(
        name='email_address',
        tooltip='Enter email address',
        x=150,
        y=675,
        width=200,
        height=20,
        borderStyle='solid',
        borderWidth=1
    )

    # Phone field
    c.drawString(50, 640, "Phone Number:")
    form.textfield(
        name='phone_number',
        tooltip='Enter phone number',
        x=150,
        y=635,
        width=200,
        height=20,
        borderStyle='solid',
        borderWidth=1
    )

    # Address field
    c.drawString(50, 600, "Mailing Address:")
    form.textfield(
        name='mailing_address',
        tooltip='Enter mailing address',
        x=150,
        y=595,
        width=300,
        height=20,
        borderStyle='solid',
        borderWidth=1
    )

    # Professional Information Section
    c.drawString(50, 550, "Professional Information")
    c.line(50, 545, 550, 545)

    # Job Title field
    c.drawString(50, 520, "Current Position:")
    form.textfield(
        name='job_title',
        tooltip='Enter current job title',
        x=150,
        y=515,
        width=200,
        height=20,
        borderStyle='solid',
        borderWidth=1
    )

    # Department field
    c.drawString(50, 480, "Department:")
    form.textfield(
        name='department',
        tooltip='Enter department',
        x=150,
        y=475,
        width=200,
        height=20,
        borderStyle='solid',
        borderWidth=1
    )

    # Start Date field
    c.drawString(50, 440, "Start Date:")
    form.textfield(
        name='start_date',
        tooltip='Enter start date (YYYY-MM-DD)',
        x=150,
        y=435,
        width=200,
        height=20,
        borderStyle='solid',
        borderWidth=1
    )

    # Employee ID field
    c.drawString(50, 400, "Employee ID:")
    form.textfield(
        name='employee_id',
        tooltip='Enter employee ID',
        x=150,
        y=395,
        width=200,
        height=20,
        borderStyle='solid',
        borderWidth=1
    )

    # Emergency Contact Section
    c.drawString(50, 350, "Emergency Contact Information")
    c.line(50, 345, 550, 345)

    # Emergency Contact Name
    c.drawString(50, 320, "Contact Name:")
    form.textfield(
        name='emergency_contact_name',
        tooltip='Enter emergency contact name',
        x=150,
        y=315,
        width=200,
        height=20,
        borderStyle='solid',
        borderWidth=1
    )

    # Emergency Contact Phone
    c.drawString(50, 280, "Contact Phone:")
    form.textfield(
        name='emergency_contact_phone',
        tooltip='Enter emergency contact phone',
        x=150,
        y=275,
        width=200,
        height=20,
        borderStyle='solid',
        borderWidth=1
    )

    # Emergency Contact Relationship
    c.drawString(50, 240, "Relationship:")
    form.textfield(
        name='emergency_contact_relation',
        tooltip='Enter relationship to emergency contact',
        x=150,
        y=235,
        width=200,
        height=20,
        borderStyle='solid',
        borderWidth=1
    )

    # Save the PDF
    c.save()

    # Get the value of the buffer
    pdf_value = buffer.getvalue()
    buffer.close()

    return pdf_value


def save_sample_form(output_path: str = "sample_form.pdf"):
    """Save the sample form to a file"""
    pdf_content = create_sample_form()
    with open(output_path, 'wb') as f:
        f.write(pdf_content)
    print(f"Sample form created at: {output_path}")


# Generate sample JSON data matching the form fields
SAMPLE_JSON_DATA = {
    "full_name": "John Doe",
    "email_address": "john.doe@example.com",
    "phone_number": "123-456-7890",
    "mailing_address": "123 Main St, City, State 12345",
    "job_title": "Software Engineer",
    "department": "Engineering",
    "start_date": "2024-01-01",
    "employee_id": "EMP001",
    "emergency_contact_name": "Jane Doe",
    "emergency_contact_phone": "987-654-3210",
    "emergency_contact_relation": "Spouse"
}

if __name__ == "__main__":
    # Create the sample form
    save_sample_form()

    # Save the sample JSON data
    with open("sample_data.json", "w") as f:
        json.dump(SAMPLE_JSON_DATA, f, indent=4)
    print("Sample JSON data created at: sample_data.json")