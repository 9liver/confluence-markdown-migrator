#!/usr/bin/env python3
"""
Confluence to Markdown Migration Tool - Main CLI Entry Point

This script provides the command-line interface for migrating documentation
from Confluence to Markdown files, Wiki.js, or BookStack with high-fidelity
content conversion and preservation of hierarchical structure.
"""

import argparse
import sys
import os
from pathlib import Path
from typing import Optional, List, Set
import logging

# Add project root to Python path for relative imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# Project imports
from config_loader import ConfigLoader
from logger import setup_logging, log_section, log_config
from models import DocumentationTree, ConfluenceSpace, ConfluencePage
from fetchers import FetcherFactory
from confluence_client import ConfluenceClient

# Optional TUI import - only needed for interactive mode
try:
    from tui.interactive_app import InteractiveMigrationApp
    HAS_TUI = True
except ImportError:
    HAS_TUI = False

from orchestrator import MigrationOrchestrator, MigrationReport

# Version
__version__ = "1.0.0"


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser for CLI."""
    parser = argparse.ArgumentParser(
        description="Migrate documentation from Confluence to Markdown, Wiki.js, or BookStack",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export to markdown files
  python migrate.py --config config.yaml
  
  # Interactive mode with TUI
  python migrate.py --interactive
  
  # Direct import to Wiki.js
  python migrate.py --export-target wikijs
  
  # Direct import to BookStack
  python migrate.py --export-target bookstack
  
  # Import to both wikis
  python migrate.py --export-target both_wikis
  
  # Dry-run mode (preview)
  python migrate.py --dry-run --export-target wikijs
  
  # Filter by spaces
  python migrate.py --spaces "ENG,HR,DOC"
  
  # Single page migration
  python migrate.py --page-id 123456
  
  # Date filtering
  python migrate.py --since-date 2024-01-01
  
  # Verbose logging
  python migrate.py -vv
        """
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )
    
    parser.add_argument(
        '--checkpoint-path',
        type=str,
        help='Path to save/load migration checkpoint for resumability'
    )
    
    parser.add_argument(
        '--resume',
        action=argparse.BooleanOptionalAction,
        default=None,
        help='Resume from checkpoint if available'
    )
    
    parser.add_argument(
        '--mode',
        choices=['api', 'html'],
        default='api',
        help='Fetch mode - API or HTML export (default: api)'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='Path to configuration YAML file (default: config.yaml)'
    )
    
    parser.add_argument(
        '--export-target',
        choices=['markdown_files', 'wikijs', 'bookstack', 'both_wikis'],
        default='markdown_files',
        help='Export destination (default: markdown_files)'
    )
    
    parser.add_argument(
        '--workflow',
        choices=['export_only', 'import_only', 'export_then_import'],
        default='export_only',
        help='Migration workflow (default: export_only)'
    )
    
    parser.add_argument(
        '--spaces',
        type=str,
        help='Comma-separated space keys to migrate (e.g., ENG,HR)'
    )
    
    parser.add_argument(
        '--page-id',
        type=str,
        help='Single page ID to migrate (includes all children)'
    )
    
    parser.add_argument(
        '--since-date',
        type=str,
        help='ISO date to filter pages modified after (e.g., 2024-01-01)'
    )
    
    parser.add_argument(
        '--dry-run',
        action=argparse.BooleanOptionalAction,
        default=None,
        help='Preview migration without making changes'
    )
    
    parser.add_argument(
        '-i', '--interactive',
        action=argparse.BooleanOptionalAction,
        default=None,
        help='Launch interactive TUI for content selection'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='count',
        default=0,
        help='Increase verbosity (-v for INFO, -vv for DEBUG)'
    )
    
    return parser


def validate_configuration(config: dict, args: argparse.Namespace, logger: logging.Logger) -> bool:
    """Validate runtime-specific configuration beyond ConfigLoader.validate()."""
    try:
        # Validate since_date format if provided
        if args.since_date:
            try:
                from datetime import datetime
                datetime.fromisoformat(args.since_date.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                logger.error(f"Invalid ISO date format: {args.since_date}")
                return False
        
        # Validate HTML export path if mode is html
        if args.mode == 'html':
            html_path = config.get('confluence', {}).get('html_export_path')
            if not html_path:
                logger.error("HTML export path must be configured when using html mode")
                return False
            
            path = Path(html_path)
            if not path.exists() or not path.is_dir():
                logger.error(f"HTML export path does not exist or is not a directory: {html_path}")
                return False
        
        # Validate space keys if provided
        if args.spaces:
            space_keys = [key.strip() for key in args.spaces.split(',') if key.strip()]
            if not space_keys:
                logger.error("No valid space keys provided in --spaces argument")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Configuration validation error: {str(e)}")
        return False


def _space_has_selected_pages(space: ConfluenceSpace, selected_ids: Set[str]) -> bool:
    """Check if space contains any selected pages recursively."""
    def check_page_and_children(page: ConfluencePage) -> bool:
        if page.id in selected_ids:
            return True
        for child in page.children:
            if check_page_and_children(child):
                return True
        return False
    
    return any(check_page_and_children(page) for page in space.pages)


def _filter_page_tree(page: ConfluencePage, selected_ids: Set[str]) -> Optional[ConfluencePage]:
    """Recursively filter page tree to include selected pages and their descendants."""
    # Process children first
    filtered_children = []
    for child in page.children:
        filtered_child = _filter_page_tree(child, selected_ids)
        if filtered_child:
            filtered_children.append(filtered_child)
    
    # Include if page itself is selected or has selected descendants
    is_selected = page.id in selected_ids
    has_selected_descendants = len(filtered_children) > 0
    
    if is_selected or has_selected_descendants:
        # Create new page with filtered children
        filtered_page = ConfluencePage(
            id=page.id,
            title=page.title,
            content=page.content,
            space_key=page.space_key,
            parent_id=page.parent_id,
            children=filtered_children
        )
        # Copy other attributes
        filtered_page.markdown_content = page.markdown_content
        filtered_page.attachments = page.attachments
        filtered_page.metadata = page.metadata.copy()
        filtered_page.conversion_metadata = page.conversion_metadata.copy()
        return filtered_page
    
    return None


def _filter_tree_by_selection(tree: DocumentationTree, selected_page_ids: Set[str]) -> DocumentationTree:
    """Filter DocumentationTree to only include selected items from TUI."""
    filtered_tree = DocumentationTree()
    
    for space_key, space in tree.spaces.items():
        # Include space if it contains selected pages
        space_has_selected = _space_has_selected_pages(space, selected_page_ids)
        
        if space_has_selected:
            # Filter pages in space
            filtered_pages = []
            for page in space.pages:
                filtered_page = _filter_page_tree(page, selected_page_ids)
                if filtered_page:
                    filtered_pages.append(filtered_page)
            
            # Create new space with filtered pages
            filtered_space = ConfluenceSpace(
                key=space.key,
                name=space.name,
                description=space.description
            )
            filtered_space.pages = filtered_pages
            
            filtered_tree.add_space(filtered_space)
    
    # Update metadata with accurate counts
    total_pages = 0
    total_attachments = 0
    
    for space_key, space in filtered_tree.spaces.items():
        # Count pages recursively
        def count_pages(pages_list):
            count = 0
            for page in pages_list:
                count += 1
                if page.children:
                    count += count_pages(page.children)
            return count
        
        space_page_count = sum(count_pages([page]) for page in space.pages)
        total_pages += space_page_count
        
        # Count attachments
        def collect_attachments(pages_list):
            attachments = []
            for page in pages_list:
                attachments.extend(page.attachments)
                if page.children:
                    attachments.extend(collect_attachments(page.children))
            return attachments
        
        space_attachment_count = sum(len(collect_attachments([page])) for page in space.pages)
        total_attachments += space_attachment_count
    
    # Update tree metadata
    filtered_tree.metadata['total_pages_fetched'] = total_pages
    filtered_tree.metadata['total_attachments_fetched'] = total_attachments
    
    return filtered_tree


def run_migration(config: dict, args: argparse.Namespace, logger: logging.Logger) -> int:
    """Execute the complete migration pipeline."""
    logger.info("Starting migration pipeline")
    
    # Extract settings
    mode = args.mode
    # Dry-run: use args.dry_run if provided, fall back to config, default to False
    dry_run = args.dry_run if args.dry_run is not None else config.get('migration', {}).get('dry_run', False)
    spaces_arg = args.spaces
    page_id = args.page_id
    since_date = args.since_date
    export_target = args.export_target
    
    logger.info(f"Mode: {mode}, Dry-run: {dry_run}, Export target: {export_target}")
    
    try:
        # Create fetcher
        logger.debug("Creating fetcher")
        fetcher = FetcherFactory.create_fetcher(config, logger)
        
        # Test connectivity (API mode only)
        if mode == 'api':
            logger.info("Testing Confluence connectivity")
            try:
                client = ConfluenceClient.from_config(config)
                # Lightweight test - try to fetch spaces with limit=1
                spaces = client.get_spaces(limit=1)
                if not spaces:
                    logger.warning("No spaces found or connectivity issue detected")
            except Exception as e:
                logger.error(f"Confluence connectivity test failed: {str(e)}")
                return 1
        
        # Build filters
        filters = {}
        if page_id:
            filters['page_id'] = page_id
        if since_date:
            filters['since_date'] = since_date
        
        # Parse space keys
        space_keys = None
        if spaces_arg:
            space_keys = [key.strip() for key in spaces_arg.split(',') if key.strip()]
        elif page_id:
            # If page_id specified, don't limit by spaces
            space_keys = None
        else:
            # Get all spaces if not specified
            space_keys = None
        
        # Handle checkpoint resume logic
        checkpoint_path = args.checkpoint_path or config.get('migration', {}).get('checkpoint_path')
        existing_stats = {}
        workflow = args.workflow
        
        if args.resume and checkpoint_path and Path(checkpoint_path).exists():
            logger.info(f"Attempting to resume from checkpoint: {checkpoint_path}")
            # Create temporary orchestrator for loading state
            temp_orchestrator = MigrationOrchestrator(config, None, logger)
            tree_data, loaded_stats = temp_orchestrator._load_state(checkpoint_path)
            
            if tree_data:
                tree = DocumentationTree.from_dict(tree_data)
                logger.info(f'Resumed tree: {tree.metadata.get("total_pages_fetched", 0)} pages')
                existing_stats = loaded_stats
                logger.info(f'Resuming with {len(loaded_stats)} completed phases')
            else:
                logger.warning('Invalid checkpoint tree data, building fresh tree')
                tree = fetcher.build_documentation_tree(space_keys=space_keys, filters=filters)
        else:
            # Build documentation tree
            logger.info("Building documentation tree from Confluence")
            if space_keys:
                logger.info(f"Fetching spaces: {', '.join(space_keys)}")
            
            tree = fetcher.build_documentation_tree(space_keys=space_keys, filters=filters)
        
        logger.info(
            f"Fetched {len(tree.spaces)} spaces, "
            f"{tree.metadata.get('total_pages_fetched', 0)} pages, "
            f"{tree.metadata.get('total_attachments_fetched', 0)} attachments"
        )
        
        # Interactive mode
        if args.interactive:
            if not HAS_TUI:
                logger.error("Interactive mode requires the 'textual' library. Please install it with: pip install textual")
                return 1
            logger.info("Launching interactive TUI for content selection")
            app = InteractiveMigrationApp(tree, config)
            selection_result = app.run()
            
            if not selection_result or not selection_result.selected_page_ids:
                logger.info("No content selected. Exiting.")
                return 0
            
            # Filter tree based on selection
            selected_page_ids = selection_result.selected_page_ids
            logger.info(f"Filtering tree to {len(selected_page_ids)} selected pages")
            tree = _filter_tree_by_selection(tree, selected_page_ids)
            
            logger.info(
                f"After filtering: {len(tree.spaces)} spaces, "
                f"{tree.metadata.get('total_pages_fetched', 0)} pages"
            )
        
        # Dry run mode - display preview and exit
        if dry_run:
            logger.info("Dry-run mode: displaying migration preview")
            _print_tree_preview(tree)
            logger.info("Dry-run complete. No changes made.")
            return 0
        
        # Run migration orchestrator
        logger.info("Creating migration orchestrator")
        logger.info(f'Workflow: {workflow}, Target: {export_target}')
        orchestrator = MigrationOrchestrator(config, tree, logger, workflow=workflow)
        
        logger.info("Starting migration orchestration")
        report = orchestrator.orchestrate_migration(tree, existing_phase_stats=existing_stats, checkpoint_path=checkpoint_path)
        
        # Display report
        report_generator = MigrationReport(logger)
        console_report = report_generator.format_console_report(report)
        print("\n" + console_report)
        
        # Save checkpoint after successful orchestration
        if checkpoint_path:
            try:
                orchestrator._save_state(tree, report.get('phases', {}), checkpoint_path)
                logger.info(f"Final checkpoint saved to {checkpoint_path}")
            except Exception as e:
                logger.warning(f"Failed to save final checkpoint: {str(e)}")
        
        # Export JSON report
        report_path = config.get('migration', {}).get('report_path', 'migration_report.json')
        try:
            report_generator.export_json_report(report, report_path)
            logger.info(f"Migration report saved to {report_path}")
        except Exception as e:
            logger.warning(f"Failed to export JSON report: {str(e)}")
        
        # Check for errors
        errors = report.get('summary', {}).get('total_errors', 0)
        if errors > 0:
            logger.warning(f"Migration completed with {errors} errors")
            return 1
        else:
            logger.info("Migration completed successfully")
            return 0
        
    except KeyboardInterrupt:
        logger.error("Migration interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}", exc_info=True)
        return 1


def _print_tree_preview(tree: DocumentationTree) -> None:
    """Print a preview of the documentation tree structure."""
    print("\n" + "="*60)
    print("MIGRATION PREVIEW (DRY RUN)")
    print("="*60)
    print(f"\nSpaces to migrate: {len(tree.spaces)}")
    print(f"Total pages: {tree.metadata.get('total_pages_fetched', 0)}")
    print(f"Total attachments: {tree.metadata.get('total_attachments_fetched', 0)}")
    
    print("\nSpace Breakdown:")
    print("-" * 60)
    for space_key, space in sorted(tree.spaces.items()):
        page_count = _count_pages_in_space(space)
        print(f"  {space_key}: {space.name} ({page_count} pages)")
    
    print("\n" + "="*60)


def _count_pages_in_space(space: ConfluenceSpace) -> int:
    """Count total pages in a space including nested children."""
    count = 0
    
    def count_page_and_children(page: ConfluencePage) -> None:
        nonlocal count
        count += 1
        for child in page.children:
            count_page_and_children(child)
    
    for page in space.pages:
        count_page_and_children(page)
    
    return count


def main() -> int:
    """Main entry point for the CLI."""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    try:
        # Setup minimal logging for config loading
        if args.verbose >= 2:
            log_level = 'DEBUG'
        elif args.verbose >= 1:
            log_level = 'INFO'
        else:
            log_level = 'WARNING'
        
        setup_logging(log_level=log_level, config={})
        logger = logging.getLogger(__name__)
        
        log_section("Confluence to Markdown Migration Tool")
        logger.info(f"Version: {__version__}")
        
        # Load configuration
        logger.info(f"Loading configuration from {args.config}")
        config_loader = ConfigLoader()
        config = config_loader.load(args.config)
        
        # Merge with CLI arguments (CLI takes precedence)
        config = config_loader.merge_with_args(config, args)
        
        # Validate configuration
        if not config_loader.validate(config):
            logger.error("Configuration validation failed")
            return 2
        
        # Reconfigure logging with config file settings
        setup_logging(config=config, log_level=log_level)
        logger = logging.getLogger(__name__)
        
        # Log sanitized configuration
        log_config(config)
        
        # Validate runtime configuration
        if not validate_configuration(config, args, logger):
            logger.error("Runtime configuration validation failed")
            return 2
        
        # Run migration
        exit_code = run_migration(config, args, logger)
        
        return exit_code
        
    except FileNotFoundError as e:
        print(f"ERROR: File not found: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"ERROR: Configuration error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nMigration interrupted by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())