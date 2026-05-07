import pytest
from django.contrib.auth.models import User
from MeetFlowV1.models import Module, Unit, MasterExercise, UserModuleProgress
from MeetFlowV1.services import validate_exercise_response, update_user_progress, generate_ai_lesson

@pytest.mark.django_db
class TestServices:

    @pytest.fixture
    def user(self):
        return User.objects.create_user(username="testuser", password="password")

    @pytest.fixture
    def module(self):
        return Module.objects.create(title="Test Module", order=1)

    @pytest.fixture
    def unit(self, module):
        return Unit.objects.create(module=module, title="Test Unit", order=1)

    @pytest.fixture
    def exercise(self, unit):
        return MasterExercise.objects.create(
            unit=unit,
            type='CODE',
            content={
                "instruction": "Print 42",
                "initial_code": "",
                "expected_output": "42"
            },
            solution={
                "explanation": "The answer to everything"
            },
            order=1
        )

    def test_validate_exercise_response_correct(self, exercise):
        # Using the new payload structure
        payload = {"is_pyodide_success": True}
        is_correct, explanation = validate_exercise_response(exercise.id, payload)
        assert is_correct is True
        assert explanation == "The answer to everything"

    def test_validate_exercise_response_incorrect(self, exercise):
        payload = {"is_pyodide_success": False, "error_log": "Execution error"}
        is_correct, explanation = validate_exercise_response(exercise.id, payload)
        assert is_correct is False
        assert explanation == "Execution error"

    def test_validate_exercise_response_not_found(self):
        is_correct, explanation = validate_exercise_response(999, {"answer": "42"})
        assert is_correct is False
        assert explanation == "Exercise not found."

    def test_validate_exercise_response_flexible_keys(self, exercise):
        # Test 'is_correct' key
        is_correct, _ = validate_exercise_response(exercise.id, {"is_correct": True})
        assert is_correct is True

        # Test 'passed' key
        is_correct, _ = validate_exercise_response(exercise.id, {"passed": True})
        assert is_correct is True

        # Test string 'true'
        is_correct, _ = validate_exercise_response(exercise.id, {"is_pyodide_success": "true"})
        assert is_correct is True

    def test_update_user_progress_completed(self, user, module):
        progress = update_user_progress(user, module.id, exercises_completed=True)
        assert progress.status == 'COMPLETED'
        
        # Check if it created the progress object
        assert UserModuleProgress.objects.filter(user=user, module=module, status='COMPLETED').exists()

    def test_update_user_progress_unlocks_next(self, user, module):
        from MeetFlowV1.models import ModuleDependency
        next_module = Module.objects.create(title="Next Module", order=2)
        ModuleDependency.objects.create(source_node=module, target_node=next_module)
        
        update_user_progress(user, module.id, exercises_completed=True)
        
        # Check if next module is now AVAILABLE
        assert UserModuleProgress.objects.filter(user=user, module=next_module, status='AVAILABLE').exists()

    def test_generate_ai_lesson(self, user, module):
        content = generate_ai_lesson(user, module.id)
        
        assert content['title'] == f"Reinforcement: {module.title}"
        assert 'theory' in content
        assert content['exercise']['correct_answer'] == "Constant practice"
        
        # Check if status updated to STUCK
        progress = UserModuleProgress.objects.get(user=user, module=module)
        assert progress.status == 'STUCK'

    def test_validate_theory_exercise_correct(self, unit):
        exercise = MasterExercise.objects.create(
            unit=unit,
            type='THEORY',
            content={
                "instruction": "Select correct",
                "question": "1+1?",
                "options": {"a": "1", "b": "2"}
            },
            solution={"expected": "b", "explanation": "Correct answer is 2"},
            order=2
        )
        payload = {"answer": "b"}
        is_correct, explanation = validate_exercise_response(exercise.id, payload)
        assert is_correct is True
        assert explanation == "Correct answer is 2"

    def test_validate_theory_exercise_incorrect(self, unit):
        exercise = MasterExercise.objects.create(
            unit=unit,
            type='THEORY',
            content={
                "instruction": "Select correct",
                "question": "1+1?",
                "options": {"a": "1", "b": "2"}
            },
            solution={"expected": "b", "explanation": "Try again"},
            order=3
        )
        payload = {"answer": "a"}
        is_correct, explanation = validate_exercise_response(exercise.id, payload)
        assert is_correct is False
        assert explanation == "Try again"

    def test_validate_theory_exercise_case_insensitive(self, unit):
        exercise = MasterExercise.objects.create(
            unit=unit,
            type='THEORY',
            content={"question": "1+1?", "options": {"a": "1", "b": "2"}},
            solution={"expected": "B", "explanation": "Good"},
            order=4
        )
        # Frontend sends lowercase 'b'
        is_correct, _ = validate_exercise_response(exercise.id, {"answer": "b "})
        assert is_correct is True

    def test_inject_reinforcement_module_mocked(self, user, module, unit, monkeypatch):
        from MeetFlowV1.services import AIService
        from MeetFlowV1.models import AIExercise, Module, Unit as UnitModel
        
        # Mock LLM response for 3 theoretical exercises
        mock_json = {
            "module_title": "Theoretical Reinforcement: Test Module",
            "exercises": [
                {
                    "type": "THEORY",
                    "content": {"question": "Q1", "options": {"a": "1", "b": "2"}},
                    "solution": {"expected": "a", "explanation": "Exp1"}
                },
                {
                    "type": "THEORY",
                    "content": {"question": "Q2", "options": {"a": "1", "b": "2"}},
                    "solution": {"expected": "b", "explanation": "Exp2"}
                },
                {
                    "type": "THEORY",
                    "content": {"question": "Q3", "options": {"a": "1", "b": "2"}},
                    "solution": {"expected": "a", "explanation": "Exp3"}
                }
            ]
        }
        
        def mock_call_llm(*args, **kwargs):
            import json
            return json.dumps(mock_json)
            
        monkeypatch.setattr(AIService, "_call_llm", mock_call_llm)
        
        # Inject reinforcement
        new_module = AIService.inject_reinforcement_module(user, module, "CODE", ["error1"])
        
        assert new_module is not None
        assert new_module.title == "Theoretical Reinforcement: Test Module"
        assert new_module.is_ai_generated is True
        
        # Check if 3 AI exercises were created
        ai_exercises = AIExercise.objects.filter(user=user, type='THEORY')
        assert ai_exercises.count() == 3
        assert ai_exercises.first().solution['expected'] == "a"
        
        # Check if they belong to a unit named "Theoretical Review"
        ai_unit = UnitModel.objects.get(module=new_module)
        assert ai_unit.title == "Theoretical Review"
