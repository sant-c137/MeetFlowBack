from django.db import models
from django.contrib.auth.models import User


class Module(models.Model):
    title = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='custom_modules')
    is_ai_generated = models.BooleanField(default=False)
    source_module = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_reinforcements')
    reinforcement_type = models.CharField(max_length=20, null=True, blank=True)
    order = models.PositiveIntegerField(default=0)
    position_x = models.FloatField(default=0.0)
    position_y = models.FloatField(default=0.0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title

class Unit(models.Model):
    module = models.OneToOneField(Module, on_delete=models.CASCADE, related_name='unit', null=True, blank=True)

    title = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.module.title} - {self.title}"

class Exercise(models.Model):
    TYPE_CHOICES = [
        ('BLANKS', 'Fill in the blanks'),
        ('PARSONS', 'Parsons Problems'),
        ('DEBUG', 'Debugging'),
        ('CODE', 'Coding Task'),
        ('THEORY', 'Theoretical MCQ'),
    ]
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    content = models.JSONField(help_text="Exercise content/structure")
    solution = models.JSONField(help_text="Expected solution")
    ai_metadata = models.JSONField(null=True, blank=True, help_text="AI generation metadata")
    
    class Meta:
        abstract = True

class MasterExercise(Exercise):
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='master_exercises')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"Master: {self.unit.title} - {self.type}"

class AIExercise(Exercise):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_exercises')
    source_unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='ai_generated_exercises')

    def __str__(self):
        return f"AI ({self.user.username}): {self.source_unit.title} - {self.type}"

class ModuleDependency(models.Model):
    source_node = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='outgoing_dependencies')
    target_node = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='incoming_dependencies')
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='custom_dependencies')

    class Meta:
        unique_together = ('source_node', 'target_node', 'user')

    def __str__(self):
        return f"{self.source_node} -> {self.target_node} (User: {self.user})"

class UserExerciseAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exercise_attempts')
    master_exercise = models.ForeignKey(MasterExercise, on_delete=models.CASCADE, null=True, blank=True, related_name='attempts')
    ai_exercise = models.ForeignKey(AIExercise, on_delete=models.CASCADE, null=True, blank=True, related_name='attempts')
    
    attempts_count = models.PositiveIntegerField(default=0)
    error_log = models.JSONField(default=list)
    is_flagged_for_ai = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)
    last_attempt_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [
            ['user', 'master_exercise'],
            ['user', 'ai_exercise']
        ]

class UserModuleProgress(models.Model):
    STATUS_CHOICES = [
        ('LOCKED', 'Locked'),
        ('AVAILABLE', 'Available'),
        ('COMPLETED', 'Completed'),
        ('STUCK', 'Stuck'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='module_progress')
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='LOCKED')
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'module']

    def __str__(self):
        return f"{self.user.username} - {self.module.title}: {self.status}"
