import os
import re
import sys
import copy

import openai
from dialog import ClaudeDialog

from pysyun.conversation.flow.console_bot import ConsoleBot
from authenticator import ClaudeAuthenticator

from context_folder_dialog import ContextFolderDialog
from llm_dialog import LLMDialog
from settings import load_settings


def filter_source_code_file_names(file_path):

    if 'node_modules' in file_path:
        return False

    if 'typechain-types' in file_path:
        return False

    if 'venv/' in file_path:
        return False

    return (
            file_path.endswith('Dockerfile') or
            file_path.endswith('package.json') or
            file_path.endswith('requirements.txt') or
            file_path.endswith('.md') or
            file_path.endswith('.dot') or
            file_path.endswith('.env') or
            file_path.endswith('.py') or
            file_path.endswith('.sol') or
            file_path.endswith('.sh') or
            file_path.endswith('.rs') or
            file_path.endswith('.js') or
            file_path.endswith('.ts')
    )


def build_current_project_context():
    # Load the current folder context
    context_folder = ContextFolderDialog(".", filter_callback=filter_source_code_file_names)
    context_folder.process([])

    return context_folder


class MorphBot(ConsoleBot):

    def __init__(self, token):

        super().__init__(token)

        load_settings()

    @staticmethod
    def augment_chat_with_openai(messages):

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

    @staticmethod
    def augment_chat_with_claude(messages):

        content = "\n".join(item["content"] for item in messages)

        dialog = ClaudeDialog()
        data = dialog.process([content])

        return data[0]

    @staticmethod
    def augment_chat(dialog):

        openai_api_key = os.getenv("OPENAI_API_KEY")
        claude_cookie = os.getenv("CLAUDE_COOKIE")

        # Make a deep copy of the conversation
        conversation = copy.deepcopy(dialog.conversation)

        # Remove time fields
        for message in conversation:
            if 'time' in message:
                del message['time']

        # Prefer Claude over OpenAI
        if claude_cookie is not None:
            return MorphBot.augment_chat_with_claude(conversation)
        elif openai_api_key is not None:
            return MorphBot.augment_chat_with_openai(conversation)

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
    def build_analyze_transition():

        openai_api_key = os.getenv("OPENAI_API_KEY")

        async def transition(action):

            if not openai_api_key:
                text = "mrph> Please, configure the LLM API key as stated in \"/settings\"."
            else:
                text = "mrph> Enter the file name to be analyzed:"

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

    def build_generate_file_name_input_transition(self):

        async def transition(action):
            file_name = action['text']
            action["context"].add("generate_file_name", file_name)
            text = f"mrph> Ok, I will create a file \"{file_name}\" when finished. What should be in this file?"
            await self.build_menu_response_transition(text, ['Unit test', 'Statement flow', '*'])(action)

        return transition

    def build_patch_file_name_input_transition(self):

        async def transition(action):

            file_name = action['text']
            action["context"].add("patch_file_name", file_name)
            text = f"mrph> Loaded \"{file_name}\". How to augment that?"

            await self.build_menu_response_transition(text, ['/todo (criticize and add comments)', '*'])(action)

        return transition

    @staticmethod
    def build_analyze_file_name_input_transition():

        async def transition(action):
            file_name = action['text']
            action["context"].add("analyze_file_name_input", file_name)
            text = f"mrph> Loaded \"{file_name}\". Where to save a report?"
            await action["context"].bot.send_message(chat_id=action["update"]["effective_chat"]["id"], text=text)

        return transition

    def build_analyze_file_name_output_transition(self):

        async def transition(action):
            file_name = action['text']
            action["context"].add("analyze_file_name_output", file_name)
            text = f"mrph> Will be saving report to \"{file_name}\". Which AI assistant profile would you prefer to " \
                   f"use for analyzing your code?"

            nested_transition = self.build_menu_response_transition(text, ["Crypto Audit"])
            await nested_transition(action)

        return transition

    @staticmethod
    def build_generate_prompt_input_transition(nested_transition):

        async def transition(action):

            prompt = action['text']

            # The dialog
            dialog = LLMDialog()
            dialog += build_current_project_context()
            dialog.assign("user", prompt)

            response = MorphBot.augment_chat(dialog)
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
    def build_generate_unit_test_prompt_input_transition(nested_transition):

        async def transition(action):

            prompt = action['text']

            # The dialog
            dialog = LLMDialog()
            dialog += build_current_project_context()
            dialog.assign("user", "Please, generate a unit test for my project.")
            dialog.assign("user", prompt)

            response = MorphBot.augment_chat(dialog)
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
    def build_generate_statement_flow_prompt_input_transition(nested_transition):

        async def transition(action):

            prompt = action['text']

            # The dialog
            dialog = LLMDialog()
            dialog += build_current_project_context()
            message = f"Please, generate a logical statement flow graph in the Graphviz format for the \"{prompt}\" " \
                      f"method."
            dialog.assign("user", message)

            response = MorphBot.augment_chat(dialog)
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
    def build_generate_prompt_input_unit_test_choice_transition():

        async def transition(action):

            file_name = action["context"].get("generate_file_name")

            text = f"mrph> Will generate the \"{file_name}\" unit test. Please, describe, what should " \
                   f"be checked in this test."
            await action["context"].bot.send_message(chat_id=action["update"]["effective_chat"]["id"], text=text)

        return transition

    @staticmethod
    def build_generate_prompt_input_statement_flow_choice_transition():

        async def transition(action):

            file_name = action["context"].get("generate_file_name")

            text = f"mrph> Will generate the \"{file_name}\" statement flow Graphviz representation. Please, " \
                   f"describe, which ClassName.MethodName needs to be analyzed."
            await action["context"].bot.send_message(chat_id=action["update"]["effective_chat"]["id"], text=text)

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

                # The dialog
                dialog = LLMDialog()
                dialog.assign("system", f"Let's update the {file_name} file provided.")
                dialog.assign("assistant", f"Original file:\n\n---\n{file_contents}\n---\n")
                dialog += build_current_project_context()
                dialog.assign("user", prompt)

                # Augment the file contents based on the user's prompt
                response = MorphBot.augment_chat(dialog)
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
    def build_crypto_audit_transition(nested_transition):
        async def transition(action):

            analyze_file_name_input = action['context'].get("analyze_file_name_input")
            analyze_file_name_output = action['context'].get("analyze_file_name_output")

            try:
                # Load file contents
                with open(analyze_file_name_input, 'r', encoding='utf-8') as file:
                    file_contents = file.read()

                # The agent profile
                profile = '''You are a Solidity smart contract audit expert. The user sends you a smart contract 
                code. You return the list of possible errors in this contract including: 1. Security issues. 2. Code 
                style issues. 3. Performance improvements. Please, return results as a report in the Markdown format.'''

                # The dialog
                dialog = LLMDialog()
                dialog.assign("system", profile)
                dialog.assign("user", f"The file name is: {analyze_file_name_input}.")
                dialog.assign("user", file_contents)

                # Augment the file contents based on the user's prompt
                response = MorphBot.augment_chat(dialog)
                print(f"llm> {response}")

                # Save response to a text file
                with open(analyze_file_name_output, 'w', encoding='utf-8') as file:
                    file.write(response)

                text = f"mrph> File \"{analyze_file_name_input}\" analysis report \"{analyze_file_name_output}\" has " \
                       f"been saved."
                await action["context"].bot.send_message(chat_id=action["update"]["effective_chat"]["id"], text=text)
                await nested_transition(action)
            except Exception as e:
                text = f"mrph> An error occurred while processing the file: {str(e)}"
                await action["context"].bot.send_message(chat_id=action["update"]["effective_chat"]["id"], text=text)

        return transition

    @staticmethod
    def build_todo_transition(nested_transition):
        async def transition(action):

            file_name = action['context'].get("patch_file_name")

            try:
                # Load file contents
                with open(file_name, 'r', encoding='utf-8') as file:
                    file_contents = file.read()

                # The dialog
                dialog = LLMDialog()
                dialog.assign("system", f"Let's update the {file_name} file provided.")
                dialog.assign("assistant", f"Original file:\n\n---\n{file_contents}\n---\n")
                dialog.assign("user", "Please, criticize this file contents and add \"TODO:\" comments, saying, "
                                      "what can be improved.")

                # Augment the file contents based on the user's prompt
                response = MorphBot.augment_chat(dialog)
                print(f"llm> {response}")

                # Parse code blocks
                code_blocks = re.findall(r"```(.*?)\n(.*?)\n```", response, re.DOTALL)

                # Save code blocks to a text file
                for language, code_block in code_blocks:
                    with open(file_name, 'w', encoding='utf-8') as file:
                        file.write(f"{code_block}\n")

                text = f"mrph> The file \"{file_name}\" has been criticized. Please, review \"TODO:\" comments."
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
            .edge("/generate_file_name_input", "/start", "/start", on_transition=main_menu_transition) \
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
            .edge("/generate_prompt_input", "/start", "/start", on_transition=main_menu_transition) \
            .edge("/generate_prompt_input", "/start", "/exit", on_transition=self.build_exit_transition()) \
            .edge(
                "/generate_prompt_input",
                "/generate_unit_test_prompt_input",
                "/unit_test",
                on_transition=self.build_generate_prompt_input_unit_test_choice_transition()) \
            .edge(
                "/generate_prompt_input",
                "/generate_statement_flow_prompt_input",
                "/statement_flow",
                on_transition=self.build_generate_prompt_input_statement_flow_choice_transition()) \
            .edge(
                "/generate_prompt_input",
                "/start",
                None,
                matcher=re.compile("^.*$"),
                on_transition=self.build_generate_prompt_input_transition(main_menu_transition)) \
            .edge("/generate_statement_flow_prompt_input", "/start", "/start", on_transition=main_menu_transition) \
            .edge("/generate_statement_flow_prompt_input", "/start", "/exit", on_transition=self.build_exit_transition()) \
            .edge("/generate_unit_test_prompt_input", "/start", "/start", on_transition=main_menu_transition) \
            .edge("/generate_unit_test_prompt_input", "/start", "/exit", on_transition=self.build_exit_transition()) \
            .edge(
                "/generate_unit_test_prompt_input",
                "/start",
                None,
                matcher=re.compile("^.*$"),
                on_transition=self.build_generate_unit_test_prompt_input_transition(main_menu_transition)) \
            .edge(
                "/generate_statement_flow_prompt_input",
                "/start",
                None,
                matcher=re.compile("^.*$"),
                on_transition=self.build_generate_statement_flow_prompt_input_transition(main_menu_transition)) \
            .edge("/start", "/patch_file_name_input", "/patch", on_transition=self.build_patch_transition()) \
            .edge("/patch_file_name_input", "/start", "/start", on_transition=main_menu_transition) \
            .edge("/patch_file_name_input", "/start", "/exit", on_transition=self.build_exit_transition()) \
            .edge("/patch_file_name_input", "/settings", "/settings", on_transition=self.build_settings_transition()) \
            .edge(
                "/patch_file_name_input",
                "/patch_prompt_input",
                None,
                matcher=re.compile("^.*$"),
                on_transition=self.build_patch_file_name_input_transition()) \
            .edge("/patch_prompt_input", "/start", "/start", on_transition=main_menu_transition) \
            .edge("/patch_prompt_input", "/start", "/exit", on_transition=self.build_exit_transition()) \
            .edge(
                "/patch_prompt_input",
                "/start",
                "/todo",
                on_transition=self.build_todo_transition(main_menu_transition)) \
            .edge(
                "/patch_prompt_input",
                "/start",
                None,
                matcher=re.compile("^.*$"),
                on_transition=self.build_patch_prompt_input_transition(main_menu_transition)) \
            .edge("/start", "/analyze_file_name_input", "/analyze", on_transition=self.build_analyze_transition()) \
            .edge("/analyze_file_name_input", "/start", "/start", on_transition=main_menu_transition) \
            .edge("/analyze_file_name_input", "/settings", "/settings") \
            .edge("/analyze_file_name_input", "/start", "/exit", on_transition=self.build_exit_transition()) \
            .edge(
                "/analyze_file_name_input",
                "/analyze_file_name_output",
                None,
                matcher=re.compile("^.*$"),
                on_transition=self.build_analyze_file_name_input_transition()) \
            .edge("/analyze_file_name_output", "/start", "/start", on_transition=main_menu_transition) \
            .edge("/analyze_file_name_output", "/start", "/exit", on_transition=self.build_exit_transition()) \
            .edge(
                "/analyze_file_name_output",
                "/analyze_type",
                None,
                matcher=re.compile("^.*$"),
                on_transition=self.build_analyze_file_name_output_transition()) \
            .edge("/analyze_type", "/start", "/start", on_transition=main_menu_transition) \
            .edge("/analyze_type", "/start", "/exit", on_transition=self.build_exit_transition()) \
            .edge(
                "/analyze_type",
                "/start",
                "/crypto_audit",
                on_transition=self.build_crypto_audit_transition(main_menu_transition))
