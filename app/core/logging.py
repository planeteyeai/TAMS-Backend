"""
Logging configuration
"""

import logging
import sys
from pythonjsonlogger import jsonlogger


def setup_logging():
    """Setup structured JSON logging"""
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # JSON formatter for structured logging
    json_formatter = jsonlogger.JsonFormatter(
        fmt='%(timestamp)s %(level)s %(name)s %(message)s',
        timestamp=True
    )
    
    # Stream handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(json_formatter)
    root_logger.addHandler(stream_handler)
    
    # Suppress verbose logging from libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
