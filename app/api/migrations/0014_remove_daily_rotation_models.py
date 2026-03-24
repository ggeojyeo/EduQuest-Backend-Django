from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0013_userquestattempt_bonus_claimed_at'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='userquestattempt',
            name='bonus_claimed_at',
        ),
        migrations.DeleteModel(
            name='DailyTaskClaim',
        ),
    ]

