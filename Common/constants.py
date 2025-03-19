import json

DEFAULT_API_KEY ="AIzaSyAvNz1x-OZl3kUDEm4-ZhwzJJy1Tqq6Flg"
API_KEY_1 ="AIzaSyBdgesVDKSwGPoJrF0lh5sA4iRWJOEUQwc"
API_KEY_2 ="AIzaSyBdgesVDKSwGPoJrF0lh5sA4iRWJOEUQwc"
API_KEY_3 ="AIzaSyCTqp_VyTh5n9GKrVETOO8SsKng76FkqYo"
API_KEY_4 ="AIzaSyBdgesVDKSwGPoJrF0lh5sA4iRWJOEUQwc"



FIELD_MATCHING_PROMPT = """
You are an expert at analyzing and matching form fields, with deep knowledge of business and legal document terminology. Your task is to match JSON data fields to PDF form fields by understanding their semantic meaning, even when the exact wording differs significantly.

HIGHEST PRIORITY FIELDS (MUST BE MATCHED):
1. Company Name Fields:
   - Look for fields containing: "Limited Liability Company Name", "LLC Name", "Company Name" a
   - These fields MUST be matched with the highest confidence
   - Common JSON field variations: "company_name", "name", "legal_name", "business_name"
   - Always prioritize the official company name field over other name fields

2. Other Critical Fields:
   - Entity type/structure
   - Business purpose
   - Formation date
   - Principal office address
   - Registered agent information
2. Limited Liability Company Name. 
  - Check the for the term Limited Liability Company Name in the fields and fill in appropriate fields.
  -"Limited Liability Company Name" 
  -"Limited Liability Name LLC"
  -"LLC"
  Check for the word Limited Liability Company Name and fill in the value
3. The Order ID is mandatory and should be mapped from one of these JSON keys: "orderId", "orderDetails.orderId", "data.orderDetails.orderId", "entityNumber", or "registrationNumber".
4. Address Information
   - Principal office location
   - Mailing address
   - Agent for service address

4. Management Details
   - Manager/Member information
   - Authorized persons
   - Officers and roles
5. Organizer Details: 
  - Add  organizer name as the signature in the field mentioned 

6. Legal Requirements
   - Registered agent information
   - State filing details
   - Tax and regulatory information
   
    also check of the Business Addresses.Initial Street Address of Principal Office.State
• Service of Process.Individual.Street Address.City
• Service of Process.Individual.Street Address.State
• Service of Process.Individual.Street Address.Zip Code
• Management
• Purpose Statement

JSON Data to Process:
{json_data}

Available PDF Form Fields:
{pdf_fields}

MATCHING INSTRUCTIONS:
1. First identify and match all company name fields
2. For company names, use exact matches from the JSON data
3. Ensure required fields are never left empty
4. Match remaining fields based on semantic similarity
  

Return matches in this exact format (do not modify the structure):
{{
    "matches": [
        {{
            "json_field": "field_name",
            "pdf_field": "corresponding_pdf_field",
            "confidence": 0.0-1.0,
            "suggested_value": "value",
            "field_type": "type",
            "editable": boolean,
            "reasoning": "detailed explanation"
        }}
    ]
}}

For company name fields:
- Set confidence to 1.0 for exact matches
-consider the fields if they are slightly matching or very less mathcing 
- Preserve exact capitalization and spacing
- Do not abbreviate or modify the company name
- Include detailed reasoning for the match 
- Fill all the fields even if they are  by semantic search dont keep anything blank and even if they are seem unnecessaary

"""
API_KEY= "AIzaSyBHkJvcositehBgALC6ONIiOwBvjsgPfZY"
FIELD_MATCHING_PROMPT1 = """
You are an expert form field matching AI with deep knowledge of business documents and legal terminology. Analyze and match JSON data fields to PDF form fields based on semantic meaning and context.
SPECIAL ATTENTION - COMPANY NAME FIELDS:
- The JSON data may contain multiple company name fields (e.g., "llc_name", "entity_name")
- Choose the most appropriate company name value when multiple exist
- Ensure the company name is matched to the correct PDF field
- Common PDF field variations include "Limited Liability Company Name", "LLC Name", etc.
-ENTITY NUMBER / ORDER ID MAPPING:
   PDF Field Patterns:
   - "Entity Number"
   - "Entity Number if applicable"
   - "Entity Information"
   
   
   - "Filing Number"
   - "Registration ID"

   JSON Field Patterns:
   - "orderId"                    # PRIMARY MATCH FOR ENTITY NUMBER
   - "orderDetails.orderId"
   - "data.orderDetails.orderId"
   - "entityNumber"
   - "registrationNumber"
   - Any field ending with "Id" or "Number"
   

   Agent Name and Address Fields:
   PDF Patterns:
   - "Get the agent first and Last Name from the data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Registered_Agent.RA_Name split the name in way example if name is "Corporate Creations Network Inc." then first name  would be "Corporate" and LastName would be "Creations Network Inc." search for ssik
   - "Agent Street Address"
   - "Agent Physical Address"
   - "b Street Address (if agent is not a corporation)"
   - "City no abbreviations_3"
   - "Zip Code_3"
   - "Agent State"

   JSON Patterns:
   - "RA_Address_Line_1"
   - "agent.address"
   - "registeredAgent.streetAddress"
   - "Registered_Agent.Address"

   Agent Contact Information:
   PDF Patterns:
   - "Agent Phone"
   - "Agent Email"
   - "Agent Contact Number"

   JSON Patterns:
   - "RA_Email_Address"
   - "RA_Contact_No"
   - "agent.contactDetails"
   
  Principal Address: 
      find the principal address field   in the pdf 
      - fill the address line 1 pdf field with data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Address_Line_1 or similar json field 
      - fill the address line 2 pdf field with data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Address_Line_2 or similar json field 
      - fill the city pdf field with data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_City or similar json field
      - fill the state pdf field with data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_State or similar json field 
      - fill the Zip or Zip Code or similar pdf field with data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Zip_Code or similar json field 
 Principal  Office:
   - "a. Initial Street Address of Principal Office - Do not enter a P.O. Box"
   - "Postal Address"
   - "Correspondence Address"
   - "Alternative Address"
   -"State_2"
   - "Zip Code_2"
   - "City no abbreviations_2"
   - "State"
   - "Zip Code"
 

ORGANIZER INFORMATION:
   Name Fields:
   - "Organizer Name"
   - "Org_Name"
   - "Organizer.Name"
   - "Formation Organizer"

   Contact Details:
   - "Org_Email_Address"
   - "Org_Contact_No"
   - "Organizer Phone"
   - "Organizer Email"
   -Get the FirstName and Last name from the contact Details json present the first Name can be fetched or obtained at data.contactDetails.firstName json field and the last Name at data.contactDetails.lastName and fill them at right position in the form in pdf.

   Signature Fields:
   - "Organizer Signature"
   - "Authorized Signature"
   - "Execution"

FORM CONTROLS AND BUTTONS:
   - "Box"
   - "Reset1"
   - "Print"
   - "RadioButton1"
   - "RadioButton2"
   - "RadioButton3"
   - "Clear Form"
   - "Print Form"
-If any field likem Limited Liability Company Name is found in the pdf then print the company name or the  entity name in that field . 
INTELLIGENT MATCHING RULES:

1. PRIORITY MATCHING:
   Highest Priority:
   - Company Name (1.0 confidence)
   - Entity Number/Order ID (1.0 confidence)
   - Registered Agent Information (0.9-1.0 confidence)

   Secondary Priority:
   - Address Information (0.8-0.9 confidence)
   - Organizer Details (0.8-0.9 confidence)
   - Contact Information (0.7-0.8 confidence)

INPUT DATA:
JSON Data: {json.dumps(flat_json, indent=2)}
PDF Fields: {json.dumps(pdf_fields,indent=2)}

MATCHING REQUIREMENTS:
1. Analyze ALL fields in both JSON and PDF
2. Match based on semantic meaning, not just exact text
3. Include ALL PDF fields in the response, even if no match is found
4. Consider field types and formatting requirements
5. Handle variations in terminology and formatting
6. Pay special attention to:
   - Company/Entity names
   - Addresses
   - Dates
   - Contact information
   - Legal identifiers
   - Optional and required fields
   - Empty fields

PROVIDE MATCHES IN THIS FORMAT:
{{
    "matches": [
        {{
            "json_field": "source_field",  // Empty string if no match
            "pdf_field": "target_field",
            "confidence": 0.0-1.0,         // 0.0 for unmatched fields
            "suggested_value": "processed_value",  // Empty string if no value
            "field_type": "field_type",
            "editable": boolean,
            "reasoning": "detailed_explanation"
        }}
    ]
}}

MATCHING GUIDELINES:
1. Include ALL PDF fields in the response
2. Preserve exact values for company names and identifiers
3. Format dates according to form requirements
4. Structure addresses appropriately
5. Handle special characters correctly
6. Consider field constraints and types
7. Provide confidence scores:
   - 0.0 for unmatched fields
   - 0.1-0.5 for potential matches
   - 0.6-0.8 for good matches
   - 0.9-1.0 for exact matches
8. Include clear reasoning for each match or lack thereof

Return ALL fields, including those with no matches or empty values.
"""
FIELD_CONTEXT_ANALYSIS='''

You are an expert in form field interpretation and context extraction. Your task is to analyze PDF form fields and OCR text to extract meaningful contextual information.

Input:
- A list of PDF form fields with their locations
- A comprehensive list of OCR text elements extracted from the document

Objective:
Provide a detailed, structured analysis that maps contextual information for each form field, focusing on:
1. Nearby text elements
2. Potential label or description associations
3. Semantic relationships between text and fields
4. Contextual hints that could help in field value prediction

Output Requirements:
- Return a JSON array of field context objects
- Each object should contain:
  - field_name: Original field identifier
  - page: Page number
  - nearby_text: Array of most relevant text elements
  - potential_labels: Possible labels or descriptions
  - context_hints: Semantic insights about the field

Nearby Text Criteria:
- Consider spatial proximity (vertical and horizontal)
- Evaluate semantic relevance
- Look for text that could be labels, descriptions, or related information
- Prioritize text that provides meaningful context

Context Extraction Guidelines:
- Within 100-200 pixels of the field
- Consider text orientation and reading flow
- Differentiate between actual labels and irrelevant nearby text
- Capture text that provides meaningful information about the field's purpose

Example Output Structure:
```json
[
  {{
    "field_name": "first_name",
    "page": 1,
    "nearby_text": [
      {"text": "First Name", "position": "left", "confidence": 0.95},
      {"text": "Legal Name Details", "position": "above", "confidence": 0.75}
    ],
    "potential_labels": ["First Name", "Given Name"],
    "context_hints": ["Personal identification section", "Required field"]
  }}
]
```

Important Notes:
- Be precise and confident in your text selection
- If no meaningful context is found, return an empty array for that field
- Ensure the output is valid, parseable JSON
- Confidence scores help indicate the reliability of context extraction
'''
# prompts.py

FIELD_MATCHING_PROMPT2 = '''
        You are an expert at intelligent form field matching. I need you to match JSON data to PDF form fields.

        JSON DATA:
        {json_data}

        PDF FIELDS:
        {pdf_fields}

        YOUR TASK:
        1. For EVERY PDF field, find the most appropriate JSON field that should fill it
        2. Consider semantic meaning, not just exact matches
        3. Assign a value for EVERY field, even if you need to derive it from multiple JSON fields
        4. For fields with no clear match, suggest a reasonable default value based on available data

        Return your response as a JSON object with a "matches" array containing objects with:
        - pdf_field: The PDF field name
        - json_field: The matched JSON field name (or "derived" if combining fields)
        - confidence: A number from 0 to 1 indicating match confidence
        - suggested_value: T
        SPECIAL ATTENTION - COMPANY NAME FIELDS:
- The JSON data may contain multiple company name fields (e.g., "llc_name", "entity_name")
- Choose the most appropriate company name value when multiple exist
- Ensure the company name is matched to the correct PDF field
- Common PDF field variations include "Limited Liability Company Name", "LLC Name", etc.
- if their is a substring containing "Limited Liability Company Name" then add the  entity name in that field 
-ENTITY NUMBER / ORDER ID MAPPING:
   PDF Field Patterns:
   - "Entity Number"
   - "Entity Number if applicable"
   - "Entity Information"
   - "Filing Number"
   - "Registration ID"

   JSON Field Patterns:
   - "orderId"                    # PRIMARY MATCH FOR ENTITY NUMBER
   - "orderDetails.orderId"
   - "data.orderDetails.orderId"
   - "entityNumber"
   - "registrationNumber"
   - Any field ending with "Id" or "Number"
   

   REGISTERED AGENT INFORMATION: (Highly Required) 
   Name Address Fields:
   PDF Patterns:
   - "Agent Name" 
   - "California Agent's First Name" 
   - "Agent" 
   - "Registered Agent Name" 
   - "Agent's Name"
   - "Agent Street Address"
   - "Agent Physical Address"
   - "b Street Address (if agent is not a corporation)"
   - "City no abbreviations_3"
   - "Zip Code_3"
   - "Agent State"

   JSON Patterns:
   - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Registered_Agent.RA_Name" (for full name)
   - "RA_Address_Line_1" (for street address)
   - "agent.address" (for address)
   - "registeredAgent.streetAddress" (for street address)
   - "Registered_Agent.Address" (for address)
   - "Get the agent first and Last Name from the data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Registered_Agent.RA_Name split the name in way example if name is 'Corporate Creations Network Inc.' then first name would be 'Corporate' and LastName would be 'Creations Network Inc.'"

   Contact Information:
   PDF Patterns:
   - "Agent Phone"
   - "Agent Email"
   - "Agent Contact Number"

   JSON Patterns:
   - "RA_Email_Address" (for email)
   - "RA_Contact_No" (for contact number)
   - "agent.contactDetails" (for contact details)

   
  PRINCIPAL ADDRESS (MANDATORY FIELD):
   Address Fields:
   PDF Patterns:
   -  "Initial Street Address of Principal Office - Do not enter a P" → MUST be mapped to a Principal Address field in JSON "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Address_Line_1".
   
   - "Postal Address"
   - "Correspondence Address"
   - "Alternative Address"
   - "City no abbreviations_2"
   - "State"
   - "Zip Code"

   JSON Patterns:
   - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Address_Line_1" (for Initial Street Address)
   - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Address_Line_2" (for Address Line 2)
   - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_City" (for City)
   - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_State" (for State)
   - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Zip_Code" (for Zip Code)



ORGANIZER or Incorporator INFORMATION:
   Name Fields:
   - "Organizer Name"
   - "Org_Name"
   - "Organizer.Name"
   - "Formation Organizer"
   - "Incorporator Name"
   - "Inc_Name"
   - "Incorporator.Name"
   - "Formation Incorporator"

   Contact Details:
   - "Org_Email_Address"
   - "Org_Contact_No"
   - "Organizer Phone"
   - "Organizer Email"
   - "Inc_Email_Address"
   - "Inc_Contact_No"
   - "Incorporator Phone"
   - "Incorporator Email"
   -Get the FirstName and Last name from the contact Details json present the first Name can be fetched or obtained at data.contactDetails.firstName json field and the last Name at data.contactDetails.lastName and fill them at right position in the form in pdf.

   Signature Fields:
   - "Organizer Signature"
   - "Authorized Signature"
   - "Execution"

FORM CONTROLS AND BUTTONS:
   - "Box"
   - "Reset1"
   - "Print"
   - "RadioButton1"
   - "RadioButton2"
   - "RadioButton3"
   - "Clear Form"
   - "Print Form"
        
        
        he actual value to fill in the PDF field
        - field_type: The type of field (text, checkbox, etc.)
        - editable: Whether the field is editable
        - reasoning: Brief explanation of why this match was made

        IMPORTANT: Every PDF field must have a suggested value, even if you need to derive one.
        '''
PDF_FIELD_MATCHING_PROMPT = """
Match the following JSON fields to PDF form fields.
ENTITY NAME FIELDS (MANDATORY):
- If "Entity Name" or "LLC Name" appears in multiple places in the PDF, ensure that the same entity name is used in each and filled the pdf .

- The JSON data may contain multiple entity name fields, e.g., "entity_name", "llc_name".
- Common PDF field names for entity name include:
  - "Entity Information - Name"
  - "1. Limited Liability Company Name"
  -"LImited Liability Company"
  - "LLC Name"
  - "Business Name"
  - "Company Name"
- Use the most appropriate entity name value and ensure it appears consistently.

Mailing Address Group (MANDATORY):
   PDF Field Patterns:
   - Main Address: "b. Initial Mailing Address ", "Mailing Address of LLC"
   - City: Field containing "City" near mailing address
   - State: Field containing "State" near mailing address
   - ZIP: Field containing "Zip" or "Zip Code" near mailing address
   
   JSON Field Patterns:
   - Address: "Mailing_Address.MA_Address_Line_1", "Entity_Formation.Mailing_Address.MA_Address_Line_1"
   - City: "Mailing_Address.MA_City", "Entity_Formation.Mailing_Address.MA_City"
   - State: "Mailing_Address.MA_State", "Entity_Formation.Mailing_Address.MA_State"
   - ZIP: "Mailing_Address.MA_Zip_Code", "Entity_Formation.Mailing_Address.MA_Zip_Code"


ENTITY NUMBER / ORDER ID MAPPING(MANDATORY) :

    PDF Field Patterns:
    - "Entity Number"
    - "Entity Number if applicable"
    - "Entity Information"
    - "Filing Number"
    - "Registration ID"

    JSON Field Patterns:
    - "orderId"                    # PRIMARY MATCH FOR ENTITY NUMBER
    - "orderDetails.orderId"
    - "data.orderDetails.orderId"
    - "entityNumber"
    - "registrationNumber"
    - Any field ending with "Id" or "Number"
      REGISTERED AGENT INFORMATION (HIGHLY REQUIRED):
- Ensure the AI agent correctly fills the Registered Agent fields, even if names are slightly different.
- Match agent names using:
  - "California Agent's First Name"
  - "California Agent's Last Name"
  - "Registered Agent Name"
  - "Agent's Name"
  - "Agent Street Address"
  - "Agent Physical Address"
  - "b Street Address (if agent is not a corporation)"
- Prioritize JSON fields:
  - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Registered_Agent.RA_Name"
  - "RA_Address_Line_1"
  - "registeredAgent.streetAddress"
  - "Registered_Agent.Address"

  :
- "Organizer Name"
- "Authorized Signature"
- "Execution"
-If the form ask for "Signature" or "Organizer Sign"  then add the Organizer name from the json value "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Organizer_Information.Org_Name"
- If an agent's name is provided as a full name string, split it into first and last names  example if agent name is CC tech Filings then first name is "CC" and last Name would be "tech Filings".
-1. ADDRESSES:
       - Distinguish between different address types (mailing, physical, agent, principal office)
       - Correctly match address components (street, city, state, zip) to corresponding JSON fields
       - If a field contains "mailing" or is labeled as a mailing address, prioritize JSON fields with "mail"
       - If a field contains "principal" or "physical", prioritize JSON fields with those terms
    

JSON Data:
{json_data}

PDF Fields:
{pdf_fields}

Respond with a valid JSON in this format:
{{
    "matches": [
        {{
            "json_field": "<JSON key>",
            "pdf_field": "<PDF field name>",
            "confidence": 0.95,
            "suggested_value": "<value to fill>",
            "reasoning": "Matched based on..."
        }}
    ]
}}
"""

PDF_FIELD_MATCHING_PROMPT1 = """
Match the following JSON fields to PDF form fields.
I need to fill a PDF form with data from a JSON object. Match JSON fields to the appropriate PDF form fields or OCR-detected text areas based on keyword similarity, even if spelling errors exist. Fill them in a single process.
ENTITY NAME FIELDS (MANDATORY):
- If "Entity Name" or "LLC Name" appears in multiple places in the PDF, ensure that the same entity name is used in each and filled in the PDF.

- The JSON data may contain multiple entity name fields, e.g., "entity_name", "llc_name".
- Common PDF field names for entity name include:
  - "Entity Information - Name"
  - "1. Limited Liability Company Name"
  - "Limited Liability Company"
  - "LLC Name"
  - "Business Name"
  - "Company Name"
- Use the most appropriate entity name value and ensure it appears consistently.

Mailing Address Group (MANDATORY):
   PDF Field Patterns:
   - Main Address: "b. Initial Mailing Address ", "Mailing Address of LLC"
   - City: Field containing "City" near mailing address
   - State: Field containing "State" near mailing address
   - ZIP: Field containing "Zip" or "Zip Code" near mailing address

   JSON Field Patterns:
   - Address: "Mailing_Address.MA_Address_Line_1", "Entity_Formation.Mailing_Address.MA_Address_Line_1"
   - City: "Mailing_Address.MA_City", "Entity_Formation.Mailing_Address.MA_City"
   - State: "Mailing_Address.MA_State", "Entity_Formation.Mailing_Address.MA_State"
   - ZIP: "Mailing_Address.MA_Zip_Code", "Entity_Formation.Mailing_Address.MA_Zip_Code"

ENTITY NUMBER / ORDER ID MAPPING (MANDATORY):

    PDF Field Patterns:
    - "Entity Number"
    - "Entity Number if applicable"
    - "Entity Information"
    - "Filing Number"
    - "Registration ID"

    JSON Field Patterns:
    - "orderId"                    # PRIMARY MATCH FOR ENTITY NUMBER
    - "orderDetails.orderId"
    - "data.orderDetails.orderId"
    - "entityNumber"
    - "registrationNumber"
    - Any field ending with "Id" or "Number"

REGISTERED AGENT INFORMATION (MANDATORY):
- Ensure the AI agent correctly fills the Registered Agent fields, even if names are slightly different.
- Match agent names using:
  - "California Agent's First Name"
  - "California Agent's Last Name"
  - "Registered Agent Name"
  - "Agent's Name"
  - "Agent Street Address"
  - "Agent Physical Address"
  - "b Street Address (if agent is not a corporation)"
- Prioritize JSON fields:
  - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Registered_Agent.RA_Name"
  - "RA_Address_Line_1"
  - "registeredAgent.streetAddress"
  - "Registered_Agent.Address"

SIGNATURE & ORGANIZER INFORMATION:
- Match the following fields:
  - "Organizer Name"
  - "Authorized Signature"
  - "Execution"
- If the form asks for "Signature" or "Organizer Sign," then add the organizer name from the JSON value:
  - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Organizer_Information.Org_Name"
- If an agent's name is provided as a full name string, split it into first and last names.  
  Example: If agent name is "CC Tech Filings," then first name is **"CC"** and last name is **"Tech Filings"**.

ADDRESSES:
- Distinguish between different address types (mailing, physical, agent, principal office).
- Correctly match address components (street, city, state, zip) to corresponding JSON fields.
- If a field contains "mailing" or is labeled as a mailing address, prioritize JSON fields with "mail".
- If a field contains "principal" or "physical," prioritize JSON fields with those terms.

### **NEWLY ADDED FIELDS TO BE FILLED IN PDF:**

BUSINESS PURPOSE FIELD:
- Ensure that the business purpose section is correctly populated from:
  - JSON Field: `"orderDetails.strapiOrderFormJson.Entity_Formation.Business_Purpose"`
- Common PDF Field Names:
  - "Purpose of Business"
  - "Business Purpose"
  - "Nature of Business"
- If the business purpose is missing, default to: **"General Business Activities"**.

MEMBER/MANAGER SELECTION (MANDATORY):
- Identify if the LLC will be **Member-Managed** or **Manager-Managed**.
- Match JSON Field:
  - `"orderDetails.strapiOrderFormJson.Entity_Formation.Management_Type"`
- Common PDF Field Names:
  - "LLC Managed By"
  - "Management Structure"
  - "The LLC will be managed by:"
- Set values as:
  - `"One Manager"` → Manager-Managed
  - `"More than One Manager"` → Multiple Managers
  - `"All LLC Member(s)"` → Member-Managed

EMAIL CONTACT (OPTIONAL BUT IMPORTANT):
- Match JSON Field:
  - `"contactDetails.emailId"`
- Common PDF Field Names:
  - "Contact Email"
  - "Business Email"
  - "Registered Email Address"

FILING FEE & TAX INFORMATION (IF REQUIRED):
- If the form includes a **Filing Fee** section, ensure the amount is populated.
- Match JSON Field:
  - `"orderDetails.orderAmount"`
- Common PDF Field Names:
  - "Filing Fee"
  - "Total Payment"
  - "Amount Paid"

ADDITIONAL NOTES & COMPLIANCE STATEMENTS:
- If the form requires **additional notes or compliance agreements**, populate them from:
  - `"orderDetails.strapiOrderFormJson.Entity_Formation.Compliance_Notes"`
- Common PDF Field Names:
  - "Additional Notes"
  - "Compliance Statement"
  - "Regulatory Agreement"
- If missing, use: **"LLC agrees to comply with all state regulations and filing requirements."**

JSON Data:
{json_data}

PDF Fields:
{pdf_fields}

Respond with a valid JSON in this format:
{{
    "matches": [
        {{
            "json_field": "<JSON key>",
            "pdf_field": "<PDF field name>",
            "confidence": 0.95,
            "suggested_value": "<value to fill>",
            "reasoning": "Matched based on..."
        }}
    ]
}}
"""
PDF_FIELD_MATCHING_PROMPT2="""
I need to fill a PDF form with data from a JSON object. Match JSON fields to PDF form fields based on semantic similarity, not just exact string matches.
    
    IMPORTANT INSTRUCTIONS:
    1. For each PDF field, find the most relevant JSON field, even if names are different.
    2. Consider field context (nearby text in the PDF) to understand the purpose of each field.
    3. For name fields, match to company name or individual name appropriately.
    4. Registered agent name and address fields need to be accurately filled.
    5. For address fields, properly distribute address components (street, city, state, zip).
    6. Pay special attention to UUIDs in the form - these need to be matched based on context.
    7. Create matches for ALL PDF fields if possible - aim for 100% coverage.
    8. Be particularly careful with matching text from OCR with the corresponding PDF fields.
    
    ENTITY NAME FIELDS (MANDATORY):
    - If "Entity Name" or "LLC Name" appears in multiple places in the PDF, ensure that the same entity name is used consistently.
    - The JSON data may contain multiple entity name fields, e.g., "entity_name", "llc_name","Corporation Name ,"Corp_Name, "Corporation_Name".
    - Common PDF field names for entity name include:
      - "Entity Information - Name"
      - "1. Limited Liability Company Name"
      - "Limited Liability Company"
      - "LLC Name"
      -"Corporation"
      -"Corp" 
      -"Incorporation Name" 
      
      - "Business Name"
      - "Company Name"
    
    MAILING ADDRESS GROUP (MANDATORY):
    - PDF Field Patterns:
      - "b. Initial Mailing Address ", "Mailing Address of LLC"
      - City fields near "Mailing Address"
      - State fields near "Mailing Address"
      - ZIP fields near "Mailing Address"
    - JSON Field Patterns:
      - Address: "Mailing_Address.MA_Address_Line_1"
      - City: "Mailing_Address.MA_City"
      - State: "Mailing_Address.MA_State"
      - ZIP: "Mailing_Address.MA_Zip_Code"
    
    ENTITY NUMBER / ORDER ID MAPPING (MANDATORY):
    - PDF Field Patterns:
      - "Entity Number", "Filing Number", "Registration ID"
    - JSON Field Patterns:
      - "orderId", "registrationNumber", any field ending with "Id" or "Number"
    
    REGISTERED AGENT INFORMATION (MANDATORY):
     REGISTERED AGENT fields should be filled with registered agent data (like registeredAgent.name)
    - Match agent names using:
      - "Registered Agent Name", "Agent's Name", "Agent Street Address","Register Agent Name","Register Agent" ,"Registered Agent".
      "Initial Registered Agent"
    - Prioritize JSON fields:
      - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Registered_Agent.RA_Name", "RA_Address_Line_1"
    
    SIGNATURE & ORGANIZER INFORMATION:
    - Match the following fields:
      - "Organizer Name", "Authorized Signature"
      - JSON field: "Organizer_Information.Org_Name"
    
    ADDRESSES:
    - Distinguish between different address types (mailing, physical, agent, principal office).
    - Correctly match address components (street, city, state, zip) to corresponding JSON fields.
    
    BUSINESS PURPOSE FIELD:
    - Ensure that the business purpose section is correctly populated from JSON field:
      - "Business_Purpose"
    - Default value: "General Business Activities" if missing.
    
    MEMBER/MANAGER SELECTION (MANDATORY):
    - Identify if the LLC is Member-Managed or Manager-Managed.
    - JSON Field: "Management_Type"
    - Set values:
      - "One Manager" → Manager-Managed
      - "More than One Manager" → Multiple Managers
      - "All LLC Member(s)" → Member-Managed
    
    EMAIL CONTACT (OPTIONAL BUT IMPORTANT):
    - JSON Field: "contactDetails.emailId"
    
    FILING FEE & TAX INFORMATION (IF REQUIRED):
    - JSON Field: "orderDetails.orderAmount"
    
    ADDITIONAL NOTES & COMPLIANCE STATEMENTS:
    - Populate from JSON: "Compliance_Notes"
    - Default value: "LLC agrees to comply with all state regulations and filing requirements."
    
    JSON DATA:
    {json_data}
    
    PDF FORM FIELDS (with UUIDs):
    {pdf_fields}
    
    OCR TEXT ELEMENTS:
    {ocr_elements}
    
    FIELD CONTEXT (NEARBY TEXT):
    {field_context}
    
    Respond with a valid JSON in this format:
    {{
        "matches": [
            {{
                "json_field": "<JSON key>",
                "pdf_field": "<PDF field name>",
                "confidence": 0.95,
                "suggested_value": "<value to fill>",
                "reasoning": "Matched based on..."
            }}
        ],
        "ocr_matches": [

    {{

      "json_field": "field.name.in.json",

      "ocr_text": "Extracted text from OCR",

      "pdf_field": "uuid_of_pdf_field",

      "confidence": 0.8,

      "suggested_value": "Value to annotate",

      "reasoning": "Why this OCR text matches this field"

    }}

  ]

}}
    }}
    """



FIELD_MATCHING_PROMPT_UPDATED =  """
        I need to fill a PDF form with data from a JSON object. Match JSON fields to PDF form fields based on semantic similarity, not just exact string matches.

        IMPORTANT INSTRUCTIONS:
        1. For each PDF field, find the most relevant JSON field, even if names are different.
        2. Consider field context (nearby text in the PDF) to understand the purpose of each field
        
        3. Registered agent name and address fields need to be accurately filled for registered agent name get  the value for the name in pdf fields it is present as  "Commercial Registered Agent" or similar at  "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Registered_Agent.RA_Name" and fill in the pdf field "initial regisered agent" or "registered agent" for registered agent accurately using this value only.
        4. ENTITY NAME FIELDS (MANDATORY):
    - If "Entity Name" or "LLC name" or "limited liability company" or similar  appears in multiple places in the PDF, ensure that the same entity name is used consistently enter the company name only if the field has the label "entity name or relevant".
    - The JSON data may contain multiple "entity name" fields, e.g., "entity_name", "llc_name","Corporation Name ,"Corp_Name, "Corporation_Name".
    - Common PDF field names for entity name include:
      - "Entity Information - Name"
      - "1. Limited Liability Company Name"
      - "Limited Liability Company"
      - "LLC Name"
      -"Corporation"
      -"Corp" 
      -"Incorporation Name" 
      
      - "Business Name"
      - "Company Name"
        5.PRINCIPAL ADDRESS (MANDATORY FIELD):
   Address Fields:
   PDF Patterns:
   -  "Initial Street Address of Principal Office - Do not enter a P" → MUST be mapped to a Principal Address field in JSON "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Address_Line_1".
   
   - "Postal Address"
   - "Correspondence Address"
   - "Alternative Address"
   - "City no abbreviations_2"
   - "State"
   - "Zip Code"

   JSON Patterns:
   - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Address_Line_1" (for Initial Street Address)
   - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Address_Line_2" (for Address Line 2)
   - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_City" (for City)
   - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_State" (for State)
   - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Zip_Code" (for Zip Code)
        6.  Organizer Details:
   - "Org_Email_Address"
   - "Org_Contact_No"
   - "Organizer Phone"
   - "Organizer Email"
   -"Organizer Name" 
   JSON Patterns:
   - get the organizer name from  "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Organizer_Information.Organizer_Details.Org_Name" value in the Organizer Signature Field or Signature along with the organizer name field or Similar .
   - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Organizer_Information.Organizer_Address.Org_Address_Line1 or similar"_Line_1 (for Address Line 2)
   - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Organizer_Information.Organizer_Details.Organizer_Email or similar" (for City)
   - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Organizer_Information.Organizer_Address.Org_State or Similar" (for State)
   - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Organizer_Information.Organizer_Address.Org_Zip_Code" (for Zip Code)
   
   - "Inc_Email_Address"
   - "Inc_Contact_No"
   - "Incorporator Phone"
   - "Incorporator Email"
           6. If the code as for business purpose then fill it accurately by selecting the business purpose field from json .
           7.SIGNATURE & ORGANIZER INFORMATION:
    - Match the following fields:
      - "Organizer Name", "Authorized Signature"
      - JSON field: "Organizer_Information.Org_Name"
         8. Pay special attention to UUIDs in the form - these need to be matched based on context.
        9. For phone number or contact information fetch the relevant value from the json 
        10. Create matches for ALL PDF fields if possible - aim for 100% coverage.
        11. Be particularly careful with matching text from OCR with the corresponding PDF fields.
        12. Use the "likely_purpose" keywords to help determine what each field is for.
        13.Also match the fields semantically accurate as their might be spelling errors in the keywords.
        14. IMPORTANT: Pay special attention to fields related to "registered agent", "agent name", or similar terms. These fields are critical for legal forms and must be filled correctly. Look for fields with these terms in their name or nearby text.
        15. Select the relevant checkbox if present if required based on json.
        16. EMAIL CONTACT (OPTIONAL BUT IMPORTANT):
        17. If the pdf asked for the name then enter the value from Get the FirstName and Last name from the contact details JSON field: "data.contactDetails.firstName" and "data.contactDetails.lastName".
    - JSON Field: "contactDetails.emailId"
        JSON DATA:
        {json_data}

        PDF FORM FIELDS (with UUIDs):
        {pdf_fields}

        OCR TEXT ELEMENTS:
        {ocr_elements}

        FIELD CONTEXT (NEARBY TEXT):
        {field_context}

        Return results in this format:
        {{
          "matches": [
            {{
              "json_field": "field.name.in.json",
              "pdf_field": "uuid_of_pdf_field",
              "confidence": 0.9,
              "suggested_value": "Value to fill",
              "reasoning": "Why this field was matched"
            }}
          ],
          "ocr_matches": [
            {{
              "json_field": "field.name.in.json",
              "ocr_text": "Extracted text from OCR",
              "pdf_field": "uuid_of_pdf_field",
              "confidence": 0.8,
              "suggested_value": "Value to annotate",
              "reasoning": "Why this OCR text matches this field"
            }}
          ]
        }}
        """

MISTRAL_API_KEY= "7NZvr1Bugz4jpKuWks11jX9jMDCbkv3G"
FIELD_MATCHING_PROMPT3 = '''
        You are an expert at intelligent form field matching. I need you to match JSON data to PDF form fields.

        JSON DATA:
        {json_data}

        PDF FIELDS:
        {pdf_fields}

        YOUR TASK:
        1. For EVERY PDF field, find the most appropriate JSON field that should fill it
        2. Prioritize exact matches first, but also consider semantic meaning, abbreviations, and truncations.
        3. Assign a value for EVERY field, even if you need to derive it from multiple JSON fields
        4. For fields with no clear match, suggest a reasonable default value based on available data
        5.Perform regex-based fuzzy matching to detect relevant fields even if they are named differently in JSON.
        6. Ensure that all required fields (e.g., Principal Office Address, Registered Agent) are filled.
        7. If the field is detected but remains empty, force assign the extracted value
        8.Ensure strict enforcement of field population for mandatory fields, even if confidence is low.
        9. If a field appears truncated in the extracted PDF fields, compare against the full field name and always use the complete version before considering a truncated match 
    10. Extract full PDF field names accurately. If a field appears truncated (e.g., missing prefixes like "a." or "b."), match it against the full list of extracted fields before making a decision. 
    EGISTERED AGENT FIELDS (HIGHEST PRIORITY)

Agent Name: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Registered_Agent.RA_Name
PDF field patterns: "initial registered agent", "registered agent", "agent name"
Include agent address using the appropriate JSON fields under Registered_Agent

PRINCIPAL ADDRESS (MANDATORY)

Address Line 1: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Address_Line_1
Address Line 2: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Address_Line_2
City: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_City
State: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_State
Zip: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Zip_Code
PDF patterns: "Principal Office", "Initial Street Address", "Main Address"

ORGANIZER INFORMATION

Organizer Name: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Organizer_Information.Organizer_Details.Org_Name
Email: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Organizer_Information.Organizer_Details.Org_Email_Address
Phone: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Organizer_Information.Organizer_Details.Org_Contact_No
Address: Fields under Organizer_Information.Organizer_Address.*
Use name for signature fields too

BUSINESS PURPOSE

Use exact text from JSON field related to business purpose
Handle checkbox selections based on JSON values

FIELD TYPE HANDLING
CHECKBOXES

For boolean PDF fields, convert string values:

"true", "yes", "on", "1" → TRUE
"false", "no", "off", "0" → FALSE


Look for JSON boolean fields or text indicating preferences

DATE FIELDS

Format dates consistently: MM/DD/YYYY
If the PDF has separate month/day/year fields, split accordingly

OCR FIELD POSITIONING

For OCR text matches, include precise position data (x1, y1, x2, y2)
Place annotations adjacent to but not overlapping the original text

       SPECIAL ATTENTION - FIELD NAME TRUNCATION:
        Return your response as a JSON object with a "matches" array containing objects with:
        - pdf_field: The PDF field name
        - json_field: The matched JSON field name (or "derived" if combining fields)
        - confidence: A number from 0 to 1 indicating match confidence
        - suggested_value: The actual value to fill in the PDF field
        - field_type: The type of field (text, checkbox, etc.)
        - editable: Whether the field is editable
        - reasoning: Brief explanation of why this match was made

        SPECIAL ATTENTION - COMPANY NAME FIELDS:
        - The JSON data may contain multiple company name fields (e.g., "llc_name", "entity_name")
        - Choose the most appropriate company name value when multiple exist
        - Ensure the company name is matched to the correct PDF field
        - Common PDF field variations include "Limited Liability Company Name", "LLC Name", etc.

        ENTITY NUMBER / ORDER ID MAPPING:
        PDF Field Patterns:
        - "Entity Number"
        - "Entity Number if applicable"
        - "Entity Information"
        - "Filing Number"
        - "Registration ID"

        JSON Field Patterns:
        - "orderId"                    # PRIMARY MATCH FOR ENTITY NUMBER
        - "orderDetails.orderId"
        - "data.orderDetails.orderId"
        - "entityNumber"
        - "registrationNumber"
        - Any field ending with "Id" or "Number"

        REGISTERED AGENT INFORMATION (HIGHLY REQUIRED):
    - Ensure the AI agent correctly fills the Registered Agent fields, even if names are slightly different.
    - Match agent names using:
      - "California Agent's First Name"
      - "California Agent's Last Name"
      - "Registered Agent Name"
      - "Agent's Name"
      - "Agent Street Address"
      - "Agent Physical Address"
      - "b Street Address (if agent is not a corporation)"
    - Prioritize JSON fields:
      - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Registered_Agent.RA_Name"
      - "RA_Address_Line_1"
      - "registeredAgent.streetAddress"
      - "Registered_Agent.Address"
    - If an agent's name is provided as a full name string, split it into first and last names as needed.
    - If the field is detected but remains empty, force assign the extracted value and log the issue.
    
    DEBUGGING AND VALIDATION:
    - Log any fields that remain unfilled after processing.
    - Ensure the AI agent provides a summary of unmatched fields and suggests corrections.
    - Cross-check all assigned values to confirm they align with expected data.
    
        Contact Information:
        PDF Patterns:
        - "Agent Phone"
        - "Agent Email"
        - "Agent Contact Number"

        JSON Patterns:
        - "RA_Email_Address" (for email)
        - "RA_Contact_No" (for contact number)
        - "agent.contactDetails" (for contact details)

        SPECIAL ATTENTION - FIELD NAME TRUNCATION:
    
    - If no full match is found, use regex-based similarity matching.
    - Ensure prefixes (e.g., "a. ", "b. ") do not cause mismatches.

   PRINCIPAL ADDRESS (MANDATORY FIELD):
    - Ensure "a. Initial Street Address of Principal Office - Do not enter a P.O. Box" is correctly matched.
    - If an exact match is not found, fallback to these:
      - "Initial Street Address of Principal Office"
      - "Principal Office Address"
      - "Business Address"
      
      - "Physical Address"
    - Use fuzzy matching to detect variations of the address field name.
    - If no direct match exists, derive an address from multiple related fields.
    - If the field is detected but remains empty after filling, **force assign the extracted value** and log it for debugging.
        JSON Patterns:
        - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Address_Line_1" (for Initial Street Address)
        - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Address_Line_2" (for Address Line 2)
        - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_City" (for City)
        - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_State" (for State)
        - "data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Zip_Code" (for Zip Code)
        - If no direct match exists, derive an address from multiple related fields (e.g., general company address fields).

        ORGANIZER INFORMATION:
        Name Fields:
        - "Organizer Name"
        - "Org_Name"
        - "Organizer.Name"
        - "Formation Organizer"

        Contact Details:
        - "Org_Email_Address"
        - "Org_Contact_No"
        - "Organizer Phone"
        - "Organizer Email"
        - Get the FirstName and Last name from the contact details JSON field: "data.contactDetails.firstName" and "data.contactDetails.lastName".

        Signature Fields:
        - "Organizer Signature"
        - "Authorized Signature"
        - "Execution"

        FORM CONTROLS AND BUTTONS:
        - "Box"
        - "Reset1"
        - "Print"
        - "RadioButton1"
        - "RadioButton2"
        - "RadioButton3"
        - "Clear Form"
        - "Print Form"

        IMPORTANT: Every PDF field must have a suggested value, even if you need to derive one.
'''


FIELD_MATCHING_PROMPT_UPDATED1='''
PDF Form Field Mapping Instructions
I need to fill a PDF form with data from a JSON object. Match JSON fields to PDF form fields based on semantic similarity, not just exact string matches.
CRITICAL MAPPING RULES (ALl the fields are critical) 

For each PDF field, find the most relevant JSON field, even if names differ
Consider field context (nearby text in the PDF) to understand field purpose
When multiple matches exist, prioritize:

Semantic relevance over keyword matching
Field type compatibility (text to text, numbers to numbers)
Context from nearby OCR text



MANDATORY FIELD MAPPINGS
ENTITY NAME FIELDS (HIGHEST PRIORITY)

If "Entity Name" or  "limited liability company name" or  similar appears multiple times, use consistent values
JSON path: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Entity_Name
PDF field patterns to look for:

"Entity Information - Name"
"Limited Liability Company Name"
'limited liability company"
"LLC Name"
"Corporation"/"Corp"
"Incorporation Name"
"Business Name"
"Company Name"
"limited liability company " or semantic perform the semantic mapping if you see company name then fill the above json value for the entity name. 



REGISTERED AGENT FIELDS (HIGHEST PRIORITY)

Agent Name: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Registered_Agent.RA_Name
PDF field patterns: "initial registered agent", "registered agent", "agent name"
Include agent address using the appropriate JSON fields under Registered_Agent

PRINCIPAL ADDRESS (MANDATORY)

Address Line 1: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Address_Line_1
Address Line 2: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Address_Line_2
City: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_City
State: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_State
Zip: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Principal_Address.PA_Zip_Code
PDF patterns: "Principal Office", "Initial Street Address", "Main Address"

ORGANIZER INFORMATION

Organizer Name: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Organizer_Information.Organizer_Details.Org_Name
Email: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Organizer_Information.Organizer_Details.Org_Email_Address
Phone: data.orderDetails.strapiOrderFormJson.Payload.Entity_Formation.Organizer_Information.Organizer_Details.Org_Contact_No
Address: Fields under Organizer_Information.Organizer_Address.*
Use name for signature fields too

BUSINESS PURPOSE

Use exact text from JSON field related to business purpose
Handle checkbox selections based on JSON values

FIELD TYPE HANDLING
CHECKBOXES

For boolean PDF fields, convert string values:

"true", "yes", "on", "1" → TRUE
"false", "no", "off", "0" → FALSE


Look for JSON boolean fields or text indicating preferences

DATE FIELDS

Format dates consistently: MM/DD/YYYY
If the PDF has separate month/day/year fields, split accordingly

OCR FIELD POSITIONING

For OCR text matches, include precise position data (x1, y1, x2, y2)
Place annotations adjacent to but not overlapping the original text

RESPONSE FORMAT
Return results in this precise format:
{{
  "matches": [
    {{
      "json_field": "field.name.in.json",
      "pdf_field": "uuid_of_pdf_field",
      "confidence": 0.9,
      "suggested_value": "Value to fill",
      "reasoning": "Detailed explanation of why this mapping is correct"
    }}
  ],
  "ocr_matches": [
    {{
      "json_field": "field.name.in.json",
      "ocr_text": "Extracted text from OCR",
      "page_num": 1,
      "x1": 100.0,
      "y1": 200.0,
      "x2": 300.0,
      "y2": 220.0,
      "confidence": 0.8,
      "suggested_value": "Value to annotate",
      "reasoning": "Explanation of OCR text match with positioning details"
    }}
  ]
}}
Aim for 100% field coverage with high-confidence mappings. Document any uncertain matches with lower confidence scores and detailed reasoning.


'''

SYSTEM_PROMPT_MATCHER = """
        You are an expert recruiter AI. Your goal is to autonomously analyze resumes and job descriptions.
        - Identify key skills, qualifications, and missing requirements.
        - Decide the next best step: Extract text, reanalyze, or improve match.
        - Maintain memory of past matches and refine recommendations.
        - Provide an updated match score and reasoning.
        """
jsonData = {

       "jsonData":{
        "EntityType": {
            "id": 1,
            "entityShortName": "LLC",
            "entityFullDesc": "Limited Liability Company",
            "onlineFormFilingFlag": False
        },
        "State": {
            "id": 33,
            "stateShortName": "NC",
            "stateFullDesc": "North Carolina",
            "stateUrl": "https://www.sosnc.gov/",
            "filingWebsiteUsername": "redberyl",
            "filingWebsitePassword": "yD7?ddG0!$09",
            "strapiDisplayName": "North-Carolina",
            "countryMaster": {
                "id": 3,
                "countryShortName": "US",
                "countryFullDesc": "United States"
            }
        },
        "County": {
            "id": 2006,
            "countyCode": "Alleghany",
            "countyName": "Alleghany",
            "stateId": {
                "id": 33,
                "stateShortName": "NC",
                "stateFullDesc": "North Carolina",
                "stateUrl": "https://www.sosnc.gov/",
                "filingWebsiteUsername": "redberyl",
                "filingWebsitePassword": "yD7?ddG0!$09",
                "strapiDisplayName": "North-Carolina",
                "countryMaster": {
                    "id": 3,
                    "countryShortName": "US",
                    "countryFullDesc": "United States"
                }
            }
        },
        "Payload": {
            "Entity_Formation": {
                "Name": {
                    "CD_LLC_Name": "redberyl llc",
                    "CD_Alternate_LLC_Name": "redberyl llc"
                },

                "Principal_Address": {
                    "PA_Address_Line_1": "123 Main Street",
                    "PA_Address_Line_2": "",
                    "PA_City": "Solapur",
                    "PA_Zip_Code": "11557",
                    "PA_State": "AL"
                },
                "Registered_Agent": {
                    "RA_Name": "Interstate Agent Services LLC",
                    "RA_Email_Address": "agentservice@vstatefilings.com",
                    "RA_Contact_No": "(718) 569-2703",
                    "Address": {
                        "RA_Address_Line_1": "6047 Tyvola Glen Circle, Suite 100",
                        "RA_Address_Line_2": "",
                        "RA_City": "Charlotte",
                        "RA_Zip_Code": "28217",
                        "RA_State": "NC"
                    }
                },
                "Billing_Information": {
                    "BI_Name": "Johson Charles",
                    "BI_Email_Address": "johson.charles@redberyktech.com",
                    "BI_Contact_No": "(555) 783-9499",
                    "BI_Address_Line_1": "123 Main Street",
                    "BI_Address_Line_2": "",
                    "BI_City": "Albany",
                    "BI_Zip_Code": "68342",
                    "BI_State": "AL"
                },
                "Mailing_Information": {
                    "MI_Name": "Johson Charles",
                    "MI_Email_Address": "johson.charles@redberyktech.com",
                    "MI_Contact_No": "(555) 783-9499",
                    "MI_Address_Line_1": "123 Main Street",
                    "MI_Address_Line_2": "",
                    "MI_City": "Albany",
                    "MI_Zip_Code": "68342",
                    "MI_State": "AL"
                },
                "Organizer_Information": {
                    "Organizer_Details": {
                        "Org_Name": "Johson Charles",
                        "Org_Email_Address": "johson.charles@redberyktech.com",
                        "Org_Contact_No": "(555) 783-9499"
                    },
                    "Address": {
                        "Org_Address_Line_1": "123 Main Street",
                        "Org_Address_Line_2": "",
                        "Org_City": "Albany",
                        "Org_Zip_Code": "68342",
                        "Org_State": "AL"
                    }
                }
            }
        }
       }

}
AUTOMATION_TASK = f"""
      ### **Advanced AI Agent for Automated LLC Registration** 
      - Wait for sometime until the screen is loaded and the fields are accurately populated
      For image buttons, try these approaches in order:
      -Only  search for business related registration not other. 

if their is button  with the name "Start Filing" or any relevant field then perform image click .
- Properly check for all the fields and button similar button names and wait until the required button or label is searched and desired action is performed
  Parent elements containing target text: //a[contains(., 'Start Filing')] | //button[contains(., 'Start Filing')]

      In case of 400 error reload the page and continue the automation from the point left  
      -Interact with the elements even though they are images not proper input fields.

      You are an advanced AI agent responsible for automating LLC registration form submissions across different state websites. Your task is to dynamically detect form fields, input the required data accurately, handle pop-ups or alerts, and ensure successful form submission. The AI should adapt to varying form structures and selectors without relying on predefined element locators.  
       If their are questions asked on the site like Has this entity been created in another state or country? or similar then select No from the dropdown 
       -Properly select all the fields and ensure that the fields are populated accurately
       - Properly Select the LLC entity type: `${jsonData["jsonData"]["EntityType"]["entityShortName"]}` or .`${jsonData["jsonData"]["EntityType"]["entityFullDesc"]}` from the dropdown or from any relevent field. 

       -Select the button with text Start Filing or Begin Filing or Start Register Business even if its an image ]
      ### **Task Execution Steps**  

      #### **1. Navigate to the Registration Page**  
    - Go to the url `${jsonData["jsonData"]["State"]["stateUrl"]}` url.  
    - Wait for the page to load completely.  

    #### **2. Handle Pop-ups and Initial UI Elements**  
    - Automatically close any pop-ups, notifications, or modals.  
    - Detect and handle Cloudflare captcha if present.  
    - Identify any initial login-related triggers:  
         - "Sign In" or "Login" buttons/links that open login forms  
    - Menu items or navigation elements that lead to login  
    - Modal triggers or popups for login  

#### **3. Perform Login (If Required)**  
- If a login form appears, identify:  
  - Username/email input field  
  - Password input field  
  - Login/Submit button  
- Enter credentials from the JSON:  
  - Username: `${jsonData["jsonData"]["State"]["filingWebsiteUsername"]}`  
  - Password: `${jsonData["jsonData"]["State"]["filingWebsitePassword"]}`  
- Click the login button and wait for authentication to complete.  

#### **4. Start LLC Registration Process**  
- Identify and click the appropriate link or button to start a new business  filing or Register  New Business button .

 -
- Select the LLC entity type: `${jsonData["jsonData"]["EntityType"]["entityShortName"]}` or .`${jsonData["jsonData"]["EntityType"]["entityFullDesc"]}` from the dropdown or from any relevent field. 
 - if the site ask for the options file online or upload the pdf select or click the file online button or select it from dropdown or from checkbox 
 -If a button has text like "Start Filing", "Begin Filing", or "Start Register Business", click it whether it's a standard button or an image.
 -If we need to save the name then click the save the name button or proceed next button.
- Proceed to the form.  

#### **5. Identify and Fill Required Fields**  
- Dynamically detect all required fields on the form and fill in the values from `${jsonData["jsonData"]["Payload"]}` make sure to flatten it at is dynamic json.  
- Ignore non-mandatory fields unless explicitly required for submission.  

#### **6. LLC Name and Designator**  
- Extract the LLC name from `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Name"]["CD_LLC_Name"]}`.  
- If  LLC a name does not work then replace the LLC name with the Alternate llc name  , use `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Name"]["CD_Alternate_LLC_Name"]}`.  
- Identify and select the appropriate business designator.  
- Enter the LLC name and ensure compliance with form requirements.  

#### **7. Registered Agent Information**  
- If an email field is detected, enter `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Registered_Agent"]["RA_Email_Address"]}`. 

- Identify and respond to any required business declarations (e.g., tobacco-related questions, management type).  

#### **8. Principal Office Address** (If Required)  
- Detect address fields and input the values accordingly:  
  - Street Address: `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Principal_Address"]["PA_Address_Line_1"]}`.  
  - City: `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Principal_Address"]["PA_City"]}`.  
  - State: `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Principal_Address"]["PA_State"]}`.  
  - ZIP Code: `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Principal_Address"]["PA_Zip_Code"]}`.  

#### **9. Organizer Information** (If Required)  
- If the form includes an organizer section, enter `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Organizer_Information"]["Organizer_Details"]["Org_Name"]}`.  

#### **10. Registered Agent Details**  
-Enter the Registered Agent details in its respective fields only by identifying the label for Registered Agent
- Detect and select if the registered agent is an individual or business entity.  
- If required, extract and split the registered agent’s full name   "from `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Registered_Agent"]["RA_Name"]}`, then input:  
  - First Name  
  - Last Name  
  -If for example the name of the registered agent is Interstate Agent Services LLC then the  First Name would be "Interstate" and the Last Name would be "Agent Services LLC"
- If an address field is present, enter:  
  - Street Address/ Address Line_1 `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Registered_Agent"]["Address"]["RA_Address_Line_1"]}`.  
  - City: `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Registered_Agent"]["Address"]["RA_City"]}`.  
  - ZIP Code or Zip Code or similar field: `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Registered_Agent"]["Address"]["RA_Zip_Code"]}`.  
  - IF  in the address their is requirement of County , select `${jsonData['jsonData']['County']['countyName']} either from dropdown or enter the value in it 

#### **11. Registered Agent Signature (If Required)**  
- If a signature field exists, input the registered agent’s first and last name.  

#### **12. Finalization and Submission**  
- Identify and check any agreement or confirmation checkboxes.  
- Click the final submission button to complete the filing.  

#### **13. Handling Pop-ups, Alerts, and Dialogs**  
- Detect and handle any pop-ups, alerts, or confirmation dialogs.  
- If an alert appears, acknowledge and dismiss it before proceeding.  

#### **14. Response and Error Handling**  
- Return `"Form filled successfully"` upon successful completion.  
- If an error occurs, log it and return `"Form submission failed: <error message>"`.  
- If required fields are missing or contain errors, capture the issue and provide feedback on what needs to be corrected.  

### **AI Agent Execution Guidelines**  
- Dynamically detect and interact with form elements without relying on predefined selectors.  
- Adapt to different form structures and ignore unnecessary fields.  
- Handle UI changes and errors efficiently, ensuring smooth automation.  
- Maintain accuracy and compliance while minimizing user intervention.  


"""

AUTOMATION_TASK1 = f"""
      ### **Highly Accurate AI Agent for LLC Registration Automation** 

      #### **Execution Guidelines:**
      - In case of the error "Site cannot be reached," reload the page.
      - Accurately detect and interact with all required form fields dynamically.
      - Ensure precise population of values from `jsonData`, verifying each entry before submission.
      - Adapt to different state-specific form layouts, handling field variations seamlessly.
      - Implement intelligent wait times and fallback strategies if elements are not immediately detected.
      - Manage multi-step forms efficiently, tracking progress and resuming from failures.

      #### **Handling Buttons and Interactive Elements:**
      - Identify and click buttons labeled "Start Filing," "Begin Filing," or "Start Register Business."
      - Ensure the button is visible and enabled before clicking.
      - Use image recognition if buttons are non-standard or embedded as images.
      -Properly click the "Start Filing" button and wait until the button is clicked try until the button is detected. 
      - XPath detection strategy: `//a[contains(., 'Start Filing')] | //button[contains(., 'Start Filing')]`.
      - **Ensure visibility before clicking:** Scroll the element into view before clicking.
      - **Retry clicking up to 3 times** if the button does not respond.
      - **Alternative click methods:**
        - If standard clicking fails, use JavaScript execution:
        ```js
        arguments[0].click();
        ```
        - If interception issues occur, use:
        ```js
        document.querySelector('button_selector').click();
        ```
      - **Error Handling:** If the click fails after retries, log the issue and attempt a page refresh before retrying.
      - Click on "Start Online Filing" or a relevant button by intelligently detecting it and retrying until successful.

      #### **Error Handling & Page Recovery:**
      - If a `400` error occurs, reload the page and continue from the last completed step.
      - Implement automatic retries for failed interactions and dynamically adjust timeouts.
      - Log errors with contextual information to facilitate debugging.

      ### **Task Execution Steps**  

      #### **1. Navigate to the Registration Page**  
      - Access the website at `${jsonData["jsonData"]["State"]["stateUrl"]}`.
      - Wait for the page to fully load before proceeding.
      - Validate correct page navigation to prevent misdirected automation.

      #### **2. Handle Pop-ups, Captchas, and Authentication**
      - Detect and dismiss pop-ups, notifications, or modals that obstruct navigation.
      - If a CAPTCHA is present, attempt automatic solving or notify for manual intervention.
      - Enter credentials from JSON:
        - Username: `${jsonData["jsonData"]["State"]["filingWebsiteUsername"]}`
        - Password: `${jsonData["jsonData"]["State"]["filingWebsitePassword"]}`

      #### **3. Initiate LLC Registration**
      - Locate and click appropriate links or buttons to start business registration such as "Register Your Business," "Begin Business," or "File New Business."
      - Select the LLC entity type from dropdown menus:
        - `${jsonData["jsonData"]["EntityType"]["entityShortName"]}` or
        - `${jsonData["jsonData"]["EntityType"]["entityFullDesc"]}`.
      - Choose "File Online" if given the option.
      - Click "Save Name" or "Proceed" as required.

      #### **4. Form Completion with Accurate Data Entry**
      - Dynamically identify and populate all mandatory fields using `${jsonData["jsonData"]["Payload"]}`.
      - **Implement fallback mechanisms:** If a field is not detected, retry and attempt to find alternative identifiers.
      - Validate each input field to ensure correctness before proceeding.
      - Log missing or problematic fields for debugging.
      - Ignore optional fields unless explicitly necessary.

      #### **5. Registered Agent Information**
      - Enter email: `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Registered_Agent"]["RA_Email_Address"]}`.
      - Detect and select if the registered agent is an individual or business entity.
      - Split and input first and last names where applicable.
      - Fill address fields including street, city, state, ZIP, and county.
      - If the form asks whether the "Registered Agent Mailing Address" is the same as the "Registered Agent Address," select "Yes."
      - Ensure fields are accurately detected and values properly entered before proceeding.

      #### **6. Principal Office Address**
      - Accurately fill out address fields:
        - Street: `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Principal_Address"]["PA_Address_Line_1"]}`.
        - City: `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Principal_Address"]["PA_City"]}`.
        - State: `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Principal_Address"]["PA_State"]}`.
        - ZIP Code: `${jsonData["jsonData"]["Payload"]["Entity_Formation"]["Principal_Address"]["PA_Zip_Code"]}`.
      - If required, select county from dropdown or manually enter value.
      - Cross-check ZIP code validity to prevent errors.

      #### **7. Final Review and Submission**
      - Accept agreements and confirm all required checkboxes.
      - Validate all input fields to ensure correctness before submission.
      - Click the final submission button to complete the filing.
      - Handle any confirmation pop-ups or alerts that appear post-submission.
      - Capture and store confirmation details, including filing reference numbers.

      #### **8. Intelligent Error Handling & Logging**
      - Implement robust exception handling for missing or undetectable fields.
      - Log errors in a structured format for debugging and tracking.
      - Retry failed actions dynamically with adaptive logic up to three times.
      - If document upload is required, check for a "Continue" button and proceed if optional.
      - Wait for selectors to be fully detected before performing actions.
      - Return `"Form filled successfully"` upon completion.

      ### **Optimized AI Agent Execution Guidelines**  
      - Ensure consistent automation across diverse state registration portals.
      - Adapt dynamically to UI changes with advanced form detection.
      - Validate field detection dynamically to prevent failures.
      - Maintain an optimal balance between speed and precision.
      - Minimize manual intervention while ensuring compliance with regulatory requirements.

"""

QA_URL = "https://accounts.intuit.com/app/sign-in?app_group=ExternalDeveloperPortal&asset_alias=Intuit.devx.devx&redirect_uri=https%3A%2F%2Fdeveloper.intuit.com%2Fapp%2Fdeveloper%2Fplayground%3Fcode%3DAB11727954854bIo1ROpRDYcmv1obOf0mpd0Hrei8JYX1HtMvS%26state%3DPlaygroundAuth%26realmId%3D9341453172471531&single_sign_on=false&partner_uid_button=google&appfabric=true"


QA_USERNAME="sales@redberyltech.com"

QA_PASSWORD="Passw0rd@123"

NC_USERNAME="shreyas.deodhare@redberyltech.com"

NC_PASSWORD="yD7?ddG0!$09"
QA_PASS ="RedBeryl#123"

NC_URL = "https://firststop.sos.nd.gov/forms/new/523"


UI_PROMPT= """
       
 Conduct a comprehensive analysis of the provided UI elements (screenshots) for compliance with the following standards and best practices, and to identify areas for improvement:

Accessibility:
ADA (Americans with Disabilities Act)
WCAG (Web Content Accessibility Guidelines)
Design Standards:
US Web Design System (USWDS)
Industry Standard UI Design
Usability and User Experience
Text Content Quality
Specific Areas of Focus:

Navigation
Evaluate: Clarity, intuitiveness, and ease of understanding of the navigation structure.
Check: Keyboard accessibility for all navigation elements.
Assess: Consistency of navigation elements (e.g., menus, breadcrumbs) throughout the UI.
Color and Typography
Evaluate: Color Contrast for readability, checking against WCAG guidelines.
Assess: Adherence to the USWDS color palette (if applicable) or other established color palettes.
Analyze: Font choices, sizing, and line spacing for optimal readability and visual appeal.
Forms
Evaluate: Clarity, conciseness, and user-friendliness of form labels.
Analyze: Appropriateness and clarity of input field labels and instructions.
Assess: Effectiveness of input validation mechanisms in guiding users and preventing errors.
Evaluate: Clarity, conciseness, and helpfulness of error messages.
Accessibility Features
Check: Screen reader compatibility (ARIA attributes, alternative text).
Assess: Appropriate use of ARIA attributes to enhance accessibility for screen reader users.
Evaluate: Effectiveness of focus management (visual cues).
Text Content
Check: Consistent use of sentence case throughout the UI.
Evaluate: Clarity, conciseness, and freedom from jargon in the text.
Analyze: Correctness of grammar and punctuation throughout all text elements.
Identify and report: Any grammatical errors (e.g., subject-verb agreement, pronoun errors, run-on sentences).
Assess: Consistency of terminology and phrasing across the entire UI.
Evaluate: Appropriateness of language for the target audience (business owners).
Assess: Appropriateness of the tone of the text (professional, friendly, informative).
UI Design
Evaluate: Effectiveness of whitespace, clear visual hierarchy, and logical layout.
Analyze: Visual prominence of important elements.
Assess: Consistency of design elements (buttons, icons, typography, spacing) throughout the UI.
Evaluate: Adaptability of the UI to different screen sizes and devices (desktops, tablets, mobile).
Assess: Alignment with current UI/UX best practices and modern design trends.
Process Accuracy (Specific to Business Registration)
Verify: Accuracy of the depicted process compared to the actual steps involved in filing a new business in the United States (e.g.,
Choosing a business structure (LLC, S-Corp, PLLC, Sole Proprietorship, Partnership, etc.)
Registering with the Secretary of State
Obtaining necessary licenses and permits
Understanding tax obligations
Legal and compliance requirements)
Evaluate: Completeness of the information provided regarding the business registration process (e.g., are all relevant business structures covered, are there links to relevant government resources?).
Assess: User-friendliness of the process flow presented in the UI.
Identify: Potential pain points and areas of confusion for users within the process.
Analyze: Compliance of the depicted process with current U.S. business laws and regulations.
Deliverables:

Detailed Compliance Report:
List: Identified issues related to accessibility, usability, design, and content.
Provide: Specific and actionable recommendations to address each identified issue.
Identify: Areas where the UI meets the specified standards.
Assess: Overall visual appeal, user experience, and alignment with industry best practices.
Analyze: Accuracy and user-friendliness of the depicted process, specifically within the U.S. context.
To provide the most accurate and helpful analysis, please provide the following:


Context:
Purpose of the UI (e.g., e-commerce website, government application).
Target audience for the UI (business owners, entrepreneurs).
Any relevant style guides or brand guidelines.
 Analyze this screenshot in detail:
            1. UI Elements and Layout
            2. Text Content Quality:
               - Identify any text present
               - Check grammar and spelling
               - Assess clarity and readability
               - Note any technical jargon
            3. Process Flow
            4. Compliance Requirements

            Provide detailed analysis with corrected text where applicable.
            ```  
Conduct a comprehensive UI compliance and usability analysis based on accessibility, usability, design standards, and content quality. Ensure adherence to U.S. best practices, legal requirements, and industry standards, specifically considering accessibility (ADA & WCAG), UI/UX best practices, and business registration accuracy. The agent must actively test and validate UI elements against WCAG compliance rather than just recommending improvements.  

1. Accessibility Compliance (Automated WCAG Testing)  
- Color Contrast Compliance (WCAG 2.1 AA & AAA)  
  - Analyze text and background contrast to detect low-contrast elements that fail WCAG standards.  
  - Validate compliance with minimum contrast ratios: 4.5:1 for text, 3:1 for UI components.  
  - Identify non-compliant colors and suggest corrected color codes.  

- Keyboard Navigation & Focus Management  
  - Verify that all interactive elements (buttons, links, forms) are navigable using the Tab key.  
  - Detect missing or inconsistent focus indicators and highlight accessibility violations.  
  - Ensure the tab order follows a logical sequence for ease of navigation.  

- Screen Reader & ARIA Attribute Testing  
  - Check for missing ARIA attributes in UI components.  
  - Verify that screen readers can accurately interpret UI elements (headings, buttons, forms, alerts).  
  - Identify improperly labeled elements and suggest correct ARIA roles or labels.  

2. Navigation & Usability  
- Evaluate clarity, intuitiveness, and ease of use of navigation menus.  
- Check keyboard accessibility for menus and interactive elements.  
- Detect inconsistent navigation elements (menus, breadcrumbs) across screens.  

3. Form Accessibility & Input Validation  
- Validate presence of clear and descriptive labels for all form fields.  
- Check if input fields provide helpful instructions or placeholders.  
- Ensure proper error handling and inline validation, with clear and accessible error messages.  
- Detect missing required field indicators and suggest proper implementations.  

4. UI Design Compliance (USWDS & Industry Standards)  
- Analyze button, icon, typography, and spacing consistency.  
- Assess visual hierarchy and layout logic for usability.  
- Validate UI adaptability across desktop, tablet, and mobile devices.  

5. Text Content Quality & Grammar Validation  
- Detect grammar, punctuation, and spelling errors in UI text.  
- Ensure sentence case consistency throughout UI.  
- Identify instances of unclear or jargon-heavy text and suggest more user-friendly phrasing.  

6. Business Registration Process Accuracy  
- Verify correctness of business registration steps based on U.S. regulations.  
- Identify missing steps or incomplete guidance (e.g., tax registration, licenses).  
- Check if links to relevant government resources are provided for user reference.  

7. Comprehensive UI Testing & Issue Reporting  
- Automatically detect and highlight UI issues in screenshots.  
- Generate a detailed WCAG compliance report, listing all violations and actionable fixes.  
- Provide recommended code snippets or design modifications to resolve detected issues.  
- Identify any inconsistencies or missing elements impacting user experience.  

Deliverables:  
1. Automated Compliance Report – Issues, compliance status, and suggested fixes.  
2. Highlighted Non-Compliant UI Elements – Identifying specific problem areas in screenshots.  
3. Actionable Recommendations – Providing practical solutions (CSS fixes, ARIA attributes, improved error handling).  
4. Overall Usability and UI Evaluation – Summarizing strengths, weaknesses, and compliance status.  

The agent must conduct real-time WCAG compliance testing on provided screenshots, highlighting specific elements that fail accessibility standards and offering actionable fixes.  
```  
  
"""

UI_ANALYSIS_PROMPT = """
  Analyze this screenshot in detail:
  1. UI Elements and Layout
  2. Text Content Quality:
     - Identify any text present
     - Check grammar and spelling
     - Assess clarity and readability
     - Note any technical jargon
  3. Process Flow
  4. Compliance Requirements

  Provide detailed analysis with corrected text where applicable.
  """

