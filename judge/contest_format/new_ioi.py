from collections import defaultdict

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext as _, gettext_lazy

from judge.contest_format.legacy_ioi import LegacyIOIContestFormat
from judge.contest_format.registry import register_contest_format
from judge.utils.new_ioi import get_hidden_batches_for_problem, should_mask_live_hidden


@register_contest_format('new_ioi')
class NewIOIContestFormat(LegacyIOIContestFormat):
    name = gettext_lazy('New IOI')
    config_defaults = {'cumtime': False, 'show_test_details': 'visible_only', 'reveal_after_end': True}

    @classmethod
    def validate(cls, config):
        if config is None:
            return

        if not isinstance(config, dict):
            raise ValidationError('New IOI contest expects no config or dict as config')

        allowed = set(cls.config_defaults.keys())
        for key in config.keys():
            if key not in allowed:
                raise ValidationError('unknown config key "%s"' % key)

        if 'cumtime' in config and not isinstance(config['cumtime'], bool):
            raise ValidationError('invalid type for config key "cumtime"')
        if 'reveal_after_end' in config and not isinstance(config['reveal_after_end'], bool):
            raise ValidationError('invalid type for config key "reveal_after_end"')
        if 'show_test_details' in config and config['show_test_details'] not in ('visible_only', 'all'):
            raise ValidationError('invalid value for config key "show_test_details"')

    def __init__(self, contest, config):
        self.config = self.config_defaults.copy()
        self.config.update(config or {})
        self.contest = contest

    def update_participation(self, participation):
        now = timezone.now()
        live_masking = should_mask_live_hidden(self.contest, now=now)

        total_effective = 0.0
        total_admin = 0.0
        cumtime_effective = 0
        cumtime_admin = 0

        per_problem = {}
        hidden_batches_cache = {}

        submissions = (
            participation.submissions.select_related('problem__problem', 'submission')
            .prefetch_related('submission__test_cases')
            .order_by('submission__date', 'submission_id')
        )

        for contest_submission in submissions:
            contest_problem_id = contest_submission.problem_id
            key = str(contest_problem_id)
            state = per_problem.setdefault(
                key,
                {
                    'visible_max': defaultdict(float),
                    'all_max': defaultdict(float),
                    'best_visible': 0.0,
                    'best_admin': 0.0,
                    'best_visible_time': 0,
                    'best_admin_time': 0,
                },
            )

            if contest_problem_id not in hidden_batches_cache:
                hidden_batches_cache[contest_problem_id] = get_hidden_batches_for_problem(
                    contest_submission.problem.problem,
                    is_pretested=contest_submission.is_pretest,
                )

            hidden_batches = hidden_batches_cache[contest_problem_id]
            batch_points = defaultdict(list)

            for test_case in contest_submission.submission.test_cases.all():
                if test_case.points is None:
                    continue
                bucket_id = ('case', test_case.case) if test_case.batch is None else ('batch', test_case.batch)
                batch_points[bucket_id].append(test_case.points)

            for bucket_id, points_list in batch_points.items():
                bucket_type, bucket_value = bucket_id
                score = min(points_list)
                if score > state['all_max'][bucket_id]:
                    state['all_max'][bucket_id] = score

                is_hidden_bucket = bucket_type == 'batch' and bucket_value in hidden_batches
                if not is_hidden_bucket and score > state['visible_max'][bucket_id]:
                    state['visible_max'][bucket_id] = score

            dt = max((contest_submission.submission.date - participation.start).total_seconds(), 0)
            current_visible = sum(state['visible_max'].values())
            current_admin = sum(state['all_max'].values())

            if current_visible > state['best_visible']:
                state['best_visible'] = current_visible
                state['best_visible_time'] = dt

            if current_admin > state['best_admin']:
                state['best_admin'] = current_admin
                state['best_admin_time'] = dt

        format_data = {}

        for problem_id, state in per_problem.items():
            visible_points = sum(state['visible_max'].values())
            admin_points = sum(state['all_max'].values())
            hidden_points = admin_points - visible_points

            if live_masking:
                effective_points = visible_points
                effective_time = state['best_visible_time']
            else:
                effective_points = admin_points
                effective_time = state['best_admin_time']

            format_data[problem_id] = {
                'points': effective_points,
                'time': effective_time,
                'visible_points': visible_points,
                'hidden_points': hidden_points,
                'admin_points': admin_points,
                'admin_time': state['best_admin_time'],
            }

            total_effective += effective_points
            total_admin += admin_points

            if self.config['cumtime'] and effective_points > 0:
                cumtime_effective += int(effective_time)
            if self.config['cumtime'] and admin_points > 0:
                cumtime_admin += int(state['best_admin_time'])

        format_data['__new_ioi__'] = {
            'visible_total': round(sum(v.get('visible_points', 0) for v in format_data.values() if isinstance(v, dict)),
                                   self.contest.points_precision),
            'hidden_total': round(sum(v.get('hidden_points', 0) for v in format_data.values() if isinstance(v, dict)),
                                  self.contest.points_precision),
            'admin_total': round(total_admin, self.contest.points_precision),
            'effective_total': round(total_effective, self.contest.points_precision),
            'admin_cumtime': max(cumtime_admin, 0),
            'effective_cumtime': max(cumtime_effective, 0),
            'live_masking': live_masking,
        }

        participation.score = round(total_effective, self.contest.points_precision)
        participation.cumtime = max(cumtime_effective, 0) if self.config['cumtime'] else 0
        participation.tiebreaker = participation.cumtime if self.config['cumtime'] else 0
        participation.format_data = format_data
        participation.save()

    def get_short_form_display(self):
        yield _('The maximum score for each problem batch will be used (IOI-style).')
        yield _('During the contest, hidden subtasks are masked and excluded from participant-visible score.')
        yield _('After contest end, hidden subtasks are revealed and final ranking is recomputed.')

        if self.config['cumtime']:
            yield _('Ties will be broken by the sum of score-improving submission times.')
        else:
            yield _('Ties by score will **not** be broken.')
