from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .models import BillingDataUpload, MappedField, AnalyticsQuery

User = get_user_model()


class FileUploadForm(forms.ModelForm):
    """Form for uploading billing data files (CSV/Excel)."""
    
    class Meta:
        model = BillingDataUpload
        fields = ["file"]
        widgets = {
            "file": forms.FileInput(attrs={
                "class": "block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100",
                "accept": ".csv,.xlsx,.xls"
            })
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        
        self.fields["file"].help_text = (
            "Upload your billing data file. Supported formats: CSV, Excel (.xlsx, .xls). "
            "Maximum file size: 50MB"
        )
    
    def clean_file(self):
        """Validate the uploaded file."""
        file = self.cleaned_data.get("file")
        
        if file:
            # Check file size (50MB limit)
            if file.size > 50 * 1024 * 1024:
                raise ValidationError("File size must be less than 50MB.")
            
            # Check file extension
            allowed_extensions = ["csv", "xlsx", "xls"]
            file_extension = file.name.split(".")[-1].lower()
            if file_extension not in allowed_extensions:
                raise ValidationError(
                    f"File type '{file_extension}' is not supported. "
                    f"Please upload: {', '.join(allowed_extensions)}"
                )
            
            # Basic content validation for CSV files
            if file_extension == "csv":
                try:
                    # Read first few bytes to ensure it's valid CSV-like content
                    file.seek(0)
                    first_line = file.read(1024).decode("utf-8")
                    file.seek(0)
                    
                    if not first_line.strip():
                        raise ValidationError("The CSV file appears to be empty.")
                        
                except UnicodeDecodeError:
                    raise ValidationError("The CSV file contains invalid characters.")
        
        return file
    
    def save(self, commit: bool = True) -> BillingDataUpload:
        """Save the form with additional metadata."""
        instance = super().save(commit=False)
        
        if self.user:
            instance.user = self.user
        
        if instance.file:
            instance.original_filename = instance.file.name
            instance.file_size = instance.file.size
        
        if commit:
            instance.save()
        
        return instance


class ColumnMappingForm(forms.Form):
    """Dynamic form for mapping uploaded file columns to predefined fields."""
    
    def __init__(self, *args, **kwargs):
        self.upload = kwargs.pop("upload", None)
        self.columns = kwargs.pop("columns", [])
        super().__init__(*args, **kwargs)
        
        # Create dynamic fields for each column
        for column in self.columns:
            field_name = f"mapping_{column}"
            
            # Field type selection
            self.fields[field_name] = forms.ChoiceField(
                label=f"Map '{column}' to:",
                choices=self._get_field_choices(),
                required=False,
                widget=forms.Select(attrs={
                    "class": "mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm",
                    "data-column": column
                })
            )
            
            # Custom field name (for custom mappings)
            custom_field_name = f"custom_{column}"
            self.fields[custom_field_name] = forms.CharField(
                label=f"Custom name for '{column}':",
                required=False,
                widget=forms.TextInput(attrs={
                    "class": "mt-1 block w-full py-2 px-3 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm",
                    "placeholder": "Enter custom field name",
                    "style": "display: none;"  # Hidden by default, shown via JavaScript
                })
            )
            
            # Data type selection
            data_type_field_name = f"data_type_{column}"
            self.fields[data_type_field_name] = forms.ChoiceField(
                label=f"Data type for '{column}':",
                choices=[
                    ("string", "Text"),
                    ("number", "Number"),
                    ("date", "Date"),
                    ("boolean", "Yes/No"),
                ],
                initial="string",
                widget=forms.Select(attrs={
                    "class": "mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                })
            )
    
    def _get_field_choices(self) -> List[tuple]:
        """Get choices for field mapping dropdown."""
        choices = [("", "-- Skip this column --")]
        
        # Add predefined field types
        for value, label in MappedField.FieldType.choices:
            choices.append((value, label))
        
        return choices
    
    def clean(self) -> Dict:
        """Validate the form data."""
        cleaned_data = super().clean()
        
        # Check for required field mappings
        required_fields = ["date", "customer_name", "invoice_number", "amount"]
        mapped_fields = []
        
        for column in self.columns:
            field_name = f"mapping_{column}"
            mapping = cleaned_data.get(field_name)
            
            if mapping:
                mapped_fields.append(mapping)
                
                # Validate custom field names
                if mapping == "custom":
                    custom_name = cleaned_data.get(f"custom_{column}")
                    if not custom_name:
                        self.add_error(
                            f"custom_{column}",
                            "Custom field name is required when selecting 'Custom Field'."
                        )
        
        # Check if at least the minimum required fields are mapped
        missing_required = set(required_fields) - set(mapped_fields)
        if missing_required:
            raise ValidationError(
                f"The following required fields must be mapped: {', '.join(missing_required)}"
            )
        
        # Check for duplicate mappings (except custom and skipped fields)
        non_custom_mappings = [m for m in mapped_fields if m and m != "custom"]
        if len(non_custom_mappings) != len(set(non_custom_mappings)):
            raise ValidationError("Each field can only be mapped once.")
        
        return cleaned_data
    
    def save(self) -> List[MappedField]:
        """Save the column mappings."""
        if not self.upload:
            raise ValueError("Upload instance is required to save mappings.")
        
        # Delete existing mappings for this upload
        MappedField.objects.filter(upload=self.upload).delete()
        
        mappings = []
        for column in self.columns:
            field_name = f"mapping_{column}"
            mapping = self.cleaned_data.get(field_name)
            
            if mapping:  # Skip empty mappings
                mapped_field = MappedField(
                    upload=self.upload,
                    original_column=column,
                    mapped_field=mapping,
                    data_type=self.cleaned_data.get(f"data_type_{column}", "string")
                )
                
                # Set custom field name if applicable
                if mapping == "custom":
                    mapped_field.custom_field_name = self.cleaned_data.get(f"custom_{column}")
                
                # Mark required fields
                if mapping in ["date", "customer_name", "invoice_number", "amount"]:
                    mapped_field.is_required = True
                
                mapped_field.save()
                mappings.append(mapped_field)
        
        return mappings


class DateRangeForm(forms.Form):
    """Form for selecting date ranges for analytics."""
    
    DATE_RANGE_CHOICES = [
        ("", "Custom Range"),
        ("today", "Today"),
        ("yesterday", "Yesterday"),
        ("last_7_days", "Last 7 Days"),
        ("last_30_days", "Last 30 Days"),
        ("this_month", "This Month"),
        ("last_month", "Last Month"),
        ("this_quarter", "This Quarter"),
        ("this_year", "This Year"),
        ("last_year", "Last Year"),
    ]
    
    quick_select = forms.ChoiceField(
        choices=DATE_RANGE_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            "class": "mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm",
            "onchange": "updateDateRange(this.value)"
        }),
        label="Quick Select"
    )
    
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            "type": "date",
            "class": "mt-1 block w-full py-2 px-3 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
        }),
        label="Start Date"
    )
    
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            "type": "date",
            "class": "mt-1 block w-full py-2 px-3 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
        }),
        label="End Date"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default date range (last 30 days)
        today = timezone.now().date()
        self.fields["end_date"].initial = today
        self.fields["start_date"].initial = today - timedelta(days=30)
    
    def clean(self) -> Dict:
        """Validate date range."""
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        
        if start_date and end_date:
            if start_date > end_date:
                raise ValidationError("Start date must be before or equal to end date.")
            
            # Check if date range is not too large (e.g., more than 2 years)
            if (end_date - start_date).days > 730:
                raise ValidationError("Date range cannot exceed 2 years.")
            
            # Check if end date is not in the future
            if end_date > timezone.now().date():
                raise ValidationError("End date cannot be in the future.")
        
        return cleaned_data


class AnalyticsQueryForm(forms.ModelForm):
    """Form for submitting analytics queries to ChatGPT."""
    
    class Meta:
        model = AnalyticsQuery
        fields = ["query_text", "query_type"]
        widgets = {
            "query_text": forms.Textarea(attrs={
                "class": "mt-1 block w-full py-2 px-3 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm",
                "rows": 4,
                "placeholder": "Ask a question about your billing data... e.g., 'What are the top 5 customers by revenue this month?'"
            }),
            "query_type": forms.Select(attrs={
                "class": "mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
            })
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        self.upload = kwargs.pop("upload", None)
        super().__init__(*args, **kwargs)
        
        self.fields["query_text"].help_text = (
            "Ask questions about your billing data in natural language. "
            "Examples: 'Show me revenue trends', 'Who are my top customers?', "
            "'What's the average invoice amount?'"
        )
    
    def clean_query_text(self) -> str:
        """Validate query text."""
        query_text = self.cleaned_data.get("query_text", "").strip()
        
        if len(query_text) < 10:
            raise ValidationError("Query must be at least 10 characters long.")
        
        if len(query_text) > 1000:
            raise ValidationError("Query must be less than 1000 characters.")
        
        # Basic content filtering (optional)
        prohibited_words = ["delete", "drop", "truncate", "insert", "update"]
        if any(word in query_text.lower() for word in prohibited_words):
            raise ValidationError("Query contains prohibited operations.")
        
        return query_text
    
    def save(self, commit: bool = True) -> AnalyticsQuery:
        """Save the analytics query."""
        instance = super().save(commit=False)
        
        if self.user:
            instance.user = self.user
        
        if self.upload:
            instance.upload = self.upload
        
        if commit:
            instance.save()
        
        return instance


class BulkActionForm(forms.Form):
    """Form for bulk actions on billing records."""
    
    ACTION_CHOICES = [
        ("", "Select an action..."),
        ("export_csv", "Export to CSV"),
        ("export_excel", "Export to Excel"),
        ("update_status", "Update Payment Status"),
        ("delete", "Delete Selected"),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={
            "class": "mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
        })
    )
    
    # Optional payment status for update action
    payment_status = forms.ChoiceField(
        choices=[("", "Select status...")] + list(
            (status.value, status.label) 
            for status in BillingRecord.PaymentStatus
        ),
        required=False,
        widget=forms.Select(attrs={
            "class": "mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm",
            "style": "display: none;"  # Hidden by default
        })
    )
    
    selected_records = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
    
    def clean(self) -> Dict:
        """Validate bulk action form."""
        cleaned_data = super().clean()
        action = cleaned_data.get("action")
        payment_status = cleaned_data.get("payment_status")
        selected_records = cleaned_data.get("selected_records")
        
        if action and not selected_records:
            raise ValidationError("Please select at least one record.")
        
        if action == "update_status" and not payment_status:
            raise ValidationError("Payment status is required for status update action.")
        
        return cleaned_data 