from types import SimpleNamespace

from django.test import SimpleTestCase

from bou_routines_app.tabulation_views import (
    _excel_tabulation_header_rows,
    _tabulation_table_col_widths,
    course_percent,
    earned_credits,
    format_course_credits,
    letter_and_grade_point,
)


class TabulationGradeScaleTests(SimpleTestCase):
    def test_ugc_boundaries(self):
        self.assertEqual(letter_and_grade_point(100), ('A+', 4.00))
        self.assertEqual(letter_and_grade_point(80), ('A+', 4.00))
        self.assertEqual(letter_and_grade_point(79.99), ('A', 3.75))
        self.assertEqual(letter_and_grade_point(75), ('A', 3.75))
        self.assertEqual(letter_and_grade_point(70), ('A-', 3.50))
        self.assertEqual(letter_and_grade_point(65), ('B+', 3.25))
        self.assertEqual(letter_and_grade_point(60), ('B', 3.00))
        self.assertEqual(letter_and_grade_point(55), ('B-', 2.75))
        self.assertEqual(letter_and_grade_point(50), ('C+', 2.50))
        self.assertEqual(letter_and_grade_point(45), ('C', 2.25))
        self.assertEqual(letter_and_grade_point(40), ('D', 2.00))
        self.assertEqual(letter_and_grade_point(39.99), ('F', 0.00))
        self.assertEqual(letter_and_grade_point(0), ('F', 0.00))

    def test_pass_is_forty_percent_of_course_total(self):
        percent = course_percent(20, 50)
        self.assertEqual(percent, 40.0)
        self.assertEqual(letter_and_grade_point(percent), ('D', 2.00))
        fail_percent = course_percent(19, 50)
        self.assertEqual(letter_and_grade_point(fail_percent), ('F', 0.00))

    def test_theory_hundred_mark_pass(self):
        self.assertEqual(letter_and_grade_point(course_percent(40, 100)), ('D', 2.00))
        self.assertEqual(letter_and_grade_point(course_percent(39, 100)), ('F', 0.00))

    def test_earned_credits_only_when_passed(self):
        self.assertEqual(earned_credits(3, 2.00), 3.0)
        self.assertEqual(earned_credits(3, 0.00), 0.0)
        self.assertEqual(earned_credits(1.5, 4.00), 1.5)

    def test_format_course_credits(self):
        self.assertEqual(format_course_credits(3), '3.0')
        self.assertEqual(format_course_credits(0.75), '0.75')

    def test_header_matches_sample_five_rows(self):
        payload = {
            'courses': [SimpleNamespace(code='0222-101', credits=3)],
            'course_maxima': [(70, 30, 100)],
        }
        rows, merges = _excel_tabulation_header_rows(payload)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0][0], 'Course Code & Title')
        self.assertEqual(rows[1][0], 'Credit')
        self.assertEqual(rows[2][0], 'Components')
        self.assertEqual(rows[3][0], 'Weightage')
        self.assertEqual(rows[4][:2], ["Student's ID", 'Name'])
        self.assertEqual(rows[0][2], '0222-101')
        self.assertEqual(rows[2][2:6], ['SF', 'CA', 'Total', 'GP'])
        self.assertIn((0, 0, 0, 1), merges)
        self.assertIn((3, 0, 3, 1), merges)
        self.assertIn((0, 2, 0, 5), merges)
        widths = _tabulation_table_col_widths(1, 800)
        self.assertEqual(len(widths), 6)
