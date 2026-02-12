"""
Telegram channel integration using python-telegram-bot.
"""

import asyncio
import logging

from pathlib import Path
from typing import Any
from agp.channels.base import BaseChannel
from agp.bus.events import InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)


class TelegramChannel(BaseChannel):
    """
    Telegram channel using python-telegram-bot v20+.

    Handles:
    - Text messages
    - Photos, documents, voice/audio messages
    - Commands: /start, /reset, /help
    """

    def __init__(self, name: str, bus: Any, config: dict[str, Any]):
        super().__init__(name, bus, config)
        self._bot = None
        self._app: Any = None
        self._consumer_task: asyncio.Task[None] | None = None
        self._handlers_registered = False
        self._media_dir: Path | None = None

    @property
    def token(self) -> str:
        return self.config.get("token", "")

    @property
    def allow_from(self) -> list[str]:
        """List of allowed user IDs (empty = all allowed)."""
        return self.config.get("allowFrom", [])

    def _is_allowed(self, user_id: int) -> bool:
        """Check if user is allowed to use the bot."""
        if not self.allow_from:
            return True
        return str(user_id) in self.allow_from

    async def start(self) -> None:
        """Start Telegram channel with long polling."""
        try:
            from telegram.ext import Application
        except ImportError:
            print("python-telegram-bot not installed. Install with:")
            print("  pip install python-telegram-bot")
            return

        if not self.token:
            print("Telegram token not configured")
            return

        try:
            # Build application
            self._app = Application.builder().token(self.token).build()
            self._bot = self._app.bot

            # Register message handlers
            self._register_handlers()

            # Proper PTB lifecycle: initialize → start → updater.start_polling
            self._running = True
            assert self._app is not None
            await self._app.initialize()
            await self._app.start()
            assert self._app.updater is not None
            await self._app.updater.start_polling()

            # Create media download directory
            workspace = self.config.get("workspace", "~/.agp/workspace")
            self._media_dir = (
                Path(workspace).expanduser().resolve() / "media" / "telegram"
            )
            self._media_dir.mkdir(parents=True, exist_ok=True)

            print(f"✓ Telegram channel started (@{self.token[:8]}...)")

        except Exception as e:
            print(f"✗ Telegram channel failed: {e}")
            import traceback

            traceback.print_exc()

    def _register_handlers(self):
        """Register message and command handlers."""
        if self._handlers_registered:
            return

        async def handle_message(update, context):
            """Handle incoming messages from Telegram (text + media)."""
            try:
                if not update.effective_user or not update.message:
                    return

                user_id = update.effective_user.id

                # Check allow list
                if not self._is_allowed(user_id):
                    await update.message.reply_text(
                        "Sorry, you're not authorized to use this bot."
                    )
                    return

                # Show typing indicator while agent processes
                from telegram.constants import ChatAction

                await update.effective_chat.send_action(ChatAction.TYPING)

                # Extract text content
                content = update.message.text or update.message.caption or ""

                # Download any attached media
                media_paths: list[Path] = []

                # Photos — get the highest resolution version
                if update.message.photo:
                    photo = update.message.photo[-1]  # Highest res
                    path = await self._download_file(photo.file_id, "photo", ".jpg")
                    if path:
                        media_paths.append(path)
                    if not content:
                        content = "[Photo attached]"

                # Documents (PDF, etc.)
                if update.message.document:
                    doc = update.message.document
                    ext = Path(doc.file_name).suffix if doc.file_name else ""
                    path = await self._download_file(doc.file_id, "doc", ext)
                    if path:
                        media_paths.append(path)
                    if not content:
                        content = f"[Document attached: {doc.file_name or 'file'}]"

                # Voice messages
                if update.message.voice:
                    path = await self._download_file(
                        update.message.voice.file_id, "voice", ".ogg"
                    )
                    if path:
                        media_paths.append(path)
                    if not content:
                        content = "[Voice message attached]"

                # Audio files
                if update.message.audio:
                    audio = update.message.audio
                    ext = Path(audio.file_name).suffix if audio.file_name else ".mp3"
                    path = await self._download_file(audio.file_id, "audio", ext)
                    if path:
                        media_paths.append(path)
                    if not content:
                        content = f"[Audio attached: {audio.file_name or 'audio'}]"

                # Create inbound message
                msg = InboundMessage(
                    channel="telegram",
                    sender_id=str(user_id),
                    chat_id=str(update.effective_chat.id),
                    content=content,
                    media=media_paths,
                    metadata={"update_id": update.update_id},
                )

                # Publish to bus (may be rejected by rate limiter)
                accepted = await self.bus.publish_inbound(msg)
                if not accepted:
                    await update.message.reply_text(
                        "⏳ I'm a bit busy right now, please try again in a moment."
                    )
            except Exception as e:
                print(f"Error handling message: {e}")
                import traceback

                traceback.print_exc()

        async def handle_command(update, context):
            """Handle bot commands."""
            try:
                if not update.effective_user or not update.message:
                    return

                command = update.message.text.split()[0]
                user_id = update.effective_user.id

                if not self._is_allowed(user_id):
                    await update.message.reply_text(
                        "Sorry, you're not authorized to use this bot."
                    )
                    return

                if command == "/start":
                    await update.message.reply_text(
                        "👋 Hi! I'm agp, your personal AI assistant.\n\n"
                        "Just send me a message and I'll respond!"
                    )
                elif command == "/help":
                    await update.message.reply_text(
                        "📖 *Available commands:*\n\n"
                        "/start - Start the bot\n"
                        "/help - Show this help\n"
                        "/reset - Reset conversation\n\n"
                        "Just send any message to chat with me!",
                        parse_mode="Markdown",
                    )
                elif command == "/reset":
                    msg = InboundMessage(
                        channel="telegram",
                        sender_id=str(user_id),
                        chat_id=str(update.effective_chat.id),
                        content="/reset",
                        metadata={"command": "reset"},
                    )
                    await self.bus.publish_inbound(msg)
                    await update.message.reply_text("🔄 Conversation reset!")
            except Exception as e:
                print(f"Error handling command: {e}")

        from telegram.ext import MessageHandler, filters, CommandHandler

        # Accept text, photos, documents, voice, and audio
        media_filter = (
            (filters.TEXT & ~filters.COMMAND)
            | filters.PHOTO
            | filters.Document.ALL
            | filters.VOICE
            | filters.AUDIO
        )
        assert self._app is not None
        self._app.add_handler(MessageHandler(media_filter, handle_message))
        self._app.add_handler(
            CommandHandler(["start", "help", "reset"], handle_command)
        )
        self._handlers_registered = True

    async def _download_file(self, file_id: str, prefix: str, ext: str) -> Path | None:
        """Download a Telegram file to the media directory."""
        if not self._media_dir or not self._app:
            return None

        try:
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}_{timestamp}_{file_id[:8]}{ext}"
            dest = self._media_dir / filename

            tg_file = await self._app.bot.get_file(file_id)
            await tg_file.download_to_drive(dest)
            print(f"  Downloaded: {dest.name}")
            return dest
        except Exception as e:
            print(f"Error downloading file {file_id}: {e}")
            return None

    async def stop(self) -> None:
        """Stop Telegram channel with proper PTB shutdown sequence."""
        self._running = False
        if self._app:
            try:
                if self._app.updater and self._app.updater.running:
                    await self._app.updater.stop()
                if self._app.running:
                    await self._app.stop()
                    await self._app.shutdown()
            except Exception as e:
                print(f"Telegram shutdown error: {e}")

    # Telegram message length limit
    MAX_MESSAGE_LENGTH = 4096

    def _chunk_message(self, text: str) -> list[str]:
        """Split a message into chunks that fit Telegram's 4096-char limit.

        Splits at paragraph boundaries first, then sentence boundaries,
        then word boundaries as a last resort.
        """
        if len(text) <= self.MAX_MESSAGE_LENGTH:
            return [text]

        chunks = []
        remaining = text

        while remaining:
            if len(remaining) <= self.MAX_MESSAGE_LENGTH:
                chunks.append(remaining)
                break

            # Find a good split point within the limit
            limit = self.MAX_MESSAGE_LENGTH
            chunk = remaining[:limit]

            # Try splitting at paragraph boundary
            split_at = chunk.rfind("\n\n")
            # Try sentence boundary
            if split_at <= 0:
                split_at = chunk.rfind(". ")
                if split_at > 0:
                    split_at += 1  # Include the period
            # Fall back to word boundary
            if split_at <= 0:
                split_at = chunk.rfind(" ")
            # Absolute fallback: hard cut
            if split_at <= 0:
                split_at = limit

            chunks.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip()

        return chunks

    async def send(self, msg: OutboundMessage) -> None:
        """Send an outbound message to Telegram, chunking if needed."""
        if not self._app:
            logger.warning("Telegram app not initialized")
            return

        logger.info(
            f"TelegramChannel sending message: {len(msg.content)} chars, {len(msg.media)} media items"
        )

        try:
            # Send text content (chunked if needed)
            if msg.content:
                chunks = self._chunk_message(msg.content)
                for chunk in chunks:
                    await self._app.bot.send_message(
                        chat_id=msg.chat_id,
                        text=chunk,
                    )

            # Send any attached media files
            for media_path in msg.media:
                path = Path(media_path)
                logger.debug(f"Checking media path: {path}")
                if not path.exists():
                    logger.warning(
                        f"Media file not found: {media_path} (resolved as {path.absolute()})"
                    )
                    continue

                suffix = path.suffix.lower()
                with open(path, "rb") as f:
                    if suffix in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                        await self._app.bot.send_photo(chat_id=msg.chat_id, photo=f)
                    elif suffix == ".ogg":
                        # Send as a voice message (the round bubble)
                        await self._app.bot.send_voice(chat_id=msg.chat_id, voice=f)
                    elif suffix in (".mp3", ".m4a", ".wav", ".flac"):
                        # Send as a playable audio file
                        await self._app.bot.send_audio(chat_id=msg.chat_id, audio=f)
                    else:
                        await self._app.bot.send_document(
                            chat_id=msg.chat_id, document=f
                        )

        except Exception:
            logger.exception(
                f"Error sending message to Telegram (chat_id: {msg.chat_id})"
            )
