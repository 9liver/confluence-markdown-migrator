"""Structured logging infrastructure with verbosity levels and progress tracking."""

import logging
import logging.handlers
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Union

import copy


def setup_logging(
    verbosity: int = 0,
    log_file: Optional[str] = None,
    log_format: Optional[str] = None,
    date_format: Optional[str] = None,
    level: Optional[str] = None
) -> logging.Logger:
    """
    Set up structured logging with configurable verbosity levels.
    
    Args:
        verbosity: Verbosity level (0=WARNING, 1=INFO, 2+=DEBUG)
        log_file: Optional path to log file
        log_format: Optional custom log format string
        date_format: Optional custom date format string
        level: Optional explicit log level string
        
    Returns:
        Configured logger instance
    """
    # Determine log level
    if level:
        # Validate level before using it
        allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        level_upper = level.upper()
        if level_upper not in allowed_levels:
            raise ValueError(
                f"Invalid log level '{level}'. Must be one of: {sorted(allowed_levels)}"
            )
        log_level = getattr(logging, level_upper)
    else:
        # Default levels based on verbosity
        if verbosity >= 2:
            log_level = logging.DEBUG
        elif verbosity >= 1:
            log_level = logging.INFO
        else:
            log_level = logging.WARNING
    
    # Set default formats
    if log_format is None:
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    if date_format is None:
        date_format = '%Y-%m-%d %H:%M:%S'
    
    # Configure root logger
    logging.basicConfig(
        level=logging.WARNING,  # Set root to WARNING to avoid noise from dependencies
        format=log_format,
        datefmt=date_format
    )
    
    # Get module logger
    logger = logging.getLogger('confluence_markdown_migrator')
    logger.setLevel(log_level)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler with color support if available
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    try:
        import colorlog
        
        # Use colored formatter if available
        formatter = colorlog.ColoredFormatter(
            fmt='%(log_color)s' + log_format,
            datefmt=date_format,
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
    except ImportError:
        # Fallback to standard formatter
        formatter = logging.Formatter(fmt=log_format, datefmt=date_format)
    
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        try:
            # Use rotating file handler
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,  # Keep 5 backups
                encoding='utf-8'
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(logging.Formatter(fmt=log_format, datefmt=date_format))
            logger.addHandler(file_handler)
            
            logger.info(f"Logging to file: {log_file}")
            logger.info(f"Log level: {logging.getLevelName(log_level)}")
        except Exception as e:
            logger.warning(f"Failed to set up file logging: {str(e)}")
    else:
        logger.info(f"Console logging only. Level: {logging.getLevelName(log_level)}")
    
    return logger


class ProgressTracker:
    """Context manager for tracking progress across operations."""
    
    def __init__(self, total_items: int, item_type: str = "items"):
        """
        Initialize progress tracker.
        
        Args:
            total_items: Total number of items to process
            item_type: Description of item type (e.g., "pages", "attachments")
        """
        self.total_items = total_items
        self.item_type = item_type
        self.processed_items = 0
        self.successful_items = 0
        self.failed_items = 0
        self.start_time: Optional[float] = None
        self.logger = logging.getLogger('confluence_markdown_migrator')
    
    def __enter__(self) -> 'ProgressTracker':
        """Enter progress tracking context."""
        self.start_time = time.time()
        self.logger.info(
            f"Starting processing of {self.total_items} {self.item_type}"
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit progress tracking context and log summary."""
        if self.start_time is None:
            return
        
        elapsed = time.time() - self.start_time
        success_rate = (self.successful_items / self.total_items * 100) if self.total_items > 0 else 0
        
        # Use appropriate log level based on failure rate
        if self.failed_items > 0 and self.failed_items == self.total_items:
            log_method = self.logger.error
        elif self.failed_items > 0:
            log_method = self.logger.warning
        else:
            log_method = self.logger.info
        
        log_method(f"=== Progress Summary: {self.item_type.upper()} ===")
        log_method(f"Total: {self.total_items}")
        log_method(f"Processed: {self.processed_items}")
        log_method(f"Successful: {self.successful_items}")
        log_method(f"Failed: {self.failed_items}")
        log_method(f"Success Rate: {success_rate:.1f}%")
        log_method(f"Elapsed Time: {self._format_elapsed(elapsed)}")
    
    def increment(self, success: bool = True) -> None:
        """
        Increment progress counter.
        
        Args:
            success: Whether the item was processed successfully
        """
        self.processed_items += 1
        
        if success:
            self.successful_items += 1
        else:
            self.failed_items += 1
        
        # Log progress every 10 items or on failure
        if self.processed_items % 10 == 0 or not success:
            remaining = self.total_items - self.processed_items
            status = "Success" if success else "Failed"
            self.logger.info(
                f"Processed {self.processed_items}/{self.total_items} {self.item_type} "
                f"({remaining} remaining) - Last: {status}"
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current progress statistics."""
        if self.start_time is None:
            elapsed = 0.0
        else:
            elapsed = time.time() - self.start_time
        
        return {
            'total': self.total_items,
            'processed': self.processed_items,
            'successful': self.successful_items,
            'failed': self.failed_items,
            'success_rate': (self.successful_items / self.total_items * 100) 
                           if self.total_items > 0 else 0,
            'elapsed_time': elapsed,
            'elapsed_time_formatted': self._format_elapsed(elapsed)
        }
    
    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        """Format elapsed time in human-readable format."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        
        if minutes < 60:
            return f"{minutes}m {seconds}s"
        
        hours = minutes // 60
        minutes = minutes % 60
        
        return f"{hours}h {minutes}m {seconds}s"


def log_section(title: str) -> None:
    """
    Log a decorative section header.
    
    Args:
        title: Section title to display
    """
    logger = logging.getLogger('confluence_markdown_migrator')
    
    separator = "=" * 60
    logger.info("")
    logger.info(separator)
    logger.info(f"  {title.upper()}")
    logger.info(separator)
    logger.info("")


def log_config(config: Dict[str, Any]) -> None:
    """
    Log sanitized configuration for debugging.
    
    Args:
        config: Configuration dictionary to log
    """
    logger = logging.getLogger('confluence_markdown_migrator')
    
    sanitized_config = _sanitize_config(config)
    
    log_section("Configuration")
    
    # Log Confluence settings
    confluence = sanitized_config.get('confluence', {})
    logger.info(f"Confluence Base URL: {confluence.get('base_url', 'Not Set')}")
    logger.info(f"Authentication Type: {confluence.get('auth_type', 'basic')}")
    if confluence.get('username'):
        logger.info(f"Username: {confluence.get('username')}")
    if confluence.get('password'):
        logger.info("Password: ***REDACTED***")
    if confluence.get('api_token'):
        logger.info("API Token: ***REDACTED***")
    if confluence.get('html_export_path'):
        logger.info(f"HTML Export Path: {confluence.get('html_export_path')}")
    
    logger.info("")
    
    # Log Wiki.js settings
    wikijs = sanitized_config.get('wikijs', {})
    if wikijs:
        logger.info(f"Wiki.js Base URL: {wikijs.get('base_url', 'Not Set')}")
        logger.info("API Key: ***REDACTED***" if wikijs.get('api_key') else "API Key: Not Set")
        logger.info("")
    
    # Log BookStack settings
    bookstack = sanitized_config.get('bookstack', {})
    if bookstack:
        logger.info(f"BookStack Base URL: {bookstack.get('base_url', 'Not Set')}")
        logger.info(f"Token ID: {bookstack.get('token_id', 'Not Set')}")
        logger.info("Token Secret: ***REDACTED***" if bookstack.get('token_secret') else "Token Secret: Not Set")
        logger.info("")
    
    # Log migration settings
    migration = sanitized_config.get('migration', {})
    logger.info(f"Migration Mode: {migration.get('mode', 'api')}")
    logger.info(f"Export Target: {migration.get('export_target', 'markdown_files')}")
    logger.info(f"Spaces: {migration.get('spaces', 'All Spaces')}")
    logger.info(f"Page ID: {migration.get('page_id', 'Not Set')}")
    logger.info(f"Since Date: {migration.get('since_date', 'Not Set')}")
    logger.info(f"Dry Run: {migration.get('dry_run', False)}")
    logger.info(f"Interactive: {migration.get('interactive', False)}")
    logger.info(f"Batch Size: {migration.get('batch_size', 5)}")
    logger.info(f"Preserve Page IDs: {migration.get('preserve_page_ids', True)}")
    
    logger.info("")
    
    # Log export settings
    export_settings = sanitized_config.get('export', {})
    logger.info(f"Output Directory: {export_settings.get('output_directory', './confluence-export')}")
    logger.info(f"Markdown Flavor: {export_settings.get('markdown_flavor', 'gfm')}")
    logger.info(f"Create Index Files: {export_settings.get('create_index_files', True)}")
    logger.info(f"Organize by Space: {export_settings.get('organize_by_space', True)}")


def _sanitize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a sanitized copy of configuration with sensitive fields masked.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Sanitized configuration copy
    """
    sanitized = copy.deepcopy(config)
    
    # Define sensitive field patterns
    sensitive_fields = {
        'password', 'token_secret', 'api_key', 'secret', 
        'api_token', 'access_token', 'auth_header'
    }
    
    def mask_sensitive(data: Any, parent_key: str = "") -> Any:
        """Recursively mask sensitive fields."""
        if isinstance(data, dict):
            masked = {}
            for key, value in data.items():
                full_key = f"{parent_key}.{key}" if parent_key else key
                
                # Check if field is sensitive
                is_sensitive = any(sensitive in key.lower() for sensitive in sensitive_fields)
                
                if is_sensitive and isinstance(value, str):
                    masked[key] = "***REDACTED***"
                else:
                    masked[key] = mask_sensitive(value, full_key)
            
            return masked
        elif isinstance(data, list):
            return [mask_sensitive(item, parent_key) for item in data]
        else:
            return data
    
    return mask_sensitive(sanitized)


__all__ = [
    'setup_logging',
    'ProgressTracker', 
    'log_section',
    'log_config'
]
