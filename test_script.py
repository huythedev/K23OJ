import django
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dmoj.settings")
django.setup()

from judge.models import Contest, ContestParticipation, ContestSubmission

c = Contest.objects.first()
if c:
    cp_list = list(c.contest_problems.values_list('problem_id', 'points'))
    print("Contest Problems values_list:", cp_list)
    
    p = ContestParticipation.objects.filter(contest=c).first()
    if p:
        submissions = p.submissions.select_related('problem__problem', 'submission').all()
        for cs in submissions:
            print(f"cs.problem_id: {cs.problem_id!r}, cs.submission.problem_id: {cs.submission.problem_id!r}")
            print(f"cs.problem: {type(cs.problem)}")
            print(f"cs.problem.points: {cs.problem.points}")
            print(f"cs.problem.problem.points: {cs.problem.problem.points}")
