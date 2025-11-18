"""Configuration loader with YAML support and environment variable substitution."""

import copy
import os
import re
from typing import Any, Dict, Optional, Union
from urllib.parse import urlparse

import yaml

from models import ExportTarget


class ConfigLoader:
    """Handles loading and validation of configuration files."""
    
    ENV_VAR_PATTERN = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')
    
    @classmethod
    def load(cls, config_path: str) -> Dict[str, Any]:
        """
        Load configuration from YAML file with environment variable substitution.
        
        Args:
            config_path: Path to YAML configuration file
            
        Returns:
            Parsed configuration dictionary
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If YAML parsing fails
        """
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        if not isinstance(config_data, dict):
            raise ValueError("Configuration file must contain a dictionary")
        
        # Substitute environment variables recursively
        config_data = cls._substitute_env_vars_recursive(config_data)
        
        return config_data
    
    @classmethod
    def validate(cls, config: Dict[str, Any]) -> None:
        """
        Validate configuration for required fields and correct values.
        
        Args:
            config: Configuration dictionary to validate
            
        Raises:
            ValueError: If validation fails
        """
        # Validate migration mode
        mode = get_nested(config, 'migration.mode', 'api')
        if mode not in ['api', 'html']:
            raise ValueError("migration.mode must be 'api' or 'html'")
        
        # Validate export target
        export_target = get_nested(config, 'migration.export_target', 'markdown_files')
        try:
            ExportTarget(export_target)
        except ValueError:
            raise ValueError(
                f"migration.export_target must be one of: {[t.value for t in ExportTarget]}"
            )
        
        # Validate API mode settings
        if mode == 'api':
            cls._validate_required_field(config, 'confluence.base_url')
            auth_type = get_nested(config, 'confluence.auth_type', 'basic')
            
            if auth_type == 'basic':
                cls._validate_required_field(config, 'confluence.username')
                cls._validate_required_field(config, 'confluence.password')
            elif auth_type == 'bearer':
                cls._validate_required_field(config, 'confluence.api_token')
            else:
                raise ValueError("confluence.auth_type must be 'basic' or 'bearer'")
            
            # Validate base URL
            base_url = get_nested(config, 'confluence.base_url')
            if base_url:
                cls._validate_url(base_url, 'confluence.base_url')
        
        # Validate HTML mode settings
        elif mode == 'html':
            cls._validate_required_field(config, 'confluence.html_export_path')
            html_path = get_nested(config, 'confluence.html_export_path')
            if html_path and not os.path.isdir(html_path):
                raise ValueError(
                    f"confluence.html_export_path '{html_path}' is not a valid directory"
                )
        
        # Validate Wiki.js settings if used
        if export_target in [ExportTarget.WIKIJS.value, ExportTarget.BOTH_WIKIS.value]:
            cls._validate_required_field(config, 'wikijs.base_url')
            cls._validate_required_field(config, 'wikijs.api_key')
            
            base_url = get_nested(config, 'wikijs.base_url')
            if base_url:
                cls._validate_url(base_url, 'wikijs.base_url')
            
            # Validate conflict_resolution (must be one of: skip, overwrite, version)
            conflict_resolution = get_nested(config, 'wikijs.conflict_resolution', 'skip')
            if conflict_resolution not in ['skip', 'overwrite', 'version']:
                raise ValueError("wikijs.conflict_resolution must be one of: skip, overwrite, version")
            
            # Validate preserve_labels (must be boolean)
            preserve_labels = get_nested(config, 'wikijs.preserve_labels', True)
            if not isinstance(preserve_labels, bool):
                raise ValueError("wikijs.preserve_labels must be a boolean")
            
            # Validate include_space_in_path (must be boolean)
            include_space_in_path = get_nested(config, 'wikijs.include_space_in_path', True)
            if not isinstance(include_space_in_path, bool):
                raise ValueError("wikijs.include_space_in_path must be a boolean")
            
            # Validate asset_upload settings
            asset_upload = get_nested(config, 'wikijs.asset_upload', {})
            
            # Validate asset_upload.enabled
            enabled = asset_upload.get('enabled', True)
            if not isinstance(enabled, bool):
                raise ValueError("wikijs.asset_upload.enabled must be a boolean")
            
            # Validate asset_upload.max_workers
            max_workers = asset_upload.get('max_workers', 3)
            if not isinstance(max_workers, int) or max_workers < 1:
                raise ValueError("wikijs.asset_upload.max_workers must be a positive integer")
            
            # Validate asset_upload.folder
            folder = asset_upload.get('folder', '/confluence-assets')
            if folder and not folder.startswith('/'):
                raise ValueError("wikijs.asset_upload.folder must be an absolute path starting with /")
            
            # Validate asset_upload.rewrite_links
            rewrite_links = asset_upload.get('rewrite_links', True)
            if not isinstance(rewrite_links, bool):
                raise ValueError("wikijs.asset_upload.rewrite_links must be a boolean")
        
        
        # Validate BookStack settings if used
        if export_target in [ExportTarget.BOOKSTACK.value, ExportTarget.BOTH_WIKIS.value]:
            cls._validate_required_field(config, 'bookstack.base_url')
            cls._validate_required_field(config, 'bookstack.token_id')
            cls._validate_required_field(config, 'bookstack.token_secret')
            
            base_url = get_nested(config, 'bookstack.base_url')
            if base_url:
                cls._validate_url(base_url, 'bookstack.base_url')
        
        # Validate markdown files export settings
        if export_target == ExportTarget.MARKDOWN_FILES.value:
            cls._validate_required_field(config, 'export.output_directory')
            output_dir = get_nested(config, 'export.output_directory')
            if output_dir and os.path.exists(output_dir) and not os.path.isdir(output_dir):
                raise ValueError(f"export.output_directory '{output_dir}' is not a directory")
        
        # Validate markdown flavor
        markdown_flavor = get_nested(config, 'export.markdown_flavor', 'gfm')
        if markdown_flavor not in ['commonmark', 'gfm', 'wikijs']:
            raise ValueError("export.markdown_flavor must be 'commonmark', 'gfm', or 'wikijs'")
        
        # Validate timeout settings
        timeout = get_nested(config, 'advanced.request_timeout', 30)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("advanced.request_timeout must be a positive number")
        
        batch_size = get_nested(config, 'migration.batch_size', 5)
        if not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("migration.batch_size must be a positive integer")
    
    @classmethod
    def merge_with_args(cls, config: Dict[str, Any], args) -> Dict[str, Any]:
        """
        Merge configuration file with CLI arguments.
        CLI arguments take precedence over config file values.
        
        Args:
            config: Base configuration dictionary
            args: CLI arguments with attributes matching config keys
            
        Returns:
            Merged configuration dictionary
        """
        merged = copy.deepcopy(config)
        
        # Ensure nested dictionaries exist
        if 'migration' not in merged:
            merged['migration'] = {}
        if 'confluence' not in merged:
            merged['confluence'] = {}
        if 'export' not in merged:
            merged['export'] = {}
        if 'logging' not in merged:
            merged['logging'] = {}
        
        # Merge migration settings
        if hasattr(args, 'mode') and args.mode:
            merged['migration']['mode'] = args.mode
        
        if hasattr(args, 'spaces') and args.spaces:
            merged['migration']['spaces'] = args.spaces
        
        if hasattr(args, 'page_id') and args.page_id:
            merged['migration']['page_id'] = args.page_id
        
        if hasattr(args, 'since_date') and args.since_date:
            merged['migration']['since_date'] = args.since_date
        
        if hasattr(args, 'dry_run'):
            merged['migration']['dry_run'] = args.dry_run
        
        if hasattr(args, 'interactive'):
            merged['migration']['interactive'] = args.interactive
        
        if hasattr(args, 'batch_size'):
            merged['migration']['batch_size'] = args.batch_size
        
        # Merge export target
        if hasattr(args, 'export_target') and args.export_target:
            if isinstance(args.export_target, ExportTarget):
                merged['migration']['export_target'] = args.export_target.value
            else:
                merged['migration']['export_target'] = args.export_target
        
        # Merge confluence settings
        if hasattr(args, 'confluence_url') and args.confluence_url:
            merged['confluence']['base_url'] = args.confluence_url
        
        if hasattr(args, 'username') and args.username:
            merged['confluence']['username'] = args.username
        
        if hasattr(args, 'password') and args.password:
            merged['confluence']['password'] = args.password
        
        # Merge export settings
        if hasattr(args, 'output_dir') and args.output_dir:
            merged['export']['output_directory'] = args.output_dir
        
        if hasattr(args, 'verbose'):
            if hasattr(args, 'verbose_level') and args.verbose_level and args.verbose:
                merged['logging']['level'] = args.verbose_level
            elif args.verbose:
                merged['logging']['level'] = 'INFO'
        
        return merged
    
    @classmethod
    def _substitute_env_vars_recursive(cls, data: Any) -> Any:
        """Recursively substitute environment variables in data structure."""
        if isinstance(data, dict):
            return {key: cls._substitute_env_vars_recursive(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [cls._substitute_env_vars_recursive(item) for item in data]
        elif isinstance(data, str):
            return cls._substitute_env_vars(data)
        else:
            return data
    
    @classmethod
    def _substitute_env_vars(cls, value: str) -> str:
        """Substitute environment variables in a string value."""
        def replace_match(match):
            var_name = match.group(1)
            env_value = os.getenv(var_name)
            return env_value if env_value is not None else match.group(0)
        
        return cls.ENV_VAR_PATTERN.sub(replace_match, value)
    
    @staticmethod
    def _validate_required_field(config_section: dict, field: str) -> None:
        """Validate that a required field exists and has a value."""
        value = get_nested(config_section, field)
        if value is None or value == '':
            raise ValueError(f"Missing required configuration: {field}")
        
        # Check for unsubstituted environment variables
        if isinstance(value, str) and '${' in value:
            # Use the ENV_VAR_PATTERN regex to extract the variable name
            match = ConfigLoader.ENV_VAR_PATTERN.search(value)
            if match:
                var_name = match.group(1)
            else:
                var_name = value  # Fallback if pattern doesn't match
            raise ValueError(
                f"Configuration field '{field}' contains unsubstituted environment variable: {value}. "
                f"Please set the {var_name} environment variable or provide a value in config file."
            )
    
    @staticmethod
    def _validate_url(url: str, field_name: str) -> None:
        """Validate URL format."""
        try:
            parsed = urlparse(url)
            if not parsed.scheme or parsed.scheme not in ['http', 'https']:
                raise ValueError(f"{field_name} must use http or https scheme: {url}")
            if not parsed.netloc:
                raise ValueError(f"{field_name} missing hostname: {url}")
        except Exception as e:
            raise ValueError(f"Invalid URL for {field_name}: {url}. Error: {str(e)}")


def get_nested(config: dict, path: str, default: Any = None) -> Any:
    """Safely retrieve nested configuration values using dot notation.
    
    Args:
        config: Configuration dictionary
        path: Dot-separated path (e.g., "confluence.base_url")
        default: Default value if path doesn't exist
        
    Returns:
        Value at the nested path or default
    """
    keys = path.split('.')
    value = config
    
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    
    return value


__all__ = ['ConfigLoader', 'get_nested']
