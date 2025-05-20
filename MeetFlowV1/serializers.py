# your_app/serializers.py
from rest_framework import serializers
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Event, TimeOption, LocationOption, Invitation, TimeVote, LocationVote, Notification

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class TimeOptionSerializer(serializers.ModelSerializer):
    event_id = serializers.PrimaryKeyRelatedField(
        queryset=Event.objects.all(), source='event', write_only=True
    )
    class Meta:
        model = TimeOption
        fields = ['id', 'event', 'event_id', 'start_time', 'end_time']
        read_only_fields = ['event'] # event is set based on event_id or context

    def validate(self, data):
        if 'start_time' in data and 'end_time' in data:
            if data['start_time'] >= data['end_time']:
                raise serializers.ValidationError("End time must be after start time.")
        return data

class LocationOptionSerializer(serializers.ModelSerializer):
    event_id = serializers.PrimaryKeyRelatedField(
        queryset=Event.objects.all(), source='event', write_only=True
    )
    class Meta:
        model = LocationOption
        fields = ['id', 'event', 'event_id', 'name', 'address', 'details']
        read_only_fields = ['event']

class InvitationSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='user', write_only=True
    )
    event_id = serializers.PrimaryKeyRelatedField(
        queryset=Event.objects.all(), source='event', write_only=True
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Invitation
        fields = ['id', 'event', 'event_id', 'user', 'user_id', 'user_details', 'status', 'status_display', 'sent_date', 'response_date']
        read_only_fields = ['event', 'sent_date', 'response_date'] # Event set by URL, user by creator

    def update(self, instance, validated_data):
        # When an invitation status is updated, also update response_date
        instance = super().update(instance, validated_data)
        if 'status' in validated_data and validated_data['status'] != 'pending':
            instance.response_date = timezone.now()
            instance.save()
        return instance

class EventSerializer(serializers.ModelSerializer):
    creator = UserSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    # Nested serializers for read operations
    time_options = TimeOptionSerializer(many=True, read_only=True)
    location_options = LocationOptionSerializer(many=True, read_only=True)
    # invitations = InvitationSerializer(many=True, read_only=True) # Can be too verbose, access via separate endpoint

    class Meta:
        model = Event
        fields = [
            'id', 'title', 'description', 'creation_date', 'update_date',
            'status', 'status_display', 'creator', 'time_options', 'location_options'
            # 'invitations' # Add if you want invitations directly in event detail
        ]
        read_only_fields = ['creation_date', 'update_date', 'creator']

class TimeVoteSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    # user_id = serializers.PrimaryKeyRelatedField(source='user', read_only=True) # User is set from request
    time_option_id = serializers.PrimaryKeyRelatedField(
        queryset=TimeOption.objects.all(), source='time_option', write_only=True
    )

    class Meta:
        model = TimeVote
        fields = ['id', 'user', 'user_details', 'time_option', 'time_option_id', 'preference', 'vote_date']
        read_only_fields = ['user', 'vote_date', 'time_option']

    def validate_preference(self, value):
        if not (0 <= value <= 5):
            raise serializers.ValidationError("Preference must be between 0 and 5.")
        return value

class LocationVoteSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    # user_id = serializers.PrimaryKeyRelatedField(source='user', read_only=True)
    location_option_id = serializers.PrimaryKeyRelatedField(
        queryset=LocationOption.objects.all(), source='location_option', write_only=True
    )

    class Meta:
        model = LocationVote
        fields = ['id', 'user', 'user_details', 'location_option', 'location_option_id', 'preference', 'vote_date']
        read_only_fields = ['user', 'vote_date', 'location_option']

    def validate_preference(self, value):
        if not (0 <= value <= 5):
            raise serializers.ValidationError("Preference must be between 0 and 5.")
        return value

class NotificationSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    event_title = serializers.CharField(source='event.title', read_only=True)
    type_display = serializers.CharField(source='get_type_display', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'user_details', 'event', 'event_title', 'type', 'type_display',
            'message', 'read', 'creation_date'
        ]
        read_only_fields = ['user', 'event', 'type', 'message', 'creation_date', 'user_details', 'event_title', 'type_display']