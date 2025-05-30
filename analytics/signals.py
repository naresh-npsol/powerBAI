from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import BillingDataUpload, MappedField, BillingRecord


@receiver(post_save, sender=BillingDataUpload)
def handle_upload_status_change(sender, instance: BillingDataUpload, created: bool, **kwargs):
    """Handle upload status changes."""
    # We don't need to automatically set timestamps here since we do it manually in views
    # This signal can be used for other purposes like sending notifications
    pass


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
        
        # If all required fields are mapped, set status to MAPPED (not PROCESSING)
        if all(field in mapped_fields for field in required_fields):
            instance.upload.status = BillingDataUpload.UploadStatus.MAPPED
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