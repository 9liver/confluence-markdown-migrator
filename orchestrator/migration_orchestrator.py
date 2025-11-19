"""
Migration orchestrator for coordinating the complete migration pipeline.

This module provides the central coordinator that sequences all migration phases:
Fetch → Convert → Export/Import → Report. It handles the complete pipeline for
migrating Confluence content to various targets.
"""

import logging
import time
import json
from typing import Optional, Dict, Any, Set
from pathlib import Path

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

from models import DocumentationTree, ConfluencePage
from converters import convert_page
from exporters import MarkdownExporter, MarkdownReader
from importers import WikiJsImporter, BookStackImporter
from logger import log_section, ProgressTracker
from orchestrator.migration_report import MigrationReport
from integrity_verifier import IntegrityVerifier

logger = logging.getLogger(__name__)


class MigrationOrchestrator:
    """Central coordinator sequencing all migration phases: Fetch → Convert → Export/Import → Report."""
    
    def __init__(self, config: Dict[str, Any], tree, logger: Optional[logging.Logger] = None, workflow: Optional[str] = None, export_dir: Optional[str] = None):
        """
        Initialize migration orchestrator.

        Args:
            config: Configuration dictionary
            tree: DocumentationTree with Confluence content
            logger: Optional logger instance
            workflow: Optional workflow mode ('export_only', 'import_only', 'export_then_import', 'import_from_markdown')
            export_dir: Optional directory for exporting/importing Markdown files
        """
        self.config = config
        self.tree = tree
        self.logger = logger or logging.getLogger(__name__)

        # Determine export target
        import_target = config.get('migration', {}).get('export_target', 'markdown_files')
        self.export_target = import_target

        # Set workflow mode
        self.workflow = workflow or 'export_only'

        # Store export directory override
        self.export_dir = export_dir

        # Initialize component references (created on-demand)
        self.converter = None
        self.exporter = None
        self.markdown_reader = None
        self.wikijs_importer = None
        self.bookstack_importer = None
        self.report_generator = None
        self.integrity_verifier = None

        # Extract integrity verification settings
        self.verify_integrity = config.get('advanced', {}).get('integrity_verification', {}).get('enabled', False)

        self.logger.info(f"MigrationOrchestrator initialized with workflow: {self.workflow}, target: {self.export_target}, verify_integrity: {self.verify_integrity}")
    
    def orchestrate_migration(self, tree: DocumentationTree, existing_phase_stats: Optional[Dict[str, Any]] = None, checkpoint_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Orchestrate the complete migration pipeline.
        
        Args:
            tree: DocumentationTree to process
            existing_phase_stats: Optional stats from resumed checkpoint
            checkpoint_path: Optional path for saving checkpoints
            
        Returns:
            Comprehensive report dictionary
        """
        self.logger.info("Starting migration orchestration")
        start_time = time.time()
        
        phase_stats = {}
        existing_stats = existing_phase_stats or {}

        try:
            # Handle import_from_markdown workflow - skip fetch/convert phases
            if self.workflow == 'import_from_markdown':
                self.logger.info("Executing import_from_markdown workflow - skipping fetch and conversion phases")

                # Load tree from markdown files
                phase_stats['markdown_import'] = self._execute_markdown_import()
                if phase_stats['markdown_import'].get('failed'):
                    raise Exception(f"Markdown import failed: {phase_stats['markdown_import'].get('error')}")

                # Get the loaded tree
                tree = phase_stats['markdown_import'].get('tree')
                if not tree:
                    raise Exception("No tree loaded from markdown import")

                # Skip to wiki import phase
                if self.export_target == 'wikijs':
                    phase_stats['wikijs_import'] = self._execute_wikijs_import(tree)
                elif self.export_target == 'bookstack':
                    phase_stats['bookstack_import'] = self._execute_bookstack_import(tree)
                elif self.export_target == 'both_wikis':
                    phase_stats['wikijs_import'] = self._execute_wikijs_import(tree)
                    phase_stats['bookstack_import'] = self._execute_bookstack_import(tree)
                else:
                    self.logger.warning(
                        f"import_from_markdown workflow requires wiki target, got '{self.export_target}'"
                    )

                # Calculate duration and generate report
                migration_duration = time.time() - start_time
                self.logger.info("Generating migration report")
                report = self._generate_report(tree, phase_stats, migration_duration)
                self.logger.info(f"Migration orchestration complete in {migration_duration:.2f}s")
                return report

            # Standard workflow - Phase 1.5: Integrity Verification (if enabled and not resumed)
            if self.verify_integrity and (not existing_stats or 'integrity_verification' not in existing_stats):
                self.logger.info("Executing Phase 1.5: Integrity Verification")
                verification_report = self._execute_integrity_verification(tree)
                phase_stats['integrity_verification'] = verification_report

                # Save checkpoint after verification
                if checkpoint_path:
                    self._save_state(tree, phase_stats, checkpoint_path)
            elif existing_stats and 'integrity_verification' in existing_stats:
                self.logger.info("Skipping integrity verification (resumed)")
                phase_stats['integrity_verification'] = existing_stats['integrity_verification']
                # Restore integrity report to tree
                tree.integrity_report = existing_stats['integrity_verification']
            else:
                self.logger.info("Integrity verification disabled")
                phase_stats['integrity_verification'] = {'enabled': False}

            # Phase 1: Content Conversion
            if existing_stats and 'content_conversion' in existing_stats:
                self.logger.info("Skipping content conversion (resumed)")
                phase_stats['content_conversion'] = existing_stats['content_conversion']
            else:
                self.logger.info("Executing Phase 1: Content Conversion")
                phase_stats['content_conversion'] = self._execute_content_conversion(tree)
                # Save checkpoint after conversion
                if checkpoint_path:
                    self._save_state(tree, phase_stats, checkpoint_path)
            
            # Phase 2: Export/Import based on workflow and target
            self.logger.info(f"Executing Phase 2: workflow={self.workflow}, target={self.export_target}")
            
            # Track pre-phase stats for rollback
            pre_phase_stats = phase_stats.copy()
            rollback_occurred = False
            
            try:
                # Handle export_then_import workflow
                if self.workflow == 'export_then_import':
                    if existing_stats and 'markdown_export' in existing_stats:
                        self.logger.info("Skipping markdown export (resumed)")
                        phase_stats['markdown_export'] = existing_stats['markdown_export']
                    else:
                        phase_stats['markdown_export'] = self._execute_markdown_export(tree)
                        if checkpoint_path:
                            self._save_state(tree, phase_stats, checkpoint_path)
                    
                    # Proceed to import if target is wiki
                    if self.export_target in ['wikijs', 'bookstack', 'both_wikis']:
                        if self.export_target == 'wikijs':
                            if existing_stats and 'wikijs_import' in existing_stats:
                                self.logger.info("Skipping Wiki.js import (resumed)")
                                phase_stats['wikijs_import'] = existing_stats['wikijs_import']
                            else:
                                phase_stats['wikijs_import'] = self._execute_wikijs_import(tree)
                        elif self.export_target == 'bookstack':
                            if existing_stats and 'bookstack_import' in existing_stats:
                                self.logger.info("Skipping BookStack import (resumed)")
                                phase_stats['bookstack_import'] = existing_stats['bookstack_import']
                            else:
                                phase_stats['bookstack_import'] = self._execute_bookstack_import(tree)
                        elif self.export_target == 'both_wikis':
                            if existing_stats and 'wikijs_import' in existing_stats and 'bookstack_import' in existing_stats:
                                self.logger.info("Skipping both wiki imports (resumed)")
                                phase_stats['wikijs_import'] = existing_stats['wikijs_import']
                                phase_stats['bookstack_import'] = existing_stats['bookstack_import']
                            else:
                                phase_stats['wikijs_import'] = self._execute_wikijs_import(tree)
                                phase_stats['bookstack_import'] = self._execute_bookstack_import(tree)
                
                # Handle import_only workflow
                elif self.workflow == 'import_only':
                    if self.export_target == 'wikijs':
                        phase_stats['wikijs_import'] = self._execute_wikijs_import(tree)
                    elif self.export_target == 'bookstack':
                        phase_stats['bookstack_import'] = self._execute_bookstack_import(tree)
                    elif self.export_target == 'both_wikis':
                        phase_stats['wikijs_import'] = self._execute_wikijs_import(tree)
                        phase_stats['bookstack_import'] = self._execute_bookstack_import(tree)
                    else:
                        self.logger.warning(f"Import-only workflow with target '{self.export_target}' has no effect")
                
                # Handle export_only workflow (or default)
                else:
                    if self.export_target == 'markdown_files':
                        if existing_stats and 'markdown_export' in existing_stats:
                            self.logger.info("Skipping markdown export (resumed)")
                            phase_stats['markdown_export'] = existing_stats['markdown_export']
                        else:
                            phase_stats['markdown_export'] = self._execute_markdown_export(tree)
                    elif self.workflow == 'export_only':
                        self.logger.warning(f"Export-only workflow with wiki target '{self.export_target}' performs no action")
                
                # Calculate duration
                migration_duration = time.time() - start_time
                
                # Generate final report
                self.logger.info("Generating migration report")
                report = self._generate_report(tree, phase_stats, migration_duration)
                
                self.logger.info(f"Migration orchestration complete in {migration_duration:.2f}s")
                return report
            
            except Exception as e:
                # Phase failed, execute rollback if needed
                self.logger.error(f"Phase 2 failed: {str(e)}", exc_info=True)
                
                rollback_on_failure = self.config.get('migration', {}).get('rollback_on_failure', True)
                if rollback_on_failure:
                    self.logger.warning("Executing rollback for failed phase")
                    self._execute_rollback()
                    rollback_occurred = True
                
                # Re-raise to generate error report
                raise
            
            finally:
                # For export_then_import, preserve export files even if import fails
                if self.workflow == 'export_then_import' and rollback_occurred:
                    self.logger.info("Preserving exported files as backup (export_then_import workflow)")
                    # Don't rollback markdown export in this case
        
        except Exception as e:
            self.logger.error(f"Migration orchestration failed: {str(e)}", exc_info=True)
            
            # Generate error report
            try:
                migration_duration = time.time() - start_time
                report = self._generate_report(tree, phase_stats, migration_duration)
                report['summary']['orchestration_failed'] = True
                report['summary']['orchestration_error'] = str(e)
                return report
            except:
                # If even error report generation fails, return minimal report
                return {
                    'summary': {
                        'orchestration_failed': True,
                        'orchestration_error': str(e)
                    }
                }
    
    def _execute_content_conversion(self, tree: DocumentationTree) -> Dict[str, Any]:
        """
        Execute Phase 1: Convert HTML to Markdown for all pages.
        
        Args:
            tree: DocumentationTree containing pages to convert
            
        Returns:
            Conversion statistics dictionary
        """
        log_section("Phase 1: Content Conversion")
        
        stats = {
            'pages_processed': 0,
            'pages_success': 0,
            'pages_failed': 0,
            'pages_partial': 0,
            'errors': []
        }
        
        # Get all pages
        all_pages = self._get_all_pages_from_tree(tree)
        
        if not all_pages:
            self.logger.warning("No pages to convert")
            return stats
        
        self.logger.info(f"Converting {len(all_pages)} pages to Markdown")
        
        # Process pages with progress tracker
        with ProgressTracker(total_items=len(all_pages), item_type='pages') as tracker:
            for page in all_pages:
                success = True  # Assume success unless we hit an error
                try:
                    # Convert the page
                    convert_page(page, self.config, self.logger)
                    
                    # Check conversion status
                    conversion_status = page.conversion_metadata.get('conversion_status', 'failed')
                    
                    if conversion_status == 'success':
                        stats['pages_success'] += 1
                        stats['pages_processed'] += 1
                    elif conversion_status == 'failed':
                        stats['pages_failed'] += 1
                        stats['pages_processed'] += 1
                        success = False
                        stats['errors'].append({
                            'phase': 'content_conversion',
                            'page_id': page.id,
                            'page_title': page.title,
                            'error': page.conversion_metadata.get('errors', ['Unknown error'])
                        })
                    elif conversion_status == 'partial':
                        stats['pages_partial'] += 1
                        stats['pages_processed'] += 1
                    else:
                        # Handle unexpected status
                        stats['pages_failed'] += 1
                        stats['pages_processed'] += 1
                        success = False
                        
                    tracker.increment(success=success)
                    
                except Exception as e:
                    self.logger.error(f"Failed to convert page '{page.title}' (ID: {page.id}): {str(e)}")
                    stats['pages_failed'] += 1
                    stats['pages_processed'] += 1
                    tracker.increment(success=False)
                    stats['errors'].append({
                        'phase': 'content_conversion',
                        'page_id': page.id,
                        'page_title': page.title,
                        'error': str(e)
                    })
        
        self.logger.info(
            f"Phase 1 complete: {stats['pages_success']} success, "
            f"{stats['pages_failed']} failed, "
            f"{stats['pages_partial']} partial"
        )
        
        # Save checkpoint if path configured
        checkpoint_path = self.config.get('migration', {}).get('checkpoint_path')
        if checkpoint_path:
            self._save_state(tree, {'content_conversion': stats}, checkpoint_path)
        
        return stats
    
    def _execute_markdown_export(self, tree: DocumentationTree) -> Dict[str, Any]:
        """
        Execute Phase 2a: Export to local markdown files.
        
        Args:
            tree: DocumentationTree with converted pages
            
        Returns:
            Export statistics dictionary
        """
        log_section("Phase 2a: Markdown Export")
        
        try:
            # Create exporter
            self.logger.info("Creating Markdown exporter")
            self.exporter = MarkdownExporter(self.config, self.logger, output_dir=self.export_dir)
            
            # Export tree
            self.logger.info("Exporting documentation tree to markdown files")
            stats = self.exporter.export_tree(tree)

            pages_exported = stats.get('total_pages_exported', 0)
            attachments_saved = stats.get('total_attachments_saved', 0)

            self.logger.info(
                f"Phase 2a complete: {pages_exported} pages exported, "
                f"{attachments_saved} attachments saved"
            )
            
            return stats

        except Exception as e:
            self.logger.error(f"Markdown export failed: {str(e)}", exc_info=True)
            return {
                'failed': True,
                'error': str(e),
                'total_pages_exported': 0,
                'total_attachments_saved': 0
            }

    def _execute_markdown_import(self) -> Dict[str, Any]:
        """
        Execute markdown import: Read local markdown files and reconstruct DocumentationTree.

        Returns:
            Import statistics dictionary with 'tree' key containing loaded DocumentationTree
        """
        log_section("Phase: Markdown Import")

        try:
            # Get export directory from config
            export_config = self.config.get('export', {})
            output_dir = export_config.get('output_directory', './confluence-export')
            # Override with CLI argument if provided
            if self.export_dir:
                output_dir = self.export_dir
            export_dir = Path(output_dir)

            if not export_dir.exists():
                raise ValueError(f"Export directory does not exist: {export_dir}")

            if not export_dir.is_dir():
                raise ValueError(f"Export path is not a directory: {export_dir}")

            # Create markdown reader
            self.logger.info(f"Creating MarkdownReader for {export_dir}")
            self.markdown_reader = MarkdownReader(self.config, self.logger)

            # Read and reconstruct tree
            self.logger.info("Reading markdown files and reconstructing DocumentationTree")
            tree = self.markdown_reader.read_export_directory(export_dir)

            # Get reader stats
            reader_stats = self.markdown_reader.get_stats()

            # Build result
            stats = {
                'tree': tree,
                'export_directory': str(export_dir),
                'files_scanned': reader_stats.get('files_scanned', 0),
                'files_parsed': reader_stats.get('files_parsed', 0),
                'files_skipped': reader_stats.get('files_skipped', 0),
                'files_failed': reader_stats.get('files_failed', 0),
                'pages_loaded': reader_stats.get('pages_loaded', 0),
                'attachments_loaded': reader_stats.get('attachments_loaded', 0),
                'spaces_created': reader_stats.get('spaces_created', 0),
                'orphan_pages': reader_stats.get('orphan_pages', 0),
                'errors': reader_stats.get('errors', [])
            }

            self.logger.info(
                f"Markdown import complete: {stats['pages_loaded']} pages loaded from "
                f"{stats['files_parsed']} files across {stats['spaces_created']} spaces"
            )

            return stats

        except Exception as e:
            self.logger.error(f"Markdown import failed: {str(e)}", exc_info=True)
            return {
                'failed': True,
                'error': str(e),
                'pages_loaded': 0,
                'files_parsed': 0
            }

    def _execute_wikijs_import(self, tree: DocumentationTree) -> Dict[str, Any]:
        """
        Execute Phase 2b: Import to Wiki.js.
        
        Args:
            tree: DocumentationTree with converted pages
            
        Returns:
            Import statistics dictionary
        """
        log_section("Phase 2b: Wiki.js Import")
        
        try:
            # Get dry-run setting
            dry_run = self.config.get('migration', {}).get('dry_run', False)
            
            # Create importer
            self.logger.info("Creating Wiki.js importer")
            self.wikijs_importer = WikiJsImporter(self.config, tree, self.logger)
            
            # Get selected page IDs (from TUI if available)
            selected_page_ids = None
            if hasattr(tree, 'metadata') and tree.metadata.get('selected_page_ids'):
                selected_page_ids = set(tree.metadata['selected_page_ids'])
                self.logger.info(f"Using {len(selected_page_ids)} pages from TUI selection")
            
            # Import pages
            self.logger.info("Importing pages to Wiki.js")
            stats = self.wikijs_importer.import_pages(selected_page_ids, dry_run)
            
            created = stats.get('created', 0)
            updated = stats.get('updated', 0)
            failed = stats.get('failed', 0)
            
            self.logger.info(
                f"Phase 2b complete: {created} created, {updated} updated, {failed} failed"
            )
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Wiki.js import failed: {str(e)}", exc_info=True)
            return {
                'failed': True,
                'error': str(e),
                'created': 0,
                'updated': 0
            }
    
    def _execute_integrity_verification(self, tree: DocumentationTree) -> Dict[str, Any]:
        """
        Execute Phase 1.5: Integrity Verification.
        
        Args:
            tree: DocumentationTree with fetched content
            
        Returns:
            Verification statistics dictionary
        """
        log_section("Phase 1.5: Integrity Verification")
        
        try:
            # Create verifier
            self.logger.info("Creating IntegrityVerifier")
            self.integrity_verifier = IntegrityVerifier(self.config, tree, self.logger)
            
            # Run verification
            self.logger.info("Verifying content integrity")
            verification_report = self.integrity_verifier.verify_tree(tree)
            
            # Store report in tree
            tree.integrity_report = verification_report
            tree.metadata['integrity_verified'] = True
            tree.metadata['integrity_timestamp'] = time.time()
            tree.metadata['integrity_score'] = verification_report.get('summary', {}).get('integrity_score', 0.0)
            
            # Log summary
            summary = verification_report.get('summary', {})
            integrity_score = summary.get('integrity_score', 0.0)
            total_issues = summary.get('total_issues', 0)
            
            self.logger.info(
                f"Phase 1.5 complete: Integrity score {integrity_score:.1%}, "
                f"{total_issues} issues found"
            )
            
            # Check if we should halt on critical failures
            halt_on_failure = self.config.get('advanced', {}).get('integrity_verification', {}).get('halt_on_failure', False)
            if halt_on_failure and integrity_score < 0.5:  # Less than 50% integrity
                raise Exception(f"Integrity verification failed: score {integrity_score:.1%} below threshold")
            
            return verification_report
            
        except Exception as e:
            self.logger.error(f"Integrity verification failed: {str(e)}", exc_info=True)
            return {
                'failed': True,
                'error': str(e),
                'summary': {
                    'integrity_score': 0.0,
                    'total_issues': -1
                }
            }

    def _execute_bookstack_import(self, tree: DocumentationTree) -> Dict[str, Any]:
        """
        Execute Phase 2c: Import to BookStack.
        
        Args:
            tree: DocumentationTree with converted pages
            
        Returns:
            Import statistics dictionary
        """
        log_section("Phase 2c: BookStack Import")
        
        try:
            # Get dry-run setting
            dry_run = self.config.get('migration', {}).get('dry_run', False)
            
            # Create importer
            self.logger.info("Creating BookStack importer")
            self.bookstack_importer = BookStackImporter(self.config, tree, self.logger)
            
            # Get selected page IDs (from TUI if available)
            selected_page_ids = None
            if hasattr(tree, 'metadata') and tree.metadata.get('selected_page_ids'):
                selected_page_ids = set(tree.metadata['selected_page_ids'])
                self.logger.info(f"Using {len(selected_page_ids)} pages from TUI selection")
            
            # Import pages
            self.logger.info("Importing pages to BookStack")
            stats = self.bookstack_importer.import_pages(selected_page_ids, dry_run)
            
            shelves = stats.get('shelves', 0)
            books = stats.get('books', 0)
            chapters = stats.get('chapters', 0)
            pages = stats.get('pages', 0)
            
            self.logger.info(
                f"Phase 2c complete: {shelves} shelves, {books} books, "
                f"{chapters} chapters, {pages} pages created"
            )
            
            return stats
            
        except Exception as e:
            self.logger.error(f"BookStack import failed: {str(e)}", exc_info=True)
            return {
                'failed': True,
                'error': str(e),
                'shelves': 0,
                'books': 0,
                'chapters': 0,
                'pages': 0
            }
    
    def _execute_rollback(self):
        """
        Execute rollback for all components that support it.
        """
        if self.exporter:
            try:
                rollback_stats = self.exporter.rollback()
                if rollback_stats.get('rollback_executed'):
                    self.logger.info(f"Rolled back markdown export: {rollback_stats['files_deleted']} files deleted")
            except Exception as e:
                self.logger.warning(f"Failed to rollback markdown export: {str(e)}")
        
        if self.wikijs_importer:
            try:
                rollback_stats = self.wikijs_importer.rollback()
                if rollback_stats.get('rollback_executed'):
                    self.logger.info(f"Rolled back Wiki.js import: {rollback_stats['pages_deleted']} pages deleted")
            except Exception as e:
                self.logger.warning(f"Failed to rollback Wiki.js import: {str(e)}")
        
        if self.bookstack_importer:
            try:
                rollback_stats = self.bookstack_importer.rollback()
                if rollback_stats.get('rollback_executed'):
                    self.logger.info(f"Rolled back BookStack import: {rollback_stats['pages_deleted']} pages, "
                                   f"{rollback_stats['chapters_deleted']} chapters, "
                                   f"{rollback_stats['books_deleted']} books, "
                                   f"{rollback_stats['shelves_deleted']} shelves deleted")
            except Exception as e:
                self.logger.warning(f"Failed to rollback BookStack import: {str(e)}")
    
    def _generate_report(self, tree: DocumentationTree, phase_stats: Dict[str, Any], migration_duration: float) -> Dict[str, Any]:
        """
        Generate comprehensive migration report.
        
        Args:
            tree: DocumentationTree that was migrated
            phase_stats: Statistics from all phases
            migration_duration: Total migration duration in seconds
            
        Returns:
            Migration report dictionary
        """
        try:
            # Create report generator
            report_generator = MigrationReport(self.logger)
            
            # Get integrity report if available
            integrity_report = tree.integrity_report if hasattr(tree, 'integrity_report') else None
            
            # Generate report with integrity data
            report = report_generator.generate_report(
                tree, phase_stats, migration_duration, self.export_target, integrity_report=integrity_report
            )
            
            self.logger.info("Migration report generated successfully")
            
            return report
            
        except Exception as e:
            self.logger.error(f"Failed to generate migration report: {str(e)}", exc_info=True)
            # Return minimal report
            return {
                'summary': {
                    'report_generation_failed': True,
                    'report_generation_error': str(e)
                }
            }
    
    def _get_all_pages_from_tree(self, tree: DocumentationTree) -> list:
        """
        Get all pages from a DocumentationTree recursively.
        
        Args:
            tree: DocumentationTree
            
        Returns:
            List of all pages
        """
        all_pages = []
        
        def collect_pages(pages):
            for page in pages:
                all_pages.append(page)
                if page.children:
                    collect_pages(page.children)
        
        for space in tree.spaces.values():
            collect_pages(space.pages)
        
        return all_pages
    
    def _save_state(self, tree: DocumentationTree, phase_stats: Dict[str, Any], checkpoint_path: str) -> None:
        """
        Save migration state for resumability (optional feature).
        
        Args:
            tree: DocumentationTree
            phase_stats: Statistics from completed phases
            checkpoint_path: Path to save checkpoint
        """
        try:
            # Serialize tree to dict
            tree_data = tree.to_dict()
            
            checkpoint = {
                'tree_data': tree_data,
                'phase_stats': phase_stats,
                'timestamp': time.time(),
                'checkpoint_version': '1.0'
            }
            
            with open(checkpoint_path, 'w') as f:
                json.dump(checkpoint, f, indent=2)
            
            self.logger.info(f"Migration state saved to {checkpoint_path}")
            
        except Exception as e:
            self.logger.warning(f"Failed to save migration state: {str(e)}")
    
    def _load_state(self, checkpoint_path: str):
        """
        Load migration state from checkpoint (optional feature).
        
        Args:
            checkpoint_path: Path to checkpoint file
            
        Returns:
            Tuple of (DocumentationTree, phase_stats)
        """
        try:
            with open(checkpoint_path, 'r') as f:
                checkpoint = json.load(f)
            
            # Check checkpoint version
            version = checkpoint.get('checkpoint_version', '1.0')
            if version != '1.0':
                raise ValueError(f'Incompatible checkpoint version: {version}')
            
            # Deserialize tree
            tree_data = checkpoint.get('tree_data', {})
            if tree_data:
                try:
                    tree = DocumentationTree.from_dict(tree_data)
                    self.logger.info(f"DocumentationTree reconstructed from checkpoint")
                    self.logger.info(f"Tree contains {len(tree.spaces)} spaces")
                except Exception as e:
                    self.logger.error(f"Failed to reconstruct tree from checkpoint: {str(e)}")
                    tree = None
            else:
                tree = None
            
            phase_stats = checkpoint.get('phase_stats', {})
            
            self.logger.info(f"Migration state loaded from {checkpoint_path}")
            
            return tree, phase_stats
            
        except Exception as e:
            self.logger.error(f"Failed to load migration state: {str(e)}")
            return None, {}