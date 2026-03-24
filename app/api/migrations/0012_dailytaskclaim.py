from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0011_eduquestuser_daily_checkin_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailyTaskClaim',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('claim_date', models.DateField()),
                ('task_code', models.CharField(max_length=50)),
                ('points_awarded', models.PositiveIntegerField(default=0)),
                ('claimed_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='daily_task_claims', to='api.eduquestuser')),
            ],
            options={
                'unique_together': {('user', 'claim_date', 'task_code')},
            },
        ),
    ]
