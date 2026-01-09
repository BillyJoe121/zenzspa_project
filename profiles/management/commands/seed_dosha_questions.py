from django.core.management.base import BaseCommand
from django.db import transaction

from profiles.models import DoshaQuestion, DoshaOption

from .dosha_fixtures import DOSHA_QUESTIONS


class Command(BaseCommand):
    help = "Carga las 25 preguntas del quiz de doshas con sus opciones"

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Elimina todas las preguntas existentes antes de crear las nuevas',
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            if options['clear']:
                deleted_options = DoshaOption.objects.all().delete()[0]
                deleted_questions = DoshaQuestion.objects.all().delete()[0]
                self.stdout.write(
                    self.style.WARNING(
                        f"Eliminadas {deleted_questions} preguntas y {deleted_options} opciones existentes."
                    )
                )

            questions_created = 0
            options_created = 0

            for question_data in DOSHA_QUESTIONS:
                # Evitar mutar el fixture original
                options_data = list(question_data.get('options', ()))
                question_fields = {
                    'category': question_data['category'],
                    'order': question_data['order'],
                    'is_active': question_data['is_active'],
                }

                question, created = DoshaQuestion.objects.update_or_create(
                    text=question_data['text'],
                    defaults=question_fields,
                )
                if created:
                    questions_created += 1

                for option_data in options_data:
                    option, created = DoshaOption.objects.get_or_create(
                        question=question,
                        associated_dosha=option_data['associated_dosha'],
                        defaults={
                            'text': option_data['text'],
                            'weight': option_data['weight'],
                        }
                    )
                    if created:
                        options_created += 1

        self.stdout.write(self.style.SUCCESS("✅ Quiz de Doshas cargado exitosamente"))
        self.stdout.write(f"📊 Total preguntas: {len(DOSHA_QUESTIONS)}")
        self.stdout.write(f"✨ Preguntas nuevas: {questions_created}")
        self.stdout.write(f"🎯 Opciones nuevas: {options_created}")
        self.stdout.write("")
        self.stdout.write("Categorías:")
        categories = {}
        for q in DOSHA_QUESTIONS:
            cat = q['category']
            categories[cat] = categories.get(cat, 0) + 1

        for cat, count in sorted(categories.items()):
            self.stdout.write(f"  {cat}: {count} preguntas")


__all__ = ["Command"]
