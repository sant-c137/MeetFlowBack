from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Event(models.Model):
    """
    Model to represent scheduled events or meetings
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('planning', 'Planning'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    update_date = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_events')
    
    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"
    
    class Meta:
        verbose_name = "Event"
        verbose_name_plural = "Events"
        ordering = ['-creation_date']


class TimeOption(models.Model):
    """
    Model for proposed time options for an event
    """
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='time_options')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    
    def __str__(self):
        return f"{self.event.title}: {self.start_time.strftime('%Y-%m-%d %H:%M')} - {self.end_time.strftime('%H:%M')}"
    
    class Meta:
        verbose_name = "Time Option"
        verbose_name_plural = "Time Options"
        ordering = ['start_time']


class LocationOption(models.Model):
    """
    Model for proposed location options for an event
    """
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='location_options')
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
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('tentative', 'Tentative'),
    ]
    
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='invitations')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_invitations')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    sent_date = models.DateTimeField(auto_now_add=True)
    response_date = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.event.title}: {self.get_status_display()}"
    
    class Meta:
        verbose_name = "Invitation"
        verbose_name_plural = "Invitations"
        unique_together = ['event', 'user']
        ordering = ['-sent_date']


class TimeVote(models.Model):
    """
    Model for user votes on time options
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='time_votes')
    time_option = models.ForeignKey(TimeOption, on_delete=models.CASCADE, related_name='votes')
    preference = models.IntegerField(default=0, help_text="From 0 to 5, where 5 is the highest preference")
    vote_date = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.time_option}: {self.preference}"
    
    class Meta:
        verbose_name = "Time Vote"
        verbose_name_plural = "Time Votes"
        unique_together = ['user', 'time_option']


class LocationVote(models.Model):
    """
    Model for user votes on location options
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='location_votes')
    location_option = models.ForeignKey(LocationOption, on_delete=models.CASCADE, related_name='votes')
    preference = models.IntegerField(default=0, help_text="From 0 to 5, where 5 is the highest preference")
    vote_date = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.location_option}: {self.preference}"
    
    class Meta:
        verbose_name = "Location Vote"
        verbose_name_plural = "Location Votes"
        unique_together = ['user', 'location_option']


class Notification(models.Model):
    """
    Model for notifications sent to users
    """
    TYPE_CHOICES = [
        ('invitation', 'Event Invitation'),
        ('reminder', 'Event Reminder'),
        ('update', 'Event Update'),
        ('confirmation', 'Event Confirmation'),
        ('cancellation', 'Event Cancellation'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    message = models.TextField()
    read = models.BooleanField(default=False)
    creation_date = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.get_type_display()}: {self.event.title}"
    
    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ['-creation_date']