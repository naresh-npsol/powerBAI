"""
Custom template filters for the analytics application.

Provides additional filters for template rendering including:
- Dictionary lookup functionality
- Data formatting helpers
- Analytics-specific formatters
"""

from django import template
from django.utils.safestring import mark_safe
import json
from typing import Any, Dict, Union
from django.db.models import QuerySet

register = template.Library()


@register.filter
def lookup(dictionary: Dict[str, Any], key: str) -> Any:
    """
    Lookup a value in a dictionary by key.
    
    Usage: {{ mappings|lookup:field_key }}
    
    Args:
        dictionary: The dictionary to lookup in
        key: The key to lookup
        
    Returns:
        The value if found, empty string otherwise
    """
    if not isinstance(dictionary, dict):
        return ""
    return dictionary.get(key, "")


@register.filter
def keyvalue(dictionary: Dict[str, Any], key: str) -> Any:
    """
    Alternative lookup filter for dictionaries.
    
    Usage: {{ mappings|keyvalue:field_key }}
    
    Args:
        dictionary: The dictionary to lookup in
        key: The key to lookup
        
    Returns:
        The value if found, None otherwise
    """
    if not isinstance(dictionary, dict):
        return None
    return dictionary.get(key)


@register.filter
def to_json(value: Any) -> str:
    """
    Convert a Python object to JSON string.
    
    Usage: {{ data|to_json }}
    
    Args:
        value: The value to convert to JSON
        
    Returns:
        JSON string representation
    """
    try:
        return mark_safe(json.dumps(value))
    except (TypeError, ValueError):
        return "[]"


@register.filter
def currency(value: Union[str, int, float]) -> str:
    """
    Format a number as currency.
    
    Usage: {{ amount|currency }}
    
    Args:
        value: The numeric value to format
        
    Returns:
        Formatted currency string
    """
    try:
        num_value = float(value)
        return f"${num_value:,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


@register.filter
def percentage(value: Union[str, int, float]) -> str:
    """
    Format a number as percentage.
    
    Usage: {{ growth_rate|percentage }}
    
    Args:
        value: The numeric value to format as percentage
        
    Returns:
        Formatted percentage string
    """
    try:
        num_value = float(value)
        return f"{num_value:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


@register.filter
def file_size(value: Union[str, int]) -> str:
    """
    Format file size in human readable format.
    
    Usage: {{ file_size|file_size }}
    
    Args:
        value: File size in bytes
        
    Returns:
        Human readable file size string
    """
    try:
        size = int(value)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"
    except (TypeError, ValueError):
        return "0 B"


@register.filter
def status_class(status: str) -> str:
    """
    Get CSS class for status badges.
    
    Usage: {{ upload.status|status_class }}
    
    Args:
        status: Status string
        
    Returns:
        CSS class string
    """
    status_classes = {
        "PENDING": "bg-gray-100 text-gray-800",
        "PROCESSING": "bg-yellow-100 text-yellow-800",
        "MAPPED": "bg-blue-100 text-blue-800",
        "COMPLETED": "bg-green-100 text-green-800",
        "ERROR": "bg-red-100 text-red-800",
        "PAID": "bg-green-100 text-green-800",
        "PENDING_PAYMENT": "bg-yellow-100 text-yellow-800",
        "OVERDUE": "bg-red-100 text-red-800",
        "CANCELLED": "bg-gray-100 text-gray-800",
    }
    return status_classes.get(str(status).upper(), "bg-gray-100 text-gray-800")


@register.filter
def truncate_filename(filename: str, max_length: int = 25) -> str:
    """
    Truncate filename while preserving extension.
    
    Usage: {{ upload.file.name|truncate_filename:20 }}
    
    Args:
        filename: The filename to truncate
        max_length: Maximum length before truncation
        
    Returns:
        Truncated filename with extension preserved
    """
    if not filename or len(filename) <= max_length:
        return filename
    
    # Split filename and extension
    if '.' in filename:
        name, ext = filename.rsplit('.', 1)
        # Calculate available space for name
        available = max_length - len(ext) - 4  # 4 for "..." and "."
        if available > 0:
            return f"{name[:available]}...{ext}"
    
    # Fallback to simple truncation
    return f"{filename[:max_length-3]}..."


@register.filter
def get_item(dictionary: Dict[str, Any], key: str) -> Any:
    """
    Get item from dictionary - alias for lookup filter.
    
    Usage: {{ dict|get_item:key }}
    
    Args:
        dictionary: The dictionary to access
        key: The key to get
        
    Returns:
        The value if found, empty string otherwise
    """
    return lookup(dictionary, key)


@register.filter
def multiply(value: Union[str, int, float], multiplier: Union[str, int, float]) -> float:
    """
    Multiply two values.
    
    Usage: {{ value|multiply:2 }}
    
    Args:
        value: The first value
        multiplier: The multiplier
        
    Returns:
        The product of the values
    """
    try:
        return float(value) * float(multiplier)
    except (TypeError, ValueError):
        return 0


@register.filter
def divide(value: Union[str, int, float], divisor: Union[str, int, float]) -> float:
    """
    Divide two values.
    
    Usage: {{ value|divide:2 }}
    
    Args:
        value: The dividend
        divisor: The divisor
        
    Returns:
        The quotient of the values
    """
    try:
        dividend = float(value)
        div = float(divisor)
        if div == 0:
            return 0
        return dividend / div
    except (TypeError, ValueError):
        return 0


@register.filter
def progress_percentage(processed: Union[str, int], total: Union[str, int]) -> int:
    """
    Calculate progress percentage.
    
    Usage: {{ upload.processed_rows|progress_percentage:upload.total_rows }}
    
    Args:
        processed: Number of processed items
        total: Total number of items
        
    Returns:
        Progress percentage as integer
    """
    try:
        proc = int(processed or 0)
        tot = int(total or 0)
        if tot == 0:
            return 0
        return min(100, int((proc / tot) * 100))
    except (TypeError, ValueError):
        return 0


@register.filter
def default_if_none(value: Any, default: Any = "") -> Any:
    """
    Return default value if the input is None.
    
    Usage: {{ value|default_if_none:"No data" }}
    
    Args:
        value: The value to check
        default: Default value to return if value is None
        
    Returns:
        Original value or default if None
    """
    return value if value is not None else default 