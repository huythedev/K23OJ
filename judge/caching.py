from django.conf import settings
from django.core.cache import cache


def submission_started(sub):
    keys = ['user_complete:%d' % sub.user_id, 'user_attempted:%d' % sub.user_id]
    cache.delete_many(keys)


def contest_submission_started(participation):
    cache.delete_many(['contest_complete:%d' % participation.id, 'contest_attempted:%d' % participation.id])


def finished_submission(sub):
    keys = ['user_complete:%d' % sub.user_id, 'user_attempted:%s' % sub.user_id]
    if hasattr(sub, 'contest'):
        participation = sub.contest.participation
        keys += ['contest_complete:%d' % participation.id]
        keys += ['contest_attempted:%d' % participation.id]
    cache.delete_many(keys)


def invalidate_contest_ranking_cache(contest):
    keys = []
    for show_virtual in (False, True):
        for is_frozen in (False, True):
            for lang, _ in settings.LANGUAGES:
                for new_ioi_visibility in ('na', 'masked', 'hidden'):
                    keys.append(
                        f'contest_ranking_cache_{contest.key}_{show_virtual}_{is_frozen}_{lang}_{new_ioi_visibility}'
                    )
    cache.delete_many(keys)
