# Generated by Django 4.2.20 on 2025-05-17 20:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0004_semestercourse'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='currentroutine',
            name='time_slot',
        ),
        migrations.RemoveField(
            model_name='newroutine',
            name='time_slot',
        ),
        migrations.AddField(
            model_name='currentroutine',
            name='end_time',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='currentroutine',
            name='start_time',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='newroutine',
            name='end_time',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='newroutine',
            name='start_time',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.DeleteModel(
            name='TimeSlot',
        ),
    ]
