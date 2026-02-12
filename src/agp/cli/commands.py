"""
CLI commands for agp.

Uses Typer for command-line interface.
"""

import asyncio
import traceback
import logging
from typing import Optional

import typer
from agp.config import load_config
from agp.agent import AgpAgent
from agp.bus import MessageBus, OutboundMessage
from agp.channels import ChannelManager
from agp.cron.service import CronService
from agp.heartbeat.service import HeartbeatService
from agp.health import HealthServer


app = typer.Typer(
    name="agp",
    help="AGP — Claude Agent SDK Edition",
)


@app.command()
def agent(
    message: Optional[str] = typer.Option(
        None, "-m", "--message", help="Single message to process"
    ),
    model: str = typer.Option(
        "sonnet", "--model", help="Model to use (haiku/sonnet/opus)"
    ),
):
    """
    Run agent in CLI mode.

    Without -m: Interactive REPL (TODO)
    With -m: Process single message and exit
    """
    if message:
        asyncio.run(_single_message(message, model))
    else:
        typer.echo("Interactive REPL coming soon. Use -m for single messages.")
        typer.echo('Example: agp agent -m "What\'s the weather?"')


def _build_provider_env(config) -> dict[str, str]:
    """Build provider environment variables from config."""
    env = {}
    if config.provider.base_url:
        env["ANTHROPIC_BASE_URL"] = config.provider.base_url
    if config.provider.auth_token:
        env["ANTHROPIC_AUTH_TOKEN"] = config.provider.auth_token
    if config.provider.model_override:
        env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = config.provider.model_override
        env["ANTHROPIC_DEFAULT_CLAUDE_MODEL"] = config.provider.model_override
        env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = config.provider.model_override
    return env


async def _single_message(message: str, model: str) -> None:
    """Process a single message and print response."""
    # Load config
    config = load_config()
    provider_env = _build_provider_env(config)

    # Create agent (no bus needed for direct mode)
    agent = AgpAgent(
        workspace=config.workspace,
        model=model,
        provider_env=provider_env,
        mcp_servers=config.mcp_servers,
        env=config.env,
    )

    # Process message
    response = await agent.process_direct(
        prompt=message,
        session_key="cli:direct",
    )

    typer.echo(f"\n{response}")


@app.command()
def status():
    """Show configuration and status."""
    config = load_config()

    typer.echo("\n=== AGP Status ===")
    typer.echo(f"Workspace: {config.workspace}")
    typer.echo(f"Model: {config.model}")
    typer.echo("\nChannels:")

    for channel_name, channel_config in config.channels.model_dump().items():
        enabled = channel_config.get("enabled", False)
        status = "✓ enabled" if enabled else "✗ disabled"
        typer.echo(f"  {channel_name}: {status}")

    if config.env:
        typer.echo("\nEnvironment Variables:")
        for k, v in config.env.items():
            typer.echo(f"  {k}={v}")

    typer.echo("")


@app.command()
def heartbeat():
    """
    Test heartbeat — run a single heartbeat tick.

    This checks HEARTBEAT.md and has the agent process any tasks.
    """
    asyncio.run(_heartbeat_tick())


async def _heartbeat_tick() -> None:
    """Run a single heartbeat tick."""
    config = load_config()
    provider_env = _build_provider_env(config)

    typer.echo(f"Workspace: {config.workspace}")
    typer.echo(f"Model: {config.model}")

    # Create agent (no bus/cron for direct mode)
    agent = AgpAgent(
        workspace=config.workspace,
        model=config.model,
        provider_env=provider_env,
        mcp_servers=config.mcp_servers,
        env=config.env,
    )

    # Create heartbeat service with agent reference
    heartbeat = HeartbeatService(
        agent=agent,
        interval_s=1,  # Short interval for manual test
    )

    typer.echo("\n=== Running Heartbeat Tick ===")
    await heartbeat._tick()
    typer.echo("\n=== Heartbeat Tick Complete ===")


@app.command()
def gateway(
    model: str = typer.Option(
        "sonnet", "--model", help="Model to use (haiku/sonnet/opus)"
    ),
):
    """
    Start full gateway server.

    This runs:
    - Message bus for routing
    - Agent processing inbound messages
    - All enabled channels (Telegram, etc.)
    - Cron scheduler
    - Heartbeat monitor
    """
    config = load_config()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger_agp = logging.getLogger("agp")
    logger_agp.info("Starting AGP Gateway")

    typer.echo("\n=== AGP Gateway ===")
    typer.echo(f"Workspace: {config.workspace}")
    typer.echo(f"Model: {config.model}")

    # Core infrastructure
    bus = MessageBus()
    bus.start()  # start() is synchronous

    # Import channel manager and telegram channel (delayed import to avoid circular dependency)
    from agp.channels.telegram import TelegramChannel

    # Build provider environment variables from config
    provider_env = _build_provider_env(config)

    if provider_env:
        typer.echo(f"Provider: {config.provider.base_url or 'default'}")

    # Create agent first (without services - will add after)
    agent = AgpAgent(
        workspace=config.workspace,
        model=model,
        bus=bus,
        provider_env=provider_env,
        mcp_servers=config.mcp_servers,
        env=config.env,
    )

    # Now create cron service with agent reference
    cron = CronService(agent=agent, interval_s=60)

    # Create heartbeat service with agent reference
    heartbeat = HeartbeatService(agent=agent, interval_s=30 * 60)

    # Update agent with service references (services exist now)
    agent.cron = cron
    agent.bus = bus

    # Channel manager - initialize with bus, then add channels from config
    channels = ChannelManager(bus)
    tg_config = config.channels.telegram.model_dump()
    tg_config["workspace"] = str(config.workspace)
    channels.init_channel("telegram", TelegramChannel, tg_config)

    # Health endpoint
    health_server = HealthServer(bus=bus, channels=channels)

    # Main gateway loop
    async def run_gateway():
        """Main gateway loop coordinating all services."""
        import signal

        # Use asyncio Event for shutdown coordination
        shutdown_event = asyncio.Event()

        # Define coroutines for each service
        async def _send_typing(chat_id: str):
            """Periodically send typing indicator to Telegram."""
            tg_channel = channels.channels.get("telegram")
            if not tg_channel or not isinstance(tg_channel, TelegramChannel) or not tg_channel._app:
                return
            try:
                from telegram.constants import ChatAction

                while True:
                    await tg_channel._app.bot.send_chat_action(
                        chat_id=int(chat_id),
                        action=ChatAction.TYPING,
                    )
                    await asyncio.sleep(4)  # Telegram typing expires after ~5s
            except asyncio.CancelledError:
                pass
            except Exception:
                pass  # Non-critical, don't break the loop

        async def agent_loop():
            """Agent consumes inbound messages and processes them."""
            typer.echo("Agent loop started (Ctrl+C to stop)")
            max_retries = 2
            try:
                while not shutdown_event.is_set():
                    msg = await bus.consume_inbound(timeout=1)
                    if msg is None:
                        continue

                    # Start typing indicator
                    typing_task = asyncio.create_task(_send_typing(msg.chat_id))

                    try:
                        for attempt in range(max_retries + 1):
                            try:
                                response = await agent.process_message(msg)
                                await bus.publish_outbound(response)
                                break
                            except Exception as e:
                                typer.echo(
                                    f"Agent error (attempt {attempt + 1}/{max_retries + 1}): {e}"
                                )
                                traceback.print_exc()
                                if attempt < max_retries:
                                    await asyncio.sleep(2**attempt)
                                else:
                                    # Final failure — send error to user
                                    error_msg = OutboundMessage(
                                        channel=msg.channel,
                                        chat_id=msg.chat_id,
                                        content="⚠️ Sorry, I ran into an error processing your message. Please try again.",
                                    )
                                    await bus.publish_outbound(error_msg)
                    finally:
                        typing_task.cancel()

            except asyncio.CancelledError:
                typer.echo("Agent loop cancelled")

        async def outbound_dispatcher():
            """Dispatch outbound messages from bus to channels."""
            typer.echo("Outbound dispatcher started")
            try:
                while not shutdown_event.is_set():
                    msg = await bus.consume_outbound(timeout=1)
                    if msg is None:
                        continue
                    await channels._dispatch_outbound(msg)
            except asyncio.CancelledError:
                typer.echo("Outbound dispatcher cancelled")

        async def cron_loop():
            """Cron service background loop."""
            await cron.start()

        async def heartbeat_loop():
            """Heartbeat service background loop."""
            await heartbeat.start()

        async def channels_loop():
            """Start all enabled channels."""
            await channels.start_all()

        async def health_loop():
            """Start health HTTP server."""
            await health_server.start()

        # Create all tasks
        typer.echo("Starting background services...")
        cron_task = asyncio.create_task(cron_loop())
        heartbeat_task = asyncio.create_task(heartbeat_loop())
        channels_task = asyncio.create_task(channels_loop())
        agent_task = asyncio.create_task(agent_loop())
        dispatcher_task = asyncio.create_task(outbound_dispatcher())
        health_task = asyncio.create_task(health_loop())

        # Setup signal handlers using asyncio's add_signal_handler
        loop = asyncio.get_running_loop()

        def _handle_signal():
            """Handle shutdown signal from within asyncio context."""
            typer.echo("\nShutdown signal received, stopping...")
            shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _handle_signal)

        try:
            # Wait for shutdown signal
            await shutdown_event.wait()
            typer.echo("\nShutdown event triggered, cleaning up...")

        finally:
            # Remove signal handlers
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.remove_signal_handler(sig)

            # Cancel all running tasks
            typer.echo("Cancelling tasks...")
            all_tasks = [
                agent_task,
                dispatcher_task,
                cron_task,
                heartbeat_task,
                channels_task,
                health_task,
            ]
            for task in all_tasks:
                if not task.done():
                    task.cancel()

            # Wait for all tasks to complete
            typer.echo("Waiting for tasks to finish...")
            await asyncio.gather(*all_tasks, return_exceptions=True)

            # Stop services
            typer.echo("Stopping services...")
            await cron.stop()
            await heartbeat.stop()
            await health_server.stop()
            await channels.stop_all()
            await bus.stop()

            typer.echo("Goodbye!")

    asyncio.run(run_gateway())


def main() -> None:
    """Entry point for CLI."""
    app()
