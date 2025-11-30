# Generated manually for adding category to WorkerProfile

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('services', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerprofile',
            name='category',
            field=models.ForeignKey(
                blank=True,
                help_text="Worker's primary specialization/category (e.g., Electrician, Plumber, HVAC)",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='workers',
                to='services.servicecategory'
            ),
        ),
    ]

