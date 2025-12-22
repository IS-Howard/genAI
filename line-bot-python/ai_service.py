"""
Google Gemini AI Service
Handles all AI interactions with optimized context
"""
import google.generativeai as genai
from typing import List, Dict
from loguru import logger
from config import settings
from prompts import prompt_manager


# Configure Gemini
genai.configure(api_key=settings.gemini_api_key)


class AIService:
    """AI service for chat responses"""

    def __init__(self):
        self.model = genai.GenerativeModel(settings.gemini_model)
        self.prompt_manager = prompt_manager

    async def normal_chat(self, message: str, user_name: str, history: List[Dict]) -> str:
        """
        Normal user chat with basic persona
        """
        # Format conversation history
        history_context = self.prompt_manager.format_history(history)

        # Build system prompt using prompt manager
        system_prompt = self.prompt_manager.build_normal_chat_prompt(
            user_name=user_name,
            history_context=history_context
        )

        try:
            response = await self.model.generate_content_async(
                f"{system_prompt}\n\n{message}"
            )
            return response.text
        except Exception as e:
            logger.error(f"Normal chat error: {e}")
            return "抱歉，我現在有點狀況，等等回你。"

    async def group_chat(self, message: str, user_name: str, history: List[Dict]) -> str:
        """
        Group chat with adjusted persona
        """
        # Format conversation history
        history_context = self.prompt_manager.format_history(history)

        # Build system prompt using prompt manager
        system_prompt = self.prompt_manager.build_group_chat_prompt(
            user_name=user_name,
            history_context=history_context
        )

        # Clean @HOWN_BOT mention
        clean_message = message.replace('@HOWN_BOT', '').strip()

        try:
            response = await self.model.generate_content_async(
                f"{system_prompt}\n\n{user_name}: {clean_message}"
            )
            return response.text
        except Exception as e:
            logger.error(f"Group chat error: {e}")
            return "欸，我剛恍神了，你說啥？"

    async def analyze_image(self, image_data: bytes, user_prompt: str = None) -> str:
        """
        Analyze image with Gemini Vision

        Args:
            image_data: Binary image data
            user_prompt: Optional custom prompt from user
        """
        # Build prompt using prompt manager
        prompt = self.prompt_manager.build_image_analysis_prompt(user_prompt)

        try:
            response = await self.model.generate_content_async([
                prompt,
                {"mime_type": "image/jpeg", "data": image_data}
            ])
            return response.text
        except Exception as e:
            logger.error(f"Image analysis error: {e}")
            return "抱歉，我看不清楚這張圖。"

    async def analyze_audio(self, audio_data: bytes, user_prompt: str = None) -> str:
        """
        Analyze audio with Gemini

        Args:
            audio_data: Binary audio data
            user_prompt: Optional custom prompt from user
        """
        # Build prompt using prompt manager
        prompt = self.prompt_manager.build_audio_analysis_prompt(user_prompt)

        try:
            response = await self.model.generate_content_async([
                prompt,
                {"mime_type": "audio/mpeg", "data": audio_data}
            ])
            return response.text
        except Exception as e:
            logger.error(f"Audio analysis error: {e}")
            return "抱歉，我聽不清楚這段音檔。"


# Global AI service instance
ai_service = AIService()
