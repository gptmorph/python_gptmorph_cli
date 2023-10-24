import os
import re
import sys

import openai

from pysyun.conversation.flow.console_bot import ConsoleBot
from authenticator import ClaudeAuthenticator

from settings import load_settings


class MorphBot(ConsoleBot):

    def __init__(self, token):

        super().__init__(token)

        load_settings()

    @staticmethod
    def augment_chat(messages):

        total_word_count = 0
        bottom_items = []

        for item in reversed(messages):
            word_count = len(item['content'].split())
            total_word_count += word_count
            if total_word_count < 4097:
                bottom_items.append(item)
            else:
                print("Skipping context", item)

        bottom_items.reverse()

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=bottom_items
        )

        result = ''
        for choice in response.choices:
            result += choice.message.content

        return result

    def build_settings_transition(self):

        async def transition(action):

            openai_api_key = os.getenv("OPENAI_API_KEY")
            claude_cookie = os.getenv("CLAUDE_COOKIE")

            text = "mrph>\n"
            help_prompt = ""

            if openai_api_key:
                text += f"Your OpenAI API key (.env): \"{openai_api_key}\"\n\n"
            else:
                help_prompt += '''--------------------------------------------------
    HOW TO GET OPENAI API KEY?

Please set your OpenAI API key by following these steps:

1. Create a file named ".env" in the project folder.
2. Open the .env file and add the following line:
      OPENAI_API_KEY=<YOUR_API_KEY>
   Replace <YOUR_API_KEY> with your actual OpenAI API key.

   If you don't have an API key yet, sign up at https://platform.openai.com/signup

3. Save the .env file.

Once the OpenAI API key is added, you can proceed with running the program.

--------------------------------------------------
'''

            if claude_cookie:
                text += f"Your Claude (Anthropic) API key (.env): \"{claude_cookie}\"\n\n"
            else:
                help_prompt += '''--------------------------------------------------
    HOW TO GET Claude (Anthropic) API KEY?
    
Claude official API is not for all.
Therefore, we are using the Web API for accessing Claude:

1. Open the Claude Web Authenticator by typing "/authenticate_claude".
2. Enter your credentials to authenticate into https://claude.ai/.
3. Enjoy!

--------------------------------------------------
'''

            text += help_prompt

            nested_transition = self.build_menu_response_transition(text, ["Start", "Authenticate Claude", "Exit"])
            await nested_transition(action)

        return transition

    @staticmethod
    def build_authenticate_claude_transition():

        async def transition(_):

            await ClaudeAuthenticator().process_async([])

            load_settings()

            print("Claude API authenticated")

        return transition

    @staticmethod
    def build_help_transition():
        async def transition(action):

            text = '''/generate - Generate a new file for your project based on a human language description.
/patch - Update an existing file (re-factor) by prompting what the update should be.
/settings - Display your LLM settings.
/graph - Graphviz representation for this bot's API.
/help - Show this help page.
/exit - Close the application.
            '''

            await action["context"].bot.send_message(chat_id=action["update"]["effective_chat"]["id"], text=text)

        return transition

    @staticmethod
    def build_generate_transition():

        openai_api_key = os.getenv("OPENAI_API_KEY")

        async def transition(action):

            if not openai_api_key:
                text = "mrph> Please, configure the LLM API key as stated in \"/settings\"."
            else:
                text = "mrph> Enter the file name for saving the generated file:"

            await action["context"].bot.send_message(chat_id=action["update"]["effective_chat"]["id"], text=text)

        return transition

    @staticmethod
    def build_patch_transition():

        openai_api_key = os.getenv("OPENAI_API_KEY")

        async def transition(action):

            if not openai_api_key:
                text = "mrph> Please, configure the LLM API key as stated in \"/settings\"."
            else:
                text = "mrph> Enter the file name to be patched:"

            await action["context"].bot.send_message(chat_id=action["update"]["effective_chat"]["id"], text=text)

        return transition

    @staticmethod
    def build_generate_file_name_input_transition():

        async def transition(action):
            file_name = action['text']
            action["context"].add("generate_file_name", file_name)
            text = f"mrph> Ok, I will create a file \"{file_name}\" when finished. What should be in this file?"
            await action["context"].bot.send_message(chat_id=action["update"]["effective_chat"]["id"], text=text)

        return transition

    @staticmethod
    def build_patch_file_name_input_transition():

        async def transition(action):
            file_name = action['text']
            action["context"].add("patch_file_name", file_name)
            text = f"mrph> Loaded \"{file_name}\". How to augment that?"
            await action["context"].bot.send_message(chat_id=action["update"]["effective_chat"]["id"], text=text)

        return transition

    @staticmethod
    def build_generate_prompt_input_transition(nested_transition):

        async def transition(action):

            prompt = action['text']

            messages = [{
                "role": "user",
                "content": prompt
            }]

            response = MorphBot.augment_chat(messages)
            print(f"llm> {response}")

            file_name = action["context"].get("generate_file_name")

            # Parse code blocks
            code_blocks = re.findall(r"```(.*?)\n(.*?)\n```", response, re.DOTALL)

            # Save code blocks to a text file
            for language, code_block in code_blocks:
                with open(file_name, 'w', encoding='utf-8') as file:
                    file.write(f"{code_block}\n")

            text = f"mrph> Your \"{file_name}\" file was saved."
            await action["context"].bot.send_message(chat_id=action["update"]["effective_chat"]["id"], text=text)
            await nested_transition(action)

        return transition

    @staticmethod
    def build_patch_prompt_input_transition(nested_transition):
        async def transition(action):

            file_name = action['context'].get("patch_file_name")

            try:
                # Load file contents
                with open(file_name, 'r', encoding='utf-8') as file:
                    file_contents = file.read()

                prompt = action['text']

                messages = [{
                    "role": "system",
                    "content": f"Let's update the {file_name} file provided."
                }, {
                    "role": "assistant",
                    "content": f"Original file:\n\n---\n{file_contents}\n---\n"
                }, {
                    "role": "user",
                    "content": prompt
                }]

                # Augment the file contents based on the user's prompt
                response = MorphBot.augment_chat(messages)
                print(f"llm> {response}")

                # Parse code blocks
                code_blocks = re.findall(r"```(.*?)\n(.*?)\n```", response, re.DOTALL)

                # Save code blocks to a text file
                for language, code_block in code_blocks:
                    with open(file_name, 'w', encoding='utf-8') as file:
                        file.write(f"{code_block}\n")

                text = f"mrph> File \"{file_name}\" has been augmented based on your prompt."
                await action["context"].bot.send_message(chat_id=action["update"]["effective_chat"]["id"], text=text)
                await nested_transition(action)
            except Exception as e:
                text = f"mrph> An error occurred while processing the file: {str(e)}"
                await action["context"].bot.send_message(chat_id=action["update"]["effective_chat"]["id"], text=text)

        return transition

    @staticmethod
    def build_exit_transition():

        async def transition(_):
            sys.exit()

        return transition

    def build_state_machine(self, builder):
        main_menu_transition = self.build_menu_response_transition(
            '''mrph> Welcome to the GPT Morph CLI Bot! You are currently in the main menu.
To execute a command, type the corresponding option and press Enter.
You can always return to the main menu by typing "/start".
Type "/help" for more.\n''',
            [["Analyze", "Generate", "Patch"], ["Settings", "Help", "Exit"], ["Graph"]])

        return builder \
            .edge(
                "/start",
                "/start",
                "/graph",
                on_transition=self.build_graphviz_response_transition()) \
            .edge("/start", "/start", "/start", on_transition=main_menu_transition) \
            .edge("/start", "/settings", "/settings", on_transition=self.build_settings_transition()) \
            .edge("/settings", "/start", "/exit", on_transition=self.build_exit_transition()) \
            .edge(
                "/settings",
                "/start",
                "/authenticate_claude",
                on_transition=self.build_authenticate_claude_transition()) \
            .edge("/settings", "/start", "/start", on_transition=main_menu_transition) \
            .edge("/start", "/start", "/help", on_transition=self.build_help_transition()) \
            .edge("/start", "/start", "/exit", on_transition=self.build_exit_transition()) \
            .edge("/start", "/generate_file_name_input", "/generate", on_transition=self.build_generate_transition()) \
            .edge("/generate_file_name_input", "/start", "/start") \
            .edge("/generate_file_name_input", "/start", "/exit", on_transition=self.build_exit_transition()) \
            .edge(
                "/generate_file_name_input",
                "/settings",
                "/settings",
                on_transition=self.build_settings_transition()) \
            .edge(
                "/generate_file_name_input",
                "/generate_prompt_input",
                None,
                matcher=re.compile("^.*$"),
                on_transition=self.build_generate_file_name_input_transition()) \
            .edge("/generate_prompt_input", "/start", "/start") \
            .edge("/generate_prompt_input", "/start", "/exit", on_transition=self.build_exit_transition()) \
            .edge(
                "/generate_prompt_input",
                "/start",
                None,
                matcher=re.compile("^.*$"),
                on_transition=self.build_generate_prompt_input_transition(main_menu_transition)) \
            .edge("/start", "/patch_file_name_input", "/patch", on_transition=self.build_patch_transition()) \
            .edge("/patch_file_name_input", "/start", "/start") \
            .edge("/patch_file_name_input", "/start", "/exit", on_transition=self.build_exit_transition()) \
            .edge("/patch_file_name_input", "/settings", "/settings", on_transition=self.build_settings_transition()) \
            .edge(
                "/patch_file_name_input",
                "/patch_prompt_input",
                None,
                matcher=re.compile("^.*$"),
                on_transition=self.build_patch_file_name_input_transition()) \
            .edge("/patch_prompt_input", "/start", "/start") \
            .edge("/patch_prompt_input", "/start", "/exit", on_transition=self.build_exit_transition()) \
            .edge(
                "/patch_prompt_input",
                "/start",
                None,
                matcher=re.compile("^.*$"),
                on_transition=self.build_patch_prompt_input_transition(main_menu_transition)) \
            .edge("/start", "/analyze", "/analyze") \
            .edge("/analyze", "/start", "/start") \
            .edge("/analyze", "/settings", "/settings") \
            .edge("/analyze", "/start", "/exit", on_transition=self.build_exit_transition())
