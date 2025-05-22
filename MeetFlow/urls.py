"""
URL configuration for MeetFlow project.

The `urlpatterns` list routes URLs to  For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from MeetFlowV1.views import *

urlpatterns = [
    path('admin/', admin.site.urls),

    # Auth
    path("api/login/", login_view, name="login"),
    path("api/register/", register_view, name="register"),
    path("api/logout/", logout_view, name="logout"),
    path("api/check_session/", check_session, name="check_session"),

    # Events
    path("api/events/", event_list_create_view, name="event_list_create"),
    path("api/users/search/", user_search_view, name="user_search"),
    path('api/events/search/', event_search_view, name='event_search'),
    path("api/events/<int:event_id>/", event_detail_view, name="event_detail"),

    # Event Options (add only by creator)
    path("api/events/<int:event_id>/time_options/", add_time_option_view, name="add_time_option"),
    path("api/events/<int:event_id>/location_options/", add_location_option_view, name="add_location_option"),

    # Invitations
    path("api/events/<int:event_id>/invite/", invite_user_view, name="invite_user"),
    path("api/invitations/<int:invitation_id>/respond/", respond_invitation_view, name="respond_invitation"),
    path("api/my_invitations/", list_my_invitations_view, name="my_invitations"),
    
    # User listing for inviting
    path("api/events/<int:event_id>/potential_invitees/", list_users_for_inviting_view, name="list_potential_invitees"),

     # Voting
    path("api/time_options/<int:option_id>/vote/", vote_on_time_option_view, name="vote_time_option"),
    path("api/location_options/<int:option_id>/vote/", vote_on_location_option_view, name="vote_location_option"),
    path("api/events/<int:event_id>/votes/", event_votes_summary_view, name="event_votes_summary"), # Para que el creador vea los votos
    
    # Notifications
    path("api/notifications/", list_my_notifications_view, name="my_notifications"),
    path("api/notifications/<int:notification_id>/read/", mark_notification_read_view, name="mark_notification_read"),
    path("api/notifications/mark_all_read/", mark_all_notifications_read_view, name="mark_all_notifications_read"),
]
