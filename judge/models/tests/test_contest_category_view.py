from django.test import TestCase
from django.urls import reverse
from lxml import html

from judge.models import ContestCategory
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

        cls.organization_a = create_organization(name='category organization a')
        cls.organization_b = create_organization(name='category organization b')
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
        self.assertNotContains(member_b_response, self.organization_contest.name)

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
