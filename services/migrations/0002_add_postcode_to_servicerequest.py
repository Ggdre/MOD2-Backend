# Generated manually for adding postcode to ServiceRequest

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicerequest',
            name='postcode',
            field=models.CharField(blank=True, help_text='Postal code extracted from address', max_length=20),
        ),
    ]

