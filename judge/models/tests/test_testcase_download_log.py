from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

from django.test import TestCase
from django.urls import reverse

from judge.models import Language, ProblemData, ProblemTestCase, Submission, TestcaseDownloadLog, problem_data_storage
from judge.models.problem import ProblemTestcaseAccess
from judge.models.tests.util import CommonDataMixin, create_problem


class TestcaseDownloadLogTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.problem = create_problem(
            code='testcase_download_log',
            testcase_visibility_mode=ProblemTestcaseAccess.ALWAYS,
            authors=('staff_problem_edit_own',),
        )
        cls.submission = Submission.objects.create(
            user=cls.users['normal'].profile,
            problem=cls.problem,
            language=Language.get_python3(),
        )
        cls.testcase = ProblemTestCase.objects.create(
            dataset=cls.problem,
            order=1,
            input_file='sample.in',
            output_file='sample.out',
            is_pretest=False,
        )

    def test_successful_testcase_download_is_logged(self):
        archive = BytesIO()
        with ZipFile(archive, 'w') as zip_file:
            zip_file.writestr('sample.in', b'1 2')
        archive_content = archive.getvalue()

        def open_file(path):
            if path.endswith('init.yml'):
                return BytesIO(b'archive: data.zip\n')
            return BytesIO(archive_content)

        self.client.force_login(self.users['normal'])
        with patch.object(problem_data_storage, 'exists', return_value=True), \
                patch.object(problem_data_storage, 'open', side_effect=open_file):
            response = self.client.get(reverse(
                'submission_testcase_download', args=(self.submission.id, 1, 'input'),
            ))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'1 2')
        log = TestcaseDownloadLog.objects.get()
        self.assertEqual(log.requester, self.users['normal'].profile)
        self.assertEqual(log.submission, self.submission)
        self.assertEqual(log.problem, self.problem)
        self.assertEqual(log.testcase, self.testcase)
        self.assertEqual(log.testcase_number, 1)
        self.assertEqual(log.download_source, TestcaseDownloadLog.SUBMISSION)
        self.assertEqual(log.file_type, TestcaseDownloadLog.INPUT)
        self.assertEqual(log.ip_address, '127.0.0.1')

    def test_test_data_archive_download_is_logged(self):
        archive_content = b'zip archive contents'
        data = ProblemData.objects.create(problem=self.problem)
        data.zipfile.name = '%s/data.zip' % self.problem.code
        data.save(update_fields=('zipfile',))

        self.client.force_login(self.users['staff_problem_edit_own'])
        with patch.object(problem_data_storage, 'open', return_value=BytesIO(archive_content)):
            response = self.client.get(reverse(
                'problem_data_file', args=(self.problem.code, 'data.zip'),
            ))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, archive_content)
        log = TestcaseDownloadLog.objects.get()
        self.assertEqual(log.requester, self.users['staff_problem_edit_own'].profile)
        self.assertIsNone(log.submission)
        self.assertEqual(log.problem, self.problem)
        self.assertIsNone(log.testcase)
        self.assertIsNone(log.testcase_number)
        self.assertEqual(log.download_source, TestcaseDownloadLog.TEST_DATA)
        self.assertEqual(log.file_type, TestcaseDownloadLog.ARCHIVE)
        self.assertEqual(log.ip_address, '127.0.0.1')
