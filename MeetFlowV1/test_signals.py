import pytest
from django.contrib.auth.models import User
from MeetFlowV1.models import Module, UserModuleProgress

@pytest.mark.django_db
def test_user_creation_assigns_intro_module():
    # 1. Create a user
    user = User.objects.create_user(username="newuser", password="password123", email="new@example.com")
    
    # 2. Check if 'Introduction' module was created
    intro_module = Module.objects.filter(title="Introduction").first()
    assert intro_module is not None
    
    # 3. Check if user has progress for that module
    progress = UserModuleProgress.objects.filter(user=user, module=intro_module).first()
    assert progress is not None
    assert progress.status == 'AVAILABLE'

@pytest.mark.django_db
def test_intro_module_is_not_duplicated_if_already_exists():
    # 1. Manually create the module first
    Module.objects.create(title="Introduction", order=0)
    
    # 2. Create multiple users
    User.objects.create_user(username="user1", password="password")
    User.objects.create_user(username="user2", password="password")
    
    # 3. Check count of modules
    assert Module.objects.filter(title="Introduction").count() == 1
    
    # 4. Check each user has progress
    assert UserModuleProgress.objects.filter(module__title="Introduction").count() == 2
