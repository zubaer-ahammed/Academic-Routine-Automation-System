# Generated manually

from django.db import migrations, models
import django.db.models.deletion


def get_default_centre_id(apps, schema_editor):
    """Get the ID of DRC Centre to use as default"""
    Centre = apps.get_model('bou_routines_app', 'Centre')
    try:
        drc_centre = Centre.objects.get(code='DRC')
        return drc_centre.id
    except Centre.DoesNotExist:
        # If DRC doesn't exist, create it or use first centre
        centre = Centre.objects.first()
        return centre.id if centre else 1


class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0036_assign_default_centre'),
    ]

    operations = [
        # First, alter Teacher centre field to be required
        migrations.AlterField(
            model_name='teacher',
            name='centre',
            field=models.ForeignKey(
                help_text='Centre this teacher belongs to (required - a teacher can teach at one centre only)',
                on_delete=django.db.models.deletion.PROTECT,
                to='bou_routines_app.centre'
            ),
        ),
        # Then, alter Semester centre field to be required
        migrations.AlterField(
            model_name='semester',
            name='centre',
            field=models.ForeignKey(
                help_text='Centre this semester belongs to (required)',
                on_delete=django.db.models.deletion.PROTECT,
                to='bou_routines_app.centre'
            ),
        ),
    ]

