"""
Analytics app views for billing data processing and analytics.

This module contains all the views for the analytics application including:
- File upload and processing views
- Dashboard and analytics views
- API endpoints for AJAX requests
- ChatGPT integration views
"""

import json
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.views.generic import (
    TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView
)
from django.views import View
from django.http import JsonResponse, HttpResponse, HttpRequest, Http404
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db.models import Q, Count, Sum, Avg, QuerySet, Max
from django.db import transaction
from django.utils import timezone
from django.conf import settings

from .models import (
    BillingDataUpload, MappedField, BillingRecord, AnalyticsQuery
)
from .utils import (
    DataProcessor, AnalyticsCalculator, ChatGPTIntegration
)


class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard view for the analytics application."""
    
    template_name = "analytics/dashboard.html"
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Add dashboard statistics to the context."""
        context = super().get_context_data(**kwargs)
        context["segment"] = "index"
        
        # Get recent uploads
        recent_uploads = BillingDataUpload.objects.filter(
            user=self.request.user
        ).order_by("-upload_date")[:5]
        
        # Calculate statistics - aggregate by invoice first
        user_records = BillingRecord.objects.filter(upload__user=self.request.user)
        total_records = user_records.count()
        
        # Aggregate by invoice_number first, then sum
        invoice_totals = user_records.values("invoice_number").annotate(
            invoice_total=Sum("amount")
        ).aggregate(total_revenue=Sum("invoice_total"))
        
        total_revenue = invoice_totals["total_revenue"] or 0
        
        # Get query count for AI queries
        query_count = AnalyticsQuery.objects.filter(
            user=self.request.user
        ).count()
        
        context.update({
            "recent_uploads": recent_uploads,
            "total_records": total_records,
            "total_revenue": total_revenue,
            "upload_count": BillingDataUpload.objects.filter(user=self.request.user).count(),
            "query_count": query_count,
        })
        
        return context


class FileUploadView(LoginRequiredMixin, CreateView):
    """View for uploading billing data files."""
    
    model = BillingDataUpload
    template_name = "analytics/file_upload.html"
    fields = ["file"]
    success_url = reverse_lazy("analytics:upload_list")
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Add segment to context."""
        context = super().get_context_data(**kwargs)
        context["segment"] = "file_upload"
        return context
    
    def form_valid(self, form):
        """Process the uploaded file and set the user."""
        form.instance.user = self.request.user
        
        # Set file metadata before saving
        uploaded_file = form.cleaned_data["file"]
        form.instance.original_filename = uploaded_file.name
        form.instance.file_size = uploaded_file.size
        
        response = super().form_valid(form)
        
        # Process file headers and sample data
        try:
            import pandas as pd
            import os
            
            file_path = form.instance.file.path
            
            # Read file to get basic info
            if file_path.endswith(".csv"):
                df = pd.read_csv(file_path, nrows=0)  # Just get headers
                total_rows = sum(1 for line in open(file_path)) - 1  # Subtract header
            elif file_path.endswith((".xlsx", ".xls")):
                df = pd.read_excel(file_path, nrows=0)  # Just get headers
                full_df = pd.read_excel(file_path)
                total_rows = len(full_df)
            else:
                raise ValueError("Unsupported file format")
            
            headers = list(df.columns)
            
            # Update the upload with file info
            form.instance.total_rows = total_rows
            form.instance.save()
            
            messages.success(
                self.request, 
                f"File uploaded successfully! Found {len(headers)} columns and {total_rows} rows."
            )
        except Exception as e:
            messages.error(
                self.request, 
                f"Error processing file: {str(e)}"
            )
        
        return response


class UploadListView(LoginRequiredMixin, ListView):
    """List view for all uploaded files."""
    
    model = BillingDataUpload
    template_name = "analytics/upload_list.html"
    context_object_name = "uploads"
    paginate_by = 20
    
    def get_queryset(self):
        """Filter uploads by current user."""
        return BillingDataUpload.objects.filter(
            user=self.request.user
        ).order_by("-upload_date")

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["segment"] = "uploads"
        return context


class UploadDetailView(LoginRequiredMixin, DetailView):
    """Display detailed information about a specific upload."""
    model = BillingDataUpload
    template_name = "analytics/upload_detail.html"
    context_object_name = "upload"
    pk_url_kwarg = "upload_id"

    def get_queryset(self) -> QuerySet[BillingDataUpload]:
        return BillingDataUpload.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        upload = self.get_object()
        
        # Get mappings
        context["mappings"] = MappedField.objects.filter(upload=upload)
        
        # Get preview of billing records
        context["billing_records"] = BillingRecord.objects.filter(
            upload=upload
        ).order_by("-created_at")[:10]
        
        return context


class UploadDeleteView(LoginRequiredMixin, DeleteView):
    """Delete an upload and all associated data."""
    model = BillingDataUpload
    template_name = "analytics/upload_confirm_delete.html"
    context_object_name = "upload"
    pk_url_kwarg = "upload_id"
    success_url = reverse_lazy("analytics:upload_list")

    def get_queryset(self) -> QuerySet[BillingDataUpload]:
        return BillingDataUpload.objects.filter(user=self.request.user)

    def delete(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        upload = self.get_object()
        messages.success(request, f"Upload '{upload.file.name}' has been deleted successfully.")
        return super().delete(request, *args, **kwargs)


class ColumnMappingView(LoginRequiredMixin, TemplateView):
    """View for mapping file columns to billing fields."""
    
    template_name = "analytics/column_mapping.html"
    
    def get_object(self):
        """Get the upload object."""
        return get_object_or_404(
            BillingDataUpload,
            pk=self.kwargs["upload_id"],
            user=self.request.user
        )
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Add upload and mapping data to context."""
        context = super().get_context_data(**kwargs)
        context["segment"] = "uploads"
        upload = self.get_object()
        
        # Ensure upload has a date format set (for backward compatibility)
        if not upload.date_format:
            upload.date_format = "DD/MM/YYYY"
            upload.save(update_fields=["date_format"])
        
        # Get existing mappings
        mappings = {
            mapping.mapped_field: mapping.original_column
            for mapping in MappedField.objects.filter(upload=upload)
        }
        
        # Read actual file columns from the uploaded file
        file_columns = self._get_file_columns(upload)
        
        # Get intelligent suggestions if no mappings exist yet
        suggested_mappings = {}
        if not mappings and file_columns:
            suggested_mappings = self._suggest_column_mappings(file_columns)
        
        # Required billing fields with their current mappings
        required_fields = [
            {
                "key": "customer_name", 
                "label": "Customer Name",
                "description": "Customer or client name",
                "mapped_column": mappings.get("customer_name", "")
            },
            {
                "key": "invoice_number", 
                "label": "Invoice Number",
                "description": "Unique invoice identifier", 
                "mapped_column": mappings.get("invoice_number", "")
            },
            {
                "key": "amount", 
                "label": "Amount",
                "description": "Invoice amount (numeric)",
                "mapped_column": mappings.get("amount", "")
            },
            {
                "key": "date", 
                "label": "Date",
                "description": "Invoice or billing date",
                "mapped_column": mappings.get("date", "")
            },
        ]
        
        # Optional billing fields with their current mappings
        optional_fields = [
            {
                "key": "payment_status", 
                "label": "Payment Status",
                "description": "Payment status",
                "mapped_column": mappings.get("payment_status", "")
            },
            {
                "key": "description", 
                "label": "Description",
                "description": "Invoice description or notes",
                "mapped_column": mappings.get("description", "")
            },
            {
                "key": "product_name", 
                "label": "Product Name",
                "description": "Product or service name",
                "mapped_column": mappings.get("product_name", "")
            },
            {
                "key": "quantity", 
                "label": "Quantity",
                "description": "Quantity of items",
                "mapped_column": mappings.get("quantity", "")
            },
            {
                "key": "unit_price", 
                "label": "Unit Price",
                "description": "Price per unit",
                "mapped_column": mappings.get("unit_price", "")
            },
            {
                "key": "tax_amount", 
                "label": "Tax Amount",
                "description": "Tax amount",
                "mapped_column": mappings.get("tax_amount", "")
            },
            {
                "key": "discount", 
                "label": "Discount",
                "description": "Discount amount",
                "mapped_column": mappings.get("discount", "")
            },
            {
                "key": "payment_method", 
                "label": "Payment Method",
                "description": "Payment method used",
                "mapped_column": mappings.get("payment_method", "")
            },
        ]
        
        # Update field mappings with suggestions
        for field in required_fields + optional_fields:
            if not field["mapped_column"] and field["key"] in suggested_mappings:
                field["suggested_column"] = suggested_mappings[field["key"]]
        
        context.update({
            "upload": upload,
            "mappings": mappings,
            "required_fields": required_fields,
            "optional_fields": optional_fields,
            "file_columns": file_columns,
            "suggested_mappings": suggested_mappings,
            "current_date_format": upload.date_format,
        })
        
        return context
    
    def _get_file_columns(self, upload: BillingDataUpload) -> List[str]:
        """Extract column names from the uploaded file."""
        try:
            import pandas as pd
            import os
            
            file_path = upload.file.path
            
            # Check if file exists
            if not os.path.exists(file_path):
                print(f"File does not exist at path: {file_path}")
                return []
            
            # Read file headers based on file type
            if file_path.endswith(".csv"):
                # Try different encodings for CSV files
                encodings = ["utf-8", "latin-1", "cp1252", "iso-8859-1"]
                df = None
                
                for encoding in encodings:
                    try:
                        df = pd.read_csv(file_path, nrows=0, encoding=encoding)
                        print(f"Successfully read CSV with encoding: {encoding}")
                        break
                    except (UnicodeDecodeError, UnicodeError) as e:
                        print(f"Failed to read with encoding {encoding}: {e}")
                        continue
                
                if df is None:
                    # Fallback: try with default encoding
                    try:
                        df = pd.read_csv(file_path, nrows=0)
                        print("Successfully read CSV with default encoding")
                    except Exception as e:
                        print(f"Failed to read CSV with default encoding: {e}")
                        return []
                    
            elif file_path.endswith((".xlsx", ".xls")):
                try:
                    df = pd.read_excel(file_path, nrows=0)
                    print("Successfully read Excel file")
                except Exception as e:
                    print(f"Failed to read Excel file: {e}")
                    return []
            else:
                print(f"Unsupported file format: {file_path}")
                return []
            
            # Get column names and clean them
            columns = list(df.columns)
            print(f"Raw columns from file: {columns}")
            
            # Clean column names (remove extra spaces, handle unnamed columns)
            cleaned_columns = []
            for i, col in enumerate(columns):
                if pd.isna(col) or str(col).startswith("Unnamed:"):
                    cleaned_columns.append(f"Column_{i+1}")
                else:
                    cleaned_columns.append(str(col).strip())
            
            print(f"Cleaned columns: {cleaned_columns}")
            return cleaned_columns
            
        except ImportError:
            print("Error: pandas library not available")
            return []
        except Exception as e:
            # Log the error (in production, use proper logging)
            print(f"Error reading file columns: {str(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return []
    
    def _suggest_column_mappings(self, file_columns: List[str]) -> Dict[str, str]:
        """Suggest column mappings based on column name similarity."""
        suggestions = {}
        
        # Define mapping patterns for common column variations
        mapping_patterns = {
            "customer_name": [
                "customer_name", "customer name", "client_name", "client name", 
                "company", "company_name", "customer", "client", "name"
            ],
            "invoice_number": [
                "invoice_number", "invoice number", "invoice_id", "invoice id",
                "inv_num", "inv_number", "bill_number", "bill number", "invoice"
            ],
            "amount": [
                "amount", "total", "invoice_amount", "invoice amount", 
                "bill_amount", "bill amount", "cost", "price", "value"
            ],
            "date": [
                "date", "invoice_date", "invoice date", "bill_date", "bill date",
                "created_date", "created date", "timestamp"
            ],
            "payment_status": [
                "payment_status", "payment status", "status", "paid", "payment"
            ],
            "description": [
                "description", "notes", "memo", "comment", "details"
            ],
            "customer_email": [
                "email", "customer_email", "customer email", "client_email", "e_mail"
            ],
            "due_date": [
                "due_date", "due date", "payment_due", "payment due", "due"
            ]
        }
        
        # Find best matches for each predefined field
        for field, patterns in mapping_patterns.items():
            best_match = None
            best_score = 0
            
            for file_col in file_columns:
                file_col_lower = file_col.lower().replace("_", " ").replace("-", " ")
                
                for pattern in patterns:
                    pattern_lower = pattern.lower()
                    
                    # Exact match gets highest score
                    if file_col_lower == pattern_lower:
                        best_match = file_col
                        best_score = 100
                        break
                    
                    # Partial match scoring
                    if pattern_lower in file_col_lower:
                        score = len(pattern_lower) / len(file_col_lower) * 80
                        if score > best_score:
                            best_match = file_col
                            best_score = score
                    
                    elif file_col_lower in pattern_lower:
                        score = len(file_col_lower) / len(pattern_lower) * 70
                        if score > best_score:
                            best_match = file_col
                            best_score = score
                
                if best_score >= 100:  # Exact match found
                    break
            
            # Only suggest if confidence is high enough
            if best_match and best_score >= 60:
                suggestions[field] = best_match
        
        return suggestions
    
    def post(self, request, *args, **kwargs):
        """Handle column mapping form submission."""
        upload = self.get_object()
        
        # Save date format preference
        date_format = request.POST.get("date_format", "DD/MM/YYYY")
        upload.date_format = date_format
        upload.save(update_fields=["date_format"])
        
        # Clear existing mappings
        MappedField.objects.filter(upload=upload).delete()
        
        # Create new mappings
        mappings_created = 0
        for field_name, column_name in request.POST.items():
            if field_name.startswith("mapping_") and column_name:
                mapped_field = field_name.replace("mapping_", "")
                is_required = mapped_field in ["customer_name", "invoice_number", "amount", "date"]
                
                MappedField.objects.create(
                    upload=upload,
                    original_column=column_name,
                    mapped_field=mapped_field,
                    is_required=is_required
                )
                mappings_created += 1
        
        # Update upload status to MAPPED if mappings were created
        if mappings_created > 0:
            upload.status = "MAPPED"
            upload.save()
            messages.success(request, f"Column mappings and date format saved successfully! {mappings_created} fields mapped. You can now process the upload.")
        else:
            messages.warning(request, "No column mappings were created. Please map at least one field.")
        
        return redirect("analytics:upload_detail", upload_id=upload.pk)


class ProcessUploadView(LoginRequiredMixin, View):
    """Process a mapped upload to create billing records."""
    
    def post(self, request: HttpRequest, upload_id: uuid.UUID) -> HttpResponse:
        try:
            upload = BillingDataUpload.objects.get(
                id=upload_id, 
                user=request.user,
                status="MAPPED"
            )
            
            # Update status to processing
            upload.status = "PROCESSING"
            upload.processing_started_at = timezone.now()
            upload.save()
            
            # Process in background (for now, we'll do it synchronously)
            self._process_upload(upload)
            
            messages.success(request, "Upload processing has started.")
            return redirect("analytics:upload_detail", upload_id=upload_id)
            
        except BillingDataUpload.DoesNotExist:
            messages.error(request, "Upload not found or not ready for processing.")
            return redirect("analytics:upload_list")
        except Exception as e:
            messages.error(request, f"Error starting processing: {str(e)}")
            return redirect("analytics:upload_detail", upload_id=upload_id)
    
    def _process_upload(self, upload: BillingDataUpload) -> None:
        """Process the upload and create billing records."""
        try:
            # Get mappings
            mappings = {
                mapping.mapped_field: mapping.original_column
                for mapping in MappedField.objects.filter(upload=upload)
            }
            
            if not mappings:
                upload.status = "ERROR"
                upload.error_message = "No column mappings found"
                upload.save()
                return
            
            # Check if required fields are mapped
            required_fields = ["customer_name", "invoice_number", "amount", "date"]
            missing_required = [field for field in required_fields if field not in mappings]
            
            if missing_required:
                upload.status = "ERROR"
                upload.error_message = f"Missing required field mappings: {', '.join(missing_required)}"
                upload.save()
                return
            
            # Read file data
            file_path = upload.file.path
            try:
                if file_path.endswith(".csv"):
                    import pandas as pd
                    # Try different encodings for CSV files
                    encodings = ["utf-8", "latin-1", "cp1252", "iso-8859-1"]
                    df = None
                    
                    for encoding in encodings:
                        try:
                            df = pd.read_csv(file_path, encoding=encoding)
                            break
                        except (UnicodeDecodeError, UnicodeError):
                            continue
                    
                    if df is None:
                        df = pd.read_csv(file_path)  # Fallback to default
                        
                elif file_path.endswith((".xlsx", ".xls")):
                    import pandas as pd
                    df = pd.read_excel(file_path)
                else:
                    upload.status = "ERROR"
                    upload.error_message = "Unsupported file format"
                    upload.save()
                    return
            except Exception as e:
                upload.status = "ERROR"
                upload.error_message = f"Error reading file: {str(e)}"
                upload.save()
                return
            
            upload.total_rows = len(df)
            upload.save()
            
            # Create billing records
            created_count = 0
            errors = []
            
            for index, row in df.iterrows():
                try:
                    # Extract data based on mappings
                    record_data = {}
                    
                    # Process each mapped field
                    for field, column in mappings.items():
                        if column in row and pd.notna(row[column]):
                            value = row[column]
                            
                            # Type conversion for specific fields
                            if field in ["amount", "tax_amount", "discount", "unit_price"]:
                                try:
                                    # Clean monetary values
                                    cleaned_value = str(value).replace("₹", "").replace(",", "").strip()
                                    record_data[field] = float(cleaned_value) if cleaned_value else 0.0
                                except (ValueError, TypeError):
                                    record_data[field] = 0.0
                            elif field in ["quantity"]:
                                try:
                                    record_data[field] = float(str(value).strip()) if str(value).strip() else None
                                except (ValueError, TypeError):
                                    record_data[field] = None
                            elif field in ["date", "due_date", "payment_date"]:
                                try:
                                    # Use the upload's date format preference for parsing
                                    record_data[field] = self._parse_date_with_format(value, upload.date_format)
                                except (ValueError, TypeError):
                                    record_data[field] = None
                            else:
                                record_data[field] = str(value).strip()
                        else:
                            # Handle missing values for required fields
                            if field in required_fields:
                                if field in ["amount"]:
                                    record_data[field] = 0.0
                                elif field in ["date"]:
                                    record_data[field] = None
                                else:
                                    record_data[field] = ""
                    
                    # Validate required fields have values
                    validation_errors = []
                    if not record_data.get("customer_name"):
                        validation_errors.append("customer_name is required")
                    if not record_data.get("invoice_number"):
                        validation_errors.append("invoice_number is required")
                    if record_data.get("amount") is None or record_data.get("amount") < 0:
                        validation_errors.append("amount must be a positive number")
                    if not record_data.get("date"):
                        validation_errors.append("date is required")
                    
                    if validation_errors:
                        errors.append(f"Row {index + 1}: {'; '.join(validation_errors)}")
                        continue
                    
                    # Create billing record
                    BillingRecord.objects.create(
                        upload=upload,
                        row_number=index + 1,
                        **record_data
                    )
                    created_count += 1
                    
                except Exception as e:
                    errors.append(f"Row {index + 1}: {str(e)}")
                
                # Update progress every 10 rows
                if (index + 1) % 10 == 0:
                    upload.processed_rows = created_count
                    upload.save()
            
            # Final update
            upload.processed_rows = created_count
            
            # Update final status
            if errors:
                upload.status = "COMPLETED" if created_count > 0 else "ERROR"
                upload.error_message = "; ".join(errors[:10])  # Keep only first 10 errors
                if created_count > 0:
                    upload.error_message += f" ({len(errors)} total errors, {created_count} records created)"
            else:
                upload.status = "COMPLETED"
            
            upload.processing_completed_at = timezone.now()
            upload.save()
            
        except Exception as e:
            upload.status = "ERROR"
            upload.error_message = f"Processing error: {str(e)}"
            upload.processing_completed_at = timezone.now()
            upload.save()

    def _parse_date_with_format(self, date_value, date_format: str):
        """Parse date value according to the specified format."""
        import pandas as pd
        from datetime import datetime
        
        if pd.isna(date_value) or not date_value:
            return None
            
        date_str = str(date_value).strip()
        if not date_str:
            return None
        
        # Define format mappings
        format_patterns = {
            "DD/MM/YYYY": ["%d/%m/%Y", "%d/%m/%y"],
            "MM/DD/YYYY": ["%m/%d/%Y", "%m/%d/%y"],
            "YYYY-MM-DD": ["%Y-%m-%d"],
            "DD-MM-YYYY": ["%d-%m-%Y", "%d-%m-%y"],
            "MM-DD-YYYY": ["%m-%d-%Y", "%m-%d-%y"],
            "DD.MM.YYYY": ["%d.%m.%Y", "%d.%m.%y"],
        }
        
        # Auto-detect format
        if date_format == "auto":
            all_patterns = []
            for patterns in format_patterns.values():
                all_patterns.extend(patterns)
        else:
            all_patterns = format_patterns.get(date_format, ["%d/%m/%Y"])
        
        # Try to parse with each pattern
        for pattern in all_patterns:
            try:
                parsed_date = datetime.strptime(date_str, pattern)
                return parsed_date.date()
            except (ValueError, TypeError):
                continue
        
        # Fallback to pandas datetime parsing
        try:
            # For Indian format, specify dayfirst=True
            dayfirst = date_format in ["DD/MM/YYYY", "DD-MM-YYYY", "DD.MM.YYYY"] or date_format == "auto"
            parsed_date = pd.to_datetime(date_str, dayfirst=dayfirst, errors="coerce")
            if pd.notna(parsed_date):
                return parsed_date.date()
        except Exception:
            pass
        
        return None


class DataPreviewView(LoginRequiredMixin, TemplateView):
    """View to preview data before processing."""
    
    template_name = "analytics/data_preview.html"
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Add preview data to context."""
        context = super().get_context_data(**kwargs)
        
        upload = get_object_or_404(
            BillingDataUpload,
            pk=self.kwargs["pk"],
            user=self.request.user
        )
        
        context.update({
            "upload": upload,
            "sample_data": [],  # Sample data not stored in model
            "headers": [],  # Headers not stored in model
        })
        
        return context


class AnalyticsView(LoginRequiredMixin, TemplateView):
    """Main analytics dashboard view."""
    
    template_name = "analytics/analytics.html"
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Add analytics data to context."""
        context = super().get_context_data(**kwargs)
        context["segment"] = "analytics"
        
        # Get user's billing records
        records = BillingRecord.objects.filter(upload__user=self.request.user)
        
        if records.exists():
            # Get recent records for display
            recent_records = records.order_by("-created_at")[:5]
            
            # Calculate aggregated analytics - aggregate by invoice first
            invoice_totals = records.values("invoice_number").annotate(
                invoice_total=Sum("amount"),
                customer_name=Max("customer_name"),  # Get customer name for each invoice
                invoice_date=Max("date")  # Use latest date for invoice
            )
            
            # Now calculate totals from invoice aggregates
            total_revenue = invoice_totals.aggregate(
                total=Sum("invoice_total")
            )["total"] or 0
            
            total_customers = invoice_totals.values("customer_name").distinct().count()
            
            average_invoice = invoice_totals.aggregate(
                avg=Avg("invoice_total")
            )["avg"] or 0
            
            total_invoices = invoice_totals.count()
            
            # Get top customers data for chart - use Python aggregation to avoid Django limitation
            from collections import defaultdict
            
            # First get all invoice totals with customer names
            invoice_data = list(invoice_totals.values("customer_name", "invoice_total"))
            
            # Aggregate by customer using Python
            customer_revenue = defaultdict(float)
            for item in invoice_data:
                customer_revenue[item["customer_name"]] += float(item["invoice_total"] or 0)
            
            # Sort and get top 10
            top_customers_data = sorted(customer_revenue.items(), key=lambda x: x[1], reverse=True)[:10]
            top_customers_labels = [item[0] for item in top_customers_data]
            top_customers_amounts = [item[1] for item in top_customers_data]
            
            # Payment status distribution - use latest status per invoice
            latest_status_per_invoice = records.values("invoice_number").annotate(
                latest_status=Max("payment_status")
            )
            
            payment_status_data = list(
                latest_status_per_invoice.values("latest_status").annotate(
                    count=Count("invoice_number")
                ).order_by("latest_status")
            )
            
            payment_status_labels = []
            payment_status_counts = []
            for item in payment_status_data:
                status = item["latest_status"] or "Unknown"
                payment_status_labels.append(status)
                payment_status_counts.append(item["count"])
            
            # Monthly revenue trend (last 6 months) - aggregate by invoice first
            from datetime import datetime, timedelta
            from django.utils import timezone
            
            monthly_revenue_labels = []
            monthly_revenue_data = []
            
            for i in range(5, -1, -1):
                month_start = (timezone.now().date().replace(day=1) - timedelta(days=i*30))
                month_end = month_start + timedelta(days=30)
                
                # Get invoice totals for the month
                monthly_invoices = records.filter(
                    date__gte=month_start,
                    date__lt=month_end
                ).values("invoice_number").annotate(
                    invoice_total=Sum("amount")
                ).aggregate(total=Sum("invoice_total"))
                
                monthly_rev = monthly_invoices["total"] or 0
                
                monthly_revenue_labels.append(month_start.strftime("%b %Y"))
                monthly_revenue_data.append(float(monthly_rev))
            
            # Create analytics_data structure that matches template expectations
            analytics_data = {
                "total_revenue": float(total_revenue),
                "total_customers": total_customers,
                "average_invoice": float(average_invoice),
                "total_records": total_invoices,  # Changed to total_invoices instead of record count
                # Chart data as JSON strings for JavaScript
                "monthly_revenue_labels": json.dumps(monthly_revenue_labels),
                "monthly_revenue_data": json.dumps(monthly_revenue_data),
                "payment_status_labels": json.dumps(payment_status_labels),
                "payment_status_data": json.dumps(payment_status_counts),
                "top_customers_labels": json.dumps(top_customers_labels),
                "top_customers_data": json.dumps(top_customers_amounts),
            }
            
            context.update({
                "analytics_data": analytics_data,
                "has_data": True,
                "recent_records": recent_records,
                "total_records": total_invoices,  # Changed to show invoice count
                "date_range": self.request.GET.get("date_range", "30"),
            })
        else:
            # Empty data structure for no data case
            analytics_data = {
                "total_revenue": 0.0,
                "total_customers": 0,
                "average_invoice": 0.0,
                "total_records": 0,
                "monthly_revenue_labels": json.dumps([]),
                "monthly_revenue_data": json.dumps([]),
                "payment_status_labels": json.dumps([]),
                "payment_status_data": json.dumps([]),
                "top_customers_labels": json.dumps([]),
                "top_customers_data": json.dumps([]),
            }
            
            context.update({
                "analytics_data": analytics_data,
                "has_data": False,
                "recent_records": [],
                "total_records": 0,
            })
        
        return context


class ChartsDataView(LoginRequiredMixin, View):
    """API view for chart data."""
    
    def get(self, request):
        """Return chart data as JSON."""
        records = BillingRecord.objects.filter(upload__user=request.user)
        
        if not records.exists():
            return JsonResponse({"error": "No data available"}, status=404)
        
        # Pass the user object instead of the records QuerySet
        calculator = AnalyticsCalculator(request.user)
        
        # Get chart data based on request parameters
        chart_type = request.GET.get("type", "revenue_trend")
        period = request.GET.get("period", "monthly")
        
        if chart_type == "revenue_trend":
            data = calculator.get_revenue_trend(period)
        elif chart_type == "top_customers":
            limit = int(request.GET.get("limit", 10))
            data = calculator.get_top_customers(limit)
        elif chart_type == "payment_status":
            data = calculator.get_payment_status_distribution()
        else:
            return JsonResponse({"error": "Invalid chart type"}, status=400)
        
        return JsonResponse(data)


class SummaryStatsView(LoginRequiredMixin, View):
    """API view for summary statistics."""
    
    def get(self, request):
        """Return summary statistics as JSON."""
        records = BillingRecord.objects.filter(upload__user=request.user)
        
        if not records.exists():
            return JsonResponse({"error": "No data available"}, status=404)
        
        # Pass the user object instead of the records QuerySet
        calculator = AnalyticsCalculator(request.user)
        stats = calculator.get_summary_stats()
        
        return JsonResponse(stats)


class ExportDataView(LoginRequiredMixin, View):
    """View to export billing data."""
    
    def get(self, request):
        """Export data as CSV."""
        records = BillingRecord.objects.filter(upload__user=request.user)
        
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="billing_data.csv"'
        
        import csv
        writer = csv.writer(response)
        
        # Write header
        writer.writerow([
            "Invoice Number", "Customer Name", "Amount", "Date",
            "Payment Status", "Due Date", "Payment Date", "Description"
        ])
        
        # Write data
        for record in records:
            writer.writerow([
                record.invoice_number,
                record.customer_name,
                record.amount,
                record.date,
                record.payment_status,
                record.due_date,
                record.payment_date,
                record.description,
            ])
        
        return response


class ExportRecordsView(LoginRequiredMixin, View):
    """View to export selected billing records."""
    
    def get(self, request):
        """Export selected records as CSV."""
        # Get selected IDs from query parameters
        selected_ids = request.GET.get("ids", "").split(",")
        
        if selected_ids and selected_ids[0]:
            records = BillingRecord.objects.filter(
                id__in=selected_ids,
                upload__user=request.user
            )
        else:
            records = BillingRecord.objects.filter(upload__user=request.user)
        
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="selected_billing_records.csv"'
        
        import csv
        writer = csv.writer(response)
        
        # Write header
        writer.writerow([
            "Invoice Number", "Customer Name", "Amount", "Date",
            "Payment Status", "Due Date", "Payment Date", "Description"
        ])
        
        # Write data
        for record in records:
            writer.writerow([
                record.invoice_number,
                record.customer_name,
                record.amount,
                record.date,
                record.payment_status,
                record.due_date,
                record.payment_date,
                record.description,
            ])
        
        return response


class BillingRecordListView(LoginRequiredMixin, ListView):
    """List view for billing records."""
    
    model = BillingRecord
    template_name = "analytics/record_list.html"
    context_object_name = "records"
    paginate_by = 50
    
    def get_queryset(self):
        """Filter records by current user with search functionality."""
        queryset = BillingRecord.objects.filter(upload__user=self.request.user)
        
        # Search functionality
        search = self.request.GET.get("search")
        if search:
            queryset = queryset.filter(
                Q(customer_name__icontains=search) |
                Q(invoice_number__icontains=search) |
                Q(description__icontains=search)
            )
        
        # Filter by upload
        upload_filter = self.request.GET.get("upload")
        if upload_filter:
            queryset = queryset.filter(upload_id=upload_filter)
        
        # Payment status filter (for pending payments card)
        payment_status_filter = self.request.GET.get("payment_status")
        if payment_status_filter == "pending":
            queryset = queryset.filter(
                Q(payment_status__isnull=True) |
                Q(payment_status__in=["", "pending", "unpaid", "overdue"])
            )
        
        # High value filter (for high value bills card)
        high_value_filter = self.request.GET.get("high_value")
        if high_value_filter == "true":
            # Calculate average invoice amount
            invoice_totals = BillingRecord.objects.filter(
                upload__user=self.request.user
            ).values("invoice_number").annotate(
                invoice_total=Sum("amount")
            )
            avg_amount = invoice_totals.aggregate(avg=Avg("invoice_total"))["avg"] or 0
            
            if avg_amount > 0:
                threshold = Decimal(str(avg_amount)) * Decimal("1.5")
                
                # Get invoice numbers that exceed the threshold
                high_value_invoices = invoice_totals.filter(
                    invoice_total__gt=threshold
                ).values_list("invoice_number", flat=True)
                
                queryset = queryset.filter(invoice_number__in=high_value_invoices)
        
        # Date range filters
        date_from = self.request.GET.get("date_from")
        date_to = self.request.GET.get("date_to")
        
        if date_from:
            from datetime import datetime
            try:
                date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
                queryset = queryset.filter(date__gte=date_from_obj)
            except ValueError:
                pass
        
        if date_to:
            from datetime import datetime
            try:
                date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
                queryset = queryset.filter(date__lte=date_to_obj)
            except ValueError:
                pass
        
        # Sorting
        sort = self.request.GET.get("sort", "-date")
        queryset = queryset.order_by(sort)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        """Add billing-specific statistics to context."""
        context = super().get_context_data(**kwargs)
        context["segment"] = "records"
        
        # Get all user's records for statistics (before filtering)
        all_records = BillingRecord.objects.filter(upload__user=self.request.user)
        
        # Get available uploads for filter dropdown
        uploads = BillingDataUpload.objects.filter(
            user=self.request.user,
            status="COMPLETED"
        ).order_by("-upload_date")
        
        # Add date values for clickable cards
        from datetime import datetime, timedelta
        from django.utils import timezone
        
        today = timezone.now().date()
        current_month_start = today.replace(day=1)
        week_ago = today - timedelta(days=7)
        
        context.update({
            "today": today.strftime("%Y-%m-%d"),
            "current_month_start": current_month_start.strftime("%Y-%m-%d"),
            "week_ago": week_ago.strftime("%Y-%m-%d"),
        })
        
        if all_records.exists():
            # Calculate billing-specific statistics - aggregate by invoice first
            today = timezone.now().date()
            current_month_start = today.replace(day=1)
            
            # 1. Pending Payments - count unique invoices with pending status
            pending_invoices = all_records.filter(
                Q(payment_status__isnull=True) |
                Q(payment_status__in=["", "pending", "unpaid", "overdue"])
            ).values("invoice_number").distinct().count()
            
            # 2. This Month's Revenue - aggregate by invoice first
            this_month_invoices = all_records.filter(
                date__gte=current_month_start,
                date__lte=today
            ).values("invoice_number").annotate(
                invoice_total=Sum("amount")
            ).aggregate(total=Sum("invoice_total"))
            
            this_month_revenue = this_month_invoices["total"] or 0
            
            # 3. High Value Invoices - invoices above average amount
            invoice_totals = all_records.values("invoice_number").annotate(
                invoice_total=Sum("amount")
            )
            avg_invoice_amount = invoice_totals.aggregate(avg=Avg("invoice_total"))["avg"] or 0
            
            high_value_count = 0
            if avg_invoice_amount > 0:
                threshold = Decimal(str(avg_invoice_amount)) * Decimal("1.5")
                high_value_count = invoice_totals.filter(
                    invoice_total__gt=threshold
                ).count()
            
            # 4. Recent Activity - invoice count added in last 7 days
            week_ago = timezone.now() - timedelta(days=7)
            recent_activity = all_records.filter(
                created_at__gte=week_ago
            ).values("invoice_number").distinct().count()
            
            # Total statistics for the filtered queryset
            filtered_records = self.get_queryset()
            total_records = filtered_records.count()
            
            # For filtered results, also aggregate by invoice
            filtered_invoice_totals = filtered_records.values("invoice_number").annotate(
                invoice_total=Sum("amount")
            )
            
            total_revenue = filtered_invoice_totals.aggregate(
                total=Sum("invoice_total")
            )["total"] or 0
            
            average_invoice = filtered_invoice_totals.aggregate(
                avg=Avg("invoice_total")
            )["avg"] or 0
            
            unique_customers = filtered_records.values("customer_name").distinct().count()
            unique_invoices = filtered_invoice_totals.count()
            
            context.update({
                "pending_payments": pending_invoices,  # Count of pending invoices
                "this_month_revenue": this_month_revenue,
                "high_value_count": high_value_count,
                "recent_activity": recent_activity,
                "total_records": total_records,  # Total record count (rows)
                "total_invoices": unique_invoices,  # Total unique invoices
                "total_revenue": total_revenue,
                "average_invoice": average_invoice,
                "unique_customers": unique_customers,
                "uploads": uploads,
            })
        else:
            # Default values when no records exist
            context.update({
                "pending_payments": 0,
                "this_month_revenue": 0,
                "high_value_count": 0,
                "recent_activity": 0,
                "total_records": 0,
                "total_invoices": 0,
                "total_revenue": 0,
                "average_invoice": 0,
                "unique_customers": 0,
                "uploads": uploads,
            })
        
        return context


class RecordDetailView(LoginRequiredMixin, DetailView):
    """Display detailed information about a billing record."""
    model = BillingRecord
    template_name = "analytics/record_detail.html"
    context_object_name = "record"
    pk_url_kwarg = "record_id"

    def get_queryset(self) -> QuerySet[BillingRecord]:
        return BillingRecord.objects.filter(upload__user=self.request.user)


class RecordEditView(LoginRequiredMixin, UpdateView):
    """Edit a billing record."""
    model = BillingRecord
    template_name = "analytics/record_edit.html"
    fields = [
        "customer_name", "customer_email", "invoice_number", "date",
        "due_date", "amount", "tax_amount", "discount_amount", "total_amount",
        "payment_status", "payment_date", "payment_method", "description"
    ]
    context_object_name = "record"
    pk_url_kwarg = "record_id"

    def get_queryset(self) -> QuerySet[BillingRecord]:
        return BillingRecord.objects.filter(upload__user=self.request.user)

    def get_success_url(self) -> str:
        return reverse("analytics:record_detail", kwargs={"record_id": self.object.pk})

    def form_valid(self, form) -> HttpResponse:
        messages.success(self.request, "Billing record updated successfully.")
        return super().form_valid(form)


class RecordDeleteView(LoginRequiredMixin, DeleteView):
    """Delete an individual billing record."""
    model = BillingRecord
    template_name = "analytics/record_confirm_delete.html"
    context_object_name = "record"
    pk_url_kwarg = "record_id"
    success_url = reverse_lazy("analytics:record_list")

    def get_queryset(self) -> QuerySet[BillingRecord]:
        return BillingRecord.objects.filter(upload__user=self.request.user)

    def delete(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        record = self.get_object()
        messages.success(request, f"Record '{record.invoice_number}' has been deleted successfully.")
        return super().delete(request, *args, **kwargs)


class BulkDeleteRecordsView(LoginRequiredMixin, View):
    """Bulk delete billing records."""
    
    def post(self, request: HttpRequest) -> HttpResponse:
        try:
            record_ids = request.POST.getlist("selected_records")
            if not record_ids:
                messages.warning(request, "No records selected for deletion.")
                return redirect("analytics:record_list")
            
            # Delete records
            deleted_count, _ = BillingRecord.objects.filter(
                id__in=record_ids,
                upload__user=request.user
            ).delete()
            
            messages.success(request, f"Successfully deleted {deleted_count} billing records.")
            return redirect("analytics:record_list")
            
        except Exception as e:
            messages.error(request, f"Error deleting records: {str(e)}")
            return redirect("analytics:record_list")


class ChatAnalyticsView(LoginRequiredMixin, TemplateView):
    """Chat interface for analytics queries."""
    
    template_name = "analytics/chat_analytics.html"
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Add recent queries and data summary to context."""
        context = super().get_context_data(**kwargs)
        context["segment"] = "chat"
        
        recent_queries = AnalyticsQuery.objects.filter(
            user=self.request.user
        ).order_by("-created_at")[:10]
        
        # Data summary for sidebar
        records = BillingRecord.objects.filter(upload__user=self.request.user)
        data_summary = {
            "total_records": records.count(),
            "total_customers": records.values("customer_name").distinct().count(),
            "last_updated": records.order_by("-created_at").first().created_at if records.exists() else None,
        }
        
        if records.exists():
            date_range = {
                "start": records.order_by("date").first().date,
                "end": records.order_by("-date").first().date,
            }
            data_summary["date_range"] = date_range
        
        context.update({
            "recent_queries": recent_queries,
            "data_summary": data_summary,
        })
        
        return context


class ProcessChatQueryView(LoginRequiredMixin, View):
    """Process ChatGPT analytics queries."""
    
    def post(self, request):
        """Process a natural language analytics query."""
        query_text = request.POST.get("query", "").strip()
        
        if not query_text:
            return JsonResponse({"error": "Query cannot be empty"}, status=400)
        
        # Check if OpenAI API key is configured
        if not hasattr(settings, "OPENAI_API_KEY") or not settings.OPENAI_API_KEY:
            return JsonResponse({
                "error": "OpenAI API key not configured. Please contact administrator."
            }, status=400)
        
        try:
            # Get user's billing data for context
            records = BillingRecord.objects.filter(upload__user=request.user)
            
            if not records.exists():
                return JsonResponse({
                    "error": "No billing data available for analysis. Please upload some data first."
                }, status=400)
            
            # Process query with ChatGPT
            chatgpt = ChatGPTIntegration()
            response = chatgpt.process_query(query_text, records)
            
            # Save query to database
            AnalyticsQuery.objects.create(
                user=request.user,
                query_text=query_text,
                response_text=response,
                created_at=timezone.now()
            )
            
            return JsonResponse({
                "success": True,
                "response": response,
                "timestamp": timezone.now().isoformat()
            })
        
        except Exception as e:
            return JsonResponse({
                "error": f"Error processing query: {str(e)}"
            }, status=500)


class ChatHistoryView(LoginRequiredMixin, ListView):
    """Display chat history."""
    model = AnalyticsQuery
    template_name = "analytics/chat_history.html"
    context_object_name = "queries"
    paginate_by = 20

    def get_queryset(self) -> QuerySet[AnalyticsQuery]:
        return AnalyticsQuery.objects.filter(
            user=self.request.user,
            query_type="CHAT"
        ).order_by("-created_at")


# API Views for AJAX requests

class UploadStatusAPIView(LoginRequiredMixin, View):
    """API view for upload status."""
    
    def get(self, request, pk):
        """Return upload status as JSON."""
        upload = get_object_or_404(
            BillingDataUpload,
            pk=pk,
            user=request.user
        )
        
        return JsonResponse({
            "status": upload.status,
            "processed_rows": upload.processed_rows,
            "total_rows": upload.total_rows,
            "progress": (upload.processed_rows / upload.total_rows * 100) if upload.total_rows > 0 else 0,
            "error_log": [upload.error_message] if upload.error_message else [],
            "upload_date": upload.upload_date.isoformat(),
            "last_updated": upload.upload_date.isoformat(),
        })


class ValidateDataAPIView(LoginRequiredMixin, View):
    """API view for data validation."""
    
    def post(self, request, pk):
        """Validate uploaded data."""
        upload = get_object_or_404(
            BillingDataUpload,
            pk=pk,
            user=request.user
        )
        
        # Get mappings
        mappings = {
            mapping.mapped_field: mapping.original_column
            for mapping in MappedField.objects.filter(upload=upload)
        }
        
        if not mappings:
            return JsonResponse({"error": "No column mappings found"}, status=400)
        
        try:
            processor = DataProcessor(mappings)
            # Validate first 10 rows
            sample_path = upload.file.path
            
            # This would implement validation logic
            validation_results = {
                "valid_rows": 0,
                "invalid_rows": 0,
                "errors": [],
                "warnings": []
            }
            
            return JsonResponse(validation_results)
        
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class SampleDataAPIView(LoginRequiredMixin, View):
    """API view for sample data."""
    
    def get(self, request, pk):
        """Return sample data as JSON."""
        upload = get_object_or_404(
            BillingDataUpload,
            pk=pk,
            user=request.user
        )
        
        return JsonResponse({
            "headers": [],  # Headers not stored in model
            "sample_data": [],  # Sample data not stored in model
            "total_rows": upload.total_rows or 0,
        })


class RevenueTrendAPIView(LoginRequiredMixin, View):
    """API view for revenue trend data."""
    
    def get(self, request):
        """Return revenue trend data."""
        records = BillingRecord.objects.filter(upload__user=request.user)
        
        if not records.exists():
            return JsonResponse({"data": []})
        
        # Pass the user object instead of the records QuerySet
        calculator = AnalyticsCalculator(request.user)
        period = request.GET.get("period", "monthly")
        trend_data = calculator.get_revenue_trend(period)
        
        return JsonResponse(trend_data)


class CustomerAnalysisAPIView(LoginRequiredMixin, View):
    """API view for customer analysis data."""
    
    def get(self, request):
        """Return customer analysis data."""
        records = BillingRecord.objects.filter(upload__user=request.user)
        
        if not records.exists():
            return JsonResponse({"data": []})
        
        # Pass the user object instead of the records QuerySet
        calculator = AnalyticsCalculator(request.user)
        limit = int(request.GET.get("limit", 10))
        customer_data = calculator.get_top_customers(limit)
        
        return JsonResponse(customer_data)


class PaymentStatusAPIView(LoginRequiredMixin, View):
    """API view for payment status distribution."""
    
    def get(self, request):
        """Return payment status distribution."""
        records = BillingRecord.objects.filter(upload__user=request.user)
        
        if not records.exists():
            return JsonResponse({"data": []})
        
        # Pass the user object instead of the records QuerySet
        calculator = AnalyticsCalculator(request.user)
        status_data = calculator.get_payment_status_distribution()
        
        return JsonResponse(status_data)


class CustomerSearchAPIView(LoginRequiredMixin, View):
    """API view for customer search."""
    
    def get(self, request):
        """Search customers by name."""
        query = request.GET.get("q", "").strip()
        
        if len(query) < 2:
            return JsonResponse({"customers": []})
        
        customers = BillingRecord.objects.filter(
            upload__user=request.user,
            customer_name__icontains=query
        ).values("customer_name").distinct()[:10]
        
        return JsonResponse({
            "customers": [c["customer_name"] for c in customers]
        })


class InvoiceSearchAPIView(LoginRequiredMixin, View):
    """API view for invoice search."""
    
    def get(self, request):
        """Search invoices by number."""
        query = request.GET.get("q", "").strip()
        
        if len(query) < 2:
            return JsonResponse({"invoices": []})
        
        invoices = BillingRecord.objects.filter(
            upload__user=request.user,
            invoice_number__icontains=query
        ).values("invoice_number", "customer_name", "amount")[:10]
        
        return JsonResponse({"invoices": list(invoices)})


class NotificationsAPIView(LoginRequiredMixin, View):
    """API view for real-time notifications."""
    
    def get(self, request):
        """Return recent notifications."""
        # This would implement real-time notifications
        notifications = []
        
        # Check for completed uploads
        recent_uploads = BillingDataUpload.objects.filter(
            user=request.user,
            status="COMPLETED",
            processing_completed_at__gte=timezone.now() - timedelta(minutes=5)
        )
        
        for upload in recent_uploads:
            notifications.append({
                "type": "upload_completed",
                "message": f"Upload '{upload.file.name}' completed successfully",
                "timestamp": upload.processing_completed_at.isoformat(),
                "url": reverse("analytics:upload_detail", kwargs={"pk": upload.pk})
            })
        
        return JsonResponse({"notifications": notifications})


class SettingsView(LoginRequiredMixin, TemplateView):
    """Settings view for analytics configuration."""
    
    template_name = "analytics/settings.html"
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Add settings data to context."""
        context = super().get_context_data(**kwargs)
        
        # Add user preferences and configuration options
        context.update({
            "openai_configured": hasattr(settings, "OPENAI_API_KEY") and bool(settings.OPENAI_API_KEY),
            "upload_limit": getattr(settings, "FILE_UPLOAD_MAX_MEMORY_SIZE", 0) / (1024 * 1024),  # MB
        })
        
        return context


class FieldMappingTemplatesView(LoginRequiredMixin, TemplateView):
    """View for managing field mapping templates."""
    
    template_name = "analytics/field_mapping_templates.html"
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Add template data to context."""
        context = super().get_context_data(**kwargs)
        
        # Get commonly used mappings for templates
        common_mappings = MappedField.objects.filter(
            upload__user=self.request.user
        ).values("mapped_field", "original_column").annotate(
            usage_count=Count("id")
        ).order_by("-usage_count")[:20]
        
        context["common_mappings"] = common_mappings
        return context


# AJAX Function-based views for better compatibility

def ajax_chat_query(request: HttpRequest) -> JsonResponse:
    """
    Handle analytics queries via AJAX.
    Function-based view for ChatGPT integration.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method allowed"}, status=405)
    
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    
    query_text = request.POST.get("query", "").strip()
    
    if not query_text:
        return JsonResponse({"error": "Query cannot be empty"}, status=400)
    
    try:
        # Get user's billing records for context
        records = BillingRecord.objects.filter(upload__user=request.user)
        
        if not records.exists():
            return JsonResponse({
                "error": "No billing data available for analysis. Please upload some data first."
            }, status=400)
        
        # Save query to database
        query_obj = AnalyticsQuery.objects.create(
            user=request.user,
            query_text=query_text,
            query_type="CHAT",
            created_at=timezone.now()
        )
        
        # Basic analytics response - aggregate by invoice first
        analytics_insights = []
        
        # Aggregate by invoice
        invoice_aggregates = records.values("invoice_number").annotate(
            invoice_total=Sum("amount")
        )
        
        # Total revenue insight
        total_revenue = invoice_aggregates.aggregate(total=Sum("invoice_total"))["total"] or 0
        analytics_insights.append(f"Total revenue: ₹{total_revenue:,.2f}")
        
        # Invoice and customer count
        invoice_count = invoice_aggregates.count()
        customer_count = records.values("customer_name").distinct().count()
        analytics_insights.append(f"Total invoices: {invoice_count}")
        analytics_insights.append(f"Total customers: {customer_count}")
        
        # Recent invoices
        recent_count = records.filter(
            created_at__gte=timezone.now() - timedelta(days=30)
        ).values("invoice_number").distinct().count()
        analytics_insights.append(f"New invoices from last 30 days: {recent_count}")
        
        # Generate response based on query
        response_text = f"Based on your billing data analysis:\n\n" + "\n".join(analytics_insights)
        
        if "revenue" in query_text.lower():
            monthly_invoices = records.filter(
                date__gte=timezone.now().date() - timedelta(days=30)
            ).values("invoice_number").annotate(
                invoice_total=Sum("amount")
            ).aggregate(total=Sum("invoice_total"))
            
            monthly_revenue = monthly_invoices["total"] or 0
            response_text += f"\n\nMonthly revenue (last 30 days): ₹{monthly_revenue:,.2f}"
        
        if "customer" in query_text.lower():
            # Use Python aggregation to avoid Django limitation
            from collections import defaultdict
            
            invoice_data = list(records.values("customer_name", "invoice_number").annotate(
                invoice_total=Sum("amount")
            ).values("customer_name", "invoice_total"))
            
            customer_revenue = defaultdict(float)
            for item in invoice_data:
                customer_revenue[item["customer_name"]] += float(item["invoice_total"] or 0)
            
            top_customers = sorted(customer_revenue.items(), key=lambda x: x[1], reverse=True)[:5]
            
            if top_customers:
                response_text += "\n\nTop 5 customers by revenue:\n"
                for i, (customer_name, total) in enumerate(top_customers, 1):
                    response_text += f"{i}. {customer_name}: ₹{total:,.2f}\n"
        
        # Update query with response
        query_obj.response_text = response_text
        query_obj.save()
        
        return JsonResponse({
            "success": True,
            "response": response_text,
            "timestamp": timezone.now().isoformat(),
            "query_id": query_obj.id
        })
        
    except Exception as e:
        return JsonResponse({
            "error": f"Error processing query: {str(e)}"
        }, status=500)


def ajax_upload_status(request: HttpRequest, upload_id: uuid.UUID) -> JsonResponse:
    """
    Get upload status via AJAX.
    Function-based view for real-time upload progress.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    
    try:
        upload = BillingDataUpload.objects.get(
            id=upload_id,
            user=request.user
        )
        
        # Calculate progress percentage
        progress = 0
        if upload.total_rows and upload.total_rows > 0:
            progress = (upload.processed_rows / upload.total_rows) * 100
        
        return JsonResponse({
            "success": True,
            "status": upload.status,
            "processed_rows": upload.processed_rows or 0,
            "total_rows": upload.total_rows or 0,
            "progress": round(progress, 2),
            "error_log": [upload.error_message] if upload.error_message else [],
            "upload_date": upload.upload_date.isoformat(),
            "last_updated": upload.upload_date.isoformat(),
        })
        
    except BillingDataUpload.DoesNotExist:
        return JsonResponse({"error": "Upload not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def ajax_analytics_data(request: HttpRequest) -> JsonResponse:
    """
    Get analytics data for charts via AJAX.
    Function-based view for dashboard charts.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    
    try:
        records = BillingRecord.objects.filter(upload__user=request.user)
        
        if not records.exists():
            return JsonResponse({
                "error": "No data available",
                "charts": {
                    "monthly_revenue": {"labels": [], "data": []},
                    "payment_status": {"labels": [], "data": []},
                    "top_customers": {"labels": [], "data": []},
                }
            })
        
        # Monthly revenue data (last 6 months) - aggregate by invoice first
        monthly_data = []
        monthly_labels = []
        
        for i in range(5, -1, -1):
            month_start = (timezone.now().date().replace(day=1) - timedelta(days=i*30))
            month_end = month_start + timedelta(days=30)
            
            # Aggregate invoices for the month
            monthly_invoices = records.filter(
                date__gte=month_start,
                date__lt=month_end
            ).values("invoice_number").annotate(
                invoice_total=Sum("amount")
            ).aggregate(total=Sum("invoice_total"))
            
            monthly_revenue = monthly_invoices["total"] or 0
            monthly_data.append(float(monthly_revenue))
            monthly_labels.append(month_start.strftime("%b %Y"))
        
        # Payment status distribution - use latest status per invoice
        latest_status_per_invoice = records.values("invoice_number").annotate(
            latest_status=Max("payment_status")
        )
        
        status_data = latest_status_per_invoice.values("latest_status").annotate(
            count=Count("invoice_number")
        ).order_by("latest_status")
        
        status_labels = []
        status_counts = []
        for item in status_data:
            status_labels.append(item["latest_status"] or "Unknown")
            status_counts.append(item["count"])
        
        # Top customers by revenue - use Python aggregation to avoid Django limitation
        from collections import defaultdict
        
        invoice_data = list(records.values("invoice_number").annotate(
            invoice_total=Sum("amount"),
            customer_name=Max("customer_name")
        ).values("customer_name", "invoice_total"))
        
        customer_revenue = defaultdict(float)
        for item in invoice_data:
            customer_revenue[item["customer_name"]] += float(item["invoice_total"] or 0)
        
        top_customers_data = sorted(customer_revenue.items(), key=lambda x: x[1], reverse=True)[:10]
        customer_labels = [item[0] for item in top_customers_data]
        customer_amounts = [item[1] for item in top_customers_data]
        
        # Summary calculations - aggregate by invoice first
        invoice_aggregates = records.values("invoice_number").annotate(
            invoice_total=Sum("amount")
        )
        
        total_revenue = invoice_aggregates.aggregate(total=Sum("invoice_total"))["total"] or 0
        total_invoices = invoice_aggregates.count()
        total_customers = records.values("customer_name").distinct().count()
        avg_invoice = invoice_aggregates.aggregate(avg=Avg("invoice_total"))["avg"] or 0
        
        return JsonResponse({
            "success": True,
            "charts": {
                "monthly_revenue": {
                    "labels": monthly_labels,
                    "data": monthly_data
                },
                "payment_status": {
                    "labels": status_labels,
                    "data": status_counts
                },
                "top_customers": {
                    "labels": customer_labels,
                    "data": customer_amounts
                }
            },
            "summary": {
                "total_revenue": float(total_revenue),
                "total_records": total_invoices,  # Changed to show invoice count
                "total_customers": total_customers,
                "avg_invoice": float(avg_invoice),
            }
        })
        
    except Exception as e:
        return JsonResponse({
            "error": f"Error getting analytics data: {str(e)}"
        }, status=500)


class DebugFileColumnsAPIView(LoginRequiredMixin, View):
    """Debug API view to test file column reading."""
    
    def get(self, request, upload_id):
        """Return debug information about file column reading."""
        try:
            upload = get_object_or_404(
                BillingDataUpload,
                pk=upload_id,
                user=request.user
            )
            
            import pandas as pd
            import os
            
            file_path = upload.file.path
            debug_info = {
                "file_path": file_path,
                "file_exists": os.path.exists(file_path),
                "file_size": upload.file_size,
                "original_filename": upload.original_filename,
                "upload_status": upload.status,
            }
            
            if os.path.exists(file_path):
                try:
                    # Try to read file
                    if file_path.endswith(".csv"):
                        df = pd.read_csv(file_path, nrows=0)
                        debug_info["csv_success"] = True
                    elif file_path.endswith((".xlsx", ".xls")):
                        df = pd.read_excel(file_path, nrows=0)
                        debug_info["excel_success"] = True
                    
                    debug_info["columns"] = list(df.columns)
                    debug_info["column_count"] = len(df.columns)
                    
                except Exception as e:
                    debug_info["error"] = str(e)
                    debug_info["success"] = False
            
            # Get existing mappings
            mappings = MappedField.objects.filter(upload=upload)
            debug_info["existing_mappings"] = [
                {
                    "original_column": m.original_column,
                    "mapped_field": m.mapped_field,
                    "is_required": m.is_required
                }
                for m in mappings
            ]
            
            return JsonResponse(debug_info)
            
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class TestDateParsingView(LoginRequiredMixin, View):
    """Test view to verify date parsing with different formats."""
    
    def get(self, request):
        """Test date parsing functionality."""
        test_dates = [
            ("15/03/2024", "DD/MM/YYYY"),
            ("03/15/2024", "MM/DD/YYYY"),
            ("2024-03-15", "YYYY-MM-DD"),
            ("15-03-2024", "DD-MM-YYYY"),
            ("03-15-2024", "MM-DD-YYYY"),
            ("15.03.2024", "DD.MM.YYYY"),
        ]
        
        results = []
        for date_str, format_type in test_dates:
            try:
                # Create a temporary instance to use the method
                view = ProcessUploadView()
                parsed_date = view._parse_date_with_format(date_str, format_type)
                results.append({
                    "input": date_str,
                    "format": format_type,
                    "parsed": str(parsed_date) if parsed_date else "Failed to parse",
                    "success": parsed_date is not None
                })
            except Exception as e:
                results.append({
                    "input": date_str,
                    "format": format_type,
                    "parsed": f"Error: {str(e)}",
                    "success": False
                })
        
        return JsonResponse({"test_results": results}) 