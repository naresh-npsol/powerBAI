# Generated by Django 5.1.4 on 2025-05-30 10:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analytics', '0004_update_upload_status_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='billingdataupload',
            name='date_format',
            field=models.CharField(choices=[('DD/MM/YYYY', 'DD/MM/YYYY (Indian Format)'), ('MM/DD/YYYY', 'MM/DD/YYYY (US Format)'), ('YYYY-MM-DD', 'YYYY-MM-DD (ISO Format)'), ('DD-MM-YYYY', 'DD-MM-YYYY (European Format)'), ('MM-DD-YYYY', 'MM-DD-YYYY (US Format with Dash)'), ('DD.MM.YYYY', 'DD.MM.YYYY (German Format)'), ('auto', 'Auto-detect Format')], default='DD/MM/YYYY', help_text='Date format used in the uploaded file', max_length=20),
        ),
    ]
