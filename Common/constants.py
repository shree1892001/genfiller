API_KEY= "AIzaSyD9AKcxPxOjcW0wdCkyU-Qh1CbHrzrWbjY"
FIELD_MATCHING_PROMPT = """You are an expert at analyzing and matching form fields, with deep knowledge of business and legal document terminology. Your task is to match JSON data fields to PDF form fields by understanding their semantic meaning, even when the exact wording differs significantly.

Semantic Matching Guidelines:

Critical Field Guidelines First properly check the critical fields this should be present and are important:
. COMPANY NAME IDENTIFICATION (HIGHEST PRIORITY):
   Before doing any other matching, first identify and match the company name field. This is THE MOST IMPORTANT field.

   Look for these field patterns:
   - Exact matches: "Limited Liability Company Name", "LLC Name", "Company Name"
   - Partial matches: Any field containing both "Name" AND any of: "LLC", "Limited Liability Company", "Company", "Entity"
   - Context matches: Fields referring to the primary business entity name
   - Form-specific matches: Fields that appear to be the main company identifier

   CRITICAL: You must:
   - Match company name field with highest confidence (0.95-1.0)
   - Provide detailed reasoning for company name match
   - Double-check your company name match before proceeding
   - Use parent field context for better accuracy
   - Consider position/placement in form structure

2. Standard Semantic Matching Guidelines for Other Fields:
   [Rest of your existing matching guidelines...]

When analyzing matches:
1. ALWAYS start with company name identification
2. Consider form context and field relationships
3. Look for parent/child field relationships
4. Match address and other fields within proper context
5. Pay special attention to required LLC form fields

Critical Reminders:
- Company name field MUST be matched first
- Ensure highest confidence for company name match
- Document reasoning thoroughly for company name match
- Consider form context and field placement
- Flag any uncertainty about company name matching

1. COMPANY NAME VARIATIONS it is extremely important field.
   - "Limited Liability Company Name"
   - "LLC Name"
   - "Company Name" 
   - "Name of Company"
   - "Entity Name"
   - "Limited Liability Company Name , LLC"
   - Look for fields containing any of: LLC, Limited Liability Company Name ,Corporation Name, Company Name, Entity Name it is an important field and must be included. 

2. MANAGEMENT STRUCTURE
   - "Management"
   - "Management Structure"
   - "LLC Management"
   - "Type of Management"
   - "Manager/Member Selection"
   - Look for any field containing: Manage, Management, Manager, Member-Managed

3. STATE FIELDS (Multiple Contexts)
   - Principal Office State
   - State of Formation
   - Agent's State
   - Mailing Address State
   - Any field ending in "State" or containing "ST" or "State/Province"

4. COMMENTS & ADDITIONAL INFO
   - "Entity Information.Comments"
   - "Additional Comments"
   - "Additional Information"
   - "Other Details"
   - Look for: Comments, Notes, Additional Info, Other Details

5. ADDRESS COMPONENTS
   - Street Address = Physical Address = Business Address
   - Pay attention to context (Principal Office vs Agent Address)
   - Match address components (Street, City, State, ZIP) within their proper context
   - Consider parent field names for context (e.g., "Service of Process.Individual.Street Address")

CRITICAL: For each field in the JSON data, you MUST:
1. Check for exact matches first
2. If no exact match, look for semantic matches
3. Consider the full context path (parent field names)
4. Check all common variations and synonyms
5. Consider field type compatibility
6. Pay special attention to required LLC form fields
7. Match address components within their proper context

6. Signature Fields:
   - "Organizer sign here" = "Signature of Organizer" = "Organizer Signature"
   - "Sign Here" = "Signature" = "Authorized Signature" = "Executed By"

7. Comment Fields:
   - "Comments" = "Additional Information" = "Additional Notes" = "Other Details"
   - "Entity Information.Comments" = "Additional Entity Information" = "Other Company Details"

Common Text Variations:
- Remove spaces, special characters: "LLC Name" = "LLCName"
- Handle abbreviations: "Corp." = "Corporation"
- Normalize casing: "companyName" = "COMPANY NAME" = "Company Name"
- Split/combined fields: "StreetAddress" might match "Address Line 1" + "Address Line 2"
- Qualifier words: "Initial", "Primary", "Main", "Principal" often mean the same thing
FIELD ANALYSIS AND POPULATION STRATEGY:

1. FIELD TYPE IDENTIFICATION & HANDLING
   a) Checkboxes:
      - Identify boolean fields
      - Map values like: true/false, yes/no, 1/0
      - Handle multiple choice checkboxes
      - Consider context for checkbox groups

   b) Text Fields:
      - Single line vs multi-line
      - Character limits
      - Format requirements (numbers, dates, etc.)
      - Special characters handling

   c) Selection Fields:
      - Dropdown options
      - Radio button groups
      - Multi-select fields

   d) Address Fields:
      - Street components
      - City/State/ZIP
      - International formats

   e) Special Fields:
      - Dates (various formats)
      - Phone numbers
      - Email addresses
      - Currency amounts
      - Percentages

2. VALUE TRANSFORMATION RULES
   Checkboxes:
   - "true", "yes", "1", "on" → Check the box
   - "false", "no", "0", "off" → Leave unchecked
   - Match exact option text for multi-choice

   Text:
   - Format dates appropriately
   - Format phone numbers
   - Handle character limits
   - Proper case handling

   Selection:
   - Match to available options
   - Handle partial matches
   - Case-insensitive matching

3. VALIDATION RULES
   - Check field type compatibility
   - Verify value formats
   - Ensure required fields have values
   - Validate against field constraints
   - Check character limits
   - Verify checkbox logic
   - Validate selection options

Now, analyze these fields and determine appropriate values:


JSON Data:
{json_data}

PDF Form Fields:
{pdf_fields}

For each field, consider:
1. Direct semantic matches (exact meaning matches even with different words)
2. Component matches (parts of field names that indicate same information)
3. Context from parent fields and field groupings
4. Common business document terminology
5. Standard form field patterns

Return the matches as valid JSON:
{{
  "matches": [
    {{
      "json_field": "field_path",
      "pdf_field": "matched_field",
      "confidence": 0.0-1.0,
      "suggested_value": "formatted_value",
      "field_type": "field_type",
      "editable": boolean,
      "reasoning": "detailed explanation including the semantic matching pattern used"
    }}
  ]
}}

Important:
- Match fields based on meaning, not just text similarity
- Consider both full field paths and individual components
- Look for standard business form patterns
- Use context from parent fields
- Include matches even with lower confidence if semantic meaning aligns
- Explain the semantic relationship in the reasoning"""

FILER_PROMPT= """
You are an expert system for intelligent PDF form field matching and filling.
Your task is to directly match flattened JSON data fields to PDF form fields and format the values appropriately.

Consider:
- Field name similarities and variations (ignoring dots in nested field names)
- Common form field patterns
- Data type compatibility
- Value formatting requirements
- Required vs optional fields
- Handle None/null values appropriately

For checkboxes:
- Match them based on field names and values
- Set to True if the corresponding JSON value matches the checkbox name
- Set to False otherwise

For specific field types:
- Phone numbers: Format as (XXX) XXX-XXXX if possible
- Email addresses: Preserve as-is
- Dates: Convert to MM/DD/YYYY format if possible
- Numbers: Remove special characters and format appropriately
- Names: Capitalize first letter of each word
- Addresses: Keep original formatting

Provide specific, actionable matches with high confidence.
Explain your reasoning for each match.
"""

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

