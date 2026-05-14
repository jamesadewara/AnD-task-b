import logging
import sys
import contextvars
from loguru import logger

# Context variable to hold the reasoning steps for the current request
reasoning_ctx = contextvars.ContextVar("reasoning_ctx", default=None)

def reasoning_sink(message):
    """
    Sink that captures loguru messages and appends them to the current 
    request's reasoning chain if reasoning_ctx is active.
    """
    ctx = reasoning_ctx.get()
    if ctx is not None and isinstance(ctx, list):
        record = message.record
        step = {
            "step": "internal_log",
            "action": f"{record['name']}:{record['function']}",
            "output": record["message"]
        }
        ctx.append(step)

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout
    )
    # Loguru setup for better tracing if needed
    from loguru import logger
    logger.remove()
    import io
    safe_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    logger.add(safe_stdout, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")

    # Add the reasoning sink
    logger.add(reasoning_sink, level="INFO", colorize=False)
