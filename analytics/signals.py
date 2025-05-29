from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import BillingDataUpload, MappedField, BillingRecord


@receiver(post_save, sender=BillingDataUpload)
def handle_upload_status_change(sender, instance: BillingDataUpload, created: bool, **kwargs):
    """Handle upload status changes."""
    if created:
        # Set initial processing timestamps
        instance.processing_started_at = timezone.now()
        instance.save(update_fields=["processing_started_at"])
    
    # Update processing completion timestamp when status changes to processed or failed
    if instance.status in [BillingDataUpload.UploadStatus.PROCESSED, BillingDataUpload.UploadStatus.FAILED]:
        if not instance.processing_completed_at:
            instance.processing_completed_at = timezone.now()
            instance.save(update_fields=["processing_completed_at"])


@receiver(post_save, sender=MappedField)
def handle_mapping_change(sender, instance: MappedField, created: bool, **kwargs):
    """Handle field mapping changes."""
    # Update upload status when mappings are created/modified
    if instance.upload.status == BillingDataUpload.UploadStatus.PENDING:
        # Check if we have all required mappings
        required_fields = ["date", "customer_name", "invoice_number", "amount"]
        mapped_fields = list(
            instance.upload.field_mappings.values_list("mapped_field", flat=True)
        )
        
        # If all required fields are mapped, we can start processing
        if all(field in mapped_fields for field in required_fields):
            instance.upload.status = BillingDataUpload.UploadStatus.PROCESSING
            instance.upload.save(update_fields=["status"])


@receiver(post_save, sender=BillingRecord)
def update_upload_progress(sender, instance: BillingRecord, created: bool, **kwargs):
    """Update upload processing progress when records are created."""
    if created:
        upload = instance.upload
        upload.processed_rows = upload.billing_records.count()
        upload.save(update_fields=["processed_rows"])


@receiver(post_delete, sender=BillingRecord)
def update_upload_progress_on_delete(sender, instance: BillingRecord, **kwargs):
    """Update upload processing progress when records are deleted."""
    upload = instance.upload
    upload.processed_rows = upload.billing_records.count()
    upload.save(update_fields=["processed_rows"]) 