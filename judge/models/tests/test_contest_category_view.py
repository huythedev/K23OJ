from django.test import TestCase
from django.urls import reverse
from lxml import html

from judge.models import ContestCategory
from judge.models.tests.util import create_contest


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

    def test_empty_state_replaces_the_root_collection(self):
        ContestCategory.objects.all().delete()
        document = self.get_document(reverse('contest_category_list_create'))
        self.assertFalse(document.xpath('//*[@data-category-id]'))
        self.assertEqual(len(document.xpath('//*[contains(@class, "category-empty-state")]')), 1)
