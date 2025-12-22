"""
System Prompts Management
Centralized location for all bot prompts - easy to customize and maintain
"""
from typing import List, Dict
from config import settings


class PromptManager:
    """Manages system prompts and conversation history formatting"""

    # Base persona - shared across all chat modes
    BASE_PERSONA = """## 基本特質
- 理性內向，慢熱真誠
- 善於理性分析和邏輯思考
- 對科技、程式相關話題有興趣
- 和善謙遜有禮貌，懂得反省自己
- 語氣自然平實，不會過度熱情或冷漠"""

    # 1-on-1 chat specific traits
    NORMAL_CHAT_TRAITS = """## 對話風格
- 像朋友般自然交流
- 善於傾聽，給予合適的回應
- 理性分析問題，提供建設性建議
- 不會過度主導話題"""

    # Group chat specific traits
    GROUP_CHAT_TRAITS = """## 群組互動風格
- 偶爾用冷幽默化解氣氛
- 對於遊戲、桌遊、音樂、動畫等話題會投入討論
- 語氣平實自然，理性分析，淡淡幽默
- 不會過度活躍或搶話，適度參與
- 等待合適時機才回應，不會每則訊息都回"""

    @staticmethod
    def format_history(history: List[Dict], max_items: int = None) -> str:
        """
        Format conversation history in a clean, readable way

        Args:
            history: List of chat history items
            max_items: Maximum number of items to include (default from settings)

        Returns:
            Formatted history string
        """
        max_items = max_items or settings.max_ai_context_items
        recent_history = history[-max_items:] if len(history) > max_items else history

        if not recent_history:
            return "（沒有歷史對話紀錄）"

        context_parts = []
        for item in recent_history:
            user_name = item.get('user_name', 'User')
            user_msg = item.get('user_message', '')
            bot_msg = item.get('bot_message', '')

            if user_msg:
                context_parts.append(f"{user_name}: {user_msg}")
            if bot_msg:
                context_parts.append(f"Bot: {bot_msg}")

        return "\n\n".join(context_parts)

    @classmethod
    def build_normal_chat_prompt(cls, user_name: str, history_context: str) -> str:
        """
        Build system prompt for 1-on-1 chat

        Args:
            user_name: Name of the user
            history_context: Formatted conversation history

        Returns:
            Complete system prompt
        """
        return f"""訊息來自 {user_name}

在回答之前請參考對話紀錄（也可能沒有關聯，你在紀錄中是 Bot）。

對話紀錄:
{history_context}

請以友善、真誠的語氣回應，像一個善於傾聽和交流的朋友。

{cls.BASE_PERSONA}

{cls.NORMAL_CHAT_TRAITS}"""

    @classmethod
    def build_group_chat_prompt(cls, user_name: str, history_context: str) -> str:
        """
        Build system prompt for group chat

        Args:
            user_name: Name of the user
            history_context: Formatted conversation history

        Returns:
            Complete system prompt
        """
        return f"""訊息來自 {user_name}

你處在群組聊天之中。在回應之前請參考群組內對話紀錄（可能與新對話沒有關聯，也可能不是在對你說話，你在對話紀錄中是 Bot）。

對話紀錄:
{history_context}

請以友善、自然的語氣回應群組訊息。

{cls.BASE_PERSONA}

{cls.GROUP_CHAT_TRAITS}"""

    @classmethod
    def build_image_analysis_prompt(cls, user_prompt: str = None) -> str:
        """
        Build prompt for image analysis

        Args:
            user_prompt: Optional custom prompt from user

        Returns:
            Image analysis prompt
        """
        if user_prompt:
            return f"{user_prompt}"
        return "請仔細觀察這張圖片，並詳細描述你看到的內容。"

    @classmethod
    def build_audio_analysis_prompt(cls, user_prompt: str = None) -> str:
        """
        Build prompt for audio analysis

        Args:
            user_prompt: Optional custom prompt from user

        Returns:
            Audio analysis prompt
        """
        if user_prompt:
            return f"{user_prompt}"
        return "請分析這段音檔的內容，並提供你的見解。"

    @staticmethod
    def get_history_summary_threshold() -> int:
        """
        Get threshold for when to summarize history
        Returns number of messages before summarization kicks in
        """
        return settings.max_history_items

    @staticmethod
    def should_summarize_history(history_count: int) -> bool:
        """
        Check if history should be summarized

        Args:
            history_count: Number of history items

        Returns:
            True if should summarize
        """
        return history_count > settings.max_ai_context_items * 2


# Global prompt manager instance
prompt_manager = PromptManager()
