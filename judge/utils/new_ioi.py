from django.utils import timezone

NEW_IOI_FORMAT = 'new_ioi'


def contest_is_new_ioi(contest):
    return contest is not None and contest.format_name == NEW_IOI_FORMAT


def get_new_ioi_config(contest):
    config = (contest.format_config or {}) if contest is not None else {}
    return {
        'cumtime': bool(config.get('cumtime', False)),
        'reveal_after_end': bool(config.get('reveal_after_end', True)),
        'show_test_details': config.get('show_test_details', 'visible_only'),
    }


def should_mask_live_hidden(contest, now=None):
    if not contest_is_new_ioi(contest):
        return False
    config = get_new_ioi_config(contest)
    if not config['reveal_after_end']:
        return False
    if now is None:
        now = timezone.now()
    return contest.end_time is not None and now < contest.end_time


def can_view_new_ioi_hidden(contest, user):
    if contest is None or user is None or not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm('judge.edit_all_contest'):
        return True
    return user.profile.id in contest.editor_ids


def get_hidden_batches_for_problem(problem, is_pretested=False):
    hidden_batches = set()
    batch_id = 0
    case_queryset = problem.cases.all().order_by('order').only('type', 'is_hidden', 'is_pretest')

    for case in case_queryset:
        if is_pretested and not case.is_pretest:
            continue
        if not is_pretested and case.is_pretest:
            continue
        if case.type != 'S':
            continue
        batch_id += 1
        if case.is_hidden:
            hidden_batches.add(batch_id)

    return hidden_batches


def should_mask_submission_hidden_results(submission, user, now=None):
    contest = submission.contest_object
    if contest is None:
        return False
    if not should_mask_live_hidden(contest, now=now):
        return False
    return not can_view_new_ioi_hidden(contest, user)
