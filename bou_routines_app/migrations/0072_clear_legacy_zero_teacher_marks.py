# Legacy default=0 should display as unset (NULL), matching semester final marks behaviour.

from django.db import migrations


def _is_zero(val):
    if val is None:
        return True
    try:
        return float(val) == 0.0
    except (TypeError, ValueError):
        return False


def _has_positive(val):
    if val is None:
        return False
    try:
        return float(val) > 0.0
    except (TypeError, ValueError):
        return False


def _normalize_group(instance, field_names, updates):
    """All-zero group -> NULL; if any mark > 0, zero cells become NULL (legacy unset)."""
    vals = {f: getattr(instance, f) for f in field_names}
    if not any(not _is_zero(v) for v in vals.values()):
        for f in field_names:
            if vals[f] is not None:
                updates[f] = None
        return
    if any(_has_positive(v) for v in vals.values()):
        for f in field_names:
            if _is_zero(vals[f]) and vals[f] is not None:
                updates[f] = None


def clear_legacy_zero_teacher_marks(apps, schema_editor):
    CAMark = apps.get_model('bou_routines_app', 'CAMark')
    MidtermExamMark = apps.get_model('bou_routines_app', 'MidtermExamMark')

    ca_assignment_fields = (
        'first_assignment_mark',
        'second_assignment_mark',
        'third_assignment_mark',
    )
    ca_lab_assignment_fields = (
        'first_lab_assignment_mark',
        'second_lab_assignment_mark',
        'third_lab_assignment_mark',
    )
    ca_class_test_fields = ('first_class_test_mark', 'second_class_test_mark')
    ca_scalar_fields = (
        'midterm_mark',
        'lab_practical_mark',
        'second_lab_practical_mark',
        'project_supervisor_mark',
        'project_evaluation_mark',
        'project_presentation_mark',
    )
    midterm_q_fields = tuple(f'q{i}' for i in range(1, 7))

    for cam in CAMark.objects.iterator(chunk_size=500):
        updates = {}
        _normalize_group(cam, ca_assignment_fields, updates)
        _normalize_group(cam, ca_lab_assignment_fields, updates)
        _normalize_group(cam, ca_class_test_fields, updates)
        for f in ca_scalar_fields:
            if _is_zero(getattr(cam, f)) and getattr(cam, f) is not None:
                updates[f] = None
        if updates:
            CAMark.objects.filter(pk=cam.pk).update(**updates)

    for mm in MidtermExamMark.objects.iterator(chunk_size=500):
        updates = {}
        _normalize_group(mm, midterm_q_fields, updates)
        if updates:
            MidtermExamMark.objects.filter(pk=mm.pk).update(**updates)

    CAMark.objects.filter(notes='None').update(notes='')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0071_nullable_teacher_marks'),
    ]

    operations = [
        migrations.RunPython(clear_legacy_zero_teacher_marks, noop_reverse),
    ]
