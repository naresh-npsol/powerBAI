"""
Django admin configuration for analytics models.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import BillingDataUpload, MappedField, BillingRecord, AnalyticsQuery

from unfold.admin import ModelAdmin


@admin.register(BillingDataUpload)
class BillingDataUploadAdmin(ModelAdmin):
    """Admin interface for BillingDataUpload model."""
    
    list_display = [
        "original_filename", "user", "status", "total_rows", "processed_rows", 
        "upload_date", "processing_completed_at", "view_file_link"
    ]
    list_filter = ["status", "upload_date", "processing_completed_at"]
    search_fields = ["original_filename", "user__username", "user__email"]
    readonly_fields = [
        "id", "upload_date", "processing_started_at", "processing_completed_at", 
        "file_size", "processing_duration", "progress_percentage", "view_mappings_link", "view_records_link"
    ]
    raw_id_fields = ["user"]
    
    fieldsets = (
        ("File Information", {
            "fields": ("file", "original_filename", "file_size")
        }),
        ("Processing Status", {
            "fields": ("status", "total_rows", "processed_rows", "error_message")
        }),
        ("Timestamps", {
            "fields": ("upload_date", "processing_started_at", "processing_completed_at", "processing_duration")
        }),
        ("Progress", {
            "fields": ("progress_percentage",),
            "classes": ("collapse",)
        }),
        ("Related Data", {
            "fields": ("view_mappings_link", "view_records_link"),
            "classes": ("collapse",)
        }),
    )
    
    def view_file_link(self, obj: BillingDataUpload) -> str:
        """Return link to view file details."""
        if obj.file:
            return format_html(
                '<a href="{}" target="_blank">View File</a>',
                obj.file.url
            )
        return "No file"
    view_file_link.short_description = "File"
    
    def view_mappings_link(self, obj: BillingDataUpload) -> str:
        """Return link to view related mappings."""
        count = obj.field_mappings.count()
        if count > 0:
            url = f"/admin/analytics/mappedfield/?upload__id__exact={obj.id}"
            return format_html(
                '<a href="{}">{} Mappings</a>',
                url, count
            )
        return "No mappings"
    view_mappings_link.short_description = "Column Mappings"
    
    def view_records_link(self, obj: BillingDataUpload) -> str:
        """Return link to view related billing records."""
        count = obj.billing_records.count()
        if count > 0:
            url = f"/admin/analytics/billingrecord/?upload__id__exact={obj.id}"
            return format_html(
                '<a href="{}">{} Records</a>',
                url, count
            )
        return "No records"
    view_records_link.short_description = "Billing Records"


@admin.register(MappedField)
class MappedFieldAdmin(ModelAdmin):
    """Admin interface for MappedField model."""
    
    list_display = ["upload", "original_column", "mapped_field", "is_required", "created_at"]
    list_filter = ["mapped_field", "is_required", "created_at"]
    search_fields = ["upload__original_filename", "original_column", "custom_field_name"]
    raw_id_fields = ["upload"]
    
    fieldsets = (
        ("Mapping Information", {
            "fields": ("upload", "original_column", "mapped_field", "custom_field_name", "is_required", "data_type")
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    readonly_fields = ["created_at", "updated_at"]


@admin.register(BillingRecord)
class BillingRecordAdmin(ModelAdmin):
    """Admin interface for BillingRecord model."""
    
    list_display = [
        "invoice_number", "customer_name", "amount", "payment_status", 
        "date", "upload", "created_at"
    ]
    list_filter = [
        "payment_status", "date", "created_at", "upload"
    ]
    search_fields = [
        "invoice_number", "customer_name", 
        "description", "upload__original_filename"
    ]
    raw_id_fields = ["upload"]
    date_hierarchy = "date"
    
    fieldsets = (
        ("Invoice Information", {
            "fields": ("invoice_number", "amount", "description")
        }),
        ("Customer Information", {
            "fields": ("customer_name",)
        }),
        ("Product Information", {
            "fields": ("product_name", "quantity", "unit_price", "tax_amount", "discount")
        }),
        ("Payment Information", {
            "fields": ("payment_status", "payment_method", "date")
        }),
        ("Custom Fields", {
            "fields": ("custom_fields",),
            "classes": ("collapse",)
        }),
        ("Metadata", {
            "fields": ("upload", "row_number", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    readonly_fields = ["created_at", "updated_at", "row_number"]
    
    actions = ["mark_as_paid", "mark_as_overdue", "mark_as_pending"]
    
    def mark_as_paid(self, request, queryset):
        """Mark selected records as paid."""
        updated = queryset.update(payment_status="PAID")
        self.message_user(
            request, 
            f"Successfully marked {updated} records as paid."
        )
    mark_as_paid.short_description = "Mark selected records as paid"
    
    def mark_as_overdue(self, request, queryset):
        """Mark selected records as overdue."""
        updated = queryset.update(payment_status="OVERDUE")
        self.message_user(
            request, 
            f"Successfully marked {updated} records as overdue."
        )
    mark_as_overdue.short_description = "Mark selected records as overdue"
    
    def mark_as_pending(self, request, queryset):
        """Mark selected records as pending."""
        updated = queryset.update(payment_status="PENDING")
        self.message_user(
            request, 
            f"Successfully marked {updated} records as pending."
        )
    mark_as_pending.short_description = "Mark selected records as pending"


@admin.register(AnalyticsQuery)
class AnalyticsQueryAdmin(ModelAdmin):
    """Admin interface for AnalyticsQuery model."""
    
    list_display = ["user", "query_preview", "query_type", "created_at", "response_preview"]
    list_filter = ["query_type", "created_at", "user"]
    search_fields = ["query_text", "response_text", "user__username", "user__email"]
    raw_id_fields = ["user", "upload"]
    date_hierarchy = "created_at"
    
    fieldsets = (
        ("Query Information", {
            "fields": ("user", "upload", "query_type", "query_text", "response_text")
        }),
        ("Technical Details", {
            "fields": ("data_context", "processing_time"),
            "classes": ("collapse",)
        }),
        ("Metadata", {
            "fields": ("created_at",),
            "classes": ("collapse",)
        }),
    )
    
    readonly_fields = ["created_at", "processing_time"]
    
    def query_preview(self, obj: AnalyticsQuery) -> str:
        """Return truncated query text."""
        if len(obj.query_text) > 50:
            return obj.query_text[:50] + "..."
        return obj.query_text
    query_preview.short_description = "Query"
    
    def response_preview(self, obj: AnalyticsQuery) -> str:
        """Return truncated response text."""
        if obj.response_text:
            if len(obj.response_text) > 50:
                return obj.response_text[:50] + "..."
            return obj.response_text
        return "No response"
    response_preview.short_description = "Response"


# Custom admin site configuration
admin.site.site_header = "PowerBAI Analytics Administration"
admin.site.site_title = "PowerBAI Analytics Admin"
admin.site.index_title = "Welcome to PowerBAI Analytics Administration" 