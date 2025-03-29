import asyncio
import json
import re
import fitz
from pydantic_ai import Agent
from pydantic_ai.models.gemini import GeminiModel
from Common.constants import  *
API_KEYS = {"field_matcher": API_KEY_1}


class PDFFieldReplacer:
    def __init__(self):
        self.agent = Agent(
            model=GeminiModel("gemini-1.5-flash", api_key=API_KEYS["field_matcher"]),
            system_prompt="You are an expert at understanding semantic relationships between PDF fields and JSON data. Provide the most accurate field mapping."
        )

    async def replace_placeholders_with_values(self, pdf_path: str, json_data: dict, output_path: str):
        print("🔎 Starting placeholder replacement using AI matching...")
        doc = fitz.open(pdf_path)

        for page_num, page in enumerate(doc, start=1):
            for widget in page.widgets():
                if widget.field_value and "{{json_key:" in widget.field_value:
                    match = re.search(r"{{json_key:([^}]+)}}", widget.field_value)
                    if match:
                        placeholder_key = match.group(1)
                        suggested_value = await self.get_suggested_value(placeholder_key, json_data)

                        if suggested_value is not None:
                            try:
                                widget.field_value = str(suggested_value)
                                widget.update()
                                print(f"✅ Replaced '{placeholder_key}' with '{suggested_value}' on Page {page_num}")
                            except Exception as e:
                                print(f"⚠️ Error replacing value on Page {page_num}: {e}")

        doc.save(output_path)
        doc.close()
        print(f"✅ PDF saved to {output_path}")

    async def get_suggested_value(self, placeholder_key: str, json_data: dict):
        # Flatten JSON data for better AI analysis
        flat_data = self.flatten_json(json_data)
        prompt = (f"Given the placeholder '{placeholder_key}', identify the most relevant value from the JSON data.")

        response = await self.agent.run(prompt, context={"json_data": flat_data})
        return response.strip() if response else None

    def flatten_json(self, data, prefix=""):
        items = {}
        for key, value in data.items():
            new_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                items.update(self.flatten_json(value, new_key))
            else:
                items[new_key] = value
        return items


async def main():
    replacer = PDFFieldReplacer()
    await replacer.replace_placeholders_with_values('MIchiganCorp.pdf', json.load(open('form_data.json')),
                                                    'Output_Filled.pdf')


if __name__ == "__main__":
    asyncio.run(main())
