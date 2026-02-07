from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0004_add_panel_layout'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='last_error',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='project',
            name='status',
            field=models.CharField(default='idle', max_length=50),
        ),
    ]
