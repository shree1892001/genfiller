import json
import os
from typing import Dict, Any

class GenFiller1:
    def __init__(self, form_data_path: str):
        self.form_data = self._load_form_data(form_data_path)
        self.entity_formation_data = self.form_data['data']['orderDetails']['strapiOrderFormJson']['Payload']['Entity_Formation']

    def _load_form_data(self, path: str) -> Dict[str, Any]:
        with open(path, 'r') as f:
            return json.load(f)

    def _extract_address_fields(self, address_dict: Dict[str, str]) -> Dict[str, str]:
        address_mapping = {
            'Address_Line_1': 'street_address',
            'Address_Line_2': 'street_address2',
            'City': 'city',
            'State': 'state',
            'Zip_Code': 'zip_code'
        }
        
        return {value: address_dict.get(f'{prefix}_{key}')
                for prefix in ['PA', 'RA', 'BI', 'MI']
                for key, value in address_mapping.items()}

    def get_form_field_mapping(self) -> Dict[str, str]:
        """Dynamically generate form field mapping based on the JSON structure"""
        field_mapping = {}
        
        # Entity Name Fields
        name_data = self.entity_formation_data['Name']
        field_mapping.update({
            'entity_name': name_data['CD_LLC_Name'],
            'alternate_name': name_data['CD_Alternate_LLC_Name']
        })

        # Address Fields
        addresses = self._extract_address_fields(self.entity_formation_data['Principal_Address'])
        field_mapping.update(addresses)

        # Registered Agent Fields
        ra_data = self.entity_formation_data['Registered_Agent']
        field_mapping.update({
            'agent_name': ra_data['RA_Name'],
            'agent_email': ra_data['RA_Email_Address'],
            'agent_phone': ra_data['RA_Contact_No']
        })

        # Billing Information
        billing_data = ra_data['Billing_Information']
        field_mapping.update({
            'billing_name': billing_data['BI_Name'],
            'billing_email': billing_data['BI_Email_Address'],
            'billing_phone': billing_data['BI_Contact_No']
        })

        # Mailing Information
        mailing_data = ra_data['Mailing_Information']
        field_mapping.update({
            'mailing_name': mailing_data['MI_Name'],
            'mailing_email': mailing_data['MI_Email_Address'],
            'mailing_phone': mailing_data['MI_Contact_No']
        })

        return field_mapping

    def fill_form(self, pdf_path: str, output_path: str) -> None:
        """Fill the PDF form using the dynamically generated field mapping"""
        field_mapping = self.get_form_field_mapping()
        
        # Here you would integrate with your PDF filling library
        # Example using a hypothetical pdf_filler:
        # pdf_filler = PDFFiller(pdf_path)
        # pdf_filler.fill_fields(field_mapping)
        # pdf_filler.save(output_path)

        print(f'Form filled successfully with the following mapping:')
        for field, value in field_mapping.items():
            print(f'{field}: {value}')

def main():
    # Example usage
    form_data_path = 'Services/form_data.json'
    pdf_path = 'path/to/your/form.pdf'
    output_path = 'path/to/output/filled_form.pdf'
    
    filler = GenFiller1(form_data_path)
    filler.fill_form(pdf_path, output_path)

if __name__ == '__main__':
    main()