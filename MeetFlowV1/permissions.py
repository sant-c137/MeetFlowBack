# your_app/permissions.py
from rest_framework import permissions

class IsCreatorOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow creators of an object to edit it.
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the creator of the event.
        return obj.creator == request.user

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    Assumes the object has a 'user' attribute.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user == request.user

class IsEventCreatorForRelatedObject(permissions.BasePermission):
    """
    Permission to check if the user is the creator of the parent event.
    Used for creating/modifying options (TimeOption, LocationOption) related to an event.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # For list views, allow if authenticated (actual filtering done in queryset)
        if view.action == 'list':
            return True
        # For create, retrieve, update, destroy, check event creator
        event_id = view.kwargs.get('event_pk') or request.data.get('event')
        if not event_id: # If event_id is not in URL or data, deny
            return False
        try:
            from .models import Event # Local import to avoid circular dependency
            event = Event.objects.get(pk=event_id)
            return event.creator == request.user
        except Event.DoesNotExist:
            return False
        return True # Fallback, though specific checks should cover cases

    def has_object_permission(self, request, view, obj):
        # For specific objects, check if the user is the creator of the parent event
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.event.creator == request.user


class IsInvitedUserOrEventCreator(permissions.BasePermission):
    """
    Permission for Invitation:
    - Invited user can view and update their own invitation (e.g., change status).
    - Event creator can view all invitations for their event and create new ones.
    """
    def has_object_permission(self, request, view, obj):
        # Allow read if user is the invited user or the event creator
        if request.method in permissions.SAFE_METHODS:
            return obj.user == request.user or obj.event.creator == request.user

        # Allow write (status update) if user is the invited user
        if obj.user == request.user:
            return True
        # Allow event creator to delete invitations (optional)
        # if request.method == 'DELETE' and obj.event.creator == request.user:
        # return True
        return False


class IsVoteOwnerOrEventCreator(permissions.BasePermission):
    """
    Permission for Votes:
    - User can create/update/delete their own votes.
    - Event creator can view all votes for their event's options.
    """
    def has_object_permission(self, request, view, obj):
        # Read access for event creator or vote owner
        if request.method in permissions.SAFE_METHODS:
            return obj.user == request.user or \
                   (hasattr(obj, 'time_option') and obj.time_option.event.creator == request.user) or \
                   (hasattr(obj, 'location_option') and obj.location_option.event.creator == request.user)

        # Write access only for the vote owner
        return obj.user == request.user