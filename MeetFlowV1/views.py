from django.http import (
    JsonResponse,
    HttpResponseForbidden,
    HttpResponseNotFound,
)
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import IntegrityError
from django.forms.models import model_to_dict
from django.db.models import Q
import json

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as rest_status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from .models import (
    Event,
    TimeOption,
    LocationOption,
    Invitation,
    Notification,
    TimeVote,
    LocationVote,
    Module,
    UserModuleProgress,
    Unit,
    MasterExercise,
    AIExercise,
    ModuleDependency,
    UserExerciseAttempt,
)
from .serializers import (
    ModuleSerializer,
    UserModuleProgressSerializer,
    UnitSerializer,
    UserStatsSerializer,
    MasterExerciseSerializer,
    AIExerciseSerializer,
)

from .services import (
    validate_exercise_response,
    is_module_unlocked,
    update_user_progress,
    generate_ai_lesson,
    ExerciseEvaluator,
    AIService,
)

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
            return JsonResponse(
                {
                    "message": "Login successful",
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                    },
                },
                status=200,
            )
        else:
            return JsonResponse({"error": "Invalid credentials"}, status=401)
    return JsonResponse({"error": "Invalid request method"}, status=400)


@require_http_methods(["POST"])
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
            return JsonResponse(
                {
                    "message": "User registered successfully",
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                    },
                },
                status=201,
            )
        except Exception as e:
            return JsonResponse({"error": f"Error creating user: {str(e)}"}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)


@login_required
@require_http_methods(["GET"])
def check_session(request):
    return JsonResponse(
        {
            "authenticated": True,
            "user": {
                "id": request.user.id,
                "username": request.user.username,
                "email": request.user.email,
            },
        },
        status=200,
    )


def create_notification(user, event, type, message):
    Notification.objects.create(user=user, event=event, type=type, message=message)


@login_required
@require_http_methods(["GET"])
def user_search_view(request):
    query = request.GET.get("q", "").strip()
    if not query or len(query) < 2:
        return JsonResponse([], safe=False)

    users = (
        User.objects.filter(Q(username__icontains=query) | Q(email__icontains=query))
        .exclude(pk=request.user.pk)
        .values("id", "username", "email")[:10]
    )

    return JsonResponse(list(users), safe=False)


@csrf_exempt
@login_required
@require_http_methods(["GET", "POST"])
def event_list_create_view(request):
    if request.method == "GET":
        created_events = Event.objects.filter(creator=request.user)
        invited_event_ids = Invitation.objects.filter(
            user=request.user, status="accepted"
        ).values_list("event_id", flat=True)
        invited_events = Event.objects.filter(id__in=invited_event_ids)

        events_qs = (
            (created_events | invited_events)
            .distinct()
            .prefetch_related("time_options")
            .order_by("-creation_date")
        )

        data = []
        for event in events_qs:
            event_data = model_to_dict(
                event, fields=["id", "title", "description", "status", "creation_date"]
            )
            event_data["creator"] = event.creator.username
            event_data["status_display"] = event.get_status_display()

            event_time_options = []

            for toption in event.time_options.all().order_by("start_time"):
                event_time_options.append(
                    {
                        "id": toption.id,
                        "start_time": (
                            toption.start_time.isoformat()
                            if toption.start_time
                            else None
                        ),
                        "end_time": (
                            toption.end_time.isoformat() if toption.end_time else None
                        ),
                    }
                )
            event_data["time_options"] = event_time_options

            data.append(event_data)
        return JsonResponse(data, safe=False, status=200)

    elif request.method == "POST":

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        title = data.get("title")
        description = data.get("description", "")
        status = data.get("status", "draft")

        if not title:
            return JsonResponse({"error": "Title is required"}, status=400)

        event = Event.objects.create(
            title=title, description=description, status=status, creator=request.user
        )

        return JsonResponse(
            {
                "id": event.id,
                "title": event.title,
                "description": event.description,
                "status": event.status,
                "creator": event.creator.username,
                "creation_date": event.creation_date.isoformat(),
                "time_options": [],
                "location_options": [],
            },
            status=201,
        )


@csrf_exempt
@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def event_detail_view(request, event_id):
    event = get_object_or_404(Event, pk=event_id)

    if request.method == "GET":
        event_data = model_to_dict(
            event, exclude=["chosen_time_option", "chosen_location_option"]
        )
        event_data["creator"] = event.creator.username
        event_data["status_display"] = event.get_status_display()
        event_data["is_creator"] = request.user == event.creator

        if event.creation_date:
            event_data["creation_date"] = event.creation_date.isoformat()
        else:
            event_data["creation_date"] = None

        time_options_data = []
        for toption in (
            event.time_options.all()
            .order_by("start_time")
            .prefetch_related("votes__user")
        ):
            option_data = {
                "id": toption.id,
                "start_time": (
                    toption.start_time.isoformat() if toption.start_time else None
                ),
                "end_time": toption.end_time.isoformat() if toption.end_time else None,
                "user_vote": None,
                "vote_count": toption.votes.filter(preference__gt=0).count(),
            }

            user_vote = toption.votes.filter(user=request.user).first()
            if user_vote:
                option_data["user_vote"] = user_vote.preference

            if request.user == event.creator:
                votes_detail = [
                    {
                        "user_id": vote.user.id,
                        "username": vote.user.username,
                        "preference": vote.preference,
                        "voted_at": (
                            vote.voted_at.isoformat() if vote.voted_at else None
                        ),
                    }
                    for vote in toption.votes.filter(preference__gt=0)
                ]
                option_data["all_votes"] = votes_detail

            time_options_data.append(option_data)
        event_data["time_options"] = time_options_data

        location_options_data = []
        for loption in event.location_options.all().prefetch_related("votes__user"):
            option_data = {
                "id": loption.id,
                "name": loption.name,
                "address": loption.address,
                "details": loption.details,
                "user_vote": None,
                "vote_count": loption.votes.filter(preference__gt=0).count(),
            }

            user_vote = loption.votes.filter(user=request.user).first()
            if user_vote:
                option_data["user_vote"] = user_vote.preference

            if request.user == event.creator:
                votes_detail = [
                    {
                        "user_id": vote.user.id,
                        "username": vote.user.username,
                        "preference": vote.preference,
                        "voted_at": (
                            vote.voted_at.isoformat() if vote.voted_at else None
                        ),
                    }
                    for vote in loption.votes.filter(preference__gt=0)
                ]
                option_data["all_votes"] = votes_detail

            location_options_data.append(option_data)
        event_data["location_options"] = location_options_data

        invitations_data = [
            {
                "id": inv.id,
                "user_id": inv.user.id,
                "username": inv.user.username,
                "status": inv.status,
                "status_display": inv.get_status_display(),
            }
            for inv in event.invitations.select_related("user").all()
        ]
        event_data["invitations"] = invitations_data

        return JsonResponse(event_data, status=200)

    if event.creator != request.user:
        return HttpResponseForbidden("You are not authorized to modify this event.")

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        event.title = data.get("title", event.title)
        event.description = data.get("description", event.description)
        new_status = data.get("status", event.status)

        if new_status != event.status and new_status in [
            choice[0] for choice in Event.STATUS_CHOICES
        ]:
            event.status = new_status

            if new_status == "confirmed":
                message = f"The event '{event.title}' has been confirmed."
                notification_type = "confirmation"
            elif new_status == "cancelled":
                message = f"The event '{event.title}' has been cancelled."
                notification_type = "cancellation"
            elif new_status in ["planning", "completed"]:
                message = f"The event '{event.title}' has been updated to {event.get_status_display()}."
                notification_type = "update"
            else:
                message = None
                notification_type = None

            if message and notification_type:
                for invitation in event.invitations.filter(status="accepted"):
                    create_notification(
                        invitation.user, event, notification_type, message
                    )

        event.save()

        updated_data = model_to_dict(event)
        updated_data["creator"] = event.creator.username
        updated_data["status_display"] = event.get_status_display()
        return JsonResponse(updated_data, status=200)

    elif request.method == "DELETE":
        event.delete()
        return JsonResponse({"message": "Event deleted successfully"}, status=204)


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

    start_time = data.get("start_time")
    end_time = data.get("end_time")

    if not start_time or not end_time:
        return JsonResponse(
            {"error": "Start time and end time are required"}, status=400
        )

    try:

        time_option = TimeOption.objects.create(
            event=event, start_time=start_time, end_time=end_time
        )
        return JsonResponse(model_to_dict(time_option), status=201)
    except Exception as e:
        return JsonResponse(
            {"error": f"Invalid date format or data: {str(e)}"}, status=400
        )


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

    name = data.get("name")
    address = data.get("address")
    details = data.get("details", "")

    if not name or not address:
        return JsonResponse({"error": "Name and address are required"}, status=400)

    location_option = LocationOption.objects.create(
        event=event, name=name, address=address, details=details
    )
    return JsonResponse(model_to_dict(location_option), status=201)


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

    user_id_to_invite = data.get("user_id")
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
            event=event, user=user_to_invite, defaults={"status": "pending"}
        )
        if not created and invitation.status != "pending":
            return JsonResponse(
                {
                    "message": f"User already invited and has status: {invitation.get_status_display()}"
                },
                status=200,
            )
        elif not created:
            return JsonResponse(
                {"message": "User already has a pending invitation."}, status=200
            )

        create_notification(
            user_to_invite,
            event,
            "invitation",
            f"You have been invited to the event: '{event.title}' by {request.user.username}.",
        )
        return JsonResponse(
            {
                "message": "Invitation sent successfully.",
                "invitation_id": invitation.id,
                "user": user_to_invite.username,
                "status": invitation.get_status_display(),
            },
            status=201 if created else 200,
        )
    except IntegrityError:
        return JsonResponse(
            {"error": "Invitation already exists or other integrity error."}, status=400
        )


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

    new_status = data.get("status")
    if not new_status or new_status not in [
        choice[0] for choice in Invitation.STATUS_CHOICES
    ]:
        return JsonResponse(
            {"error": "Valid status (accepted, declined, tentative) is required"},
            status=400,
        )

    invitation.status = new_status
    invitation.response_date = timezone.now()
    invitation.save()

    creator_message = f"{request.user.username} has {invitation.get_status_display().lower()} your invitation to '{invitation.event.title}'."
    create_notification(
        invitation.event.creator, invitation.event, "update", creator_message
    )

    return JsonResponse(
        {
            "message": "Response recorded successfully.",
            "invitation_id": invitation.id,
            "new_status": invitation.get_status_display(),
        },
        status=200,
    )


@login_required
@require_http_methods(["GET"])
def list_my_invitations_view(request):
    invitations_qs = (
        Invitation.objects.filter(user=request.user)
        .select_related("event", "event__creator")
        .prefetch_related(
            "event__time_options__votes", "event__location_options__votes"
        )
        .order_by("-sent_date")
    )

    data = []
    for inv in invitations_qs:
        event_time_options_data = []

        for toption in inv.event.time_options.all().order_by("start_time"):
            user_vote_obj = None

            for vote in toption.votes.all():
                if vote.user_id == request.user.id:
                    user_vote_obj = vote
                    break

            event_time_options_data.append(
                {
                    "id": toption.id,
                    "start_time": (
                        toption.start_time.isoformat() if toption.start_time else None
                    ),
                    "end_time": (
                        toption.end_time.isoformat() if toption.end_time else None
                    ),
                    "user_vote": user_vote_obj.preference if user_vote_obj else None,
                }
            )

        event_location_options_data = []
        for loption in inv.event.location_options.all():
            user_vote_obj = None
            for vote in loption.votes.all():
                if vote.user_id == request.user.id:
                    user_vote_obj = vote
                    break

            event_location_options_data.append(
                {
                    "id": loption.id,
                    "name": loption.name,
                    "address": loption.address,
                    "details": loption.details,
                    "user_vote": user_vote_obj.preference if user_vote_obj else None,
                }
            )

        data.append(
            {
                "id": inv.id,
                "status": inv.status,
                "status_display": inv.get_status_display(),
                "sent_date": inv.sent_date.isoformat() if inv.sent_date else None,
                "response_date": (
                    inv.response_date.isoformat() if inv.response_date else None
                ),
                "event": {
                    "id": inv.event.id,
                    "title": inv.event.title,
                    "description": inv.event.description,
                    "creator_username": inv.event.creator.username,
                    "status_display": inv.event.get_status_display(),
                    "status": inv.event.status,
                    "creation_date": inv.event.creation_date.isoformat(),
                    "time_options": event_time_options_data,
                    "location_options": event_location_options_data,
                },
            }
        )
    return JsonResponse(data, safe=False, status=200)


@login_required
@require_http_methods(["GET"])
def list_my_notifications_view(request):
    notifications = (
        Notification.objects.filter(user=request.user, read=False)
        .select_related("event")
        .order_by("-creation_date")
    )

    data = []
    for notif in notifications:
        data.append(
            {
                "id": notif.id,
                "event_id": notif.event.id if notif.event else None,
                "event_title": notif.event.title if notif.event else "General",
                "type": notif.type,
                "type_display": notif.get_type_display(),
                "message": notif.message,
                "read": notif.read,
                "creation_date": notif.creation_date.isoformat(),
            }
        )
    return JsonResponse(data, safe=False, status=200)


@csrf_exempt
@login_required
@require_http_methods(["PUT"])
def mark_notification_read_view(request, notification_id):
    notification = get_object_or_404(
        Notification, pk=notification_id, user=request.user
    )

    if not notification.read:
        notification.read = True
        notification.save()

    return JsonResponse({"message": "Notification marked as read."}, status=200)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def mark_all_notifications_read_view(request):
    Notification.objects.filter(user=request.user, read=False).update(read=True)
    return JsonResponse(
        {"message": "All unread notifications marked as read."}, status=200
    )


@login_required
@require_http_methods(["GET"])
def list_users_for_inviting_view(request, event_id):
    event = get_object_or_404(Event, pk=event_id)

    invited_user_ids = Invitation.objects.filter(event=event).values_list(
        "user_id", flat=True
    )

    users = (
        User.objects.exclude(pk=request.user.pk)
        .exclude(id__in=invited_user_ids)
        .values("id", "username", "email")
    )
    return JsonResponse(list(users), safe=False, status=200)


from django.db.models import Q
from .models import Event, Invitation, TimeOption


@login_required
@require_http_methods(["GET"])
def event_search_view(request):
    query = request.GET.get("q", "").strip()

    if not query or len(query) < 2:
        return JsonResponse([], safe=False)

    user = request.user

    created_events_qs = Event.objects.filter(creator=user)

    invited_event_ids = Invitation.objects.filter(
        user=user, status__in=["accepted", "pending", "tentative"]
    ).values_list("event_id", flat=True)
    invited_events_qs = Event.objects.filter(id__in=invited_event_ids)

    accessible_events_qs = (created_events_qs | invited_events_qs).distinct()

    search_results_qs = (
        accessible_events_qs.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
        .prefetch_related("time_options")
        .order_by("-creation_date")[:10]
    )

    results_data = []
    for event in search_results_qs:
        data_item = {
            "id": event.id,
            "title": event.title,
            "description": event.description,
        }

        first_time_option = event.time_options.order_by("start_time").first()
        if first_time_option and first_time_option.start_time:
            data_item["start_time"] = first_time_option.start_time.isoformat()
        else:
            data_item["start_time"] = None

        results_data.append(data_item)

    return JsonResponse(results_data, safe=False)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def vote_on_time_option_view(request, option_id):
    time_option = get_object_or_404(TimeOption, pk=option_id)
    event = time_option.event

    try:
        invitation = Invitation.objects.get(event=event, user=request.user)
        if invitation.status not in ["accepted", "tentative"]:
            return JsonResponse(
                {"error": "You must accept or be tentative to vote."}, status=403
            )
    except Invitation.DoesNotExist:
        return JsonResponse({"error": "You are not invited to this event."}, status=403)

    if event.status not in ["draft", "planning"]:
        return JsonResponse(
            {
                "error": f"Voting is not allowed for events in '{event.get_status_display()}' status."
            },
            status=403,
        )

    try:
        data = json.loads(request.body)
        preference = data.get("preference")
        if not isinstance(preference, int):
            return JsonResponse({"error": "Invalid preference value."}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    vote, created = TimeVote.objects.update_or_create(
        user=request.user,
        time_option=time_option,
        event=event,
        defaults={"preference": preference, "voted_at": timezone.now()},
    )

    return JsonResponse(
        {
            "message": (
                "Vote recorded successfully."
                if created
                else "Vote updated successfully."
            ),
            "vote_id": vote.id,
            "time_option_id": time_option.id,
            "preference": vote.preference,
        },
        status=201 if created else 200,
    )


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def vote_on_location_option_view(request, option_id):
    location_option = get_object_or_404(LocationOption, pk=option_id)
    event = location_option.event

    try:
        invitation = Invitation.objects.get(event=event, user=request.user)
        if invitation.status not in ["accepted", "tentative"]:
            return JsonResponse(
                {"error": "You must accept or be tentative to vote."}, status=403
            )
    except Invitation.DoesNotExist:
        return JsonResponse({"error": "You are not invited to this event."}, status=403)

    if event.status not in ["draft", "planning"]:
        return JsonResponse(
            {
                "error": f"Voting is not allowed for events in '{event.get_status_display()}' status."
            },
            status=403,
        )

    try:
        data = json.loads(request.body)
        preference = data.get("preference")
        if not isinstance(preference, int):
            return JsonResponse({"error": "Invalid preference value."}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    vote, created = LocationVote.objects.update_or_create(
        user=request.user,
        location_option=location_option,
        event=event,
        defaults={"preference": preference, "voted_at": timezone.now()},
    )

    return JsonResponse(
        {
            "message": (
                "Vote recorded successfully."
                if created
                else "Vote updated successfully."
            ),
            "vote_id": vote.id,
            "location_option_id": location_option.id,
            "preference": vote.preference,
        },
        status=201 if created else 200,
    )


@login_required
@require_http_methods(["GET"])
def event_votes_summary_view(request, event_id):
    event = get_object_or_404(Event, pk=event_id)

    if event.creator != request.user:
        return HttpResponseForbidden("Only the event creator can view vote summaries.")

    time_options_votes = []
    for toption in event.time_options.all().prefetch_related("votes__user"):
        votes_data = []
        for vote in toption.votes.filter(preference__gt=0):
            votes_data.append(
                {
                    "user_id": vote.user.id,
                    "username": vote.user.username,
                    "preference": vote.preference,
                    "voted_at": vote.voted_at.isoformat(),
                }
            )
        time_options_votes.append(
            {
                "id": toption.id,
                "start_time": (
                    toption.start_time.isoformat() if toption.start_time else None
                ),
                "end_time": toption.end_time.isoformat() if toption.end_time else None,
                "votes": votes_data,
                "vote_count": len(votes_data),
            }
        )

    location_options_votes = []
    for loption in event.location_options.all().prefetch_related("votes__user"):
        votes_data = []
        for vote in loption.votes.filter(preference__gt=0):
            votes_data.append(
                {
                    "user_id": vote.user.id,
                    "username": vote.user.username,
                    "preference": vote.preference,
                    "voted_at": vote.voted_at.isoformat(),
                }
            )
        location_options_votes.append(
            {
                "id": loption.id,
                "name": loption.name,
                "address": loption.address,
                "details": loption.details,
                "votes": votes_data,
                "vote_count": len(votes_data),
            }
        )

    return JsonResponse(
        {
            "event_id": event.id,
            "event_title": event.title,
            "time_options_summary": time_options_votes,
            "location_options_summary": location_options_votes,
        },
        status=200,
    )

class MapProgressView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # 1. Get modules: master (user=None) + user-specific AI modules
        modules_qs = Module.objects.filter(Q(user=None) | Q(user=request.user))
        serializer = ModuleSerializer(modules_qs, many=True, context={'request': request})
        
        # Pre-process modules
        master_modules = {str(m['id']): m for m in serializer.data if not m['is_ai_generated']}
        ai_modules = [m for m in serializer.data if m['is_ai_generated']]
        
        # Mapping for reinforcement types to sub-indices
        TYPE_INDEX = {
            'BLANKS': 1,
            'PARSONS': 2,
            'DEBUG': 3,
            'CODE': 4
        }
        
        # Mapping from database ID to display ID (e.g., "2" -> "2", "50" -> "2.1")
        id_map = {}
        for mod_id, mod in master_modules.items():
            id_map[mod_id] = mod_id  # Master nodes keep their ID as display ID (usually their order or real ID)
            # If the user wants master nodes to be numbered by their order:
            # id_map[mod_id] = str(mod['order'])
        
        for ai_mod in ai_modules:
            source_id = str(ai_mod.get('source_module'))
            sub_idx = TYPE_INDEX.get(ai_mod.get('reinforcement_type'), 0)
            # Display ID format: "SourceID.SubIndex"
            id_map[str(ai_mod['id'])] = f"{source_id}.{sub_idx}"

        # 2. Format nodes for React Flow
        nodes = []
        
        # Add master nodes
        for mod_id, mod in master_modules.items():
            nodes.append(self._format_node(mod, id_map[mod_id]))

        # Add AI nodes with dynamic positioning
        for ai_mod in ai_modules:
            source_db_id = str(ai_mod.get('source_module'))
            if source_db_id in master_modules:
                source_mod = master_modules[source_db_id]
                
                # Find the next master module(s)
                next_master_deps = ModuleDependency.objects.filter(source_node_id=source_db_id, user=None)
                if next_master_deps.exists():
                    target_db_id = str(next_master_deps.first().target_node_id)
                    if target_db_id in master_modules:
                        target_mod = master_modules[target_db_id]
                        
                        mid_x = (source_mod['position_x'] + target_mod['position_x']) / 2
                        mid_y = (source_mod['position_y'] + target_mod['position_y']) / 2
                        
                        offset_map = {'BLANKS': -60, 'PARSONS': -20, 'DEBUG': 20, 'CODE': 60}
                        offset_y = offset_map.get(ai_mod.get('reinforcement_type'), 0)
                        
                        ai_mod['position_x'] = mid_x
                        ai_mod['position_y'] = mid_y + offset_y
                else:
                    ai_mod['position_x'] = source_mod['position_x'] + 100
                    ai_mod['position_y'] = source_mod['position_y'] + 50

            nodes.append(self._format_node(ai_mod, id_map[str(ai_mod['id'])]))

        # 3. Build connections (edges for React Flow) 
        connections = []
        dependencies = ModuleDependency.objects.filter(Q(user=None) | Q(user=request.user))
        
        # Identify direct master edges bypassed by AI
        bypassed_edges = {}
        for ai_mod in ai_modules:
            source_db_id = str(ai_mod.get('source_module'))
            if source_db_id:
                if source_db_id not in bypassed_edges:
                    bypassed_edges[source_db_id] = set()
                
                ai_outgoing = ModuleDependency.objects.filter(source_node_id=ai_mod['id'], user=request.user)
                for out_dep in ai_outgoing:
                    bypassed_edges[source_db_id].add(str(out_dep.target_node_id))

        for dep in dependencies:
            source_db_id = str(dep.source_node_id)
            target_db_id = str(dep.target_node_id)
            
            # Skip direct master edges if an AI bypass exists
            if dep.user is None and source_db_id in bypassed_edges and target_db_id in bypassed_edges[source_db_id]:
                continue

            # Map DB IDs to Display IDs for the edge
            display_source = id_map.get(source_db_id)
            display_target = id_map.get(target_db_id)
            
            if not display_source or not display_target:
                continue

            edge_id = f"e{display_source}-{display_target}"
            is_ai_edge = dep.user is not None
            
            label = None
            if is_ai_edge:
                target_mod = Module.objects.filter(id=dep.target_node_id).first()
                if target_mod and target_mod.is_ai_generated:
                    label = f"Reinforcement: {target_mod.reinforcement_type}"
                else:
                    label = "AI Reinforcement"

            connections.append({
                'id': edge_id,
                'source': display_source,
                'target': display_target,
                'animated': is_ai_edge,
                'style': {'stroke': '#7c3aed', 'strokeWidth': 2} if is_ai_edge else {'stroke': '#94a3b8'},
                'label': label
            })
        
        return Response({
            'nodes': nodes,
            'edges': connections
        })

    def _format_node(self, mod, display_id):
        return {
            'id': display_id,
            'type': 'moduleNode',
            'position': {
                'x': mod.get('position_x', 0),
                'y': mod.get('position_y', 0)
            },
            'data': {
                'db_id': mod['id'], # Keep original DB ID for API calls
                'label': mod['title'],
                'display_id': display_id, # The "2.1" string
                'status': mod['status'],
                'completion_percentage': mod.get('completion_percentage', 0),
                'type': 'ai' if mod['is_ai_generated'] else 'master',
                'reinforcement_type': mod.get('reinforcement_type')
            }
        }

class ModuleLessonsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, module_id):
        unit = get_object_or_404(Unit, module_id=module_id)
        exercises = MasterExercise.objects.filter(unit=unit).order_by('order')
        serializer = MasterExerciseSerializer(exercises, many=True, context={'request': request})
        return Response(serializer.data)

class ExerciseSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, exercise_id):
        user_response = request.data.get('response')
        is_ai = request.data.get('is_ai', False)
        
        if is_ai:
            exercise = get_object_or_404(AIExercise, id=exercise_id)
            attempt, created = UserExerciseAttempt.objects.get_or_create(
                user=request.user, ai_exercise=exercise
            )
            unit = exercise.source_unit
        else:
            exercise = get_object_or_404(MasterExercise, id=exercise_id)
            attempt, created = UserExerciseAttempt.objects.get_or_create(
                user=request.user, master_exercise=exercise
            )
            unit = exercise.unit
            
        module_id = unit.module_id
        is_correct, explanation = validate_exercise_response(exercise_id, request.data, is_ai=is_ai)
        
        if is_correct:
            attempt.is_completed = True
            attempt.save()
            
            # Rigorous check: verify if ALL exercises of the current type (Master or AI) 
            # in this unit are completed before marking the module as COMPLETED.
            if is_ai:
                total = AIExercise.objects.filter(source_unit=unit, user=request.user).count()
                completed = AIExercise.objects.filter(
                    source_unit=unit,
                    user=request.user,
                    attempts__user=request.user,
                    attempts__is_completed=True
                ).distinct().count()
            else:
                total = MasterExercise.objects.filter(unit=unit).count()
                completed = MasterExercise.objects.filter(
                    unit=unit,
                    attempts__user=request.user,
                    attempts__is_completed=True
                ).distinct().count()

            if total > 0 and completed >= total:
                update_user_progress(request.user, module_id, exercises_completed=True)
            
            return Response({
                'correct': True,
                'message': 'Correct!',
                'explanation': explanation,
                'is_completed': True
            })
        else:
            attempt.attempts_count += 1
            attempt.save()
            return Response({
                'correct': False,
                'message': 'Incorrect answer.',
                'explanation': explanation,
                'suggest_ai': True,
                'is_completed': False
            })

class AIGenerateLessonView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, module_id):
        content = generate_ai_lesson(request.user, module_id)
        return Response(content)

class UnitSessionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get unit exercises session",
        description="Returns 8 exercises for the unit. Prioritizes AI-generated adaptive exercises if available.",
        responses={200: MasterExerciseSerializer(many=True)}
    )
    def get(self, request, unit_id):
        unit = get_object_or_404(Unit, id=unit_id)
        
        # Security check: Is the module unlocked for this user?
        if not is_module_unlocked(request.user, unit.module):
            return Response(
                {"error": "This module is locked. Complete previous modules first."}, 
                status=403
            )

        # 1. Check if there are exercises in AIExercise first
        ai_exercises = AIExercise.objects.filter(
            user=request.user, source_unit=unit
        )
        if ai_exercises.exists():
            serializer = AIExerciseSerializer(ai_exercises, many=True, context={'request': request})
            return Response(serializer.data)

        # 2. Otherwise return the exercises of the unit
        exercises = MasterExercise.objects.filter(unit_id=unit_id).order_by('order')[:8]
        serializer = MasterExerciseSerializer(exercises, many=True, context={'request': request})
        return Response(serializer.data)

class ExerciseCheckView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Submit exercise response",
        description="Validates the user's response. If it fails 3 times, triggers AI reinforcement and marks progress as STUCK.",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request, exercise_id):
        user_payload = request.data
        is_ai = user_payload.get('is_ai', False)
        
        if is_ai:
            exercise = get_object_or_404(AIExercise, id=exercise_id)
            unit = exercise.source_unit
            attempt, created = UserExerciseAttempt.objects.get_or_create(
                user=request.user, ai_exercise=exercise
            )
        else:
            exercise = get_object_or_404(MasterExercise, id=exercise_id)
            unit = exercise.unit
            attempt, created = UserExerciseAttempt.objects.get_or_create(
                user=request.user, master_exercise=exercise
            )
        
        # Security check: Is the module unlocked for this user?
        if not is_module_unlocked(request.user, unit.module):
            return Response(
                {"error": "This module is locked. You cannot submit exercises for it."}, 
                status=403
            )
        
        # Evaluate using new payload structure
        is_correct, explanation = ExerciseEvaluator.evaluate(exercise, user_payload)
        
        if is_correct:
            attempt.is_completed = True
            attempt.save()
            
            # Rigorous check: verify if ALL exercises of the current type (Master or AI) 
            # in this unit are completed before marking the module as COMPLETED.
            if is_ai:
                total = AIExercise.objects.filter(source_unit=unit, user=request.user).count()
                completed = AIExercise.objects.filter(
                    source_unit=unit,
                    user=request.user,
                    attempts__user=request.user,
                    attempts__is_completed=True
                ).distinct().count()
            else:
                total = MasterExercise.objects.filter(unit=unit).count()
                completed = MasterExercise.objects.filter(
                    unit=unit,
                    attempts__user=request.user,
                    attempts__is_completed=True
                ).distinct().count()
            
            if total > 0 and completed >= total:
                update_user_progress(request.user, unit.module_id, exercises_completed=True)

            return Response({
                'correct': True,
                'message': 'Correct!',
                'explanation': explanation,
                'is_completed': True
            })
        else:
            attempt.attempts_count += 1
            if not attempt.error_log:
                attempt.error_log = []
            
            # Store the answer or the error_log in the attempt's history
            attempt.error_log.append(
                user_payload.get('answer') or 
                user_payload.get('response') or 
                user_payload.get('error_log')
            )
            
            ai_feedback = ""
            if attempt.attempts_count >= 3:
                attempt.is_flagged_for_ai = True
                
                # Check current status: if COMPLETED, it's review mode, don't mark STUCK or generate module
                current_progress = UserModuleProgress.objects.filter(
                    user=request.user, 
                    module=unit.module
                ).first()
                
                is_review_mode = current_progress and current_progress.status == 'COMPLETED'
                
                if not is_review_mode:
                    # Mark as STUCK in progress
                    update_user_progress(request.user, unit.module_id, is_stuck=True)
                
                ai_feedback = AIService.get_adaptive_feedback(exercise, attempt.error_log)
                
                # ONLY generate reinforcement modules for MASTER exercises
                # to avoid infinite loops of AI generating AI.
                # AND only if not in review mode.
                if not is_ai and not is_review_mode:
                    # Generate adaptive reinforcement module and inject in graph
                    AIService.inject_reinforcement_module(request.user, unit.module, exercise.type, attempt.error_log)
            
            attempt.save()
            return Response({
                'correct': False,
                'message': 'Incorrect.',
                'explanation': explanation,
                'ai_feedback': ai_feedback,
                'flagged_for_ai': attempt.is_flagged_for_ai
            })


class UserStatsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get user learning stats",
        description="Returns completion stats, total attempts, and identified weak points for the learning path.",
        responses={200: UserStatsSerializer}
    )
    def get(self, request):
        attempts = UserExerciseAttempt.objects.filter(user=request.user)
        completed_master = attempts.filter(master_exercise__isnull=False, is_completed=True).count()
        completed_ai = attempts.filter(ai_exercise__isnull=False, is_completed=True).count()
        
        total_attempts = sum(a.attempts_count for a in attempts) + completed_master + completed_ai
        
        # Simple weak points logic
        weak_points = []
        struggling = attempts.filter(attempts_count__gt=2)
        for s in struggling:
            ex_type = s.master_exercise.type if s.master_exercise else s.ai_exercise.type
            unit_title = s.master_exercise.unit.title if s.master_exercise else s.ai_exercise.source_unit.title
            weak_points.append(f"Difficulty with {ex_type} in {unit_title}")

        # Learning path progress should be based on curriculum (MasterExercises)
        total_curriculum = MasterExercise.objects.count()
        curriculum_progress = (completed_master / total_curriculum * 100) if total_curriculum > 0 else 0
        
        data = {
            'completed_exercises': completed_master + completed_ai,
            'completed_master': completed_master,
            'completed_ai': completed_ai,
            'total_attempts': total_attempts,
            'weak_points': list(set(weak_points))[:3],
            'learning_path_progress': round(curriculum_progress, 2)
        }
        return Response(data)

