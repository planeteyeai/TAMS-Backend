"""
Logging configuration
"""

import logging
import sys

try:
    from pythonjsonlogger import jsonlogger

    _HAS_JSON_LOGGER = True
except ImportError:  # optional dependency — fall back to plain logging
    _HAS_JSON_LOGGER = False


def setup_logging():
    """Setup structured JSON logging (falls back to plain text if unavailable)."""

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if _HAS_JSON_LOGGER:
        formatter = jsonlogger.JsonFormatter(
            fmt='%(timestamp)s %(level)s %(name)s %(message)s',
            timestamp=True,
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s %(levelname)s %(name)s %(message)s'
        )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    # Suppress verbose logging from libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
