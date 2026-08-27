from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from judge.views.contests import ContestDetail, ContestList
from judge.views.problem import ProblemDetail, ProblemList


class PublicPageAuthenticationTest(SimpleTestCase):
    def test_problem_and_contest_pages_require_login(self):
        for view, url, kwargs in (
            (ProblemList, reverse('problem_list'), {}),
            (ProblemDetail, reverse('problem_detail', args=('example',)), {'problem': 'example'}),
            (ContestList, reverse('contest_list'), {}),
            (ContestDetail, reverse('contest_view', args=('example',)), {'contest': 'example'}),
        ):
            with self.subTest(url=url):
                request = RequestFactory().get(url)
                request.user = AnonymousUser()
                response = view.as_view()(request, **kwargs)

                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, '%s?next=%s' % (reverse('auth_login'), url))
