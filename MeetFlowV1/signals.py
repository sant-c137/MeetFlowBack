from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Module, UserModuleProgress

@receiver(post_save, sender=User)
def assign_intro_module(sender, instance, created, **kwargs):
    if created:
        # Try to find the first module in the curriculum (order=0 or 1, no user)
        # We prioritize 'Introduction to Python' or whatever has the lowest order.
        intro_module = Module.objects.filter(user=None).order_by('order').first()
        
        if intro_module:
            # Assign it to the new user
            UserModuleProgress.objects.get_or_create(
                user=instance,
                module=intro_module,
                defaults={'status': 'AVAILABLE'}
            )
