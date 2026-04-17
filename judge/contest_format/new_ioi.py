from collections import defaultdict
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.template.defaultfilters import floatformat
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _, gettext_lazy

from judge.contest_format.legacy_ioi import LegacyIOIContestFormat
from judge.contest_format.registry import register_contest_format
from judge.utils.new_ioi import get_hidden_batches_for_problem, should_mask_live_hidden
from judge.utils.timedelta import nice_repr


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

    @staticmethod
    def _build_state():
        return {
            'max_visible_subtask_scores': defaultdict(float),
            'max_subtask_scores': defaultdict(float),
            'best_visible': 0.0,
            'best_admin': 0.0,
            'best_visible_time': 0,
            'best_admin_time': 0,
            'has_submission': False,
        }

    @staticmethod
    def _apply_submission_state(state, contest_submission, hidden_batches, participation_start, score_scale):
        state['has_submission'] = True
        batch_points = defaultdict(list)

        for test_case in contest_submission.submission.test_cases.all():
            if test_case.points is None:
                continue
            bucket_id = ('case', test_case.case) if test_case.batch is None else ('batch', test_case.batch)
            batch_points[bucket_id].append(float(test_case.points) * score_scale)

        for bucket_id, points_list in batch_points.items():
            bucket_type, bucket_value = bucket_id
            score = min(points_list)
            if score > state['max_subtask_scores'][bucket_id]:
                state['max_subtask_scores'][bucket_id] = score

            is_hidden_bucket = bucket_type == 'batch' and bucket_value in hidden_batches
            if not is_hidden_bucket and score > state['max_visible_subtask_scores'][bucket_id]:
                state['max_visible_subtask_scores'][bucket_id] = score

        dt = max((contest_submission.submission.date - participation_start).total_seconds(), 0)
        current_visible = sum(state['max_visible_subtask_scores'].values())
        current_admin = sum(state['max_subtask_scores'].values())

        if current_visible > state['best_visible']:
            state['best_visible'] = current_visible
            state['best_visible_time'] = dt

        if current_admin > state['best_admin']:
            state['best_admin'] = current_admin
            state['best_admin_time'] = dt

    @staticmethod
    def _effective_points_and_time(state, live_masking):
        visible_points = sum(state['max_visible_subtask_scores'].values())
        admin_points = sum(state['max_subtask_scores'].values())
        hidden_points = admin_points - visible_points
        if live_masking:
            return visible_points, state['best_visible_time'], visible_points, admin_points, hidden_points
        return admin_points, state['best_admin_time'], visible_points, admin_points, hidden_points

    def update_participation(self, participation):
        now = timezone.now()
        live_masking = should_mask_live_hidden(self.contest, now=now)
        freeze_enabled = bool(self.contest.frozen_last_minutes)
        frozen_time = self.contest.frozen_time if freeze_enabled else None
        if freeze_enabled and frozen_time is None:
            freeze_enabled = False

        total_effective = 0.0
        total_admin = 0.0
        cumtime_effective = 0
        cumtime_admin = 0

        frozen_total_effective = 0.0
        frozen_total_admin = 0.0
        frozen_cumtime_effective = 0
        frozen_cumtime_admin = 0

        per_problem = {}
        per_problem_frozen = {}
        hidden_batches_cache = {}
        # Key by base Problem.id so submission lookups and weight retrieval use the same identifier.
        contest_weights_by_problem_id = {
            int(cp.problem_id): float(cp.points or 0)
            for cp in participation.contest.contest_problems.filter(id__isnull=False)
        }

        submissions = (
            participation.submissions.select_related('problem__problem', 'submission')
            .prefetch_related('submission__test_cases')
            .order_by('submission__date', 'submission_id')
        )

        for contest_submission in submissions:
            contest_problem_id = contest_submission.problem_id
            base_problem_id = contest_submission.submission.problem_id
            key = str(contest_problem_id)
            state = per_problem.setdefault(key, self._build_state())

            raw_total = float(contest_submission.submission.case_total or 0)
            contest_weight = contest_weights_by_problem_id.get(int(base_problem_id))
            if contest_weight is None:
                contest_weight = float(contest_submission.problem.points or 0)
            score_scale = (contest_weight / raw_total) if raw_total > 0 else 0.0

            if contest_problem_id not in hidden_batches_cache:
                hidden_batches_cache[contest_problem_id] = get_hidden_batches_for_problem(
                    contest_submission.problem.problem,
                    is_pretested=contest_submission.is_pretest,
                )

            hidden_batches = hidden_batches_cache[contest_problem_id]
            self._apply_submission_state(state, contest_submission, hidden_batches, participation.start, score_scale)

            if freeze_enabled:
                frozen_state = per_problem_frozen.setdefault(key, self._build_state())
                if contest_submission.submission.date < frozen_time:
                    self._apply_submission_state(
                        frozen_state, contest_submission, hidden_batches, participation.start, score_scale,
                    )

        format_data = {}

        for problem_id, state in per_problem.items():
            effective_points, effective_time, visible_points, admin_points, hidden_points = \
                self._effective_points_and_time(state, live_masking)

            frozen_state = per_problem_frozen.get(problem_id, self._build_state()) if freeze_enabled else state
            frozen_effective_points, frozen_effective_time, _, frozen_admin_points, _ = \
                self._effective_points_and_time(frozen_state, live_masking)

            format_data[problem_id] = {
                'points': effective_points,
                'time': effective_time,
                'visible_points': visible_points,
                'hidden_points': hidden_points,
                'admin_points': admin_points,
                'admin_time': state['best_admin_time'],
                'frozen_points': frozen_effective_points,
                'frozen_time': frozen_effective_time,
                'frozen_admin_points': frozen_admin_points,
                'frozen_admin_time': frozen_state['best_admin_time'],
                'has_frozen_submission': bool(frozen_state['has_submission']),
                'visible_score': visible_points,
                'final_score': admin_points,
            }

            total_effective += effective_points
            total_admin += admin_points

            frozen_total_effective += frozen_effective_points
            frozen_total_admin += frozen_admin_points

            if self.config['cumtime'] and effective_points > 0:
                cumtime_effective += int(effective_time)
            if self.config['cumtime'] and admin_points > 0:
                cumtime_admin += int(state['best_admin_time'])
            if self.config['cumtime'] and frozen_effective_points > 0:
                frozen_cumtime_effective += int(frozen_effective_time)
            if self.config['cumtime'] and frozen_admin_points > 0:
                frozen_cumtime_admin += int(frozen_state['best_admin_time'])

        format_data['__new_ioi__'] = {
            'visible_total': round(sum(v.get('visible_points', 0) for v in format_data.values() if isinstance(v, dict)),
                                   self.contest.points_precision),
            'hidden_total': round(sum(v.get('hidden_points', 0) for v in format_data.values() if isinstance(v, dict)),
                                  self.contest.points_precision),
            'admin_total': round(total_admin, self.contest.points_precision),
            'effective_total': round(total_effective, self.contest.points_precision),
            'visible_score': round(sum(v.get('visible_points', 0) for v in format_data.values() if isinstance(v, dict)),
                                   self.contest.points_precision),
            'final_score': round(total_admin, self.contest.points_precision),
            'admin_cumtime': max(cumtime_admin, 0),
            'effective_cumtime': max(cumtime_effective, 0),
            'frozen_admin_total': round(frozen_total_admin, self.contest.points_precision),
            'frozen_effective_total': round(frozen_total_effective, self.contest.points_precision),
            'frozen_admin_cumtime': max(frozen_cumtime_admin, 0),
            'frozen_effective_cumtime': max(frozen_cumtime_effective, 0),
            'live_masking': live_masking,
        }

        participation.score = round(total_effective, self.contest.points_precision)
        participation.cumtime = max(cumtime_effective, 0) if self.config['cumtime'] else 0
        participation.tiebreaker = participation.cumtime if self.config['cumtime'] else 0
        participation.frozen_score = round(frozen_total_effective, self.contest.points_precision)
        participation.frozen_cumtime = max(frozen_cumtime_effective, 0) if self.config['cumtime'] else 0
        participation.frozen_tiebreaker = participation.frozen_cumtime if self.config['cumtime'] else 0
        participation.format_data = format_data
        participation.save()

    def get_first_solves_and_total_ac(self, problems, participations, frozen=False):
        first_solves = {}
        total_ac = {}

        show_time = self.config['cumtime']
        for problem in problems:
            problem_id = str(problem.id)
            min_time = None
            first_solves[problem_id] = None
            total_ac[problem_id] = 0

            for participation in participations:
                format_data = (participation.format_data or {}).get(problem_id)
                if not format_data:
                    continue

                if frozen and not format_data.get('has_frozen_submission', False):
                    continue

                prefix = 'frozen_' if frozen else ''
                points = format_data.get(prefix + 'points', format_data.get('points', 0))
                time = format_data.get(prefix + 'time', format_data.get('time', 0))

                if points == problem.points:
                    total_ac[problem_id] += 1

                    if show_time and participation.virtual == 0 and (min_time is None or min_time > time):
                        min_time = time
                        first_solves[problem_id] = participation.id

        return first_solves, total_ac

    def display_user_problem(self, participation, contest_problem, first_solves, frozen=False):
        format_data = (participation.format_data or {}).get(str(contest_problem.id))
        if not format_data:
            return mark_safe('<td></td>')
        if frozen and not format_data.get('has_frozen_submission', False):
            return mark_safe('<td></td>')

        prefix = 'frozen_' if frozen else ''
        points = format_data.get(prefix + 'points', format_data.get('points', 0))
        time = format_data.get(prefix + 'time', format_data.get('time', 0))

        return format_html(
            '<td class="{state}"><a href="{url}">{points}<div class="solving-time">{time}</div></a></td>',
            state=(('pretest-' if self.contest.run_pretests_only and contest_problem.is_pretested else '') +
                   ('first-solve ' if first_solves.get(str(contest_problem.id), None) == participation.id else '') +
                   self.best_solution_state(points, contest_problem.points)),
            url=reverse('contest_user_submissions',
                        args=[self.contest.key, participation.user.user.username, contest_problem.problem.code]),
            points=floatformat(points, -self.contest.points_precision),
            time=nice_repr(timedelta(seconds=time), 'noday') if self.config['cumtime'] else '',
        )

    def display_participation_result(self, participation, frozen=False):
        points = participation.frozen_score if frozen else participation.score
        cumtime = participation.frozen_cumtime if frozen else participation.cumtime

        return format_html(
            '<td class="user-points"><a href="{url}">{points}<div class="solving-time">{cumtime}</div></a></td>',
            url=reverse('contest_all_user_submissions',
                        args=[self.contest.key, participation.user.user.username]),
            points=floatformat(points, -self.contest.points_precision),
            cumtime=nice_repr(timedelta(seconds=cumtime), 'noday') if self.config['cumtime'] else '',
        )

    def get_short_form_display(self):
        yield _('The maximum score for each problem batch will be used (IOI-style).')
        yield _('During the contest, hidden subtasks are masked and excluded from participant-visible score.')
        yield _('After contest end, hidden subtasks are revealed and final ranking is recomputed.')

        if self.config['cumtime']:
            yield _('Ties will be broken by the sum of score-improving submission times.')
        else:
            yield _('Ties by score will **not** be broken.')
