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

from .models import (
    Event,
    TimeOption,
    LocationOption,
    Invitation,
    Notification,
    TimeVote,
    LocationVote,
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
