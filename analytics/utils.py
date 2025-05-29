import csv
import io
import json
import os
import pandas as pd
import openai
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple, Any, Union
from django.conf import settings
from django.utils import timezone
from django.db.models import QuerySet, Sum, Avg, Count, Q
from django.core.exceptions import ValidationError

from .models import BillingDataUpload, MappedField, BillingRecord


class FileProcessor:
    """Utility class for processing uploaded files."""
    
    def __init__(self, upload: BillingDataUpload):
        self.upload = upload
    
    def get_file_headers(self) -> List[str]:
        """Extract column headers from the uploaded file."""
        try:
            file_extension = self.upload.original_filename.split(".")[-1].lower()
            
            if file_extension == "csv":
                return self._get_csv_headers()
            elif file_extension in ["xlsx", "xls"]:
                return self._get_excel_headers()
            else:
                raise ValueError(f"Unsupported file format: {file_extension}")
                
        except Exception as e:
            raise ValidationError(f"Error reading file headers: {str(e)}")
    
    def _get_csv_headers(self) -> List[str]:
        """Get headers from CSV file."""
        self.upload.file.seek(0)
        
        # Try different encodings
        encodings = ["utf-8", "latin-1", "cp1252"]
        for encoding in encodings:
            try:
                self.upload.file.seek(0)
                content = self.upload.file.read().decode(encoding)
                
                # Reset file pointer
                self.upload.file.seek(0)
                
                # Parse CSV
                csv_reader = csv.reader(io.StringIO(content))
                headers = next(csv_reader)
                
                # Clean headers
                return [header.strip() for header in headers if header.strip()]
                
            except UnicodeDecodeError:
                continue
            except Exception as e:
                continue
        
        raise ValidationError("Unable to read CSV file. Please check the file encoding.")
    
    def _get_excel_headers(self) -> List[str]:
        """Get headers from Excel file."""
        try:
            # Read Excel file
            df = pd.read_excel(self.upload.file, nrows=0)  # Only read headers
            return df.columns.tolist()
            
        except Exception as e:
            raise ValidationError(f"Error reading Excel file: {str(e)}")
    
    def get_sample_data(self, num_rows: int = 5) -> List[Dict[str, Any]]:
        """Get sample data from the file for preview."""
        try:
            file_extension = self.upload.original_filename.split(".")[-1].lower()
            
            if file_extension == "csv":
                return self._get_csv_sample(num_rows)
            elif file_extension in ["xlsx", "xls"]:
                return self._get_excel_sample(num_rows)
            else:
                raise ValueError(f"Unsupported file format: {file_extension}")
                
        except Exception as e:
            raise ValidationError(f"Error reading sample data: {str(e)}")
    
    def _get_csv_sample(self, num_rows: int) -> List[Dict[str, Any]]:
        """Get sample data from CSV file."""
        self.upload.file.seek(0)
        
        # Try different encodings
        encodings = ["utf-8", "latin-1", "cp1252"]
        for encoding in encodings:
            try:
                self.upload.file.seek(0)
                content = self.upload.file.read().decode(encoding)
                
                # Parse CSV
                csv_reader = csv.DictReader(io.StringIO(content))
                
                sample_data = []
                for i, row in enumerate(csv_reader):
                    if i >= num_rows:
                        break
                    sample_data.append(dict(row))
                
                return sample_data
                
            except UnicodeDecodeError:
                continue
            except Exception:
                continue
        
        raise ValidationError("Unable to read CSV file sample data.")
    
    def _get_excel_sample(self, num_rows: int) -> List[Dict[str, Any]]:
        """Get sample data from Excel file."""
        try:
            df = pd.read_excel(self.upload.file, nrows=num_rows)
            
            # Convert to list of dictionaries
            return df.to_dict("records")
            
        except Exception as e:
            raise ValidationError(f"Error reading Excel sample data: {str(e)}")
    
    def count_total_rows(self) -> int:
        """Count total rows in the file (excluding header)."""
        try:
            file_extension = self.upload.original_filename.split(".")[-1].lower()
            
            if file_extension == "csv":
                return self._count_csv_rows()
            elif file_extension in ["xlsx", "xls"]:
                return self._count_excel_rows()
            else:
                raise ValueError(f"Unsupported file format: {file_extension}")
                
        except Exception as e:
            raise ValidationError(f"Error counting rows: {str(e)}")
    
    def _count_csv_rows(self) -> int:
        """Count rows in CSV file."""
        self.upload.file.seek(0)
        
        # Try different encodings
        encodings = ["utf-8", "latin-1", "cp1252"]
        for encoding in encodings:
            try:
                self.upload.file.seek(0)
                content = self.upload.file.read().decode(encoding)
                
                # Count rows
                csv_reader = csv.reader(io.StringIO(content))
                next(csv_reader)  # Skip header
                
                row_count = sum(1 for row in csv_reader if any(cell.strip() for cell in row))
                return row_count
                
            except UnicodeDecodeError:
                continue
            except Exception:
                continue
        
        raise ValidationError("Unable to count CSV rows.")
    
    def _count_excel_rows(self) -> int:
        """Count rows in Excel file."""
        try:
            df = pd.read_excel(self.upload.file)
            return len(df)
            
        except Exception as e:
            raise ValidationError(f"Error counting Excel rows: {str(e)}")


class DataProcessor:
    """Utility class for processing and converting file data to BillingRecord objects."""
    
    def __init__(self, upload: BillingDataUpload):
        self.upload = upload
        self.mappings = {
            mapping.original_column: mapping
            for mapping in upload.field_mappings.all()
        }
    
    def process_file(self) -> Tuple[int, List[str]]:
        """Process the entire file and create BillingRecord objects."""
        errors = []
        processed_count = 0
        
        try:
            # Get file data
            file_processor = FileProcessor(self.upload)
            
            # Determine file type and process accordingly
            file_extension = self.upload.original_filename.split(".")[-1].lower()
            
            if file_extension == "csv":
                processed_count, errors = self._process_csv_file()
            elif file_extension in ["xlsx", "xls"]:
                processed_count, errors = self._process_excel_file()
            else:
                errors.append(f"Unsupported file format: {file_extension}")
            
            return processed_count, errors
            
        except Exception as e:
            errors.append(f"Processing error: {str(e)}")
            return processed_count, errors
    
    def _process_csv_file(self) -> Tuple[int, List[str]]:
        """Process CSV file."""
        self.upload.file.seek(0)
        errors = []
        processed_count = 0
        
        # Try different encodings
        encodings = ["utf-8", "latin-1", "cp1252"]
        for encoding in encodings:
            try:
                self.upload.file.seek(0)
                content = self.upload.file.read().decode(encoding)
                
                csv_reader = csv.DictReader(io.StringIO(content))
                
                for row_number, row in enumerate(csv_reader, start=2):  # Start at 2 (header is row 1)
                    try:
                        record = self._create_billing_record(row, row_number)
                        if record:
                            processed_count += 1
                    except Exception as e:
                        errors.append(f"Row {row_number}: {str(e)}")
                
                return processed_count, errors
                
            except UnicodeDecodeError:
                continue
            except Exception as e:
                errors.append(f"CSV processing error: {str(e)}")
                return processed_count, errors
        
        errors.append("Unable to read CSV file with any supported encoding.")
        return processed_count, errors
    
    def _process_excel_file(self) -> Tuple[int, List[str]]:
        """Process Excel file."""
        errors = []
        processed_count = 0
        
        try:
            df = pd.read_excel(self.upload.file)
            
            for index, row in df.iterrows():
                row_number = index + 2  # Excel rows start at 1, header is row 1
                try:
                    # Convert pandas Series to dict
                    row_dict = row.to_dict()
                    record = self._create_billing_record(row_dict, row_number)
                    if record:
                        processed_count += 1
                except Exception as e:
                    errors.append(f"Row {row_number}: {str(e)}")
            
            return processed_count, errors
            
        except Exception as e:
            errors.append(f"Excel processing error: {str(e)}")
            return processed_count, errors
    
    def _create_billing_record(self, row_data: Dict[str, Any], row_number: int) -> Optional[BillingRecord]:
        """Create a BillingRecord from row data."""
        # Initialize record data
        record_data = {
            "upload": self.upload,
            "row_number": row_number,
            "custom_fields": {}
        }
        
        # Process each mapped field
        for original_column, mapping in self.mappings.items():
            if original_column not in row_data:
                continue
            
            raw_value = row_data[original_column]
            
            # Skip empty values for non-required fields
            if pd.isna(raw_value) or raw_value == "":
                if mapping.is_required:
                    raise ValidationError(f"Required field '{original_column}' is empty")
                continue
            
            # Convert and validate value based on mapping
            processed_value = self._process_field_value(raw_value, mapping)
            
            # Map to appropriate field
            if mapping.mapped_field == "custom":
                record_data["custom_fields"][mapping.custom_field_name] = processed_value
            else:
                record_data[mapping.mapped_field] = processed_value
        
        # Validate required fields
        required_fields = ["date", "customer_name", "invoice_number", "amount"]
        for field in required_fields:
            if field not in record_data:
                raise ValidationError(f"Required field '{field}' is missing")
        
        # Create and save the record
        try:
            record = BillingRecord.objects.create(**record_data)
            return record
        except Exception as e:
            raise ValidationError(f"Error creating record: {str(e)}")
    
    def _process_field_value(self, raw_value: Any, mapping: MappedField) -> Any:
        """Process and validate a field value based on its mapping."""
        if pd.isna(raw_value):
            return None
        
        # Convert based on data type
        if mapping.data_type == "string":
            return str(raw_value).strip()
        
        elif mapping.data_type == "number":
            try:
                # Handle different number formats
                if isinstance(raw_value, str):
                    # Remove common currency symbols and separators
                    cleaned_value = raw_value.replace("$", "").replace(",", "").strip()
                    return Decimal(cleaned_value)
                else:
                    return Decimal(str(raw_value))
            except (InvalidOperation, ValueError):
                raise ValidationError(f"Invalid number format: {raw_value}")
        
        elif mapping.data_type == "date":
            try:
                if isinstance(raw_value, str):
                    # Try different date formats
                    date_formats = [
                        "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y",
                        "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"
                    ]
                    
                    for date_format in date_formats:
                        try:
                            return datetime.strptime(raw_value, date_format).date()
                        except ValueError:
                            continue
                    
                    raise ValueError("No matching date format found")
                
                elif isinstance(raw_value, pd.Timestamp):
                    return raw_value.date()
                
                elif hasattr(raw_value, "date"):
                    return raw_value.date()
                
                else:
                    raise ValueError("Unsupported date type")
                    
            except (ValueError, TypeError):
                raise ValidationError(f"Invalid date format: {raw_value}")
        
        elif mapping.data_type == "boolean":
            if isinstance(raw_value, str):
                return raw_value.lower() in ["true", "yes", "1", "y", "on"]
            else:
                return bool(raw_value)
        
        else:
            return str(raw_value).strip()


class AnalyticsCalculator:
    """Utility class for calculating analytics and generating insights."""
    
    def __init__(self, user, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None):
        self.user = user
        self.start_date = start_date
        self.end_date = end_date
        self.queryset = self._get_base_queryset()
    
    def _get_base_queryset(self) -> QuerySet:
        """Get the base queryset for analytics calculations."""
        queryset = BillingRecord.objects.filter(upload__user=self.user)
        
        if self.start_date:
            queryset = queryset.filter(date__gte=self.start_date)
        
        if self.end_date:
            queryset = queryset.filter(date__lte=self.end_date)
        
        return queryset
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """Calculate summary statistics."""
        stats = self.queryset.aggregate(
            total_revenue=Sum("amount"),
            total_records=Count("id"),
            average_invoice=Avg("amount"),
            unique_customers=Count("customer_name", distinct=True)
        )
        
        # Calculate additional metrics
        paid_revenue = self.queryset.filter(
            payment_status=BillingRecord.PaymentStatus.PAID
        ).aggregate(paid_amount=Sum("amount"))["paid_amount"] or Decimal("0")
        
        pending_revenue = self.queryset.filter(
            payment_status=BillingRecord.PaymentStatus.PENDING
        ).aggregate(pending_amount=Sum("amount"))["pending_amount"] or Decimal("0")
        
        overdue_revenue = self.queryset.filter(
            payment_status=BillingRecord.PaymentStatus.OVERDUE
        ).aggregate(overdue_amount=Sum("amount"))["overdue_amount"] or Decimal("0")
        
        return {
            "total_revenue": stats["total_revenue"] or Decimal("0"),
            "total_records": stats["total_records"] or 0,
            "average_invoice": stats["average_invoice"] or Decimal("0"),
            "unique_customers": stats["unique_customers"] or 0,
            "paid_revenue": paid_revenue,
            "pending_revenue": pending_revenue,
            "overdue_revenue": overdue_revenue,
            "collection_rate": (paid_revenue / (stats["total_revenue"] or Decimal("1"))) * 100
        }
    
    def get_revenue_trend(self, period: str = "daily") -> List[Dict[str, Any]]:
        """Get revenue trend data."""
        if period == "daily":
            date_trunc = "date"
        elif period == "weekly":
            date_trunc = "week"
        elif period == "monthly":
            date_trunc = "month"
        else:
            date_trunc = "date"
        
        from django.db.models import DateField
        from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
        
        if period == "daily":
            trunc_func = TruncDate("date")
        elif period == "weekly":
            trunc_func = TruncWeek("date")
        elif period == "monthly":
            trunc_func = TruncMonth("date")
        else:
            trunc_func = TruncDate("date")
        
        trend_data = (
            self.queryset
            .annotate(period=trunc_func)
            .values("period")
            .annotate(
                revenue=Sum("amount"),
                count=Count("id")
            )
            .order_by("period")
        )
        
        return list(trend_data)
    
    def get_top_customers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top customers by revenue."""
        return list(
            self.queryset
            .values("customer_name")
            .annotate(
                total_revenue=Sum("amount"),
                invoice_count=Count("id"),
                average_invoice=Avg("amount")
            )
            .order_by("-total_revenue")[:limit]
        )
    
    def get_payment_status_distribution(self) -> List[Dict[str, Any]]:
        """Get payment status distribution."""
        return list(
            self.queryset
            .values("payment_status")
            .annotate(
                count=Count("id"),
                total_amount=Sum("amount")
            )
            .order_by("-total_amount")
        )


class ChatGPTIntegration:
    """Utility class for integrating with ChatGPT for analytics queries."""
    
    def __init__(self):
        self.api_key = getattr(settings, "OPENAI_API_KEY", None)
        if self.api_key:
            openai.api_key = self.api_key
    
    def process_query(self, query: str, context_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a natural language query about billing data."""
        if not self.api_key:
            return {
                "success": False,
                "error": "OpenAI API key not configured"
            }
        
        try:
            # Prepare context for ChatGPT
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(query, context_data)
            
            # Make API call
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=1000,
                temperature=0.7
            )
            
            result = response.choices[0].message.content
            
            return {
                "success": True,
                "response": result,
                "usage": response.usage
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for ChatGPT."""
        return """
        You are a billing data analytics assistant. You help users analyze their billing and invoice data.
        
        You will be provided with summarized billing data (no personal information) and asked questions about it.
        
        Guidelines:
        - Provide clear, actionable insights
        - Use business terminology appropriately
        - Include specific numbers and percentages when relevant
        - Suggest practical recommendations when appropriate
        - Keep responses concise but informative
        - If data is insufficient, mention what additional data would be helpful
        
        The data provided is anonymized and aggregated for privacy.
        """
    
    def _build_user_prompt(self, query: str, context_data: Dict[str, Any]) -> str:
        """Build the user prompt with query and context."""
        # Anonymize and summarize the context data
        anonymized_context = self._anonymize_context(context_data)
        
        prompt = f"""
        Here is the billing data context:
        {json.dumps(anonymized_context, indent=2, default=str)}
        
        User Question: {query}
        
        Please analyze this data and provide insights to answer the user's question.
        """
        
        return prompt
    
    def _anonymize_context(self, context_data: Dict[str, Any]) -> Dict[str, Any]:
        """Anonymize the context data by removing or masking sensitive information."""
        anonymized = {}
        
        # Copy non-sensitive summary statistics
        if "summary_stats" in context_data:
            anonymized["summary_stats"] = context_data["summary_stats"]
        
        # Anonymize customer data
        if "top_customers" in context_data:
            anonymized["top_customers"] = [
                {
                    "customer_id": f"Customer_{i+1}",
                    "total_revenue": customer["total_revenue"],
                    "invoice_count": customer["invoice_count"],
                    "average_invoice": customer["average_invoice"]
                }
                for i, customer in enumerate(context_data["top_customers"])
            ]
        
        # Include trend data (already anonymized)
        if "revenue_trend" in context_data:
            anonymized["revenue_trend"] = context_data["revenue_trend"]
        
        # Include payment status distribution
        if "payment_status" in context_data:
            anonymized["payment_status"] = context_data["payment_status"]
        
        return anonymized 