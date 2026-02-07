from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0003_add_enhanced_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='panel',
            name='layout',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
