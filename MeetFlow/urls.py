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
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from MeetFlowV1.views import *

urlpatterns = [
    path('admin/', admin.site.urls),

    # API Schema & Docs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/docs/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Auth
    path("api/login/", login_view, name="login"),
    path("api/register/", register_view, name="register"),
    path("api/logout/", logout_view, name="logout"),
    path("api/check_session/", check_session, name="check_session"),

    # Education platform
    path("api/map/", MapProgressView.as_view(), name="map_progress"),
    path("api/module/<int:module_id>/lessons/", ModuleLessonsView.as_view(), name="module_lessons"),
    path("api/exercise/<int:exercise_id>/submit/", ExerciseSubmitView.as_view(), name="exercise_submit"),
    path("api/module/<int:module_id>/ai_reinforcement/", AIGenerateLessonView.as_view(), name="ai_reinforcement"),

    # Adaptive Learning V2
    path("api/units/<int:unit_id>/session/", UnitSessionView.as_view(), name="unit_session"),
    path("api/exercises/<int:exercise_id>/check/", ExerciseCheckView.as_view(), name="exercise_check"),
    path("api/user/stats/", UserStatsView.as_view(), name="user_stats"),
]
