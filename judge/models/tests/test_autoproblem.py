from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from judge.models import Contest
from judge.models.tests.util import CommonDataMixin, create_problem


class AutoProblemContestCreationTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.problem = create_problem(code='uploaded_problem', authors=('superuser',))

    @patch('judge.views.problem.on_new_contest.delay')
    def test_contest_post_does_not_bind_the_upload_form(self, mock_on_new_contest):
        self.client.force_login(self.users['superuser'])

        response = self.client.post(reverse('problem_autoproblem'), {
            'form_action': 'create_contest',
            'available_problem_codes': self.problem.code,
            'created_contest_keys': '',
            'contests-TOTAL_FORMS': '1',
            'contests-INITIAL_FORMS': '0',
            'contests-MIN_NUM_FORMS': '0',
            'contests-MAX_NUM_FORMS': '1000',
            'contests-0-contest_name': 'Uploaded problems contest',
            'contests-0-contest_id': 'uploaded_problems_contest',
            'contests-0-selected_problems': self.problem.code,
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['form'].is_bound)
        self.assertNotContains(response, 'This field is required.')
        self.assertTrue(Contest.objects.filter(key='uploaded_problems_contest').exists())
        mock_on_new_contest.assert_called_once_with('uploaded_problems_contest')
