from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Event(models.Model):
    """
    Model to represent scheduled events or meetings
    """

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("planning", "Planning"),
        ("confirmed", "Confirmed"),
        ("cancelled", "Cancelled"),
        ("completed", "Completed"),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    update_date = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    creator = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_events"
    )

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    class Meta:
        verbose_name = "Event"
        verbose_name_plural = "Events"
        ordering = ["-creation_date"]


class TimeOption(models.Model):
    """
    Model for proposed time options for an event
    """

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="time_options"
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    def __str__(self):
        return f"{self.event.title}: {self.start_time.strftime('%Y-%m-%d %H:%M')} - {self.end_time.strftime('%H:%M')}"

    class Meta:
        verbose_name = "Time Option"
        verbose_name_plural = "Time Options"
        ordering = ["start_time"]


class LocationOption(models.Model):
    """
    Model for proposed location options for an event
    """

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="location_options"
    )
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=255)
    details = models.TextField(blank=True)

    def __str__(self):
        return f"{self.event.title}: {self.name}"

    class Meta:
        verbose_name = "Location Option"
        verbose_name_plural = "Location Options"


class Invitation(models.Model):
    """
    Model for invitations sent to participants
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
        ("tentative", "Tentative"),
    ]

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="invitations"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="received_invitations"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    sent_date = models.DateTimeField(auto_now_add=True)
    response_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.event.title}: {self.get_status_display()}"

    class Meta:
        verbose_name = "Invitation"
        verbose_name_plural = "Invitations"
        unique_together = ["event", "user"]
        ordering = ["-sent_date"]


class UserEventTimeSelection(models.Model):
    """
    Model for a user's single selected time option for an event.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="time_selections"
    )
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="event_time_selections"
    )
    selected_time_option = models.ForeignKey(
        TimeOption, on_delete=models.CASCADE, related_name="chosen_by_users"
    )
    selection_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} selected {self.selected_time_option} for {self.event.title}"

    class Meta:
        verbose_name = "User Time Selection"
        verbose_name_plural = "User Time Selections"
        unique_together = ["user", "event"]


class UserEventLocationSelection(models.Model):
    """
    Model for a user's single selected location option for an event.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="location_selections"
    )
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="event_location_selections"
    )
    selected_location_option = models.ForeignKey(
        LocationOption, on_delete=models.CASCADE, related_name="chosen_by_users"
    )
    selection_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} selected {self.selected_location_option} for {self.event.title}"

    class Meta:
        verbose_name = "User Location Selection"
        verbose_name_plural = "User Location Selections"
        unique_together = ["user", "event"]


class Notification(models.Model):
    """
    Model for notifications sent to users
    """

    TYPE_CHOICES = [
        ("invitation", "Event Invitation"),
        ("reminder", "Event Reminder"),
        ("update", "Event Update"),
        ("confirmation", "Event Confirmation"),
        ("cancellation", "Event Cancellation"),
        ("vote_update", "Vote Update"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="notifications"
    )
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    message = models.TextField()
    read = models.BooleanField(default=False)
    creation_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_type_display()}: {self.event.title}"

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-creation_date"]

class TimeVote(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='time_votes')
    time_option = models.ForeignKey(TimeOption, on_delete=models.CASCADE, related_name='votes')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='time_option_votes') 
    preference = models.IntegerField(default=0) 
    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'time_option') 
        ordering = ['-voted_at']

    def __str__(self):
        return f"{self.user.username} voted for time {self.time_option_id} (Pref: {self.preference})"

class LocationVote(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='location_votes')
    location_option = models.ForeignKey(LocationOption, on_delete=models.CASCADE, related_name='votes')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='location_option_votes') 
    preference = models.IntegerField(default=0)
    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'location_option')
        ordering = ['-voted_at']

    def __str__(self):
        return f"{self.user.username} voted for location {self.location_option_id} (Pref: {self.preference})"

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
