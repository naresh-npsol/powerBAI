"""
Analytics app configuration.
"""

from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """Configuration for the analytics application."""
    
    default_auto_field = "django.db.models.BigAutoField"
    name = "analytics"
    verbose_name = "Billing Analytics"
    
    def ready(self):
        """Import signal handlers when the app is ready."""
        try:
            import analytics.signals  # noqa F401
        except ImportError:
            pass 