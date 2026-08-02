from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.forms import ModelForm
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from reversion.admin import VersionAdmin

from judge.models import ExamCategory, ExamProvince, ExamTag, ExamTagProblemPoint
from judge.tasks import rebuild_exams_snapshots
from judge.utils.views import NoBatchDeleteMixin
from judge.widgets import AdminSelect2Widget


class ExamProvinceAdmin(NoBatchDeleteMixin, VersionAdmin):
    list_display = ('name', 'sort_order', 'is_active')
    search_fields = ('name',)
    ordering = ('sort_order', 'name')
    list_filter = ('is_active',)


class ExamCategoryAdmin(NoBatchDeleteMixin, VersionAdmin):
    list_display = ('name', 'sort_order', 'is_active')
    search_fields = ('name',)
    ordering = ('sort_order', 'name')
    list_filter = ('is_active',)


class ExamTagAdminForm(ModelForm):
    class Meta:
        model = ExamTag
        fields = (
            'slug', 'name', 'expected_count', 'year', 'exam_date', 'exam_type',
            'province', 'category', 'status_note', 'is_public', 'sort_order',
        )
        widgets = {
            'year': AdminSelect2Widget(attrs={'style': 'width: 100%;'}),
            'province': AdminSelect2Widget(attrs={'style': 'width: 100%;'}),
            'category': AdminSelect2Widget(attrs={'style': 'width: 100%;'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_year = timezone.now().year
        existing_years = list(ExamTag.objects.exclude(year__isnull=True).values_list('year', flat=True))
        floor_year = min([current_year - 20] + existing_years)
        year_values = list(range(current_year, floor_year - 1, -1))
        if self.instance.year and self.instance.year not in year_values:
            year_values.append(self.instance.year)
            year_values.sort(reverse=True)
        self.fields['year'].widget.choices = [('', '---------')] + [(year, str(year)) for year in year_values]
        province_values = list(ExamProvince.objects.filter(is_active=True).values_list('name', flat=True))
        if self.instance.province and self.instance.province not in province_values:
            province_values.append(self.instance.province)
        self.fields['province'].widget.choices = [('', '---------')] + [
            (name, name)
            for name in province_values
        ]
        category_filter = Q(is_active=True)
        if self.instance.category_id:
            category_filter |= Q(pk=self.instance.category_id)
        category_queryset = ExamCategory.objects.filter(category_filter)
        self.fields['category'].queryset = category_queryset.order_by('sort_order', 'name')


class ExamTagProblemPointInline(admin.TabularInline):
    model = ExamTagProblemPoint
    extra = 0
    autocomplete_fields = ('problem',)
    fields = ('problem', 'points', 'sort_order')
    ordering = ('sort_order', 'problem__code')


class ExamTagAdmin(NoBatchDeleteMixin, VersionAdmin):
    form = ExamTagAdminForm
    inlines = (ExamTagProblemPointInline,)
    fieldsets = (
        (None, {
            'fields': (
                'slug', 'name', 'expected_count', 'year', 'exam_date', 'exam_type',
                'province', 'category', 'status_note', 'is_public', 'sort_order',
            ),
        }),
    )
    list_display = (
        'slug', 'name', 'expected_count', 'year', 'exam_date', 'exam_type',
        'province', 'category', 'is_public', 'sort_order',
    )
    search_fields = ('slug', 'name', 'exam_type', 'province', 'category__name', 'status_note')
    ordering = ('-year', 'sort_order', 'name', 'slug')
    list_filter = ('is_public', 'year', 'exam_date', 'exam_type', 'province', 'category')
    list_select_related = ('category',)
    date_hierarchy = 'exam_date'
    change_list_template = 'admin/judge/examtag/change_list.html'
    change_form_template = 'admin/judge/examtag/change_form.html'

    def get_urls(self):
        return [
            path('rebuild/', self.admin_site.admin_view(self.rebuild_view), name='judge_examtag_rebuild'),
        ] + super().get_urls()

    @method_decorator(require_POST)
    def rebuild_view(self, request):
        if not request.user.is_superuser:
            raise PermissionDenied()
        result = rebuild_exams_snapshots.delay()
        self.message_user(request, _('Exam list rebuild queued (task %(task_id)s).') % {'task_id': result.id})
        return HttpResponseRedirect(reverse('admin:judge_examtag_changelist'))
