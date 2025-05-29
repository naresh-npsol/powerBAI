# PowerBAI Analytics App

A comprehensive Django application for billing data analytics with file upload, processing, and AI-powered insights.

## Features

### 📊 Core Analytics Features
- **File Upload & Processing**: Support for CSV and Excel files
- **Column Mapping**: Flexible mapping of file columns to billing fields
- **Data Validation**: Automatic validation and error reporting
- **Real-time Processing**: Background processing with status updates
- **Analytics Dashboard**: Interactive charts and statistics
- **ChatGPT Integration**: Natural language queries for data insights

### 🔧 Technical Features
- **Django Admin Integration**: Full admin interface for data management
- **Signal-based Processing**: Automatic status updates and progress tracking
- **Type-safe Code**: Comprehensive TypeScript-style type hints
- **Error Handling**: Robust error handling and logging
- **User Isolation**: Multi-tenant data separation

## Installation

### Prerequisites
- Python 3.10+
- Django 4.2+
- PostgreSQL (recommended) or SQLite
- Virtual environment

### Dependencies
The following packages are required (already added to `requirements.txt`):
```
pandas==2.2.0
openpyxl==3.1.2
openai>=1.0.0
```

### Setup Steps

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run Migrations**
   ```bash
   python manage.py makemigrations analytics
   python manage.py migrate
   ```

3. **Create Superuser**
   ```bash
   python manage.py createsuperuser
   ```

4. **Configure Environment Variables**
   ```bash
   # Required for ChatGPT integration
   export OPENAI_API_KEY="your-openai-api-key"
   
   # Other required variables
   export DEBUG=1
   export SECRET_KEY="your-secret-key"
   ```

## Usage

### 1. File Upload
- Navigate to `/analytics/upload/`
- Upload CSV or Excel files with billing data
- Supported formats: `.csv`, `.xlsx`, `.xls`

### 2. Column Mapping
- After upload, map file columns to billing fields
- Required fields: Customer Name, Invoice Number, Amount, Invoice Date
- Optional fields: Payment Status, Due Date, Description, etc.

### 3. Data Processing
- Process mapped files to create billing records
- Monitor progress in real-time
- View processing errors and warnings

### 4. Analytics Dashboard
- View summary statistics
- Interactive charts for revenue trends
- Customer analysis and payment status distribution
- Export data to CSV

### 5. ChatGPT Analytics
- Ask natural language questions about your data
- Examples:
  - "What's my total revenue this month?"
  - "Who are my top 5 customers by revenue?"
  - "Show me overdue invoices"
  - "What's the average invoice amount?"

## Models

### BillingDataUpload
Tracks uploaded files and their processing status.

**Key Fields:**
- `file`: The uploaded file
- `status`: Processing status (PENDING, PROCESSING, PROCESSED, FAILED)
- `total_rows`: Total rows in the file
- `processed_rows`: Successfully processed rows
- `error_message`: Error details if processing failed

### MappedField
Stores column mapping configuration for each upload.

**Key Fields:**
- `upload`: Related upload
- `original_column`: Column name from file
- `mapped_field`: Target billing field
- `is_required`: Whether field is required

### BillingRecord
Processed billing data records.

**Key Fields:**
- `invoice_number`: Invoice identifier
- `customer_name`: Customer name
- `amount`: Invoice amount
- `date`: Invoice date
- `payment_status`: Payment status (PAID, PENDING, OVERDUE, etc.)

### AnalyticsQuery
ChatGPT query history and responses.

**Key Fields:**
- `query_text`: User's natural language query
- `response_text`: ChatGPT's response
- `query_type`: Type of analytics query

## API Endpoints

### Dashboard and Main Views
- `GET /analytics/` - Main dashboard
- `GET /analytics/analytics/` - Analytics dashboard

### File Management
- `POST /analytics/upload/` - Upload new file
- `GET /analytics/uploads/` - List uploads
- `GET /analytics/upload/<uuid:upload_id>/` - Upload details
- `DELETE /analytics/upload/<uuid:upload_id>/delete/` - Delete upload
- `POST /analytics/upload/<uuid:upload_id>/mapping/` - Set column mappings
- `POST /analytics/upload/<uuid:upload_id>/process/` - Process file
- `GET /analytics/uploads/<uuid:pk>/preview/` - Preview upload data

### Billing Records Management
- `GET /analytics/records/` - List billing records
- `GET /analytics/record/<int:record_id>/` - Record details
- `POST /analytics/record/<int:record_id>/edit/` - Edit record
- `POST /analytics/records/bulk-delete/` - Bulk delete records

### ChatGPT Integration
- `GET /analytics/chat/` - Chat interface
- `POST /analytics/chat/query/` - Process query
- `GET /analytics/chat/history/` - Query history

### Export Functionality
- `GET /analytics/export/data/` - Export analytics data (CSV)
- `GET /analytics/export/records/` - Export billing records (CSV)

### API Endpoints (AJAX/JSON)
- `POST /analytics/ajax/chat/` - AJAX chat query
- `GET /analytics/ajax/upload-status/<uuid:upload_id>/` - Upload status
- `GET /analytics/ajax/analytics-data/` - Analytics data
- `GET /analytics/api/validate-data/<uuid:pk>/` - Validate upload data
- `GET /analytics/api/sample-data/<uuid:pk>/` - Get sample data from upload
- `GET /analytics/api/charts/data/` - Chart data (JSON)
- `GET /analytics/api/summary-stats/` - Summary statistics (JSON)
- `GET /analytics/api/revenue-trend/` - Revenue trend data
- `GET /analytics/api/customer-analysis/` - Customer analysis data
- `GET /analytics/api/payment-status/` - Payment status distribution
- `GET /analytics/api/customer-search/` - Search customers
- `GET /analytics/api/invoice-search/` - Search invoices
- `GET /analytics/api/notifications/` - Get notifications

### Settings and Configuration
- `GET /analytics/settings/` - Application settings
- `GET /analytics/field-mapping-templates/` - Field mapping templates

### Help and Documentation
- `GET /analytics/help/` - General help
- `GET /analytics/help/file-formats/` - File format help
- `GET /analytics/help/column-mapping/` - Column mapping help
- `GET /analytics/help/analytics/` - Analytics help

## File Format Requirements

### CSV Files
- UTF-8 encoding preferred
- Comma-separated values
- First row should contain column headers
- Date format: YYYY-MM-DD or MM/DD/YYYY

### Excel Files
- `.xlsx` or `.xls` format
- Data should be in the first worksheet
- First row should contain column headers
- Date columns should be properly formatted

### Required Data Columns
At minimum, your file should contain columns that can be mapped to:
- **Customer Name**: Name of the customer/client
- **Invoice Number**: Unique invoice identifier
- **Amount**: Invoice amount (numeric)
- **Invoice Date**: Date of the invoice

### Optional Data Columns
- Payment Status
- Due Date
- Payment Date
- Description
- Customer Email
- Customer Phone
- Product Name
- Quantity
- Unit Price
- Tax Amount
- Discount

## Configuration

### Settings
Add to your Django settings:

```python
# Analytics app configuration
ANALYTICS_CONFIG = {
    'MAX_FILE_SIZE': 50 * 1024 * 1024,  # 50MB
    'ALLOWED_EXTENSIONS': ['csv', 'xlsx', 'xls'],
    'SAMPLE_ROWS': 5,  # Number of sample rows to show
    'CHUNK_SIZE': 1000,  # Processing chunk size
}

# OpenAI configuration (optional)
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
```

### URL Configuration
Add to your main `urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    # ... other patterns
    path('analytics/', include('analytics.urls')),
]
```

## Admin Interface

Access the Django admin at `/admin/` to:
- View and manage uploads
- Monitor processing status
- Manage billing records
- View analytics queries
- Perform bulk actions on records

### Admin Features
- **Upload Management**: View file details, processing status, and related records
- **Record Management**: Search, filter, and bulk edit billing records
- **Query History**: View ChatGPT query history and responses
- **Mapping Templates**: Manage common column mappings

## Troubleshooting

### Common Issues

1. **File Upload Errors**
   - Check file format (CSV/Excel only)
   - Verify file size limits
   - Ensure proper encoding (UTF-8 for CSV)

2. **Processing Errors**
   - Check column mappings
   - Verify required fields are mapped
   - Review data format (dates, numbers)

3. **ChatGPT Integration Issues**
   - Verify OPENAI_API_KEY is set
   - Check API quota and billing
   - Ensure internet connectivity

4. **Performance Issues**
   - Use database indexing for large datasets
   - Consider chunked processing for large files
   - Monitor memory usage during processing

### Debug Mode
Enable debug logging in settings:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': 'analytics.log',
        },
    },
    'loggers': {
        'analytics': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}
```

## Security Considerations

- **File Validation**: Only allow trusted file types
- **User Isolation**: Data is isolated per user
- **API Security**: All endpoints require authentication
- **Data Anonymization**: Sensitive data is anonymized before sending to ChatGPT
- **Input Validation**: All user inputs are validated and sanitized

## Performance Optimization

- **Database Indexing**: Key fields are indexed for fast queries
- **Chunked Processing**: Large files are processed in chunks
- **Caching**: Consider adding Redis for caching analytics results
- **Background Tasks**: Use Celery for heavy processing tasks

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure code follows PEP 8 standards
5. Submit a pull request

## License

This project is part of the PowerBAI application. See the main project license for details.

## Support

For support and questions:
- Check the troubleshooting section above
- Review the Django admin interface for detailed error logs
- Contact the development team

---

**Version**: 1.0.0  
**Last Updated**: December 2024  
**Django Version**: 4.2+  
**Python Version**: 3.10+ 