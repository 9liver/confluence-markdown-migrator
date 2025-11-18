"""Fetchers package for retrieving Confluence content via API or HTML export."""

from .base_fetcher import BaseFetcher, FetcherError, FilterValidationError
from .api_fetcher import ApiFetcher
from .html_fetcher import HtmlFetcher

class FetcherFactory:
    """Factory for creating fetcher instances based on configuration."""
    
    @staticmethod
    def create_fetcher(config: dict, logger):
        """Create appropriate fetcher based on config mode.
        
        Args:
            config: Configuration dictionary
            logger: Logger instance
            
        Returns:
            BaseFetcher instance (ApiFetcher or HtmlFetcher)
            
        Raises:
            ValueError: If mode is invalid
        """
        mode = config.get('migration', {}).get('mode', 'api')
        
        if mode == 'api':
            return ApiFetcher(config, logger)
        elif mode == 'html':
            return HtmlFetcher(config, logger)
        else:
            raise ValueError(f"Invalid fetch mode: {mode}. Must be 'api' or 'html'.")

__all__ = [
    'BaseFetcher',
    'FetcherError',
    'FilterValidationError',
    'ApiFetcher',
    'HtmlFetcher',
    'FetcherFactory'
]
