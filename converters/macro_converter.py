"""
Confluence macro converter module.

This module provides backward compatibility by re-exporting MacroHandler from macro_handler.py.
The actual implementation resides in macro_handler.py.
"""

from .macro_handler import MacroHandler

__all__ = ['MacroHandler']
