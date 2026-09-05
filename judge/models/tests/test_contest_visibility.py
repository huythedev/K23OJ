from itertools import product

from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from judge.models import Contest, ContestCategory, ContestCategoryGroup
from judge.models.tests.util import create_contest, create_organization, create_user
from judge.views.submission import AllContestSubmissions


class ContestVisibilityRegressionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user(username='visibility_outsider')
        cls.unassigned_group = ContestCategoryGroup.objects.create(name='Unassigned visibility roster')
        cls.unassigned_group.users.add(cls.user.profile)
        cls.category = ContestCategory.objects.create(name='Public folder', slug='public_folder')
        cls.contests = []
        now = timezone.now()
        for visible, private, organization_private in product((False, True), repeat=3):
            contest = create_contest(
                key='visibility_%d%d%d' % (visible, private, organization_private),
                is_visible=visible,
                is_private=private,
                is_organization_private=organization_private,
                description='Confidential contest description',
                show_submission_list=True,
                start_time=now - timezone.timedelta(hours=1),
                end_time=now + timezone.timedelta(hours=1),
            )
            cls.category.contests.add(contest)
            cls.contests.append(contest)
        cls.public = next(c for c in cls.contests if c.is_visible and not c.is_private
                          and not c.is_organization_private)

    def test_public_folder_respects_every_contest_visibility_combination(self):
        for user in (AnonymousUser(), self.user):
            self.assertEqual(list(Contest.get_visible_contests(user)), [self.public])
            for contest in self.contests:
                with self.subTest(user=str(user), contest=contest.key):
                    self.assertEqual(contest.is_accessible_by(user), contest == self.public)

    def test_lists_feeds_and_search_do_not_expose_restricted_contests(self):
        now = timezone.now()
        for authenticated in (False, True):
            if authenticated:
                self.client.force_login(self.user)
            urls = [
                self.category.get_absolute_url(),
                reverse('contest_ical'),
                reverse('contest_select2'),
                reverse('contest_calendar', args=[now.year, now.month]),
                '/api/v2/contests',
            ]
            if authenticated:
                urls.append(reverse('contest_list'))
            for url in urls:
                with self.subTest(authenticated=authenticated, url=url):
                    response = self.client.get(url)
                    self.assertContains(response, self.public.name)
                    for contest in self.contests:
                        if contest != self.public:
                            self.assertNotContains(response, contest.name)

    def test_direct_api_and_contest_pages_deny_restricted_content(self):
        for authenticated in (False, True):
            if authenticated:
                self.client.force_login(self.user)
            for contest in self.contests:
                if contest == self.public:
                    continue
                with self.subTest(authenticated=authenticated, contest=contest.key):
                    self.assertEqual(self.client.get('/api/v2/contest/' + contest.key).status_code, 404)
                    response = self.client.get(contest.get_absolute_url())
                    self.assertNotIn(contest.description.encode(), response.content)

    def test_private_submission_routes_require_contest_access(self):
        self.client.force_login(self.user)
        for contest in self.contests:
            if contest == self.public:
                continue
            for name, args in (
                ('contest_all_submissions', [contest.key]),
                ('contest_all_user_submissions', [contest.key, self.user.username]),
            ):
                with self.subTest(contest=contest.key, route=name):
                    self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 404)

    def test_submission_access_still_allows_explicit_contest_members(self):
        organization = create_organization(name='visibility_org')
        self.user.profile.organizations.add(organization)
        request = RequestFactory().get('/')
        request.user = self.user
        request.profile = self.user.profile
        for contest in self.contests:
            if not contest.is_visible:
                continue
            contest.private_contestants.add(self.user.profile)
            contest.organizations.add(organization)
            view = AllContestSubmissions()
            view._contest = contest
            with self.subTest(contest=contest.key):
                view.access_check(request)
                contest.private_contestants.clear()
                contest.organizations.clear()
                if contest != self.public:
                    with self.assertRaises(Http404):
                        view.access_check(request)

    def test_calendar_range_does_not_reveal_unpublished_dates(self):
        now = timezone.now()
        self.public.start_time = now - timezone.timedelta(days=1)
        self.public.end_time = now + timezone.timedelta(days=1)
        self.public.save()
        hidden = self.contests[0]
        hidden.start_time = now.replace(year=now.year + 10)
        hidden.end_time = hidden.start_time + timezone.timedelta(days=1)
        hidden.save()
        response = self.client.get(reverse('contest_calendar', args=[hidden.start_time.year, hidden.start_time.month]))
        self.assertEqual(response.status_code, 404)
