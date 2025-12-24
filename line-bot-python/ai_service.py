"""
Handles all AI interactions with optimized context
"""
from google import genai
from google.genai import types
from typing import List, Dict, Optional, Callable
from loguru import logger
from config import settings
from prompts import prompt_manager
from database import db


class AIService:
    """AI service for chat responses with Group Tool support"""

    def __init__(self):
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.prompt_manager = prompt_manager
        self.tools = self._define_tools()

    def _define_tools(self) -> List[types.Tool]:
        """Define tool schemas for Gemini function calling"""
        return [
            types.Tool(function_declarations=[
                types.FunctionDeclaration(
                    name="get_latest_group_file_info",
                    description="Get info about the most recently uploaded files in this group.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={"group_id": types.Schema(type=types.Type.STRING, description="Group ID")},
                        required=["group_id"]
                    )
                ),
                types.FunctionDeclaration(
                    name="analyze_latest_group_image",
                    description="Analyze the most recent image uploaded in this group.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "group_id": types.Schema(type=types.Type.STRING, description="Group ID"),
                            "prompt": types.Schema(type=types.Type.STRING, description="Analysis question/focus")
                        },
                        required=["group_id", "prompt"]
                    )
                ),
                types.FunctionDeclaration(
                    name="analyze_latest_group_audio",
                    description="Analyze the most recent audio file uploaded in this group.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "group_id": types.Schema(type=types.Type.STRING, description="Group ID"),
                            "prompt": types.Schema(type=types.Type.STRING, description="Analysis question/focus")
                        },
                        required=["group_id", "prompt"]
                    )
                )
            ])
        ]

    async def _get_latest_group_file_info(self, group_id: str) -> str:
        """Get info about the most recent file in group"""
        try:
            file = await db.get_latest_group_file(group_id)
            if not file:
                return "No files found in this group."
            return f"Latest file: Type={file['file_type']}, Uploaded={file['uploaded_at']}, Size={file['file_size_bytes']} bytes"
        except Exception as e:
            logger.error(f"Error getting file info: {e}")
            return f"Error: {e}"

    async def _analyze_file(self, group_id: str, file_type: str, prompt: str) -> str:
        """Analyze image or audio file"""
        try:
            file = await db.get_latest_group_file(group_id, file_type=file_type)
            if not file:
                return f"No {file_type} found in this group."

            # Build analysis prompt
            if file_type == 'image':
                analysis_prompt = self.prompt_manager.build_image_analysis_prompt(prompt or None)
            else:
                analysis_prompt = self.prompt_manager.build_audio_analysis_prompt(prompt or None)

            # Analyze with Gemini
            media_part = types.Part.from_bytes(data=file['file_data'], mime_type=file['mime_type'])
            response = await self.client.aio.models.generate_content(
                model=settings.gemini_model,
                contents=[analysis_prompt, media_part]
            )
            return response.text

        except Exception as e:
            logger.error(f"Error analyzing {file_type}: {e}")
            return f"Error analyzing {file_type}: {e}"

    async def normal_chat(self, message: str, user_name: str, history: List[Dict]) -> str:
        """Normal 1-on-1 chat (No tools)"""
        history_context = self.prompt_manager.format_history(history)
        system_instruction = self.prompt_manager.build_normal_chat_prompt(
            user_name=user_name,
            history_context=history_context
        )
        
        try:
            response = await self.client.aio.models.generate_content(
                model=settings.gemini_model,
                contents=message,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction
                )
            )
            return response.text
        except Exception as e:
            logger.error(f"Normal chat error: {e}")
            return "抱歉，我現在有點狀況，等等回你。"

    async def group_chat(self, message: str, user_name: str, group_id: str, history: List[Dict]) -> str:
        """Group chat with tool-calling support"""
        history_context = self.prompt_manager.format_history(history)
        system_instruction = self.prompt_manager.build_group_chat_prompt(user_name, history_context)
        system_instruction += f"\n\nYou have tools to access files in this group (group_id: '{group_id}'). Always use this group_id when calling tools."

        clean_message = message.replace('@HOWN_BOT', '').strip()

        try:
            # Initial request with tools available
            response = await self.client.aio.models.generate_content(
                model=settings.gemini_model,
                contents=f"{user_name}: {clean_message}",
                config=types.GenerateContentConfig(system_instruction=system_instruction, tools=self.tools)
            )

            # Extract function calls if any
            function_calls = [
                part.function_call for part in response.candidates[0].content.parts
                if hasattr(part, 'function_call') and part.function_call
            ]

            # No function calls? Return text response
            if not function_calls:
                return response.text

            # Execute function calls
            function_responses = await self._execute_tool_calls(function_calls)

            # Get final response with function results
            final_response = await self.client.aio.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    types.Content(role="user", parts=[types.Part(text=f"{user_name}: {clean_message}")]),
                    response.candidates[0].content,
                    types.Content(role="function", parts=function_responses)
                ],
                config=types.GenerateContentConfig(system_instruction=system_instruction, tools=self.tools)
            )

            return final_response.text

        except Exception as e:
            logger.error(f"Group chat error: {e}")
            return "抱歉，我在處理群組工具請求時遇到了問題。"

    async def _execute_tool_calls(self, function_calls: List) -> List[types.Part]:
        """Execute tool calls and return formatted responses"""
        responses = []
        for func_call in function_calls:
            func_name = func_call.name
            func_args = dict(func_call.args)

            # Dispatch to appropriate handler
            handlers = {
                'get_latest_group_file_info': self._get_latest_group_file_info,
                'analyze_latest_group_image': lambda **args: self._analyze_file(file_type='image', **args),
                'analyze_latest_group_audio': lambda **args: self._analyze_file(file_type='audio', **args)
            }

            handler = handlers.get(func_name)
            if handler:
                result = await handler(**func_args)
            else:
                result = f"Unknown function: {func_name}"
                logger.warning(f"Unknown tool called: {func_name}")

            responses.append(types.Part.from_function_response(name=func_name, response={"result": result}))

        return responses


# Global AI service instance
ai_service = AIService()
