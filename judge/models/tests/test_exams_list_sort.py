from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from judge.views.exams import ExamsListView


class ExamsListDateSortTestCase(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _sort_items(self, query, items):
        request = self.factory.get('/exams-list/', query)
        view = ExamsListView()
        view.request = request
        return view._sort_items([dict(item) for item in items])

    def test_sorts_by_exam_date_near_to_far(self):
        items = [
            {'name': 'No date', 'exam_date': ''},
            {'name': '2026-04-10', 'exam_date': '2026-04-10'},
            {'name': '2026-04-06', 'exam_date': '2026-04-06'},
            {'name': '2026-04-07', 'exam_date': '2026-04-07'},
            {'name': '2025-03-01', 'exam_date': '2025-03-01'},
        ]
        self.assertEqual(
            [item['name'] for item in self._sort_items({}, items)],
            ['2026-04-10', '2026-04-07', '2026-04-06', '2025-03-01', 'No date'],
        )


class ExamsListHideCompletedFilterTestCase(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.completed_exam = {'id': 1, 'name': 'Completed Exam', 'exam_date': '2026-04-10', 'total_points': 10}
        self.active_exam = {'id': 2, 'name': 'Active Exam', 'exam_date': '2026-04-09', 'total_points': 10}
        self.user = SimpleNamespace(is_authenticated=True, profile=SimpleNamespace(id=123))

    def _get_context(self, query):
        request = self.factory.get('/exams-list/', query)
        request.user = self.user
        view = ExamsListView()
        view.request = request
        payload = {'items': [dict(self.completed_exam), dict(self.active_exam)], 'summary': {}}
        progress_by_exam = {
            self.completed_exam['id']: SimpleNamespace(earned_points=10, total_points=10, percent=100),
            self.active_exam['id']: SimpleNamespace(earned_points=4, total_points=10, percent=40),
        }
        with patch('judge.views.exams._normalize_payload', return_value=payload), \
             patch.object(ExamsListView, '_progress_by_exam', return_value=progress_by_exam), \
             patch.object(ExamsListView, '_category_choices', return_value=[('', 'Tất cả')]), \
             patch.object(ExamsListView, '_province_choices', return_value=[('', 'Tất cả')]), \
             patch.object(ExamsListView, '_year_choices', return_value=[('', 'Tất cả')]):
            return view.get_context_data()

    def test_hide_completed_filters_out_completed_exams(self):
        context = self._get_context({'hide_completed': '1'})
        self.assertEqual([item['id'] for item in context['items']], [self.active_exam['id']])
        self.assertTrue(context['filters']['hide_completed'])

    def test_without_filter_completed_exams_still_show(self):
        context = self._get_context({})
        self.assertEqual(
            [item['id'] for item in context['items']],
            [self.completed_exam['id'], self.active_exam['id']],
        )
        self.assertFalse(context['filters']['hide_completed'])
