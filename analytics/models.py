import os
import uuid
from decimal import Decimal
from typing import Dict, Any, Optional

from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from django.urls import reverse

User = get_user_model()


def upload_to_user_directory(instance: "BillingDataUpload", filename: str) -> str:
    """Generate upload path for user files."""
    # File will be uploaded to MEDIA_ROOT/billing_uploads/user_<id>/<filename>
    return f"billing_uploads/user_{instance.user.id}/{filename}"


class BillingDataUpload(models.Model):
    """Model to track uploaded billing data files."""
    
    class UploadStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        MAPPED = "mapped", "Mapped"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        ERROR = "error", "Error"
        CANCELLED = "cancelled", "Cancelled"
    
    # Core fields
    id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False,
        help_text="Unique identifier for the upload"
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        related_name="billing_uploads",
        help_text="User who uploaded the file"
    )
    upload_date = models.DateTimeField(
        default=timezone.now,
        help_text="Date and time when the file was uploaded"
    )
    file = models.FileField(
        upload_to=upload_to_user_directory,
        validators=[FileExtensionValidator(allowed_extensions=["csv", "xlsx", "xls"])],
        help_text="The uploaded CSV or Excel file"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=UploadStatus.choices,
        default=UploadStatus.PENDING,
        help_text="Current processing status of the upload"
    )
    
    # File metadata
    original_filename = models.CharField(
        max_length=255,
        help_text="Original name of the uploaded file"
    )
    file_size = models.PositiveIntegerField(
        help_text="Size of the uploaded file in bytes"
    )
    
    # Processing metadata
    total_rows = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Total number of rows in the uploaded file"
    )
    processed_rows = models.PositiveIntegerField(
        default=0,
        help_text="Number of rows successfully processed"
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if processing failed"
    )
    
    # Processing timestamps
    processing_started_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When processing started"
    )
    processing_completed_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When processing completed"
    )
    
    # Date format preference
    date_format = models.CharField(
        max_length=20,
        default="DD/MM/YYYY",
        choices=[
            ("DD/MM/YYYY", "DD/MM/YYYY (Indian Format)"),
            ("MM/DD/YYYY", "MM/DD/YYYY (US Format)"),
            ("YYYY-MM-DD", "YYYY-MM-DD (ISO Format)"),
            ("DD-MM-YYYY", "DD-MM-YYYY (European Format)"),
            ("MM-DD-YYYY", "MM-DD-YYYY (US Format with Dash)"),
            ("DD.MM.YYYY", "DD.MM.YYYY (German Format)"),
            ("auto", "Auto-detect Format"),
        ],
        help_text="Date format used in the uploaded file"
    )
    
    class Meta:
        ordering = ["-upload_date"]
        verbose_name = "Billing Data Upload"
        verbose_name_plural = "Billing Data Uploads"
        indexes = [
            models.Index(fields=["user", "-upload_date"]),
            models.Index(fields=["status"]),
        ]
    
    def __str__(self) -> str:
        return f"{self.original_filename} - {self.user.email} ({self.status})"
    
    def get_absolute_url(self) -> str:
        return reverse("analytics:upload_detail", kwargs={"pk": self.pk})
    
    @property
    def processing_duration(self) -> Optional[str]:
        """Calculate processing duration if both timestamps exist."""
        if self.processing_started_at and self.processing_completed_at:
            duration = self.processing_completed_at - self.processing_started_at
            return str(duration)
        return None
    
    @property
    def progress_percentage(self) -> float:
        """Calculate processing progress as percentage."""
        if self.total_rows and self.total_rows > 0:
            return (self.processed_rows / self.total_rows) * 100
        return 0.0


class MappedField(models.Model):
    """Model to store column mapping configuration for uploads."""
    
    # Predefined field types for billing data
    class FieldType(models.TextChoices):
        DATE = "date", "Date"
        CUSTOMER_NAME = "customer_name", "Customer Name"
        INVOICE_NUMBER = "invoice_number", "Invoice Number"
        AMOUNT = "amount", "Amount"
        DESCRIPTION = "description", "Description"
        PRODUCT_NAME = "product_name", "Product Name"
        QUANTITY = "quantity", "Quantity"
        UNIT_PRICE = "unit_price", "Unit Price"
        TAX_AMOUNT = "tax_amount", "Tax Amount"
        DISCOUNT = "discount", "Discount"
        PAYMENT_METHOD = "payment_method", "Payment Method"
        PAYMENT_STATUS = "payment_status", "Payment Status"
        CUSTOM = "custom", "Custom Field"
    
    upload = models.ForeignKey(
        BillingDataUpload,
        on_delete=models.CASCADE,
        related_name="field_mappings",
        help_text="The upload this mapping belongs to"
    )
    original_column = models.CharField(
        max_length=255,
        help_text="Original column name from the uploaded file"
    )
    mapped_field = models.CharField(
        max_length=50,
        choices=FieldType.choices,
        help_text="Field type this column is mapped to"
    )
    custom_field_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Custom field name if mapped_field is 'custom'"
    )
    is_required = models.BooleanField(
        default=False,
        help_text="Whether this field is required for processing"
    )
    data_type = models.CharField(
        max_length=20,
        choices=[
            ("string", "Text"),
            ("number", "Number"),
            ("date", "Date"),
            ("boolean", "Yes/No"),
        ],
        default="string",
        help_text="Expected data type for this field"
    )
    
    # Mapping metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ["upload", "original_column"]
        ordering = ["original_column"]
        verbose_name = "Mapped Field"
        verbose_name_plural = "Mapped Fields"
    
    def __str__(self) -> str:
        mapped_name = self.custom_field_name if self.mapped_field == self.FieldType.CUSTOM else self.get_mapped_field_display()
        return f"{self.original_column} → {mapped_name}"


class BillingRecord(models.Model):
    """Model to store processed billing records."""
    
    class PaymentStatus(models.TextChoices):
        PAID = "paid", "Paid"
        PENDING = "pending", "Pending"
        OVERDUE = "overdue", "Overdue"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"
    
    # Core relationships
    upload = models.ForeignKey(
        BillingDataUpload,
        on_delete=models.CASCADE,
        related_name="billing_records",
        help_text="The upload this record originated from"
    )
    
    # Standard billing fields
    date = models.DateField(
        help_text="Date of the billing record"
    )
    customer_name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Name of the customer"
    )
    invoice_number = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Invoice or transaction number"
    )
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Total amount for this record"
    )
    
    # Optional standard fields
    description = models.TextField(
        blank=True,
        help_text="Description of the transaction"
    )
    product_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Product or service name"
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Quantity of items"
    )
    unit_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Price per unit"
    )
    tax_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Tax amount"
    )
    discount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Discount amount"
    )
    payment_method = models.CharField(
        max_length=50,
        blank=True,
        help_text="Payment method used"
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        help_text="Payment status"
    )
    
    # Custom fields stored as JSON
    custom_fields = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional custom fields from the upload"
    )
    
    # Record metadata
    row_number = models.PositiveIntegerField(
        help_text="Original row number in the uploaded file"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Billing Record"
        verbose_name_plural = "Billing Records"
        indexes = [
            models.Index(fields=["upload", "date"]),
            models.Index(fields=["customer_name"]),
            models.Index(fields=["invoice_number"]),
            models.Index(fields=["amount"]),
            models.Index(fields=["payment_status"]),
            models.Index(fields=["date"]),
        ]
    
    def __str__(self) -> str:
        return f"{self.invoice_number} - {self.customer_name} (${self.amount})"
    
    def get_absolute_url(self) -> str:
        return reverse("analytics:record_detail", kwargs={"pk": self.pk})
    
    @property
    def net_amount(self) -> Decimal:
        """Calculate net amount after tax and discount."""
        net = self.amount
        if self.tax_amount:
            net += self.tax_amount
        if self.discount:
            net -= self.discount
        return net


class AnalyticsQuery(models.Model):
    """Model to store ChatGPT analytics queries and responses."""
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="analytics_queries",
        help_text="User who made the query"
    )
    upload = models.ForeignKey(
        BillingDataUpload,
        on_delete=models.CASCADE,
        related_name="analytics_queries",
        null=True,
        blank=True,
        help_text="Optional: specific upload context for the query"
    )
    
    # Query details
    query_text = models.TextField(
        help_text="The user's natural language query"
    )
    query_type = models.CharField(
        max_length=50,
        choices=[
            ("summary", "Summary"),
            ("trend", "Trend Analysis"),
            ("comparison", "Comparison"),
            ("prediction", "Prediction"),
            ("custom", "Custom Query"),
        ],
        default="custom",
        help_text="Type of analytics query"
    )
    
    # Response details
    response_text = models.TextField(
        help_text="ChatGPT's response to the query"
    )
    data_context = models.JSONField(
        default=dict,
        help_text="Data context sent to ChatGPT (anonymized)"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    processing_time = models.DurationField(
        null=True,
        blank=True,
        help_text="Time taken to process the query"
    )
    
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Analytics Query"
        verbose_name_plural = "Analytics Queries"
    
    def __str__(self) -> str:
        return f"{self.user.email}: {self.query_text[:50]}..." 