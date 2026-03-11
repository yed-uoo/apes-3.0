from django.core.management.base import BaseCommand
from core.models import StudentEvaluation


class Command(BaseCommand):
    help = 'Fix finalized status for all student evaluations where both guide and coordinator have submitted'

    def handle(self, *args, **options):
        # Get all evaluations where both have submitted but finalized is False
        evaluations = StudentEvaluation.objects.filter(
            guide_submitted=True,
            coordinator_submitted=True,
            finalized=False
        )
        
        count = evaluations.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('No evaluations need to be fixed.'))
            return
        
        # Update all matching evaluations
        evaluations.update(finalized=True)
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully updated {count} evaluation(s) to finalized=True')
        )
