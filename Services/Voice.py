from playwright.sync_api import sync_playwright
import speech_recognition as sr
import pyttsx3
import re
import json
import ast
import google.generativeai as genai
from Common.constants import *
import time
from typing import List, Optional, Dict


class VoiceWebAssistant:
    def __init__(self, gemini_api_key):
        genai.configure(api_key=gemini_api_key)
        self.llm = genai.GenerativeModel('gemini-1.5-flash')

        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self._setup_voice_engine()

        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=False, slow_mo=500)
        self.context = self.browser.new_context(viewport={'width': 1280, 'height': 800})
        self.page = self.context.new_page()

        self.input_mode = self._get_initial_mode()
        print(f"🚀 Assistant initialized in {self.input_mode} mode")

    def _setup_voice_engine(self):
        self.engine = pyttsx3.init()
        voices = self.engine.getProperty('voices')
        self.engine.setProperty('voice', voices[1].id)
        self.engine.setProperty('rate', 150)
        self.engine.setProperty('volume', 0.9)

    def _get_initial_mode(self):
        print("\n🔊 Select input mode:")
        print("1. Voice\n2. Text")
        while True:
            choice = input("Choice (1/2): ").strip()
            return 'voice' if choice == '1' else 'text'

    def speak(self, text):
        print(f"ASSISTANT: {text}")
        self.engine.say(text)
        self.engine.runAndWait()

    def listen(self):
        if self.input_mode == 'voice':
            return self._listen_voice()
        return self._listen_text()

    def _listen_voice(self):
        try:
            with self.microphone as source:
                print("\n🎤 Listening...")
                self.recognizer.adjust_for_ambient_noise(source)
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                return self.recognizer.recognize_google(audio).lower()
        except sr.UnknownValueError:
            return ""
        except Exception as e:
            print(f"Audio error: {e}")
            return ""

    def _listen_text(self):
        try:
            text = input("\n⌨️ Command: ").strip()
            if text.lower() in ["voice", "voice mode"]:
                self.input_mode = 'voice'
                self.speak("Voice mode activated")
            return text
        except Exception as e:
            print(f"Input error: {e}")
            return ""

    def browse_website(self, url):
        try:
            if "://" in url:
                self.speak(f"🌐 Navigating to {url}")
                self.page.goto(url, wait_until="networkidle", timeout=20000)
            elif url.startswith('#') or url.startswith('/#'):
                current_url = self.page.url
                base_url = current_url.split('#')[0]
                new_url = f"{base_url}{url}" if url.startswith('#') else f"{base_url}{url[1:]}"
                self.speak(f"🌐 Navigating within page to {url}")
                self.page.goto(new_url, wait_until="networkidle", timeout=20000)
            elif not url.startswith(('http://', 'https://')):
                if "/" in url and not url.startswith("/"):
                    domain = url.split("/")[0]
                    self.speak(f"🌐 Navigating to https://{domain}")
                    self.page.goto(f"https://{domain}", wait_until="networkidle", timeout=20000)
                else:
                    self.speak(f"🌐 Navigating to https://{url}")
                    self.page.goto(f"https://{url}", wait_until="networkidle", timeout=20000)
            else:
                current_url = self.page.url
                domain_match = re.match(r'^(?:http|https)://[^/]+', current_url)
                if domain_match:
                    domain = domain_match.group(0)
                    new_url = f"{domain}/{url}"
                    self.speak(f"🌐 Navigating to {new_url}")
                    self.page.goto(new_url, wait_until="networkidle", timeout=20000)
                else:
                    self.speak(f"🌐 Navigating to https://{url}")
                    self.page.goto(f"https://{url}", wait_until="networkidle", timeout=20000)

            self.speak(f"📄 Loaded: {self.page.title()}")
            self._dismiss_popups()
            return True
        except Exception as e:
            self.speak(f"❌ Navigation failed: {str(e)}")
            if url.startswith('#') or url.startswith('/#'):
                if 'signin' in url or 'login' in url:
                    self.speak("Trying to find login option...")
                    login_selectors = self._get_llm_selectors("find login or sign in link or button",
                                                              self._get_page_context())
                    for selector in login_selectors:
                        try:
                            if self.page.locator(selector).count() > 0:
                                self.page.locator(selector).first.click()
                                self.page.wait_for_timeout(2000)
                                self.speak("Found and clicked login option")
                                return True
                        except Exception as click_err:
                            continue
            return False

    def _dismiss_popups(self):
        try:
            context = self._get_page_context()
            popup_selectors = self._get_llm_selectors(
                "find popup close button, cookie acceptance button, or dismiss button", context)

            for selector in popup_selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self.page.locator(selector).first.click(timeout=2000)
                        self.speak("🗑️ Closed popup")
                        self.page.wait_for_timeout(1000)
                        break
                except:
                    pass
        except:
            pass

    def process_command(self, command):
        if not command:
            return True

        command_lower = command.lower()
        if command_lower in ["exit", "quit"]:
            return False
        if command_lower == "help":
            self._show_help()
            return True

        if re.match(r'^(go to|navigate to|open)\s+', command_lower):
            match = re.match(r'^(go to|navigate to|open)\s+(.*)', command, re.IGNORECASE)
            if match:
                url = match.group(2)
                return self.browse_website(url)

        if command_lower in ["text", "voice"]:
            self.input_mode = command_lower
            self.speak(f"Switched to {command_lower} mode")
            return True

        if self._handle_direct_commands(command):
            return True

        action_data = self._get_actions(command)
        return self._execute_actions(action_data)

    def _handle_direct_commands(self, command):
        """Handle common commands directly, using LLM for complex selector generation"""
        login_match = re.search(r'login with email\s+(\S+)\s+and password\s+(\S+)', command, re.IGNORECASE)
        if login_match:
            email, password = login_match.groups()

            context = self._get_page_context()

            email_selectors = self._get_llm_selectors("find email or username input field", context)
            email_found = False
            for selector in email_selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self._retry_type(selector, email, "email address")
                        email_found = True
                        break
                except:
                    continue

            password_selectors = self._get_llm_selectors("find password input field", context)
            password_found = False
            for selector in password_selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self._retry_type(selector, password, "password")
                        password_found = True
                        break
                except:
                    continue

            if email_found and password_found:
                login_button_selectors = self._get_llm_selectors("find login or sign in button", context)
                for selector in login_button_selectors:
                    try:
                        if self.page.locator(selector).count() > 0:
                            self._retry_click(selector, "login button")
                            return True
                    except:
                        continue

                self.speak("Filled login details but couldn't find login button")
                return True
            else:
                self.speak("Could not find all required login fields")
                return False

        search_match = re.search(r'search(?:\s+for)?\s+(.+)', command, re.IGNORECASE)
        if search_match:
            query = search_match.group(1)

            context = self._get_page_context()
            search_selectors = self._get_llm_selectors("find search input field", context)

            for selector in search_selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self._retry_type(selector, query, "search query")
                        self.page.locator(selector).press("Enter")
                        self.speak(f"🔍 Searching for '{query}'")
                        self.page.wait_for_timeout(3000)
                        return True
                except:
                    continue

            self.speak("Could not find search field")
            return False

        menu_click_match = re.search(r'click(?:\s+on)?\s+menu\s+item\s+(.+)', command, re.IGNORECASE)
        if menu_click_match:
            menu_item = menu_click_match.group(1)

            context = self._get_page_context()
            menu_selectors = self._get_llm_selectors(f"find menu item '{menu_item}'", context)

            for selector in menu_selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self._retry_click(selector, f"menu item '{menu_item}'")
                        self.page.wait_for_timeout(1000)
                        return True
                except:
                    continue

            self.speak(f"Could not find menu item '{menu_item}'")
            return False

        submenu_match = re.search(r'navigate(?:\s+to)?\s+(.+?)(?:\s+under|\s+in)?\s+(.+)', command, re.IGNORECASE)
        if submenu_match:
            target_item, parent_menu = submenu_match.groups()

            context = self._get_page_context()
            parent_selectors = self._get_llm_selectors(f"find menu item '{parent_menu}'", context)

            parent_found = False
            for selector in parent_selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self.page.locator(selector).hover()
                        self.speak(f"Hovering over '{parent_menu}' menu")
                        self.page.wait_for_timeout(1000)
                        parent_found = True
                        break
                except:
                    continue

            if not parent_found:
                self.speak(f"Could not find parent menu '{parent_menu}'")
                return False

            updated_context = self._get_page_context()
            submenu_selectors = self._get_llm_selectors(f"find submenu item '{target_item}' under '{parent_menu}'",
                                                        updated_context)

            for selector in submenu_selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self._retry_click(selector, f"submenu item '{target_item}'")
                        self.page.wait_for_timeout(1000)
                        return True
                except:
                    continue

            self.speak(f"Could not find submenu item '{target_item}' under '{parent_menu}'")
            return False

        checkbox_match = re.search(r'(check|uncheck|toggle)(?:\s+the)?\s+(.+)', command, re.IGNORECASE)
        if checkbox_match:
            action, checkbox_label = checkbox_match.groups()

            context = self._get_page_context()
            checkbox_selectors = self._get_llm_selectors(f"find checkbox with label '{checkbox_label}'", context)

            return self._try_selectors_for_checkbox(checkbox_selectors, action.lower(), checkbox_label)

        dropdown_match = re.search(r'select\s+(.+?)(?:\s+from|\s+in)?\s+(.+?)(?:\s+dropdown)?', command, re.IGNORECASE)
        if dropdown_match:
            option, dropdown_name = dropdown_match.groups()

            context = self._get_page_context()
            dropdown_selectors = self._get_llm_selectors(f"find dropdown with name '{dropdown_name}'", context)

            return self._try_selectors_for_select(dropdown_selectors, option, dropdown_name)

        return False

    def _get_llm_selectors(self, task, context):
        """Use LLM to generate selectors for a task based on page context"""
        prompt = f"""
Based on the current web page context, generate the 5 most likely CSS selectors to {task}.
Focus on precise selectors that would uniquely identify the element.

Current Page:
Title: {context.get('title', 'N/A')}
URL: {context.get('url', 'N/A')}

Input Fields Found:
{self._format_input_fields(context.get('input_fields', []))}

Menu Items Found:
{self._format_menu_items(context.get('menu_items', []))}

Relevant HTML:
{context.get('html', '')[:1000]}

Respond ONLY with a JSON array of selector strings. Example:
["selector1", "selector2", "selector3", "selector4", "selector5"]
"""

        try:
            response = self.llm.generate_content(prompt)
            print(f"🔍 Selector generation response:\n", response.text)
            selectors_match = re.search(r'\[.*\]', response.text, re.DOTALL)
            if selectors_match:
                selectors_json = selectors_match.group(0)
                selectors = json.loads(selectors_json)
                return selectors[:5]
            else:
                return []
        except Exception as e:
            print(f"Selector generation error: {e}")
            return []

    def _format_input_fields(self, input_fields):
        """Format input fields for LLM prompt"""
        result = ""
        for idx, field in enumerate(input_fields):
            result += f"{idx + 1}. {field.get('tag', 'input')} - "
            result += f"type: {field.get('type', '')}, "
            result += f"id: {field.get('id', '')}, "
            result += f"name: {field.get('name', '')}, "
            result += f"placeholder: {field.get('placeholder', '')}, "
            result += f"aria-label: {field.get('aria-label', '')}\n"
        return result

    def _format_menu_items(self, menu_items):
        """Format menu items for LLM prompt"""
        result = ""
        for idx, item in enumerate(menu_items):
            submenu_indicator = " (has submenu)" if item.get("has_submenu") else ""
            result += f"{idx + 1}. {item.get('text', '')}{submenu_indicator}\n"
        return result

    def _get_actions(self, command):
        context = self._get_page_context()
        prompt = self._create_prompt(command, context)

        try:
            response = self.llm.generate_content(prompt)
            print("🔍 Raw LLM response:\n", response.text)
            return self._parse_response(response.text)
        except Exception as e:
            print(f"LLM Error: {e}")
            return {"error": str(e)}

    def _get_page_context(self):
        try:
            self.page.wait_for_timeout(1000)

            input_fields = []
            inputs = self.page.locator("input:visible, textarea:visible, select:visible")
            count = inputs.count()

            for i in range(min(count, 10)):
                try:
                    field = inputs.nth(i)
                    field_info = {
                        "tag": field.evaluate("el => el.tagName.toLowerCase()"),
                        "type": field.evaluate("el => el.type || ''"),
                        "id": field.evaluate("el => el.id || ''"),
                        "name": field.evaluate("el => el.name || ''"),
                        "placeholder": field.evaluate("el => el.placeholder || ''"),
                        "aria-label": field.evaluate("el => el.getAttribute('aria-label') || ''")
                    }
                    input_fields.append(field_info)
                except:
                    pass

            menu_items = []
            try:
                menus = self.page.locator(
                    "[role='menubar'] [role='menuitem'], .p-menuitem, nav a, .navigation a, .menu a, header a")
                menu_count = menus.count()

                for i in range(min(menu_count, 20)):
                    try:
                        menu_item = menus.nth(i)
                        text = menu_item.inner_text().strip()
                        if text:
                            has_submenu = menu_item.locator(
                                ".p-submenu-icon, [class*='submenu'], [class*='dropdown'], [class*='caret']").count() > 0
                            menu_items.append({
                                "text": text,
                                "has_submenu": has_submenu
                            })
                    except:
                        pass
            except:
                pass

            buttons = []
            try:
                button_elements = self.page.locator(
                    "button:visible, [role='button']:visible, input[type='submit']:visible, input[type='button']:visible")
                button_count = button_elements.count()

                for i in range(min(button_count, 10)):
                    try:
                        button = button_elements.nth(i)
                        text = button.inner_text().strip()
                        buttons.append({
                            "text": text,
                            "id": button.evaluate("el => el.id || ''"),
                            "class": button.evaluate("el => el.className || ''"),
                            "type": button.evaluate("el => el.type || ''")
                        })
                    except:
                        pass
            except:
                pass

            return {
                "title": self.page.title(),
                "url": self.page.url,
                "text": self.page.locator("body").inner_text()[:1000],
                "html": self._filter_html(self.page.locator("body").inner_html()[:4000]),
                "input_fields": input_fields,
                "menu_items": menu_items,
                "buttons": buttons
            }
        except Exception as e:
            print(f"Context error: {e}")
            return {}

    def _filter_html(self, html):
        return re.sub(
            r'<(input|button|a|form|select|textarea|div|ul|li)[^>]*>',
            lambda m: m.group(0) + '\n',
            html
        )[:3000]

    def _create_prompt(self, command, context):
        input_fields_info = ""
        if "input_fields" in context and context["input_fields"]:
            input_fields_info = "Input Fields Found:\n"
            for idx, field in enumerate(context["input_fields"]):
                input_fields_info += f"{idx + 1}. {field['tag']} - type: {field['type']}, id: {field['id']}, name: {field['name']}, placeholder: {field['placeholder']}, aria-label: {field['aria-label']}\n"

        menu_items_info = ""
        if "menu_items" in context and context["menu_items"]:
            menu_items_info = "Menu Items Found:\n"
            for idx, item in enumerate(context["menu_items"]):
                submenu_indicator = " (has submenu)" if item.get("has_submenu") else ""
                menu_items_info += f"{idx + 1}. {item['text']}{submenu_indicator}\n"

        buttons_info = ""
        if "buttons" in context and context["buttons"]:
            buttons_info = "Buttons Found:\n"
            for idx, button in enumerate(context["buttons"]):
                buttons_info += f"{idx + 1}. {button['text']} - id: {button['id']}, class: {button['class']}, type: {button['type']}\n"

        return f"""Analyze the web page and generate precise Playwright selectors to complete: \"{command}\".

Selector Priority:
1. ID (
2. Type and Name (input[type='email'], input[name='email'])
3. ARIA labels ([aria-label='Search'])
4. Data-testid ([data-testid='login-btn'])
5. Button text (button:has-text('Sign In'))
6. Semantic CSS classes (.login-button, .p-menuitem)
7. Input placeholder (input[placeholder='Email'])

For tiered menus:
- Parent menus: .p-menuitem, [role='menuitem']
- Submenu items: .p-submenu-list .p-menuitem, ul[role='menu'] [role='menuitem']
- For dropdown/select interactions: Use 'select_option' action when appropriate

Current Page:
Title: {context.get('title', 'N/A')}
URL: {context.get('url', 'N/A')}
Visible Text: {context.get('text', '')[:500]}

{input_fields_info}
{menu_items_info}
{buttons_info}

Relevant HTML:
{context.get('html', '')}

Respond ONLY with JSON in this format:
{{
  "actions": [
    {{
      "action": "click|type|navigate|hover|select_option|check|uncheck|toggle",
      "selector": "CSS selector",
      "text": "(only for type)",
      "purpose": "description",
      "url": "(only for navigate actions)",
      "option": "(only for select_option)",
      "fallback_selectors": ["alternate selector 1", "alternate selector 2"]
    }}
  ]
}}"""

    def _parse_response(self, raw_response):
        try:
            json_str = re.search(r'\{.*\}', raw_response, re.DOTALL)
            if not json_str:
                raise ValueError("No JSON found in response")

            json_str = json_str.group(0)
            json_str = json_str.replace('null', 'None')
            response = ast.literal_eval(json_str)

            return self._validate_actions(response.get('actions', []))

        except Exception as e:
            print(f"Parse error: {e}")
            return {"error": str(e)}

    def _validate_actions(self, actions):
        valid = []
        for action in actions:
            if not self._is_valid_action(action):
                continue
            valid.append({
                'action': action['action'].lower(),
                'selector': action.get('selector', ''),
                'text': action.get('text', ''),
                'purpose': action.get('purpose', ''),
                'url': action.get('url', ''),
                'option': action.get('option', ''),
                'fallback_selectors': action.get('fallback_selectors', [])
            })
        return {"actions": valid} if valid else {"error": "No valid actions found"}

    def _is_valid_action(self, action):
        requirements = {
            'click': ['selector'],
            'type': ['selector', 'text'],
            'navigate': [],
            'hover': ['selector'],
            'select_option': ['selector', 'option'],
            'check': ['selector'],
            'uncheck': ['selector'],
            'toggle': ['selector']
        }
        action_type = action.get('action', '').lower()

        if action_type == 'navigate':
            return True

        return all(k in action and action[k] is not None for k in requirements.get(action_type, []))

    def _execute_actions(self, action_data):
        if 'error' in action_data:
            self.speak("⚠️ Action could not be completed. Switching to fallback...")
            return False

        for action in action_data.get('actions', []):
            try:
                self._perform_action(action)
                self.page.wait_for_timeout(1000)
            except Exception as e:
                self.speak(f"❌ Failed to {action.get('purpose', 'complete action')}")
                print(f"Action Error: {str(e)}")
                return False
        return True

    def _perform_action(self, action):
        action_type = action['action']

        if action_type == 'click':
            selector = action.get('selector', '')
            fallbacks = action.get('fallback_selectors', [])
            self._try_selectors_for_click([selector] + fallbacks, action['purpose'])
        elif action_type == 'type':
            selector = action.get('selector', '')
            fallbacks = action.get('fallback_selectors', [])
            self._try_selectors_for_type([selector] + fallbacks, action['text'], action['purpose'])
        elif action_type == 'navigate':
            url = action.get('url', '')
            if not url:
                purpose = action.get('purpose', '')
                nav_selectors = self._find_navigation_selectors(purpose)
                if nav_selectors:
                    for selector in nav_selectors:
                        try:
                            if self.page.locator(selector).count() > 0:
                                self._retry_click(selector, f"Navigate to {purpose}")
                                return
                        except:
                            continue
                self.speak(f"Could not find a way to {purpose}.")
            else:
                self.browse_website(url)
        elif action_type == 'hover':
            selector = action.get('selector', '')
            fallbacks = action.get('fallback_selectors', [])
            self._try_selectors_for_hover([selector] + fallbacks, action['purpose'])
        elif action_type == 'select_option':
            selector = action.get('selector', '')
            option = action.get('option', '')
            fallbacks = action.get('fallback_selectors', [])
            self._try_selectors_for_select([selector] + fallbacks, option, action['purpose'])
        elif action_type in ['check', 'uncheck', 'toggle']:
            selector = action.get('selector', '')
            fallbacks = action.get('fallback_selectors', [])
            self._try_selectors_for_checkbox([selector] + fallbacks, action_type, action['purpose'])
        else:
            raise ValueError(f"Unknown action: {action_type}")

    def _retry_click(self, selector, purpose):
        tries = 3
        for attempt in range(tries):
            try:
                self.page.locator(selector).first.click(timeout=5000)
                self.speak(f"👆 Clicked {purpose}")
                return True
            except Exception as e:
                if attempt == tries - 1:
                    raise e
                self.page.wait_for_timeout(1000)
        return False

    def _retry_type(self, selector, text, purpose):
        tries = 3
        for attempt in range(tries):
            try:
                self.page.locator(selector).first.fill(text)
                self.speak(f"⌨️ Entered {purpose}")
                return True
            except Exception as e:
                if attempt == tries - 1:
                    raise e
                self.page.wait_for_timeout(1000)
        return False

    def _try_selectors_for_click(self, selectors, purpose):
        for selector in selectors:
            if not selector:
                continue

            try:
                if self.page.locator(selector).count() > 0:
                    self._retry_click(selector, purpose)
                    return True
            except Exception as e:
                continue

        context = self._get_page_context()
        new_selectors = self._get_llm_selectors(f"find clickable element for {purpose}", context)

        for selector in new_selectors:
            try:
                if self.page.locator(selector).count() > 0:
                    self._retry_click(selector, purpose)
                    return True
            except:
                continue

        self.speak(f"Could not find element to click for {purpose}")
        return False

    def _try_selectors_for_hover(self, selectors, purpose):
        for selector in selectors:
            if not selector:
                continue

            try:
                if self.page.locator(selector).count() > 0:
                    self.page.locator(selector).first.hover()
                    self.speak(f"🖱️ Hovering over {purpose}")
                    return True
            except Exception as e:
                continue

        context = self._get_page_context()
        new_selectors = self._get_llm_selectors(f"find hoverable element for {purpose}", context)

        for selector in new_selectors:
            try:
                if self.page.locator(selector).count() > 0:
                    self.page.locator(selector).first.hover()
                    self.speak(f"🖱️ Hovering over {purpose}")
                    return True
            except:
                continue

        self.speak(f"Could not hover over {purpose}")
        return False

    def _try_selectors_for_type(self, selectors, text, purpose):
        for selector in selectors:
            if not selector:
                continue

            try:
                if self.page.locator(selector).count() > 0:
                    return self._retry_type(selector, text, purpose)
            except Exception as e:
                continue

        context = self._get_page_context()
        new_selectors = self._get_llm_selectors(f"find input field for {purpose}", context)

        for selector in new_selectors:
            try:
                if self.page.locator(selector).count() > 0:
                    return self._retry_type(selector, text, purpose)
            except:
                continue

        self.speak(f"Could not find input field for {purpose}")
        return False

    def _try_selectors_for_select(self, selectors, option, dropdown_name):
        context = self._get_page_context()
        dropdown_type = self._determine_dropdown_type(dropdown_name)

        if dropdown_type == 'county':
            state_info = self._get_selected_state()
            if not self._does_state_require_county(state_info):
                self.speak(f"County selection is not required for {state_info}")
                return True

        prompt = f"""
        Find precise selectors for the {dropdown_name} dropdown.
        Dropdown type: {dropdown_type}
        Value to select: {option}

        Special considerations:
        1. For state dropdowns: Look for formation state or state of formation fields
        2. For county dropdowns: Look for county selection that appears after state selection
        3. Consider both visible and initially hidden dropdowns
        4. Look for dynamic dropdowns that may appear after state selection

        Current page context:
        {context}

        Return selectors ordered by specificity, focusing on:
        - id containing state/county keywords
        - name attributes
        - aria-labels
        - data-* attributes
        - associated label text
        """

        initial_selectors = self._get_llm_selectors(prompt, context)
        all_selectors = initial_selectors + selectors

        for selector in all_selectors:
            if not selector:
                continue

            try:
                self.page.wait_for_selector(selector, state="visible", timeout=5000)

                if self.page.locator(selector).count() > 0:

                    label_text = self._get_element_label(selector)
                    if not self._verify_dropdown_match(label_text, dropdown_name):
                        continue

                    is_select = self.page.locator(selector).evaluate("el => el.tagName.toLowerCase() === 'select'")
                    if is_select:
                        options = self.page.locator(f"{selector} option").all_text_contents()
                        best_match = self._find_best_option_match(option, options)
                        if best_match:
                            self.page.select_option(selector, label=best_match)
                            self.speak(f"📝 Selected '{best_match}' from {dropdown_name}")

                            if dropdown_type == 'state':
                                self._handle_post_state_selection()

                            return True
                    else:
                        self.page.locator(selector).click()
                        self.page.wait_for_timeout(1000)

                        option_prompt = f"""
                        Find selectors for the option '{option}' in the expanded {dropdown_name} dropdown.
                        Consider:
                        - Exact text matches
                        - Partial matches
                        - Case-insensitive matches
                        - Data attributes
                        """
                        option_selectors = self._get_llm_selectors(option_prompt, self._get_page_context())

                        for option_selector in option_selectors:
                            try:
                                if self.page.locator(option_selector).count() > 0:
                                    self.page.locator(option_selector).click()
                                    self.speak(f"📝 Selected '{option}' from {dropdown_name}")

                                    if dropdown_type == 'state':
                                        self._handle_post_state_selection()

                                    return True
                            except:
                                continue

            except Exception as e:
                continue

        if dropdown_type == 'county' and not self._is_county_required():
            self.speak("County selection appears to be optional - continuing without selection")
            return True

        self.speak(f"Could not select '{option}' from {dropdown_name}")
        return False

    def _determine_dropdown_type(self, dropdown_name):
        """Determine the type of dropdown based on its name"""
        dropdown_name = dropdown_name.lower()
        if any(term in dropdown_name for term in ['state', 'formation state']):
            return 'state'
        elif 'county' in dropdown_name:
            return 'county'
        elif any(term in dropdown_name for term in ['entity', 'business type', 'company type']):
            return 'entity'
        return 'general'

    def _verify_dropdown_match(self, label_text, dropdown_name):
        """Verify if the found dropdown matches the intended one"""
        if not label_text:
            return True  # If we can't find a label, proceed anyway

        label_text = label_text.lower()
        dropdown_name = dropdown_name.lower()

        # Check for type-specific matches
        if 'county' in dropdown_name:
            return 'county' in label_text
        elif 'state' in dropdown_name:
            return 'state' in label_text
        elif 'entity' in dropdown_name:
            return any(term in label_text for term in ['entity', 'business', 'company'])

        return True

    def _get_element_label(self, selector):
        """Get the label text associated with an element"""
        try:
            # Try multiple approaches to find the label
            label_text = self.page.locator(selector).evaluate("""
                element => {
                    // Check for aria-label
                    let label = element.getAttribute('aria-label');
                    if (label) return label;

                    // Check for associated label element
                    let id = element.id;
                    if (id) {
                        let labelElement = document.querySelector(`label[for="${id}"]`);
                        if (labelElement) return labelElement.textContent;
                    }

                    // Check for parent label
                    let parent = element.closest('label');
                    if (parent) return parent.textContent;

                    return '';
                }
            """)
            return label_text.strip()
        except:
            return ''

    def _find_best_option_match(self, target, options):
        """Find the best matching option from available options"""
        target = target.lower()

        # Direct match
        for option in options:
            if option.lower() == target:
                return option

        # Partial match
        for option in options:
            if target in option.lower():
                return option

        # Handle special cases for counties
        if 'county' in target:
            county_name = target.replace('county', '').strip()
            for option in options:
                if county_name in option.lower():
                    return option

        return None

    def _try_selectors_for_checkbox(self, selectors, action, checkbox_label):
        for selector in selectors:
            if not selector:
                continue

            try:
                if self.page.locator(selector).count() > 0:
                    checkbox = self.page.locator(selector).first
                    is_checked = checkbox.is_checked()

                    if (action == "check" and not is_checked) or (
                            action == "uncheck" and is_checked) or action == "toggle":
                        checkbox.click()
                        new_state = "checked" if action == "check" or (
                                action == "toggle" and not is_checked) else "unchecked"
                        self.speak(f"✓ {new_state.capitalize()} {checkbox_label}")
                        return True
                    elif (action == "check" and is_checked) or (action == "uncheck" and not is_checked):
                        # Already in desired state
                        state = "already checked" if action == "check" else "already unchecked"
                        self.speak(f"✓ {checkbox_label} is {state}")
                        return True
            except Exception as e:
                continue

        # If all selectors fail, ask LLM for better selectors
        context = self._get_page_context()
        new_selectors = self._get_llm_selectors(f"find checkbox for {checkbox_label}", context)

        for selector in new_selectors:
            try:
                if self.page.locator(selector).count() > 0:
                    checkbox = self.page.locator(selector).first
                    is_checked = checkbox.is_checked()

                    if (action == "check" and not is_checked) or (
                            action == "uncheck" and is_checked) or action == "toggle":
                        checkbox.click()
                        new_state = "checked" if action == "check" or (
                                action == "toggle" and not is_checked) else "unchecked"
                        self.speak(f"✓ {new_state.capitalize()} {checkbox_label}")
                        return True
                    elif (action == "check" and is_checked) or (action == "uncheck" and not is_checked):
                        # Already in desired state
                        state = "already checked" if action == "check" else "already unchecked"
                        self.speak(f"✓ {checkbox_label} is {state}")
                        return True
            except:
                continue

        self.speak(f"Could not find checkbox for {checkbox_label}")
        return False

    def _find_navigation_selectors(self, target):
        """Find navigation selectors based on target description"""
        selectors = []

        # Common navigation selectors
        selectors.append(f"a:has-text('{target}')")
        selectors.append(f"nav a:has-text('{target}')")
        selectors.append(f"header a:has-text('{target}')")
        selectors.append(f"[role='menuitem']:has-text('{target}')")
        selectors.append(f"button:has-text('{target}')")
        selectors.append(f".navlink:has-text('{target}')")
        selectors.append(f".menu-item:has-text('{target}')")

        return selectors

    def _show_help(self):
        """Show available commands and usage examples"""
        help_text = """
    🔍 Voice Web Assistant Help:

    Basic Navigation:
    - "Go to [website]" - Navigate to a website
    - "Navigate to [section]" - Go to a specific section on the current site
    - "Click on [element]" - Click on a button, link, or other element
    - "Search for [query]" - Use the search function

    Forms:
    - "Type [text] in [field]" - Enter text in an input field
    - "Login with email [email] and password [password]" - Fill login forms
    - "Select [option] from [dropdown]" - Select from dropdown menus
    - "Check/uncheck [checkbox]" - Toggle checkboxes

    Menu Navigation:
    - "Click on menu item [name]" - Click on a menu item
    - "Navigate to [submenu] under [menu]" - Access submenu items

    Input Mode:
    - "Voice" - Switch to voice input mode
    - "Text" - Switch to text input mode

    General:
    - "Help" - Show this help message
    - "Exit" or "Quit" - Close the assistant
    """
        self.speak("📋 Showing help")
        print(help_text)
        # Only speak the first part to avoid too much speech
        self.engine.say("Here's the help information. You can see the full list on screen.")
        self.engine.runAndWait()

    def run(self):
        """Main loop to run the assistant"""
        self.speak("Web Assistant ready. Say 'help' for available commands.")

        self.browse_website("https://www.google.com")

        while True:
            command = self.listen()
            if not command:
                self.speak("I didn't catch that. Please try again.")
                continue

            print(f"USER: {command}")

            if not self.process_command(command):
                if command.lower() in ["exit", "quit"]:
                    self.speak("Goodbye!")
                else:
                    self.speak("Something went wrong. Please try again.")

                if command.lower() in ["exit", "quit"]:
                    break

    def close(self):
        """Clean up resources"""
        try:
            self.context.close()
            self.browser.close()
            self.playwright.stop()
            print("🛑 Browser closed")
        except Exception as e:
            print(f"Error closing browser: {e}")

    def _get_selected_state(self):
        """Get the currently selected state"""
        try:
            # Try common state dropdown selectors
            state_selectors = [
                "select[name*='state']",
                "select[id*='state']",
                "[aria-label*='State'] select",
                "select.state-dropdown"
            ]

            for selector in state_selectors:
                if self.page.locator(selector).count() > 0:
                    return self.page.locator(selector).evaluate("el => el.value")

            return None
        except:
            return None

    def _does_state_require_county(self, state):
        """Check if the selected state requires county selection"""
        states_requiring_county = ['new york', 'georgia', 'alabama', 'maryland']
        return state and state.lower() in states_requiring_county

    def _handle_post_state_selection(self):
        """Handle any necessary actions after state selection"""
        try:
            # Wait for possible county dropdown to appear
            self.page.wait_for_timeout(2000)  # Wait for dynamic content

            # Check if county dropdown appeared
            county_selectors = [
                "select[name*='county']",
                "select[id*='county']",
                "[aria-label*='County'] select",
                "select.county-dropdown"
            ]

            for selector in county_selectors:
                if self.page.locator(selector).count() > 0:
                    self.speak("County selection is available for this state")
                    break

        except Exception as e:
            pass  # Silently handle any errors

    def _is_county_required(self):
        """Check if county selection is required"""
        try:
            # Look for required indicators near county dropdown
            county_required_indicators = [
                "label[for*='county'] .required",
                "label[for*='county'] .mandatory",
                "label[for*='county'][class*='required']",
                "//label[contains(text(), 'County')]//span[contains(@class, 'required')]"
            ]

            for indicator in county_required_indicators:
                if self.page.locator(indicator).count() > 0:
                    return True

            return False
        except:
            return False

    def _try_state_selectors(self, selectors: List[str], formatted_state: str) -> bool:
        """Try different selectors to find and select the state using LLM guidance"""
        context = self._get_page_context()

        # Ask LLM for state dropdown selectors
        prompt = f"""
        Find selectors for state dropdown and option '{formatted_state}'. Consider:
        1. PrimeNG p-dropdown components
        2. Standard select elements
        3. Custom dropdown implementations
        4. Both the main dropdown and its option elements

        Return selectors for:
        - Opening the dropdown
        - Using filter if present
        - Selecting the specific state option

        Focus on visible, interactive elements and consider ARIA attributes.
        """

        state_selectors = self.llm_selector.get_selectors(prompt, context)

        for selector in state_selectors:
            try:
                if self.page.locator(selector).count() > 0:
                    # Click to open dropdown
                    self.page.click(selector)
                    self.page.wait_for_timeout(500)

                    # Get new context after dropdown opens
                    updated_context = self._get_page_context()

                    # Ask LLM for option selectors
                    option_prompt = f"""
                    Dropdown is now open. Find selectors to select '{formatted_state}' considering:
                    1. Dropdown items/options
                    2. Filter input if present
                    3. Both exact and partial text matches
                    4. ARIA attributes and roles
                    """

                    option_selectors = self.llm_selector.get_selectors(option_prompt, updated_context)

                    for option_selector in option_selectors:
                        try:
                            if self.page.locator(option_selector).count() > 0:
                                self.page.click(option_selector)
                                self.page.wait_for_timeout(500)

                                # Verify selection
                                if self._verify_state_selection(formatted_state):
                                    self.speak(f"Selected state: {formatted_state}")
                                    return True
                        except Exception as e:
                            print(f"Option selector failed: {e}")
                            continue

            except Exception as e:
                print(f"Dropdown selector failed: {e}")
                continue

        return False

    def _verify_state_selection(self, state: str) -> bool:
        """Verify state was correctly selected using LLM"""
        context = self._get_page_context()

        verify_prompt = f"""
        Verify if state '{state}' is selected by checking:
        1. Selected dropdown value
        2. Active/selected state indicators
        3. Form state
        4. Any confirmation elements
        """

        verify_selectors = self.llm_selector.get_selectors(verify_prompt, context)

        for selector in verify_selectors:
            try:
                element = self.page.locator(selector)
                if element.count() > 0:
                    text = element.inner_text()
                    if state.lower() in text.lower():
                        return True
            except:
                continue

        return False


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()

    # Get API key from environment variables
    gemini_api_key = API_KEY_3

    if not gemini_api_key:
        print("❌ Error: GEMINI_API_KEY environment variable not set.")
        print("Please create a .env file with your API key or set it in your environment.")
        exit(1)

    try:
        assistant = VoiceWebAssistant(gemini_api_key)
        assistant.run()
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        try:
            assistant.close()
        except:
            pass





