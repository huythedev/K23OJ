from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse
from lxml import html

from judge.forms import ContestCategoryForm
from judge.models import Contest, ContestCategory, ContestCategoryGroup
from judge.models.tests.util import create_contest, create_organization, create_user


class ContestCategoryBrowserTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alpha = ContestCategory.objects.create(name='Alpha', slug='alpha')
        cls.zeta = ContestCategory.objects.create(name='Zeta', slug='zeta')
        cls.graphs = ContestCategory.objects.create(
            name='Graphs',
            slug='alpha/graphs',
            parent=cls.alpha,
        )
        cls.graphs.contests.add(create_contest(key='category_browser'))

        cls.organization_a = create_organization(name='category organization a', slug='category_org_a')
        cls.organization_b = create_organization(name='category organization b', slug='category_org_b')
        cls.member_a = create_user(username='category_member_a')
        cls.member_b = create_user(username='category_member_b')
        cls.member_a.profile.organizations.add(cls.organization_a)
        cls.member_b.profile.organizations.add(cls.organization_b)

        cls.organization_category = ContestCategory.objects.create(
            name='Organization B category',
            slug='organization_b_category',
        )
        cls.organization_category.organizations.add(cls.organization_b)
        cls.organization_contest = create_contest(
            key='organization_a_contest',
            is_visible=True,
            is_organization_private=True,
            organizations=('category organization a',),
        )
        cls.organization_category.contests.add(cls.organization_contest)

        cls.private_category = ContestCategory.objects.create(
            name='Private category',
            slug='private_category',
            is_public=False,
        )

    def get_document(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return html.fromstring(response.content)

    def test_root_browser_shows_only_root_folders(self):
        document = self.get_document(reverse('contest_category_list_create'))
        browser = document.get_element_by_id('contest-category-browser')
        self.assertEqual(browser.get('data-category-view'), 'grid')

        buttons = browser.xpath('.//button[@data-category-view-option]')
        self.assertEqual(
            [(button.get('data-category-view-option'), button.get('aria-pressed')) for button in buttons],
            [('grid', 'true'), ('list', 'false')],
        )
        self.assertTrue(all(button.get('type') == 'button' for button in buttons))
        self.assertTrue(all(button.get('aria-controls') == 'contest-category-items' for button in buttons))

        items = browser.xpath('.//*[@data-category-id]')
        self.assertEqual([int(item.get('data-category-id')) for item in items], [self.alpha.id, self.zeta.id])
        self.assertEqual([item.get('style') for item in items], ['--category-depth: 0;', '--category-depth: 0;'])
        self.assertEqual(
            items[0].xpath('.//a[contains(@class, "category-item-link")]/@href'),
            [reverse('contest_category_detail', args=[self.alpha.slug])],
        )

    def test_opening_a_folder_shows_its_direct_subcategories(self):
        document = self.get_document(reverse('contest_category_detail', args=[self.alpha.slug]))
        items = document.xpath('//*[@id="contest-category-browser"]//*[@data-category-id]')
        self.assertEqual([int(item.get('data-category-id')) for item in items], [self.graphs.id])
        self.assertEqual(
            items[0].xpath('.//a[contains(@class, "category-item-link")]/@href'),
            [reverse('contest_category_detail', args=[self.graphs.slug])],
        )
        self.assertEqual(
            items[0].xpath(
                'normalize-space(.//*[contains(@class, "category-contest-cell")]/span[last()])'
            ),
            '1',
        )
        self.assertTrue(document.xpath('//*[@class="category-breadcrumbs"]'))

        nested_document = self.get_document(reverse('contest_category_detail', args=[self.graphs.slug]))
        self.assertEqual(
            nested_document.xpath('//*[@class="category-breadcrumbs"]//a/@href'),
            [
                reverse('contest_category_list_create'),
                reverse('contest_category_detail', args=[self.alpha.slug]),
            ],
        )

    def test_anonymous_users_can_browse_root_and_subcategory_folders(self):
        root = self.client.get(reverse('contest_category_list_create'))
        detail = self.client.get(reverse('contest_category_detail', args=[self.alpha.slug]))
        self.assertEqual(root.status_code, 200)
        self.assertEqual(detail.status_code, 200)

    def test_category_and_contest_organization_access_is_additive(self):
        category_url = reverse('contest_category_detail', args=[self.organization_category.slug])

        self.client.force_login(self.member_a)
        member_a_response = self.client.get(category_url)
        self.assertEqual(member_a_response.status_code, 200)
        self.assertContains(member_a_response, self.organization_contest.name)

        self.client.force_login(self.member_b)
        member_b_response = self.client.get(category_url)
        self.assertEqual(member_b_response.status_code, 200)
        self.assertContains(member_b_response, self.organization_contest.name)
        self.assertContains(
            self.client.get(self.organization_contest.get_absolute_url()), self.organization_contest.name,
        )

        self.client.logout()
        self.assertEqual(self.client.get(category_url).status_code, 404)

    def test_private_categories_are_not_visible_without_an_access_grant(self):
        private_url = reverse('contest_category_detail', args=[self.private_category.slug])
        self.assertEqual(self.client.get(private_url).status_code, 404)
        self.client.force_login(self.member_a)
        self.assertEqual(self.client.get(private_url).status_code, 404)

    def test_category_organization_members_can_find_the_folder_from_the_index(self):
        self.client.force_login(self.member_a)
        member_a_categories = set(ContestCategory.get_visible_categories(self.member_a).values_list('pk', flat=True))
        self.assertIn(self.organization_category.pk, member_a_categories)

        self.client.force_login(self.member_b)
        member_b_categories = set(ContestCategory.get_visible_categories(self.member_b).values_list('pk', flat=True))
        self.assertIn(self.organization_category.pk, member_b_categories)

    def test_empty_state_replaces_the_root_collection(self):
        ContestCategory.objects.all().delete()
        document = self.get_document(reverse('contest_category_list_create'))
        self.assertFalse(document.xpath('//*[@data-category-id]'))
        self.assertEqual(len(document.xpath('//*[contains(@class, "category-empty-state")]')), 1)


class ContestCategoryAccessTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = create_user(username='group_member')
        cls.org_member = create_user(username='org_member')
        cls.outsider = create_user(username='outsider')
        cls.organization = create_organization(name='category_org')
        cls.org_member.profile.organizations.add(cls.organization)
        cls.group = ContestCategoryGroup.objects.create(name='Private training roster')
        cls.group.users.add(cls.member.profile)
        cls.category = ContestCategory.objects.create(name='Training', slug='training')
        cls.category.groups.add(cls.group)
        cls.contest = create_contest(key='group_contest', is_private=True, is_organization_private=True)
        cls.category.contests.add(cls.contest)

    def assert_access(self, user, allowed, contest=None):
        contest = contest or self.contest
        self.assertEqual(contest.is_accessible_by(user), allowed)
        self.assertEqual(Contest.get_visible_contests(user).filter(pk=contest.pk).exists(), allowed)

    def test_group_grants_category_and_unpublished_private_contest_access(self):
        self.assertTrue(self.category.is_accessible_by(self.member))
        self.assert_access(self.member, True)
        self.assertFalse(self.contest.is_editable_by(self.member))
        for user in (self.outsider, self.org_member, AnonymousUser()):
            with self.subTest(user=str(user)):
                self.assertFalse(self.category.is_accessible_by(user))
                self.assert_access(user, False)

    def test_groups_and_organizations_are_alternative_grants(self):
        self.category.organizations.add(self.organization)
        for user in (self.member, self.org_member):
            with self.subTest(user=user.username):
                self.assertTrue(self.category.is_accessible_by(user))
                self.assert_access(user, True)
        self.assert_access(self.outsider, False)
        self.assert_access(AnonymousUser(), False)

    def test_any_selected_group_grants_access_without_duplicate_contests(self):
        second_group = ContestCategoryGroup.objects.create(name='Second roster')
        second_group.users.add(self.member.profile, self.outsider.profile)
        self.category.groups.add(second_group)
        self.assert_access(self.outsider, True)
        self.assertEqual(Contest.get_visible_contests(self.member).filter(pk=self.contest.pk).count(), 1)

    def test_membership_and_category_assignment_removal_revoke_access(self):
        self.group.users.remove(self.member.profile)
        self.assert_access(self.member, False)
        self.group.users.add(self.member.profile)
        self.assert_access(self.member, True)
        self.category.contests.remove(self.contest)
        self.assert_access(self.member, False)

    def test_public_and_creator_category_grants(self):
        self.category.groups.clear()
        self.assert_access(self.outsider, True)
        self.assert_access(AnonymousUser(), True)
        self.category.is_public = False
        self.category.created_by = self.member.profile
        self.category.save()
        self.assert_access(self.member, True)
        self.assert_access(self.outsider, False)
        self.assert_access(AnonymousUser(), False)

    def test_browsing_via_a_contest_does_not_grant_sibling_contests(self):
        shared = create_contest(key='individually_shared', is_visible=True, is_private=True,
                                private_contestants=(self.outsider.username,))
        self.category.contests.add(shared)
        self.assertTrue(self.category.is_accessible_by(self.outsider))
        self.assert_access(self.outsider, True, shared)
        self.assert_access(self.outsider, False)

    def test_browsing_ancestors_does_not_grant_their_other_contests(self):
        parent = ContestCategory.objects.create(name='Parent', slug='parent', is_public=False)
        sibling = ContestCategory.objects.create(name='Sibling', slug='parent/sibling',
                                                parent=parent, is_public=False)
        parent_contest = create_contest(key='parent_private')
        sibling_contest = create_contest(key='sibling_private')
        parent.contests.add(parent_contest)
        sibling.contests.add(sibling_contest)
        self.category.parent = parent
        self.category.save()
        self.assertTrue(parent.is_accessible_by(self.member))
        self.assertFalse(sibling.is_accessible_by(self.member))
        self.assert_access(self.member, True)
        self.assert_access(self.member, False, parent_contest)
        self.assert_access(self.member, False, sibling_contest)

    def test_contest_organization_access_remains_available(self):
        self.contest.is_visible = True
        self.contest.is_private = False
        self.contest.save()
        self.contest.organizations.add(self.organization)
        self.assert_access(self.org_member, True)
        self.assert_access(self.member, True)

    def test_group_details_are_not_displayed_to_members(self):
        self.client.force_login(self.member)
        for url in (self.category.get_absolute_url(), self.contest.get_absolute_url()):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, self.contest.name)
                self.assertNotContains(response, self.group.name)
        self.assertNotIn('groups', ContestCategoryForm(user=self.member).fields)
        response = self.client.get(reverse('admin:judge_contestcategorygroup_changelist'))
        self.assertEqual(response.status_code, 302)

    def test_category_editor_has_separate_organization_and_group_selectors(self):
        editor = create_user(username='category_editor', user_permissions=('change_contestcategory',))
        self.client.force_login(editor)
        self.category.organizations.add(self.organization)
        url = reverse('contest_category_edit', args=[self.category.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        document = html.fromstring(response.content)
        for field, selected_id in (('organizations', self.organization.pk), ('groups', self.group.pk)):
            with self.subTest(field=field):
                selector = document.xpath('//select[@name="%s"]' % field)
                self.assertEqual(len(selector), 1)
                self.assertIn('multiple', selector[0].attrib)
                self.assertEqual(selector[0].xpath('./option[@selected]/@value'), [str(selected_id)])

        second_group = ContestCategoryGroup.objects.create(name='Replacement roster')
        second_group.users.add(self.outsider.profile)
        response = self.client.post(url, {
            'name': self.category.name,
            'slug': self.category.slug,
            'organizations': [self.organization.pk],
            'groups': [second_group.pk],
            'contests': [self.contest.pk],
        })
        self.assertRedirects(response, self.category.get_absolute_url())
        self.assertEqual(list(self.category.organizations.all()), [self.organization])
        self.assertEqual(list(self.category.groups.all()), [second_group])
        self.assert_access(self.org_member, True)
        self.assert_access(self.outsider, True)
        self.assert_access(self.member, False)

    def test_regular_members_cannot_open_the_category_editor(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('contest_category_edit', args=[self.category.slug]))
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, self.group.name, status_code=403)


class ContestCategoryGroupAdminTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = create_user(username='category_admin', is_staff=True, is_superuser=True)
        cls.member = create_user(username='selected_member')

    def test_admin_can_create_group_and_assign_it_alongside_organization(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('admin:judge_contestcategorygroup_add')), 'name="users"')
        response = self.client.post(reverse('admin:judge_contestcategorygroup_add'), {
            'name': 'Hand-picked users',
            'users': [self.member.profile.pk],
            '_save': 'Save',
        })
        self.assertEqual(response.status_code, 302)
        group = ContestCategoryGroup.objects.get(name='Hand-picked users')
        self.assertEqual(list(group.users.all()), [self.member.profile])

        organization = create_organization(name='admin_category_org')
        contest = create_contest(key='admin_category_contest')
        response = self.client.post(reverse('admin:judge_contestcategory_add'), {
            'name': 'Admin category',
            'slug': 'admin_category',
            'organizations': [organization.pk],
            'groups': [group.pk],
            'contests': [contest.pk],
            '_save': 'Save',
        })
        self.assertEqual(response.status_code, 302)
        category = ContestCategory.objects.get(slug='admin_category')
        self.assertEqual(list(category.groups.all()), [group])
        self.assertEqual(list(category.organizations.all()), [organization])
        self.assertTrue(contest.is_accessible_by(self.member))

        response = self.client.post(reverse('admin:judge_contestcategorygroup_change', args=[group.pk]), {
            'name': group.name,
            'users': [],
            '_save': 'Save',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(contest.is_accessible_by(self.member))

    def test_staff_without_group_permissions_cannot_read_or_change_groups(self):
        staff = create_user(username='unprivileged_staff', is_staff=True)
        self.client.force_login(staff)
        group = ContestCategoryGroup.objects.create(name='Hidden group')
        for url in (
            reverse('admin:judge_contestcategorygroup_changelist'),
            reverse('admin:judge_contestcategorygroup_add'),
            reverse('admin:judge_contestcategorygroup_change', args=[group.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
