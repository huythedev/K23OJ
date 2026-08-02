from datetime import date

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import TemplateView

from judge.models import ExamCategory, ExamProvince, ExamTag, ExamTagProblemPoint, ExamUserProgress, Problem, Submission
from judge.tasks import rebuild_exams_snapshots
from judge.utils.celery import task_status_url_by_id
from judge.utils.diggpaginator import DiggPaginator, InvalidPage
from judge.utils.exams import build_exam_snapshots, load_exam_detail_snapshot, load_exam_index_snapshot
from judge.utils.views import TitleMixin, paginate_query_context


STATUS_LABELS = {
    'complete': _('Đã có'),
    'updating': _('Đang cập nhật'),
    'missing': _('Không sở hữu'),
}


def _format_points(value):
    return f'{float(value or 0):.3f}'.rstrip('0').rstrip('.') or '0'


def _normalize_percent(value):
    return max(0.0, min(100.0, round(float(value or 0), 1)))


def _parse_exam_date(raw_value):
    if isinstance(raw_value, date):
        return raw_value
    if isinstance(raw_value, str):
        try:
            return date.fromisoformat(raw_value.strip())
        except ValueError:
            pass
    return None


def _format_exam_date(raw_value):
    parsed = _parse_exam_date(raw_value)
    return parsed.strftime('%d/%m/%Y') if parsed else '-'


def _compute_progress_points(case_points, case_total, exam_problem_points, is_partial):
    earned_points = round((case_points / case_total) * exam_problem_points if case_total > 0 else 0, 3)
    earned_points = min(earned_points, exam_problem_points)
    return earned_points if is_partial or earned_points == exam_problem_points else 0


def _normalize_payload():
    payload = load_exam_index_snapshot()
    if payload is None:
        payload = build_exam_snapshots()
    elif payload.get('items'):
        first_item = payload['items'][0]
        if 'total_points' not in first_item or 'exam_date' not in first_item:
            payload = build_exam_snapshots()
    for item in payload.get('items', []):
        item['status_label'] = str(STATUS_LABELS.get(item['status'], item['status']))
    return payload


def _load_detail_payload(slug):
    data = load_exam_detail_snapshot(slug)
    if data is None:
        build_exam_snapshots()
        data = load_exam_detail_snapshot(slug)
    return data


class ExamTagManageForm(forms.ModelForm):
    province = forms.ChoiceField(required=False, label=_('province'))

    class Meta:
        model = ExamTag
        fields = (
            'slug', 'name', 'expected_count', 'year', 'exam_date', 'category',
            'exam_type', 'province', 'status_note', 'is_public', 'sort_order',
        )
        widgets = {
            'exam_date': forms.DateInput(attrs={'type': 'date'}),
            'status_note': forms.TextInput(attrs={'placeholder': _('Optional note for internal use')}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = ExamCategory.objects.order_by('sort_order', 'name')
        province_names = list(ExamProvince.objects.filter(is_active=True).values_list('name', flat=True))
        current_province = (getattr(self.instance, 'province', '') or '').strip()
        if current_province and current_province not in province_names:
            province_names.append(current_province)
        self.fields['province'].choices = [('', _('---------'))] + [(name, name) for name in province_names]


class ExamCollectionItemForm(forms.Form):
    name = forms.CharField(max_length=64, label=_('name'))
    sort_order = forms.IntegerField(initial=0, required=False, label=_('sort order'))
    is_active = forms.BooleanField(initial=True, required=False, label=_('active'))


class ExamProblemCreateForm(forms.Form):
    problem_code = forms.CharField(max_length=64, label=_('problem code'))
    points = forms.FloatField(min_value=0, initial=0, label=_('exam points'))
    sort_order = forms.IntegerField(initial=0, required=False, label=_('sort order'))

    def clean_problem_code(self):
        code = self.cleaned_data['problem_code'].strip()
        try:
            self.problem = Problem.objects.get(code=code)
        except Problem.DoesNotExist:
            raise forms.ValidationError(_('No problem has this code.'))
        return code


class ExamProblemPointForm(forms.Form):
    points = forms.FloatField(min_value=0, label=_('exam points'))
    sort_order = forms.IntegerField(label=_('sort order'))


class ExamManagementPermissionMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)


class ExamsManageListView(ExamManagementPermissionMixin, TitleMixin, TemplateView):
    template_name = 'exams/manage_list.html'
    title = _('Manage exams')

    def _context_forms(self, **kwargs):
        return {
            'exam_form': kwargs.get('exam_form', ExamTagManageForm()),
            'category_form': kwargs.get('category_form', ExamCollectionItemForm()),
            'province_form': kwargs.get('province_form', ExamCollectionItemForm()),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self._context_forms(**kwargs))
        context['exams'] = ExamTag.objects.select_related('category').order_by('-exam_date', '-year', 'sort_order', 'name')
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        if action == 'create_exam':
            exam_form = ExamTagManageForm(request.POST)
            if exam_form.is_valid():
                exam = exam_form.save()
                messages.success(request, _('Exam created. Add its problems and points below.'))
                return self._redirect_to_exam(exam)
            return self.render_to_response(self.get_context_data(exam_form=exam_form))

        if action in {'create_category', 'create_province'}:
            item_form = ExamCollectionItemForm(request.POST)
            if item_form.is_valid():
                model = ExamCategory if action == 'create_category' else ExamProvince
                item, created = model.objects.get_or_create(
                    name=item_form.cleaned_data['name'].strip(),
                    defaults={
                        'sort_order': item_form.cleaned_data['sort_order'] or 0,
                        'is_active': item_form.cleaned_data['is_active'],
                    },
                )
                if created:
                    messages.success(request, _('%(name)s added.') % {'name': item.name})
                else:
                    messages.info(request, _('%(name)s already exists.') % {'name': item.name})
                return self._redirect_to_list()
            context_key = 'category_form' if action == 'create_category' else 'province_form'
            return self.render_to_response(self.get_context_data(**{context_key: item_form}))

        raise PermissionDenied()

    @staticmethod
    def _redirect_to_list():
        from django.shortcuts import redirect
        return redirect('exams_manage')

    @staticmethod
    def _redirect_to_exam(exam):
        from django.shortcuts import redirect
        return redirect('exam_manage_detail', slug=exam.slug)


class ExamManageDetailView(ExamManagementPermissionMixin, TitleMixin, TemplateView):
    template_name = 'exams/manage_detail.html'

    def get_exam(self):
        try:
            return ExamTag.objects.select_related('category').get(slug=self.kwargs['slug'])
        except ExamTag.DoesNotExist:
            raise Http404()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        exam = kwargs.get('exam') or self.get_exam()
        context.update({
            'title': _('Manage %(name)s') % {'name': exam.name},
            'exam': exam,
            'exam_form': kwargs.get('exam_form', ExamTagManageForm(instance=exam)),
            'problem_form': kwargs.get('problem_form', ExamProblemCreateForm()),
            'problem_points': exam.problem_points.select_related('problem').order_by('sort_order', 'problem__code'),
        })
        return context

    def post(self, request, *args, **kwargs):
        exam = self.get_exam()
        action = request.POST.get('action')

        if action == 'save_exam':
            exam_form = ExamTagManageForm(request.POST, instance=exam)
            if exam_form.is_valid():
                exam = exam_form.save()
                messages.success(request, _('Exam details saved.'))
                return self._redirect_to_exam(exam)
            return self.render_to_response(self.get_context_data(exam=exam, exam_form=exam_form))

        if action == 'add_problem':
            problem_form = ExamProblemCreateForm(request.POST)
            if problem_form.is_valid():
                problem = problem_form.problem
                point, created = ExamTagProblemPoint.objects.get_or_create(
                    exam_tag=exam,
                    problem=problem,
                    defaults={
                        'points': problem_form.cleaned_data['points'],
                        'sort_order': problem_form.cleaned_data['sort_order'] or 0,
                    },
                )
                if created:
                    messages.success(request, _('%(code)s added to this exam.') % {'code': problem.code})
                else:
                    messages.info(request, _('%(code)s is already attached to this exam.') % {'code': problem.code})
                return self._redirect_to_exam(exam)
            return self.render_to_response(self.get_context_data(exam=exam, problem_form=problem_form))

        if action in {'update_problem', 'remove_problem'}:
            try:
                point = exam.problem_points.get(pk=request.POST.get('point_id'))
            except (ExamTagProblemPoint.DoesNotExist, ValueError, TypeError):
                raise Http404()
            if action == 'remove_problem':
                code = point.problem.code
                point.delete()
                messages.success(request, _('%(code)s removed from this exam.') % {'code': code})
                return self._redirect_to_exam(exam)

            point_form = ExamProblemPointForm(request.POST)
            if point_form.is_valid():
                point.points = point_form.cleaned_data['points']
                point.sort_order = point_form.cleaned_data['sort_order']
                point.save(update_fields=('points', 'sort_order'))
                messages.success(request, _('Problem points saved.'))
                return self._redirect_to_exam(exam)
            messages.error(request, _('Problem points were not saved.'))
            return self._redirect_to_exam(exam)

        if action == 'delete_exam':
            exam.delete()
            messages.success(request, _('Exam deleted.'))
            return self._redirect_to_list()

        if action == 'rebuild':
            result = rebuild_exams_snapshots.delay()
            messages.success(request, _('Public exam list rebuild queued (task %(task_id)s).') % {'task_id': result.id})
            return self._redirect_to_exam(exam)

        raise PermissionDenied()

    @staticmethod
    def _redirect_to_list():
        from django.shortcuts import redirect
        return redirect('exams_manage')

    @staticmethod
    def _redirect_to_exam(exam):
        from django.shortcuts import redirect
        return redirect('exam_manage_detail', slug=exam.slug)


class ExamsListView(TitleMixin, TemplateView):
    template_name = 'exams/list.html'
    title = _('Thư viện đề thi')
    paginate_by = 25

    def _hide_completed_selected(self):
        return self.request.GET.get('hide_completed', '').strip().lower() in {'1', 'true', 'on', 'yes'}

    def _selected_category(self):
        return self.request.GET.get('exam_category', '').strip() or self.request.GET.get('exam_type', '').strip()

    def _category_choices(self, selected_value):
        categories = list(
            ExamCategory.objects.filter(is_active=True).order_by('sort_order', 'name').values_list('name', flat=True),
        )
        if selected_value and selected_value not in categories:
            categories.append(selected_value)
        return [('', str(_('Tất cả')))] + [(value, value) for value in categories]

    def _province_choices(self, selected_value):
        provinces = list(
            ExamProvince.objects.filter(is_active=True).order_by('sort_order', 'name').values_list('name', flat=True),
        )
        if selected_value and selected_value not in provinces:
            provinces.append(selected_value)
        return [('', str(_('Tất cả')))] + [(value, value) for value in provinces]

    def _year_choices(self, items, selected_value):
        years = sorted({int(item['year']) for item in items if item.get('year') is not None}, reverse=True)
        choices = [('', str(_('Tất cả')))] + [(str(year), str(year)) for year in years]
        if selected_value and selected_value not in {value for value, _ in choices}:
            choices.append((selected_value, selected_value))
        return choices

    def _filter_items(self, items):
        keyword = self.request.GET.get('keyword', '').strip().lower()
        category = self._selected_category().lower()
        province = self.request.GET.get('province', '').strip()
        year = self.request.GET.get('year', '').strip()

        def matched(item):
            if keyword:
                haystack = ' '.join(
                    item.get(field, '') for field in ('name', 'category', 'province', 'exam_type', 'status_note')
                ).lower()
                if keyword not in haystack:
                    return False
            return (
                (not category or category == (item.get('category', '') or '').lower()) and
                (not province or province == (item.get('province', '') or '')) and
                (not year or year == str(item.get('year') or ''))
            )

        return [item for item in items if matched(item)]

    @staticmethod
    def _sort_items(items):
        def date_sort_key(item):
            parsed_date = _parse_exam_date(item.get('exam_date'))
            return (1, 0, item.get('name', '')) if parsed_date is None else (0, -parsed_date.toordinal(), item.get('name', ''))

        return sorted(items, key=date_sort_key)

    def _progress_by_exam(self, items):
        if not self.request.user.is_authenticated:
            return {}
        exam_ids = [item['id'] for item in items if item.get('id')]
        if not exam_ids:
            return {}
        progress_rows = ExamUserProgress.objects.filter(user_id=self.request.user.profile.id, exam_tag_id__in=exam_ids)
        return {row.exam_tag_id: row for row in progress_rows}

    @staticmethod
    def _is_completed_progress(progress):
        if progress is None:
            return False
        if _normalize_percent(progress.percent) >= 100:
            return True
        return float(progress.total_points or 0) > 0 and float(progress.earned_points or 0) >= float(progress.total_points)

    def _build_user_progress(self, item, progress):
        if not self.request.user.is_authenticated:
            return None
        total_points = float(item.get('total_points') or 0)
        earned_points = float(progress.earned_points or 0) if progress else 0.0
        total_for_display = float(progress.total_points or total_points) if progress else total_points
        if total_for_display <= 0:
            total_for_display = total_points
        percent = _normalize_percent(progress.percent) if progress else 0.0
        text = (
            f'{_format_points(earned_points)}/{_format_points(total_for_display)} · {percent:.1f}%'
            if total_for_display > 0 else f'{_format_points(earned_points)} · 0.0%'
        )
        return {
            'earned_points': earned_points,
            'total_points': total_for_display,
            'percent': percent,
            'percent_css': f'{percent:.1f}',
            'text': text,
        }

    @staticmethod
    def _decorate_item(item):
        exam_kind = item.get('category') or item.get('exam_type') or ''
        meta_parts = [str(item['year'])] if item.get('year') else []
        meta_parts += [value for value in (exam_kind, item.get('province')) if value]
        item['meta_line'] = ' · '.join(meta_parts)
        item['exam_date_display'] = _format_exam_date(item.get('exam_date'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payload = _normalize_payload()
        items = payload.get('items', [])
        filtered_items = [dict(item) for item in self._sort_items(self._filter_items(items))]
        progress_by_exam = self._progress_by_exam(filtered_items)
        if self._hide_completed_selected():
            filtered_items = [
                item for item in filtered_items if not self._is_completed_progress(progress_by_exam.get(item.get('id')))
            ]
        filtered_count = len(filtered_items)

        paginator = DiggPaginator(filtered_items, self.paginate_by, body=6, padding=2)
        try:
            page_obj = paginator.page(self.request.GET.get('page', 1), softlimit=True)
        except InvalidPage:
            page_obj = paginator.page(1, softlimit=True)
        page_items = list(page_obj.object_list)
        for item in page_items:
            self._decorate_item(item)
            item['user_progress'] = self._build_user_progress(item, progress_by_exam.get(item.get('id')))

        selected_category = self._selected_category()
        selected_province = self.request.GET.get('province', '').strip()
        selected_year = self.request.GET.get('year', '').strip()
        context.update({
            'summary': payload.get('summary', {}),
            'items': page_items,
            'page_obj': page_obj,
            'paginator': paginator,
            'total_pages': paginator.num_pages,
            'current_page': page_obj.number,
            'filtered_count': filtered_count,
            'category_choices': self._category_choices(selected_category),
            'province_choices': self._province_choices(selected_province),
            'year_choices': self._year_choices(items, selected_year),
            'filters': {
                'keyword': self.request.GET.get('keyword', '').strip(),
                'exam_category': selected_category,
                'province': selected_province,
                'year': selected_year,
                'hide_completed': self._hide_completed_selected(),
            },
            'generated_at': payload.get('generated_at'),
        })
        context.update(paginate_query_context(self.request))
        return context


class ExamDetailView(TitleMixin, TemplateView):
    template_name = 'exams/detail.html'

    def _hydrate_problem_progress(self, data):
        problems = data.get('problems') or []
        if not self.request.user.is_authenticated:
            for problem in problems:
                problem['user_progress'] = None
            return
        problem_rows = list(
            Problem.objects.filter(code__in=[p.get('code') for p in problems if p.get('code')]).values_list('id', 'code', 'partial'),
        )
        meta_by_code = {code: {'id': problem_id, 'partial': bool(partial)} for problem_id, code, partial in problem_rows}
        configs = {
            meta['id']: {'points': float(problem.get('exam_points') or 0), 'partial': meta['partial']}
            for problem in problems if (meta := meta_by_code.get(problem.get('code')))
        }
        best_points = {}
        for submission in Submission.objects.filter(
            user_id=self.request.user.profile.id, problem_id__in=configs, status='D',
        ).only('problem_id', 'case_points', 'case_total').iterator():
            config = configs[submission.problem_id]
            best_points[submission.problem_id] = max(
                best_points.get(submission.problem_id, 0),
                _compute_progress_points(submission.case_points, submission.case_total, config['points'], config['partial']),
            )
        for problem in problems:
            exam_points = float(problem.get('exam_points') or 0)
            meta = meta_by_code.get(problem.get('code'))
            earned_points = float(best_points.get(meta['id'], 0)) if meta else 0.0
            percent = _normalize_percent(earned_points / exam_points * 100) if exam_points > 0 else 0.0
            problem['user_progress'] = {
                'earned_points': earned_points,
                'total_points': exam_points,
                'percent': percent,
                'percent_css': f'{percent:.1f}',
                'text': (
                    f'{_format_points(earned_points)}/{_format_points(exam_points)} · {percent:.1f}%'
                    if exam_points > 0 else f'{_format_points(earned_points)} · 0.0%'
                ),
            }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slug = self.kwargs['slug']
        data = _load_detail_payload(slug)
        if data is None:
            raise Http404()
        self._hydrate_problem_progress(data)
        data['status_label'] = str(STATUS_LABELS.get(data['status'], data['status']))
        data['exam_date_display'] = _format_exam_date(data.get('exam_date'))
        can_manage_exams = self.request.user.is_authenticated and self.request.user.is_superuser
        if can_manage_exams and not data.get('id'):
            data['id'] = ExamTag.objects.filter(slug=slug).values_list('id', flat=True).first()
        context.update({
            'exam': data,
            'title': data['name'],
            'can_manage_exams': can_manage_exams,
            'exam_admin_change_url': reverse('admin:judge_examtag_change', args=[data['id']])
            if can_manage_exams and data.get('id') else '',
        })
        return context


class ExamsListApiView(View):
    def get(self, request, *args, **kwargs):
        return JsonResponse(_normalize_payload())


class ExamDetailApiView(View):
    def get(self, request, slug, *args, **kwargs):
        data = _load_detail_payload(slug)
        if data is None:
            raise Http404()
        return JsonResponse(data)


class ExamsRebuildApiView(View):
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return JsonResponse({'ok': False, 'error': 'forbidden'}, status=403)
        queued = cache.add('exams:snapshot:queued', 1, 60)
        if not queued:
            status_id = cache.get('exams:snapshot:last_task')
            return JsonResponse({
                'ok': True,
                'queued': False,
                'task_id': status_id,
                'task_url': task_status_url_by_id(status_id) if status_id else '',
            })
        result = rebuild_exams_snapshots.delay()
        cache.set('exams:snapshot:last_task', result.id, 86400)
        return JsonResponse({
            'ok': True,
            'queued': True,
            'task_id': result.id,
            'task_url': task_status_url_by_id(
                result.id,
                message='Rebuilding exams snapshot...',
                redirect=reverse('exams_list'),
            ),
        })
