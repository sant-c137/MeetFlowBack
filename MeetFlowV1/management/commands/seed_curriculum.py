import json
import os
from django.core.management.base import BaseCommand
from django.db import transaction, connection
from MeetFlowV1.models import Module, Unit, MasterExercise, ModuleDependency, UserModuleProgress, UserExerciseAttempt

class Command(BaseCommand):
    help = 'Loads the curriculum from a JSON file, deleting previous data'

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='Path to curriculum.json file')

    def handle(self, *args, **options):
        json_file = options['json_file']
        
        if not os.path.exists(json_file):
            self.stderr.write(self.style.ERROR(f'File not found: {json_file}'))
            return

        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        try:
            with transaction.atomic():
                self.clear_existing_data()
                self.seed_data(data)
                self.stdout.write(self.style.SUCCESS('Curriculum loaded successfully after clearing previous data'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error loading curriculum: {str(e)}'))
            import traceback
            self.stderr.write(traceback.format_exc())

    def clear_existing_data(self):
        """Deletes all data and resets ID counters in PostgreSQL"""
        self.stdout.write('Clearing data and resetting sequences...')
        
        models_to_reset = [
            ModuleDependency,
            UserExerciseAttempt,
            UserModuleProgress,
            MasterExercise,
            Unit,
            Module
        ]

        with connection.cursor() as cursor:
            for model in models_to_reset:
                table_name = model._meta.db_table
                # TRUNCATE with RESTART IDENTITY resets IDs to 1 in PostgreSQL
                # CASCADE ensures dependencies are deleted if any
                cursor.execute(f"TRUNCATE TABLE \"{table_name}\" RESTART IDENTITY CASCADE;")
        
        self.stdout.write(self.style.SUCCESS('Tables cleared and sequences reset to 1.'))

    def seed_data(self, data):
        # Dictionary to map title to Module instance
        module_map = {}

        # 1. Create Modules
        for mod_data in data:
            title = mod_data.get('module_title')
            module = Module.objects.create(
                title=title,
                order=mod_data.get('order', 0),
                position_x=mod_data.get('position_x', 0.0),
                position_y=mod_data.get('position_y', 0.0),
                is_ai_generated=False,
                user=None
            )
            module_map[title] = module
            self.stdout.write(f'Module created: {module.title}')

            # Create Units within the module
            units_data = mod_data.get('units', [])
            for u_data in units_data:
                # In current schema, Unit has a OneToOneField with Module. 
                # If the JSON has multiple units per module, we might need to adjust the model.
                # Assuming one main unit per module based on the OneToOneField in models.py.
                unit, _ = Unit.objects.get_or_create(
                    module=module,
                    defaults={
                        'title': u_data.get('unit_title'),
                        'order': u_data.get('order', 1)
                    }
                )

                # Create Exercises for the unit
                exercises_data = u_data.get('exercises', [])
                for ex_data in exercises_data:
                    MasterExercise.objects.create(
                        unit=unit,
                        order=ex_data.get('order', 0),
                        type=ex_data['type'],
                        content={
                            **ex_data.get('content', {}),
                            'title': ex_data.get('title'),
                            'instruction': ex_data.get('instruction'),
                            'ai_focus': ex_data.get('ai_focus')
                        },
                        solution=ex_data['solution']
                    )

        # 2. Create Dependencies (Edges)
        for mod_data in data:
            target_title = mod_data.get('module_title')
            target_node = module_map.get(target_title)
            
            dependencies = mod_data.get('dependencies', [])
            for source_title in dependencies:
                source_node = module_map.get(source_title)
                
                if source_node and target_node:
                    ModuleDependency.objects.get_or_create(
                        source_node=source_node,
                        target_node=target_node,
                        user=None
                    )
                    self.stdout.write(f'Dependency created: {source_node.title} -> {target_node.title}')
