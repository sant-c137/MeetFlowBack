from rest_framework import serializers
from django.db.models import Q
from .models import (
    Module,
    UserModuleProgress,
    Unit,
    MasterExercise,
    AIExercise,
    UserExerciseAttempt,
    ModuleDependency,
)

from .services import is_module_unlocked

class MasterExerciseSerializer(serializers.ModelSerializer):
    is_completed = serializers.SerializerMethodField()
    is_ai = serializers.ReadOnlyField(default=False)
    # Pyodide fields flattened for the frontend
    expected_output = serializers.SerializerMethodField()
    pyodide_test_code = serializers.SerializerMethodField()
    initial_code = serializers.SerializerMethodField()
    instruction = serializers.SerializerMethodField()
    question = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()

    class Meta:
        model = MasterExercise
        fields = [
            'id', 'unit', 'type', 'order', 'is_completed', 'is_ai',
            'instruction', 'question', 'options', 'initial_code', 'expected_output', 'pyodide_test_code',
            'content', 'solution', 'ai_metadata'
        ]

    def get_is_completed(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            return UserExerciseAttempt.objects.filter(
                user=request.user, master_exercise=obj, is_completed=True
            ).exists()
        return False

    def get_expected_output(self, obj):
        return obj.content.get('expected_output', '')

    def get_pyodide_test_code(self, obj):
        return obj.content.get('pyodide_test_code', '')

    def get_initial_code(self, obj):
        return obj.content.get('initial_code', '')

    def get_instruction(self, obj):
        return obj.content.get('instruction', '')

    def get_question(self, obj):
        return obj.content.get('question', '')

    def get_options(self, obj):
        return obj.content.get('options', {})

class AIExerciseSerializer(serializers.ModelSerializer):
    is_completed = serializers.SerializerMethodField()
    is_ai = serializers.ReadOnlyField(default=True)
    unit = serializers.PrimaryKeyRelatedField(source='source_unit', read_only=True)
    order = serializers.ReadOnlyField(default=0)
    # Pyodide fields flattened for the frontend
    expected_output = serializers.SerializerMethodField()
    pyodide_test_code = serializers.SerializerMethodField()
    initial_code = serializers.SerializerMethodField()
    instruction = serializers.SerializerMethodField()
    question = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()

    class Meta:
        model = AIExercise
        fields = [
            'id', 'unit', 'type', 'order', 'is_completed', 'is_ai',
            'instruction', 'question', 'options', 'initial_code', 'expected_output', 'pyodide_test_code',
            'content', 'solution', 'ai_metadata'
        ]

    def get_is_completed(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            return UserExerciseAttempt.objects.filter(
                user=request.user, ai_exercise=obj, is_completed=True
            ).exists()
        return False

    def get_expected_output(self, obj):
        return obj.content.get('expected_output', '')

    def get_pyodide_test_code(self, obj):
        return obj.content.get('pyodide_test_code', '')

    def get_initial_code(self, obj):
        return obj.content.get('initial_code', '')

    def get_instruction(self, obj):
        return obj.content.get('instruction', '')

    def get_question(self, obj):
        return obj.content.get('question', '')

    def get_options(self, obj):
        return obj.content.get('options', {})

class UnitSerializer(serializers.ModelSerializer):
    master_exercises = MasterExerciseSerializer(many=True, read_only=True)
    
    class Meta:
        model = Unit
        fields = ['id', 'module', 'title', 'order', 'master_exercises']

class UserStatsSerializer(serializers.Serializer):
    completed_exercises = serializers.IntegerField()
    total_attempts = serializers.IntegerField()
    weak_points = serializers.ListField(child=serializers.CharField())
    learning_path_progress = serializers.FloatField()

class ModuleSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    completion_percentage = serializers.SerializerMethodField()
    outgoing_dependencies = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    unit_id = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = ['id', 'unit_id', 'title', 'order', 'user', 'is_ai_generated', 'source_module', 'reinforcement_type', 'position_x', 'position_y', 'outgoing_dependencies', 'status', 'completion_percentage']

    def get_unit_id(self, obj):
        try:
            # Module has a OneToOneField to Unit with related_name='unit'
            return obj.unit.id
        except Exception:
            return None

    def get_status(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            user = request.user
            if user.is_authenticated:
                # Use helper for consistency
                if not is_module_unlocked(user, obj):
                    return 'LOCKED'
                
                progress = UserModuleProgress.objects.filter(user=user, module=obj).first()
                if progress:
                    return progress.status
                return 'AVAILABLE'
                
        return 'LOCKED'

    def get_completion_percentage(self, obj):
        request = self.context.get('request')
        if not (request and hasattr(request, 'user') and request.user.is_authenticated):
            return 0.0
            
        user = request.user

        # If it's LOCKED, percentage should be 0.0 (UI consistency)
        if self.get_status(obj) == 'LOCKED':
            return 0.0

        # Safe access to OneToOne relation
        try:
            unit = obj.unit
        except Exception:
            unit = None

        if not unit:
            # Fallback to status if no associated unit
            progress = UserModuleProgress.objects.filter(user=user, module=obj).first()
            return 100.0 if progress and progress.status == 'COMPLETED' else 0.0

        # Prioritize AI exercises if they exist (same as in UnitSessionView)
        ai_exercises = AIExercise.objects.filter(source_unit=unit, user=user)
        
        if ai_exercises.exists():
            total = ai_exercises.count()
            completed = UserExerciseAttempt.objects.filter(
                user=user,
                ai_exercise__source_unit=unit,
                is_completed=True
            ).count()
        else:
            # If no AI, use master exercises
            total = MasterExercise.objects.filter(unit=unit).count()
            if total == 0:
                progress = UserModuleProgress.objects.filter(user=user, module=obj).first()
                return 100.0 if progress and progress.status == 'COMPLETED' else 0.0
            
            completed = UserExerciseAttempt.objects.filter(
                user=user,
                master_exercise__unit=unit,
                is_completed=True
            ).count()
            
        return round((completed / total) * 100, 2)

class UserModuleProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserModuleProgress
        fields = ['id', 'user', 'module', 'status', 'last_updated']

