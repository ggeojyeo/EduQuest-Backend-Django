from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0010_studentattendanceoverride'),
    ]

    operations = [
        migrations.AddField(
            model_name='eduquestuser',
            name='daily_checkin_last_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='eduquestuser',
            name='daily_checkin_longest_streak',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='eduquestuser',
            name='daily_checkin_streak',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
