"""
URL configuration for the analytics application.

Defines all URL patterns for the analytics app including:
- Dashboard and analytics views
- File upload and processing views
- API endpoints for AJAX requests
- ChatGPT integration views
"""

from django.urls import path, include
from django.views.generic import TemplateView

from . import views

app_name = "analytics"

urlpatterns = [
    # Dashboard and main views
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("analytics/", views.AnalyticsView.as_view(), name="analytics"),
    
    # File upload and management
    path("upload/", views.FileUploadView.as_view(), name="file_upload"),
    path("uploads/", views.UploadListView.as_view(), name="upload_list"),
    path("upload/<uuid:upload_id>/", views.UploadDetailView.as_view(), name="upload_detail"),
    path("upload/<uuid:upload_id>/delete/", views.UploadDeleteView.as_view(), name="upload_delete"),
    path("upload/<uuid:upload_id>/mapping/", views.ColumnMappingView.as_view(), name="column_mapping"),
    path("upload/<uuid:upload_id>/process/", views.ProcessUploadView.as_view(), name="process_upload"),
    path("uploads/<uuid:pk>/preview/", views.DataPreviewView.as_view(), name="data_preview"),
    
    # Billing records
    path("records/", views.BillingRecordListView.as_view(), name="record_list"),
    path("record/<int:record_id>/", views.RecordDetailView.as_view(), name="record_detail"),
    path("record/<int:record_id>/edit/", views.RecordEditView.as_view(), name="record_edit"),
    path("record/<int:record_id>/delete/", views.RecordDeleteView.as_view(), name="delete_record"),
    path("records/bulk-delete/", views.BulkDeleteRecordsView.as_view(), name="bulk_delete_records"),
    
    # ChatGPT Analytics
    path("chat/", views.ChatAnalyticsView.as_view(), name="chat_analytics"),
    path("chat/query/", views.ProcessChatQueryView.as_view(), name="process_chat_query"),
    path("chat/history/", views.ChatHistoryView.as_view(), name="chat_history"),
    
    # Export functionality
    path("export/data/", views.ExportDataView.as_view(), name="export_data"),
    path("export/records/", views.ExportRecordsView.as_view(), name="export_records"),
    
    # API endpoints for AJAX requests
    path("ajax/chat/", views.ajax_chat_query, name="ajax_chat"),
    path("ajax/upload-status/<uuid:upload_id>/", views.ajax_upload_status, name="ajax_upload_status"),
    path("ajax/analytics-data/", views.ajax_analytics_data, name="ajax_analytics_data"),
    path("api/debug-columns/<uuid:upload_id>/", views.DebugFileColumnsAPIView.as_view(), name="debug_file_columns"),
    path("api/validate-data/<uuid:pk>/", views.ValidateDataAPIView.as_view(), name="validate_data_api"),
    path("api/sample-data/<uuid:pk>/", views.SampleDataAPIView.as_view(), name="sample_data_api"),
    path("api/charts/data/", views.ChartsDataView.as_view(), name="charts_data_api"),
    path("api/summary-stats/", views.SummaryStatsView.as_view(), name="summary_stats_api"),
    path("api/revenue-trend/", views.RevenueTrendAPIView.as_view(), name="revenue_trend_api"),
    path("api/customer-analysis/", views.CustomerAnalysisAPIView.as_view(), name="customer_analysis_api"),
    path("api/payment-status/", views.PaymentStatusAPIView.as_view(), name="payment_status_api"),
    path("api/customer-search/", views.CustomerSearchAPIView.as_view(), name="customer_search_api"),
    path("api/invoice-search/", views.InvoiceSearchAPIView.as_view(), name="invoice_search_api"),
    path("api/notifications/", views.NotificationsAPIView.as_view(), name="notifications_api"),
    path("api/test-date-parsing/", views.TestDateParsingView.as_view(), name="test_date_parsing"),
    
    # Settings and configuration
    path("settings/", views.SettingsView.as_view(), name="settings"),
    path("field-mapping-templates/", views.FieldMappingTemplatesView.as_view(), name="field_mapping_templates"),
    
    # Legacy URL names for backward compatibility
    path("upload-file/", views.FileUploadView.as_view(), name="upload"),  # For template compatibility
    
    # Help and documentation
    path("help/", TemplateView.as_view(template_name="analytics/help.html"), name="help"),
    path("help/file-formats/", TemplateView.as_view(template_name="analytics/help/file_formats.html"), name="help_file_formats"),
    path("help/column-mapping/", TemplateView.as_view(template_name="analytics/help/column_mapping.html"), name="help_column_mapping"),
    path("help/analytics/", TemplateView.as_view(template_name="analytics/help/analytics.html"), name="help_analytics"),
]
