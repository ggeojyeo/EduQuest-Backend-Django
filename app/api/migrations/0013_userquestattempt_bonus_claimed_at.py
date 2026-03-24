from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0012_dailytaskclaim'),
    ]

    operations = [
        migrations.AddField(
            model_name='userquestattempt',
            name='bonus_claimed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

