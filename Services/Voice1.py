from playwright.sync_api import sync_playwright
import speech_recognition as sr
import pyttsx3
import re
import json
import ast
import google.generativeai as genai
from Common.constants import *
import time
from typing import List,Optional,Dict

from llm_selector import LLMSelector
from speaker import Speaker

class VoiceWebAssistant:  # Changed from VoiceAssistant to VoiceWebAssistant
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.speaker = Speaker()  # Changed from TextToSpeech to Speaker
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=False)
        self.page = self.browser.new_page()
        self.llm_selector = LLMSelector(api_key=API_KEY_3)  # Added API key parameter
        self.input_mode = self._select_input_mode()

    def _select_input_mode(self) -> str:
        """Let user select initial input mode"""
        print("\n=== Welcome to Voice Assistant ===")
        print("Please select your preferred input mode:")
        print("1. Voice Mode")
        print("2. Text Mode")

        while True:
            choice = input("Enter your choice (1 or 2): ").strip()
            if choice == "1":
                self.speaker.speak("Voice mode activated. You can speak your commands.")
                return "voice"
            elif choice == "2":
                self.speaker.speak("Text mode activated. You can type your commands.")
                return "text"
            else:
                print("Invalid choice. Please enter 1 for Voice Mode or 2 for Text Mode.")

    def _main_loop(self):
        """Main interaction loop"""
        try:
            self.speaker.speak(f"Assistant ready in {self.input_mode} mode. Say 'help' for available commands.")

            while True:
                if self.input_mode == "voice":
                    command = self.listen()
                else:
                    print("\nEnter your command (or 'help' for available commands):")
                    command = input(">> ").strip()

                if not command:
                    continue

                print(f"USER: {command}")

                if command.lower() in ["exit", "quit"]:
                    self.speaker.speak("Goodbye!")
                    break

                success = self.process_command(command)
                if not success:
                    self.speaker.speak("Something went wrong. Please try again.")

        except Exception as e:
            print(f"Error in main loop: {e}")
            self.speaker.speak("An error occurred. Restarting...")
        finally:
            self.close()

    def listen(self) -> str:
        """Get input based on current mode"""
        if self.input_mode == "voice":
            return self._listen_voice()
        else:
            return self._listen_text()

    def _listen_voice(self) -> str:
        """Listen for voice input"""
        try:
            with self.microphone as source:
                print("\nListening...")
                self.recognizer.adjust_for_ambient_noise(source)
                audio = self.recognizer.listen(source, timeout=5)
                text = self.recognizer.recognize_google(audio)
                return text
        except sr.WaitTimeoutError:
            print("No speech detected")
            return ""
        except sr.UnknownValueError:
            print("Could not understand audio")
            return ""
        except Exception as e:
            print(f"Error in voice listen: {e}")
            return ""

    def _listen_text(self) -> str:
        """Get text input"""
        try:
            return input("Enter command: ").strip()
        except Exception as e:
            print(f"Error in text input: {e}")
            return ""

    def process_command(self, command: str) -> bool:
        """Process and execute commands"""
        try:
            command_lower = command.lower()

            # Handle mode switching
            if command_lower == "switch mode" or command_lower == "change mode":
                self._switch_input_mode()
                return True

            # Handle navigation commands
            if re.match(r'^(go to|navigate to|open)\s+', command_lower):
                match = re.match(r'^(go to|navigate to|open)\s+(.*)', command, re.IGNORECASE)
                if match:
                    url = match.group(2)
                    return self.browse_website(url)

            # Handle login commands
            login_match = re.search(r'(?:login|log in|signin|sign in).*?email\s+(\S+@\S+)\s+(?:and\s+)?password\s+(\S+)', command, re.IGNORECASE)
            if login_match:
                email, password = login_match.groups()
                return self._handle_login(email, password)

            # Handle direct commands
            if command_lower == "help":
                self.display_help()
                return True

            # Let LLM handle all other commands
            context = self._get_page_content()
            selectors = self.llm_selector.get_selectors(command, {"page_content": context})
            return self._execute_selectors(selectors, command)

        except Exception as e:
            print(f"Error processing command: {e}")
            return False

    def _switch_input_mode(self):
        """Switch between voice and text mode"""
        self.input_mode = "text" if self.input_mode == "voice" else "voice"
        self.speaker.speak(f"Switched to {self.input_mode} mode")

    def browse_website(self, url: str) -> bool:
        """Navigate to a website"""
        try:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            self.page.goto(url)
            self.speaker.speak(f"Navigated to {url}")
            return True
        except Exception as e:
            print(f"Navigation error: {e}")
            return False

    def _get_actions(self, command: str) -> Dict:
        """Get actions from LLM based on command"""
        try:
            # Capture current page state
            page_content = self._get_page_content()
            
            prompt = f"""
            User command: {command}
            
            Current page content includes a dropdown with addresses:
            {page_content}
            
            If this is an address selection command, generate actions to:
            1. Click the dropdown if needed
            2. Use the filter if available
            3. Select the matching address
            
            Return actions in this format:
            {{
                "actions": [
                    {{"type": "click", "selector": "selector_string"}},
                    {{"type": "type", "selector": "selector_string", "text": "text_to_type"}},
                    {{"type": "wait", "time": time_in_ms}}
                ]
            }}
            """
            
            response = self.llm_selector.get_llm_response(prompt)
            return self.llm_selector.parse_response(response)

        except Exception as e:
            print(f"Error getting LLM actions: {e}")
            return {"actions": []}

    def _execute_actions(self, action_data: Dict) -> bool:
        """Execute the actions returned by LLM"""
        try:
            for action in action_data.get("actions", []):
                action_type = action.get("type")
                selector = action.get("selector")
                
                if action_type == "click":
                    self.page.wait_for_selector(selector, state="visible")
                    self.page.click(selector)
                    
                elif action_type == "type":
                    text = action.get("text", "")
                    self.page.wait_for_selector(selector, state="visible")
                    self.page.fill(selector, text)
                    
                elif action_type == "wait":
                    time = action.get("time", 500)
                    self.page.wait_for_timeout(time)
                
                # Add small delay between actions
                self.page.wait_for_timeout(200)
            
            return True

        except Exception as e:
            print(f"Error executing actions: {e}")
            return False

    def display_help(self):
        """Display available commands"""
        help_text = f"""
        Current Mode: {self.input_mode.upper()}

        Available commands:
        - 'switch mode' or 'change mode': Switch between voice and text mode
        - 'go to/navigate to/open [website]': Navigate to a website
        - 'select/choose [address]': Select an address from dropdown
        - 'help': Show this help message
        - 'exit/quit': Close the assistant
        """
        print(help_text)
        self.speaker.speak("I've displayed the help menu on screen.")

    def run(self):
        """Start the web assistant"""
        try:
            self._main_loop()
        except KeyboardInterrupt:
            print("\nShutting down gracefully...")
            self.close()

    def _get_page_context(self) -> Dict:
        """Get current page context for LLM"""
        try:
            return {
                'url': self.page.url,
                'title': self.page.title(),
                'content': self.page.content(),
                'html': self.page.inner_html('body')
            }
        except Exception as e:
            print(f"Error getting page context: {e}")
            return {}

    def close(self):
        """Clean up resources"""
        try:
            if hasattr(self, 'page') and self.page:
                self.page.context.close()
            if hasattr(self, 'playwright') and self.playwright:
                self.playwright.stop()
        except Exception as e:
            print(f"Error during cleanup: {e}")

    def _get_page_content(self) -> str:
        """Get the current page content"""
        try:
            # Get visible text content
            text_content = self.page.locator('body').text_content()
            
            # Get input fields information
            input_fields = []
            inputs = self.page.locator("input:visible, textarea:visible, select:visible")
            count = inputs.count()
            
            for i in range(min(count, 10)):  # Limit to first 10 fields
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
                    continue
            
            # Get dropdown/select options if any
            select_options = []
            selects = self.page.locator('select')
            for i in range(selects.count()):
                try:
                    select = selects.nth(i)
                    options = select.evaluate("""select => 
                        Array.from(select.options).map(option => ({
                            value: option.value,
                            text: option.text
                        }))
                    """)
                    select_options.extend(options)
                except:
                    continue
            
            # Combine all information
            page_info = {
                "url": self.page.url,
                "title": self.page.title(),
                "text_content": text_content[:1000],  # Limit text content
                "input_fields": input_fields,
                "select_options": select_options
            }
            
            return json.dumps(page_info, indent=2)
            
        except Exception as e:
            print(f"Error getting page content: {e}")
            return "{}"

    def _handle_login(self, email: str, password: str) -> bool:
        """Handle login with email and password"""
        try:
            # Try common email field selectors
            email_selectors = [
                'input[type="email"]',
                'input[name="email"]',
                'input[id*="email"]',
                'input[placeholder*="email" i]',
                'input[name*="username"]'
            ]
            
            # Try common password field selectors
            password_selectors = [
                'input[type="password"]',
                'input[name="password"]',
                'input[id*="password"]',
                'input[placeholder*="password" i]'
            ]
            
            # Try to fill email
            email_filled = False
            for selector in email_selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self.page.fill(selector, email)
                        email_filled = True
                        break
                except:
                    continue
                
            # Try to fill password
            password_filled = False
            for selector in password_selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self.page.fill(selector, password)
                        password_filled = True
                        break
                except:
                    continue
                
            # Try to click login button if both fields were filled
            if email_filled and password_filled:
                if self._click_login_button():
                    return True
                else:
                    self.speaker.speak("Filled login details but couldn't find login button")
                    return False
            else:
                self.speaker.speak("Could not find all login fields")
                return False
            
        except Exception as e:
            print(f"Login error: {e}")
            self.speaker.speak("Login failed")
            return False

    def _click_login_button(self) -> bool:
        """Use LLM to find and click login button"""
        try:
            # Get current page context
            context = {
                "page_content": self._get_page_content(),
                "current_url": self.page.url,
                "page_title": self.page.title()
            }

            # Get selectors from LLM
            selectors = self.llm_selector.get_selectors(
                """Find login button on the current page. Consider:
                1. Submit buttons in login forms
                2. Buttons/links with text variations of "Login", "Sign in"
                3. Elements with login-related classes, IDs, or roles
                4. Both visible and potentially hidden buttons
                5. Buttons within modal dialogs or popups
                Return selectors ordered by likelihood of being the correct login button.""",
                context
            )

            # Try each selector
            for selector in selectors:
                try:
                    element = self.page.locator(selector)
                    if element.count() > 0 and element.first.is_visible():
                        # Scroll into view
                        element.first.scroll_into_view_if_needed()
                        self.page.wait_for_timeout(500)
                        
                        # Try clicking
                        try:
                            element.first.click()
                        except:
                            try:
                                element.first.click(force=True)
                            except:
                                self.page.evaluate(f"document.querySelector('{selector}').click()")
                        
                        self.page.wait_for_timeout(2000)
                        self.speaker.speak("Clicked login button")
                        return True
                except Exception as e:
                    print(f"Failed with selector {selector}: {str(e)}")
                    continue

            # If first attempt failed, try with refined context
            refined_context = {
                **context,
                "visible_buttons": self._get_visible_buttons(),
                "form_elements": self._get_form_elements()
            }

            # Get new selectors with refined context
            new_selectors = self.llm_selector.get_selectors(
                """Previous login button selectors failed. Using the refined context with visible buttons and form elements,
                generate new selectors specifically targeting login/signin buttons that are currently visible on the page.""",
                refined_context
            )

            # Try new selectors
            for selector in new_selectors:
                try:
                    element = self.page.locator(selector)
                    if element.count() > 0 and element.first.is_visible():
                        element.first.click()
                        self.page.wait_for_timeout(2000)
                        self.speaker.speak("Clicked login button")
                        return True
                except:
                    continue

            self.speaker.speak("Could not find or click login button")
            return False

        except Exception as e:
            print(f"Error clicking login button: {e}")
            self.speaker.speak("Failed to click login button")
            return False

    def _get_visible_buttons(self) -> str:
        """Get text content of visible buttons"""
        try:
            buttons = self.page.evaluate("""
                Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"], a'))
                    .filter(el => {
                        const style = window.getComputedStyle(el);
                        return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
                    })
                    .map(el => ({
                        text: el.textContent.trim(),
                        tag: el.tagName.toLowerCase(),
                        type: el.type || '',
                        classes: Array.from(el.classList).join(' '),
                        id: el.id
                    }));
            """)
            return json.dumps(buttons)
        except:
            return "[]"

    def _get_form_elements(self) -> str:
        """Get form-related elements"""
        try:
            forms = self.page.evaluate("""
                Array.from(document.querySelectorAll('form'))
                    .map(form => ({
                        id: form.id,
                        classes: Array.from(form.classList).join(' '),
                        buttons: Array.from(form.querySelectorAll('button, input[type="submit"]'))
                            .map(btn => ({
                                text: btn.textContent.trim(),
                                type: btn.type,
                                classes: Array.from(btn.classList).join(' ')
                            }))
                    }));
            """)
            return json.dumps(forms)
        except:
            return "[]"

    def _execute_selectors(self, selectors: List[str], purpose: str) -> bool:
        """Try to execute actions using the provided selectors"""
        for selector in selectors:
            try:
                if self.page.locator(selector).count() > 0:
                    self.page.click(selector)
                    self.page.wait_for_timeout(1000)
                    return True
            except:
                continue
        
        self.speaker.speak(f"Could not find element for: {purpose}")
        return False

class OrderSelectionHandler:
    def __init__(self, page, llm_selector, speaker):
        self.page = page
        self.llm_selector = llm_selector
        self.speaker = speaker

    def select_order_type(self, order_type: str) -> bool:
        """Handle order type selection"""
        try:
            context = self._get_page_context()
            selectors = self._generate_menu_selectors(order_type, context)
            
            if self._try_selectors(selectors, order_type):
                self.speaker.speak(f"Selected order type: {order_type}")
                return True

            self.speaker.speak(f"Could not select order type: {order_type}")
            return False

        except Exception as e:
            self.speaker.speak(f"Error selecting order type: {str(e)}")
            return False

    def _generate_menu_selectors(self, order_type: str, context: dict) -> List[str]:
        menu_prompt = self._build_menu_prompt(order_type)
        return self.llm_selector.get_selectors(menu_prompt, context)

    def _build_menu_prompt(self, order_type: str) -> str:
        return f"""
        Find selectors to select order type "{order_type}" considering:
        - May be nested in a parent menu that needs to be clicked first
        - Could be direct menu item or in submenu
        - Consider menu hierarchy and structure
        - Look for exact and partial text matches
        - Consider aria labels and roles
        
        Return selectors for both parent menu (if needed) and target item.
        """

    def _try_selectors(self, selectors: List[str], order_type: str) -> bool:
        for selector in selectors:
            try:
                if self.page.locator(selector).count() > 0:
                    self._retry_click(selector, f"order type: {order_type}")
                    self.page.wait_for_timeout(1000)
                    
                    if self._verify_order_selection(order_type):
                        return True
            except:
                continue
        return False

    def _verify_order_selection(self, order_type: str) -> bool:
        try:
            context = self._get_page_context()
            verification_selectors = self._generate_verification_selectors(order_type, context)
            
            return (
                self._check_selectors_for_match(verification_selectors, order_type) or
                self._check_url_for_match(order_type)
            )
        except:
            return False

    def _generate_verification_selectors(self, order_type: str, context: dict) -> List[str]:
        verify_prompt = self._build_verification_prompt(order_type)
        return self.llm_selector.get_selectors(verify_prompt, context)

    def _build_verification_prompt(self, order_type: str) -> str:
        return f"""
        Find selectors to verify "{order_type}" is selected by checking:
        - Page heading or title
        - Active/selected menu state
        - Form or content indicators
        - URL patterns
        - Breadcrumb navigation
        - Any other relevant confirmation elements
        """

    def _check_selectors_for_match(self, selectors: List[str], order_type: str) -> bool:
        for selector in selectors:
            try:
                element = self.page.locator(selector)
                if element.count() > 0 and order_type.lower() in element.inner_text().lower():
                    return True
            except:
                continue
        return False

    def _check_url_for_match(self, order_type: str) -> bool:
        current_url = self.page.url.lower()
        order_words = order_type.lower().replace(" ", "-").replace("/", "-")
        return order_words in current_url


class StateSelectionHandler:
    def __init__(self, page, llm_selector, speaker):
        self.page = page
        self.llm_selector = llm_selector
        self.speaker = speaker

    def select_state(self, state: str) -> bool:
        """Handle state selection from the dropdown"""
        try:
            context = self._get_page_context()
            formatted_state = state.strip().title()
            state_selectors = self._generate_state_selectors(context)
            
            if self._try_state_selectors(state_selectors, formatted_state):
                self.speaker.speak(f"Selected state: {formatted_state}")
                return True

            self.speaker.speak(f"Could not select state: {formatted_state}")
            return False

        except Exception as e:
            self.speaker.speak(f"Error selecting state: {str(e)}")
            return False

    def _generate_state_selectors(self, context: dict) -> List[str]:
        state_prompt = self._build_state_prompt()
        return self.llm_selector.get_selectors(state_prompt, context)

    def _build_state_prompt(self) -> str:
        return """
        Find precise selectors for the State of Formation dropdown considering:
        1. Must specifically be State of Formation field (not any state field)
        2. Look for labels containing exact text "State of Formation"
        3. Consider common implementations:
           - Standard select element
           - PrimeNG p-dropdown
           - Custom dropdown components
           - React/Angular select components
        4. Check for:
           - Labels with asterisk (required field)
           - Associated help text
           - Specific IDs or names containing "formation"
        """

    def _try_state_selectors(self, selectors: List[str], formatted_state: str) -> bool:
        for selector in selectors:
            try:
                if self.page.locator(selector).count() > 0:
                    if 'select' in selector.lower():
                        self._handle_standard_select(selector, formatted_state)
                    else:
                        self._handle_custom_dropdown(selector, formatted_state)
                    
                    if self._verify_state_selection(formatted_state):
                        return True
            except Exception as e:
                print(f"Selector attempt failed: {e}")
                continue
        return False

    def _handle_standard_select(self, selector: str, state: str):
        self.page.select_option(selector, label=state)

    def _handle_custom_dropdown(self, selector: str, state: str):
        self.page.click(selector)
        self.page.wait_for_timeout(500)
        option_selectors = self._generate_option_selectors(state)
        
        for option_selector in option_selectors:
            if self.page.locator(option_selector).count() > 0:
                self.page.click(option_selector)
                break

    def _generate_option_selectors(self, state: str) -> List[str]:
        option_prompt = self._build_option_prompt(state)
        return self.llm_selector.get_selectors(option_prompt, self._get_page_context())

    def _build_option_prompt(self, state: str) -> str:
        return f"""
        Find selector for state option "{state}" in opened dropdown:
        - Look for exact text match
        - Consider li elements in dropdown list
        - Check for data-value attributes
        - Consider custom option components
        """

    def _verify_state_selection(self, state: str) -> bool:
        try:
            context = self._get_page_context()
            verification_selectors = self._generate_verification_selectors(state, context)
            return self._check_verification_selectors(verification_selectors, state)
        except:
            return False

    def _generate_verification_selectors(self, state: str, context: dict) -> List[str]:
        verify_prompt = self._build_verification_prompt(state)
        return self.llm_selector.get_selectors(verify_prompt, context)

    def _build_verification_prompt(self, state: str) -> str:
        return f"""
        Find selectors to verify state "{state}" is selected:
        1. Check selected option in State of Formation dropdown
        2. Look for confirmation text or labels
        3. Check for validation messages
        4. Consider aria-selected attributes
        """

    def _check_verification_selectors(self, selectors: List[str], state: str) -> bool:
        for selector in selectors:
            try:
                element = self.page.locator(selector)
                if element.count() > 0 and state.lower() in element.inner_text().lower():
                    return True
            except:
                continue
        return False


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    gemini_api_key = API_KEY_3

    if not gemini_api_key:
        print("❌ Error: GEMINI_API_KEY environment variable not set.")
        print("Please create a .env file with your API key or set it in your environment.")
        exit(1)

    assistant = VoiceWebAssistant()  # This now matches the class name
    assistant.run()

