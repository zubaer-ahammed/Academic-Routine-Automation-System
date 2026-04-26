# One "Experiment / Lab Project" column at 15 marks (5+5+15=25) for new curriculum lab CA.

from django.db import migrations


def forward(apps, schema_editor):
    Curriculum = apps.get_model('bou_routines_app', 'Curriculum')
    for c in Curriculum.objects.exclude(code='OLD'):
        c.lab_ca_practical_weight = 15
        c.lab_ca_practical2_weight = 0
        c.save(update_fields=['lab_ca_practical_weight', 'lab_ca_practical2_weight'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0065_lab_new_curriculum_split'),
    ]

    operations = [
        migrations.RunPython(forward, noop),
    ]
