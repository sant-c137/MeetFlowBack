from django.http import JsonResponse
from django.contrib.auth import authenticate, login, get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
import json
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

User = get_user_model()

@csrf_exempt
def login_view(request):
    if request.method == "POST":
        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return JsonResponse({"message": "Login successful"}, status=200)
        else:
            return JsonResponse({"error": "Invalid credentials"}, status=401)
    return JsonResponse({"error": "Invalid request method"}, status=400)


def logout_view(request):
    logout(request)
    return JsonResponse({"message": "Logged out successfully"}, status=200)


@csrf_exempt
def register_view(request):
    if request.method == "POST":
        try:

            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        username = data.get("username")
        password = data.get("password")
        email = data.get("email")

        if not username or not password or not email:
            return JsonResponse(
                {"error": "Username, password, and email are required"}, status=400
            )

        User = get_user_model()

        if User.objects.filter(username=username).exists():
            return JsonResponse({"error": "Username already taken"}, status=400)

        try:
            user = User.objects.create_user(
                username=username, password=password, email=email
            )
        except Exception as e:
            return JsonResponse({"error": f"Error creating user: {str(e)}"}, status=500)

        return JsonResponse({"message": "User registered successfully"}, status=201)

    return JsonResponse({"error": "Invalid request method"}, status=405)

@login_required
def check_session(request):
    return JsonResponse(
        {"authenticated": True, "username": request.user.username}, status=200
    )












from django.http import JsonResponse, HttpResponseForbidden, HttpResponseNotFound, HttpResponseBadRequest
from django.contrib.auth import authenticate, login, get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import IntegrityError
from django.forms.models import model_to_dict # Helper for serialization
import json

from .models import Event, TimeOption, LocationOption, Invitation, TimeVote, LocationVote, Notification

User = get_user_model()

# --- Auth Views (Existing) ---
@csrf_exempt
@require_http_methods(["POST"])
def login_view(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        username = data.get("username")
        password = data.get("password")

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return JsonResponse({
                "message": "Login successful",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email
                }
            }, status=200)
        else:
            return JsonResponse({"error": "Invalid credentials"}, status=401)
    return JsonResponse({"error": "Invalid request method"}, status=400)


@require_http_methods(["POST"]) # CSRF not needed for logout if POST ensures it's not accidental GET
def logout_view(request):
    logout(request)
    return JsonResponse({"message": "Logged out successfully"}, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def register_view(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        username = data.get("username")
        password = data.get("password")
        email = data.get("email")

        if not username or not password or not email:
            return JsonResponse(
                {"error": "Username, password, and email are required"}, status=400
            )

        if User.objects.filter(username=username).exists():
            return JsonResponse({"error": "Username already taken"}, status=400)
        if User.objects.filter(email=email).exists():
            return JsonResponse({"error": "Email already taken"}, status=400)

        try:
            user = User.objects.create_user(
                username=username, password=password, email=email
            )
            return JsonResponse({
                "message": "User registered successfully",
                "user": {
                     "id": user.id,
                    "username": user.username,
                    "email": user.email
                }
            }, status=201)
        except Exception as e:
            return JsonResponse({"error": f"Error creating user: {str(e)}"}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)

@login_required
@require_http_methods(["GET"])
def check_session(request):
    return JsonResponse(
        {"authenticated": True, 
         "user": {
             "id": request.user.id,
             "username": request.user.username,
             "email": request.user.email
            }
        }, status=200
    )

# --- Helper function to create notifications ---
def create_notification(user, event, type, message):
    Notification.objects.create(user=user, event=event, type=type, message=message)

# --- Event Views ---
@csrf_exempt
@login_required
@require_http_methods(["GET", "POST"])
def event_list_create_view(request):
    if request.method == "GET":
        # List events created by the user or where the user is invited
        created_events = Event.objects.filter(creator=request.user)
        invited_event_ids = Invitation.objects.filter(user=request.user, status='accepted').values_list('event_id', flat=True)
        invited_events = Event.objects.filter(id__in=invited_event_ids)
        events = (created_events | invited_events).distinct().order_by('-creation_date')
        
        data = []
        for event in events:
            event_data = model_to_dict(event)
            event_data['creator'] = event.creator.username
            event_data['status_display'] = event.get_status_display()
            # Add more details if needed from related models for list view
            data.append(event_data)
        return JsonResponse(data, safe=False, status=200)

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        title = data.get('title')
        description = data.get('description', '')
        status = data.get('status', 'draft')

        if not title:
            return JsonResponse({"error": "Title is required"}, status=400)

        event = Event.objects.create(
            title=title,
            description=description,
            status=status,
            creator=request.user
        )
        # You might want to create default TimeOption/LocationOption here or let user add them later
        return JsonResponse(model_to_dict(event), status=201)

@csrf_exempt
@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def event_detail_view(request, event_id):
    event = get_object_or_404(Event, pk=event_id)

    if request.method == "GET":
        event_data = model_to_dict(event)
        event_data['creator'] = event.creator.username
        event_data['status_display'] = event.get_status_display()
        
        event_data['time_options'] = list(event.time_options.all().values('id', 'start_time', 'end_time'))
        event_data['location_options'] = list(event.location_options.all().values('id', 'name', 'address', 'details'))
        
        invitations_data = []
        for inv in event.invitations.all():
            invitations_data.append({
                'id': inv.id,
                'user_id': inv.user.id,
                'username': inv.user.username,
                'status': inv.status,
                'status_display': inv.get_status_display()
            })
        event_data['invitations'] = invitations_data

        # Add votes information if needed
        # This can get complex, consider a separate endpoint for detailed vote counts per option

        return JsonResponse(event_data, status=200)

    # Only creator can update or delete
    if event.creator != request.user:
        return HttpResponseForbidden("You are not authorized to modify this event.")

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        event.title = data.get('title', event.title)
        event.description = data.get('description', event.description)
        new_status = data.get('status', event.status)

        if new_status != event.status and new_status in [choice[0] for choice in Event.STATUS_CHOICES]:
            event.status = new_status
            # Create notifications for status changes (e.g., confirmed, cancelled)
            if new_status == 'confirmed':
                message = f"The event '{event.title}' has been confirmed."
                notification_type = 'confirmation'
            elif new_status == 'cancelled':
                message = f"The event '{event.title}' has been cancelled."
                notification_type = 'cancellation'
            elif new_status in ['planning', 'completed']:
                 message = f"The event '{event.title}' has been updated to {event.get_status_display()}."
                 notification_type = 'update'
            else: # draft or other
                message = None
                notification_type = None
            
            if message and notification_type:
                for invitation in event.invitations.filter(status='accepted'): # or all invitees
                    create_notification(invitation.user, event, notification_type, message)
        
        event.save()
        return JsonResponse(model_to_dict(event), status=200)

    elif request.method == "DELETE":
        event_title = event.title # Get title before deleting
        # Optionally: Create cancellation notifications for invitees if not already handled by status change
        # for invitation in event.invitations.all():
        # create_notification(invitation.user, event, 'cancellation', f"The event '{event_title}' has been cancelled/deleted.")
        event.delete()
        return JsonResponse({"message": "Event deleted successfully"}, status=204) # 204 No Content

# --- TimeOption & LocationOption Views (Simplified: Add only, assuming creator adds them) ---
@csrf_exempt
@login_required
@require_http_methods(["POST"])
def add_time_option_view(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if event.creator != request.user:
        return HttpResponseForbidden("Only the event creator can add time options.")

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    start_time = data.get('start_time')
    end_time = data.get('end_time')

    if not start_time or not end_time:
        return JsonResponse({"error": "Start time and end time are required"}, status=400)
    
    # Add validation for datetime format and logical consistency (start < end)
    try:
        # Example: "2023-10-27T10:00:00Z" or "2023-10-27 10:00"
        # Ensure your frontend sends compatible datetime strings
        time_option = TimeOption.objects.create(event=event, start_time=start_time, end_time=end_time)
        return JsonResponse(model_to_dict(time_option), status=201)
    except Exception as e: # More specific exceptions for date parsing needed
        return JsonResponse({"error": f"Invalid date format or data: {str(e)}"}, status=400)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def add_location_option_view(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if event.creator != request.user:
        return HttpResponseForbidden("Only the event creator can add location options.")

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = data.get('name')
    address = data.get('address')
    details = data.get('details', '')

    if not name or not address:
        return JsonResponse({"error": "Name and address are required"}, status=400)
    
    location_option = LocationOption.objects.create(event=event, name=name, address=address, details=details)
    return JsonResponse(model_to_dict(location_option), status=201)

# --- Invitation Views ---
@csrf_exempt
@login_required
@require_http_methods(["POST"])
def invite_user_view(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if event.creator != request.user:
        return HttpResponseForbidden("Only the event creator can send invitations.")

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    
    user_id_to_invite = data.get('user_id')
    if not user_id_to_invite:
        return JsonResponse({"error": "User ID to invite is required"}, status=400)

    try:
        user_to_invite = User.objects.get(pk=user_id_to_invite)
    except User.DoesNotExist:
        return HttpResponseNotFound("User to invite not found.")

    if user_to_invite == request.user:
        return JsonResponse({"error": "You cannot invite yourself."}, status=400)

    try:
        invitation, created = Invitation.objects.get_or_create(
            event=event,
            user=user_to_invite,
            defaults={'status': 'pending'} # Only set defaults if creating
        )
        if not created and invitation.status != 'pending': # Resending an already responded invite?
             return JsonResponse({"message": f"User already invited and has status: {invitation.get_status_display()}"}, status=200)
        elif not created: # Already invited but still pending
            return JsonResponse({"message": "User already has a pending invitation."}, status=200)


        # Create a notification for the invited user
        create_notification(
            user_to_invite,
            event,
            'invitation',
            f"You have been invited to the event: '{event.title}' by {request.user.username}."
        )
        return JsonResponse({
            "message": "Invitation sent successfully.",
            "invitation_id": invitation.id,
            "user": user_to_invite.username,
            "status": invitation.get_status_display()
        }, status=201 if created else 200)
    except IntegrityError: # Should be handled by get_or_create, but good practice
        return JsonResponse({"error": "Invitation already exists or other integrity error."}, status=400)


@csrf_exempt
@login_required
@require_http_methods(["PUT"])
def respond_invitation_view(request, invitation_id):
    invitation = get_object_or_404(Invitation, pk=invitation_id)
    if invitation.user != request.user:
        return HttpResponseForbidden("You can only respond to your own invitations.")

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    
    new_status = data.get('status')
    if not new_status or new_status not in [choice[0] for choice in Invitation.STATUS_CHOICES]:
        return JsonResponse({"error": "Valid status (accepted, declined, tentative) is required"}, status=400)

    invitation.status = new_status
    invitation.response_date = timezone.now()
    invitation.save()

    # Notify event creator about the response
    creator_message = f"{request.user.username} has {invitation.get_status_display().lower()} your invitation to '{invitation.event.title}'."
    create_notification(invitation.event.creator, invitation.event, 'update', creator_message)
    
    return JsonResponse({
        "message": "Response recorded successfully.",
        "invitation_id": invitation.id,
        "new_status": invitation.get_status_display()
    }, status=200)

@login_required
@require_http_methods(["GET"])
def list_my_invitations_view(request):
    invitations = Invitation.objects.filter(user=request.user).select_related('event', 'event__creator')
    data = []
    for inv in invitations:
        data.append({
            'id': inv.id,
            'event_id': inv.event.id,
            'event_title': inv.event.title,
            'event_creator': inv.event.creator.username,
            'status': inv.status,
            'status_display': inv.get_status_display(),
            'sent_date': inv.sent_date,
            'response_date': inv.response_date
        })
    return JsonResponse(data, safe=False, status=200)

# --- Voting Views ---
@csrf_exempt
@login_required
@require_http_methods(["POST"]) # Could be PUT if you treat it as updating a preference
def vote_time_option_view(request, time_option_id):
    time_option = get_object_or_404(TimeOption, pk=time_option_id)
    event = time_option.event

    # Check if user is invited (optional, but good for restricted voting)
    if not Invitation.objects.filter(event=event, user=request.user, status__in=['pending', 'accepted', 'tentative']).exists() and event.creator != request.user:
        return HttpResponseForbidden("You must be invited or the creator to vote on this event's options.")

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    
    preference = data.get('preference')
    if preference is None or not (0 <= int(preference) <= 5): # Basic validation
        return JsonResponse({"error": "Preference (0-5) is required"}, status=400)

    vote, created = TimeVote.objects.update_or_create(
        user=request.user,
        time_option=time_option,
        defaults={'preference': int(preference)}
    )
    return JsonResponse({
        "message": "Vote recorded." if created else "Vote updated.",
        "vote_id": vote.id,
        "time_option_id": time_option.id,
        "preference": vote.preference
    }, status=201 if created else 200)

@csrf_exempt
@login_required
@require_http_methods(["POST"])
def vote_location_option_view(request, location_option_id):
    location_option = get_object_or_404(LocationOption, pk=location_option_id)
    event = location_option.event
    
    if not Invitation.objects.filter(event=event, user=request.user, status__in=['pending', 'accepted', 'tentative']).exists() and event.creator != request.user:
         return HttpResponseForbidden("You must be invited or the creator to vote on this event's options.")

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
        
    preference = data.get('preference')
    if preference is None or not (0 <= int(preference) <= 5):
        return JsonResponse({"error": "Preference (0-5) is required"}, status=400)

    vote, created = LocationVote.objects.update_or_create(
        user=request.user,
        location_option=location_option,
        defaults={'preference': int(preference)}
    )
    return JsonResponse({
        "message": "Vote recorded." if created else "Vote updated.",
        "vote_id": vote.id,
        "location_option_id": location_option.id,
        "preference": vote.preference
    }, status=201 if created else 200)

# --- Notification Views ---
@login_required
@require_http_methods(["GET"])
def list_my_notifications_view(request):
    notifications = Notification.objects.filter(user=request.user).select_related('event').order_by('-creation_date')
    data = []
    for notif in notifications:
        data.append({
            'id': notif.id,
            'event_id': notif.event.id if notif.event else None,
            'event_title': notif.event.title if notif.event else "General",
            'type': notif.type,
            'type_display': notif.get_type_display(),
            'message': notif.message,
            'read': notif.read,
            'creation_date': notif.creation_date
        })
    return JsonResponse(data, safe=False, status=200)

@csrf_exempt
@login_required
@require_http_methods(["PUT"])
def mark_notification_read_view(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, user=request.user)
    
    # Mark as read
    if not notification.read:
        notification.read = True
        notification.save()
        
    return JsonResponse({"message": "Notification marked as read."}, status=200)

@csrf_exempt
@login_required
@require_http_methods(["POST"]) # Using POST to mark all as read
def mark_all_notifications_read_view(request):
    Notification.objects.filter(user=request.user, read=False).update(read=True)
    return JsonResponse({"message": "All unread notifications marked as read."}, status=200)


# --- Utility View to get users for inviting (example) ---
@login_required
@require_http_methods(["GET"])
def list_users_for_inviting_view(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    # Exclude self and users already invited to this event
    invited_user_ids = Invitation.objects.filter(event=event).values_list('user_id', flat=True)
    
    users = User.objects.exclude(pk=request.user.pk).exclude(id__in=invited_user_ids).values('id', 'username', 'email')
    return JsonResponse(list(users), safe=False, status=200)