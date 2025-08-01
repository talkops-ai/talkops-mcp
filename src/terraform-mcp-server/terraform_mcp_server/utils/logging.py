# Copyright (C) 2025 StructBinary
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from loguru import logger
import sys
from enum import Enum
from loguru import logger
from mcp.server.fastmcp import Context
from typing import Any

class LogLevel(Enum):
    """Enum for log levels."""

    DEBUG = 'debug'
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    CRITICAL = 'critical'

def log_with_request_id(ctx: Context, level: LogLevel, message: str, **kwargs: Any) -> None:
    """Log a message with the request ID from the context.

    Args:
        ctx: The MCP context containing the request ID
        level: The log level (from LogLevel enum)
        message: The message to log
        **kwargs: Additional fields to include in the log message
    """
    # Format the log message with request_id
    log_message = f'[request_id={ctx.request_id}] {message}'

    # Log at the appropriate level
    if level == LogLevel.DEBUG:
        logger.debug(log_message, **kwargs)
    elif level == LogLevel.INFO:
        logger.info(log_message, **kwargs)
    elif level == LogLevel.WARNING:
        logger.warning(log_message, **kwargs)
    elif level == LogLevel.ERROR:
        logger.error(log_message, **kwargs)
    elif level == LogLevel.CRITICAL:
        logger.critical(log_message, **kwargs)  

# Configure Loguru globally for the project (stdout, standard format, INFO level)
logger.remove()
logger.add(sys.stdout, format='[<green>{time:YYYY-MM-DD HH:mm:ss}</green>] <level>{level: <8}</level> <cyan>{name}</cyan>: <level>{message}</level>', level='INFO')

def get_logger(name: str = None):
    """
    Returns the Loguru logger for use in this project.
    Usage:
        from tf_knowledge_graph.utils.logging import get_logger
        logger = get_logger(__name__)
    Note: Loguru automatically handles module names in output.
    """
    return logger 