from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0014_remove_daily_rotation_models'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserDailyCheckin',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('checkin_date', models.DateField()),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='daily_checkins', to='api.eduquestuser')),
            ],
            options={
                'ordering': ['-checkin_date'],
                'unique_together': {('student', 'checkin_date')},
            },
        ),
        migrations.AddField(
            model_name='eduquestuser',
            name='daily_goals',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
