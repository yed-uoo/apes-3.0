from django.core.management.base import BaseCommand
from core.models import StudentEvaluation


class Command(BaseCommand):
    help = 'Check status of all student evaluations'

    def handle(self, *args, **options):
        stages = ['first', 'second']
        
        for stage in stages:
            self.stdout.write(self.style.WARNING(f'\n=== {stage.upper()} EVALUATION ==='))
            
            evaluations = StudentEvaluation.objects.filter(stage=stage)
            
            if not evaluations.exists():
                self.stdout.write(f'No {stage} evaluations found.')
                continue
            
            for eval in evaluations:
                self.stdout.write(
                    f'Student: {eval.student.username}, '
                    f'Group ID: {eval.group.id}, '
                    f'Guide Submitted: {eval.guide_submitted}, '
                    f'Coordinator Submitted: {eval.coordinator_submitted}, '
                    f'Finalized: {eval.finalized}'
                )
        
        self.stdout.write(self.style.SUCCESS('\nDone!'))
