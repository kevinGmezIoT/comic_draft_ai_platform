# Generated manually

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0016_referenceimage'),
    ]

    operations = [
        migrations.AddField(
            model_name='panel',
            name='scenery_refs',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
