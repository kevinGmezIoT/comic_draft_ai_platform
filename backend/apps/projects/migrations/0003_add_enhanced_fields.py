from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0002_panel_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='page',
            name='merged_image_url',
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name='panel',
            name='balloons',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='panel',
            name='scene_description',
            field=models.TextField(blank=True),
        ),
    ]
