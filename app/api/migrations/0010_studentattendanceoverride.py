from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_quest_source_document_bonus_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='StudentAttendanceOverride',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_present', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quest', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_overrides', to='api.quest')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_overrides', to='api.eduquestuser')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='attendance_overrides_updated', to='api.eduquestuser')),
            ],
            options={
                'unique_together': {('student', 'quest')},
            },
        ),
    ]
