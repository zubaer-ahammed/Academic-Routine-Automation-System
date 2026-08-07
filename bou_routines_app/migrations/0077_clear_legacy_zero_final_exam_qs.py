# FinalExamMark Q fields used to default to 0. Untouched examiner columns (esp. teacher2/3)
# still show as "0" in the UI. Clear all-zero septets to NULL so empty looks blank.
# Intentional single-question 0 marks are kept (only when not all seven are zero).

from django.db import migrations


def _is_exact_zero(val):
    if val is None:
        return False
    try:
        return float(val) == 0.0
    except (TypeError, ValueError):
        return False


def clear_legacy_zero_final_exam_qs(apps, schema_editor):
    FinalExamMark = apps.get_model('bou_routines_app', 'FinalExamMark')

    for fm in FinalExamMark.objects.iterator(chunk_size=500):
        updates = {}
        for n in (1, 2, 3):
            fields = [f'teacher{n}_q{i}' for i in range(1, 8)]
            vals = [getattr(fm, f) for f in fields]
            if vals and all(_is_exact_zero(v) for v in vals):
                for f in fields:
                    updates[f] = None
                updates[f'teacher{n}_total'] = 0

        # Lab per-examiner: both PS and viva exactly 0 → treat as unset
        for prefix in ('teacher1', 'teacher2'):
            ps_f = f'{prefix}_lab_final_exam_mark'
            viv_f = f'{prefix}_lab_viva_mark'
            ps = getattr(fm, ps_f, None)
            viv = getattr(fm, viv_f, None)
            if _is_exact_zero(ps) and (viv is None or _is_exact_zero(viv)):
                if ps is not None:
                    updates[ps_f] = None
                if viv is not None and _is_exact_zero(viv):
                    updates[viv_f] = None

        if updates:
            FinalExamMark.objects.filter(pk=fm.pk).update(**updates)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0076_lab_examination_members'),
    ]

    operations = [
        migrations.RunPython(clear_legacy_zero_final_exam_qs, noop_reverse),
    ]
