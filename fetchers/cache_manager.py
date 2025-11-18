"""Cache manager for Confluence API responses with TTL support."""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger('confluence_markdown_migrator.fetcher.cache')


class CacheManager:
    """Manages local caching of Confluence API responses with TTL support."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize cache manager.
        
        Args:
            config: Configuration dictionary with cache settings
        """
        cache_config = config.get('advanced', {})
        
        self.enabled = cache_config.get('cache_enabled', False)
        self.cache_dir = os.path.abspath(cache_config.get('cache_directory', './.cache'))
        self.ttl_seconds = int(cache_config.get('cache_ttl_seconds', 86400))  # 1 day default
        
        # Ensure cache directory exists
        if self.enabled:
            os.makedirs(self.cache_dir, exist_ok=True)
            logger.info(f"Cache enabled: directory={self.cache_dir}, TTL={self.ttl_seconds}s")
        else:
            logger.debug("Cache disabled")
    
    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve data from cache if available and not expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached data or None if not found/expired
        """
        if not self.enabled:
            return None
        
        cache_file = self._get_cache_file_path(key)
        
        if not os.path.exists(cache_file):
            logger.debug(f"Cache miss: {key} (file not found)")
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_entry = json.load(f)
            
            # Check TTL
            cached_time = datetime.fromisoformat(cache_entry['timestamp'])
            age = datetime.utcnow() - cached_time
            
            if age.total_seconds() > self.ttl_seconds:
                logger.debug(f"Cache expired: {key} (age: {age.total_seconds():.0f}s > {self.ttl_seconds}s)")
                # Delete expired cache file
                try:
                    os.remove(cache_file)
                except OSError:
                    pass
                return None
            
            logger.debug(f"Cache hit: {key} (age: {age.total_seconds():.0f}s)")
            return cache_entry['data']
            
        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning(f"Cache read error for {key}: {str(e)}")
            # Remove corrupted cache file
            try:
                os.remove(cache_file)
            except OSError:
                pass
            return None
    
    def set(self, key: str, data: Any) -> bool:
        """
        Store data in cache.
        
        Args:
            key: Cache key
            data: Data to cache (must be JSON serializable)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False
        
        cache_file = self._get_cache_file_path(key)
        
        try:
            cache_entry = {
                'timestamp': datetime.utcnow().isoformat(),
                'ttl_seconds': self.ttl_seconds,
                'data': data
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_entry, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"Cache stored: {key}")
            return True
            
        except (OSError, TypeError) as e:
            logger.warning(f"Cache write error for {key}: {str(e)}")
            return False
    
    def clear(self, pattern: Optional[str] = None) -> int:
        """
        Clear cache entries matching pattern.
        
        Args:
            pattern: Optional pattern to match cache keys (supports wildcards)
                    If None, clears all cache entries
                    
        Returns:
            Number of entries cleared
        """
        if not self.enabled or not os.path.exists(self.cache_dir):
            return 0
        
        cleared = 0
        
        try:
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json'):
                    cache_key = filename[:-5]  # Remove .json extension
                    
                    if pattern is None or self._match_pattern(cache_key, pattern):
                        file_path = os.path.join(self.cache_dir, filename)
                        try:
                            os.remove(file_path)
                            cleared += 1
                            logger.debug(f"Cleared cache: {cache_key}")
                        except OSError as e:
                            logger.warning(f"Failed to clear cache file {file_path}: {str(e)}")
        
        except OSError as e:
            logger.error(f"Failed to list cache directory: {str(e)}")
        
        logger.info(f"Cleared {cleared} cache entries" + (f" matching '{pattern}'" if pattern else ""))
        return cleared
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        if not self.enabled or not os.path.exists(self.cache_dir):
            return {
                'enabled': False,
                'total_entries': 0,
                'total_size_bytes': 0,
                'expired_entries': 0
            }
        
        total_entries = 0
        total_size = 0
        expired_entries = 0
        
        try:
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json'):
                    file_path = os.path.join(self.cache_dir, filename)
                    
                    try:
                        file_size = os.path.getsize(file_path)
                        total_size += file_size
                        total_entries += 1
                        
                        # Check if expired
                        with open(file_path, 'r', encoding='utf-8') as f:
                            cache_entry = json.load(f)
                        
                        cached_time = datetime.fromisoformat(cache_entry['timestamp'])
                        age = datetime.utcnow() - cached_time
                        
                        if age.total_seconds() > cache_entry['ttl_seconds']:
                            expired_entries += 1
                            
                    except (OSError, json.JSONDecodeError, KeyError):
                        # Count as expired if we can't read it properly
                        expired_entries += 1
        
        except OSError:
            pass
        
        return {
            'enabled': True,
            'cache_dir': self.cache_dir,
            'ttl_seconds': self.ttl_seconds,
            'total_entries': total_entries,
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'expired_entries': expired_entries
        }
    
    def _get_cache_file_path(self, key: str) -> str:
        """Get file path for cache key."""
        safe_key = self._sanitize_key(key)
        return os.path.join(self.cache_dir, f"{safe_key}.json")
    
    def _sanitize_key(self, key: str) -> str:
        """
        Sanitize cache key to create valid filename.
        
        Args:
            key: Cache key
            
        Returns:
            Sanitized key safe for use as filename
        """
        # Use hash for long keys
        if len(key) > 200:
            key_hash = hashlib.md5(key.encode('utf-8')).hexdigest()[:16]
            key = key[:100] + "_" + key_hash
        
        # Replace problematic characters
        safe_key = "".join(c for c in key if c.isalnum() or c in "._-")
        return safe_key or "cache_key"
    
    def _match_pattern(self, key: str, pattern: str) -> bool:
        """
        Check if key matches pattern with wildcard support.
        
        Args:
            key: Cache key to check
            pattern: Pattern with * and ? wildcards
            
        Returns:
            True if matches
        """
        import fnmatch
        return fnmatch.fnmatch(key, pattern)
    
    @staticmethod
    def generate_cache_key(endpoint: str, **params) -> str:
        """
        Generate cache key from endpoint and parameters.
        
        Args:
            endpoint: API endpoint name
            **params: Parameters to include in key
            
        Returns:
            Cache key string
        """
        # Sort parameters for consistent key generation
        sorted_params = sorted(params.items())
        param_str = "_".join(f"{k}={v}" for k, v in sorted_params)
        
        if param_str:
            return f"{endpoint}_{param_str}"
        else:
            return endpoint