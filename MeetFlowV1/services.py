import openai
import json
import os
from django.db import transaction
from django.db.models import Q
from .models import Module, UserModuleProgress, Unit, MasterExercise, AIExercise, UserExerciseAttempt, ModuleDependency

class ExerciseEvaluator:
    @staticmethod
    def _to_bool(val):
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ['true', '1', 't', 'y', 'yes']
        return bool(val)

    @staticmethod
    def evaluate(exercise, user_payload):
        """
        Evaluates the user response based on the exercise type and Pyodide results.
        user_payload: { "answer": ..., "is_pyodide_success": bool, "error_log": string }
        """
        exercise_type = exercise.type
        # Be flexible with the key (accept 'answer' or 'response' for backward compatibility)
        user_response = user_payload.get('answer') or user_payload.get('response')
        
        if exercise_type == 'CODE':
            # Delegate validation to Pyodide result from frontend
            # We accept multiple keys for flexibility (is_pyodide_success, is_correct, passed)
            is_correct = (
                ExerciseEvaluator._to_bool(user_payload.get('is_pyodide_success', False)) or 
                ExerciseEvaluator._to_bool(user_payload.get('is_correct', False)) or 
                ExerciseEvaluator._to_bool(user_payload.get('passed', False))
            )
            explanation = exercise.solution.get('explanation', 'Code verified successfully!') if is_correct else user_payload.get('error_log', 'Execution error in Pyodide.')
            return is_correct, explanation

        # Standard validations for other types
        if exercise_type == 'BLANKS':
            return ExerciseEvaluator._evaluate_fill_blanks(exercise.content, exercise.solution, user_response)
        elif exercise_type == 'PARSONS':
            return ExerciseEvaluator._evaluate_parsons(exercise.content, exercise.solution, user_response)
        elif exercise_type == 'DEBUG':
            return ExerciseEvaluator._evaluate_debugging(exercise.content, exercise.solution, user_response)
        elif exercise_type == 'THEORY':
            return ExerciseEvaluator._evaluate_theory(exercise.content, exercise.solution, user_response)
        
        return False, "Unknown exercise type"

    @staticmethod
    def _evaluate_theory(content, solution, user_response):
        """
        Evaluates a multiple choice theoretical exercise.
        """
        expected = solution.get('expected', '').strip().lower()
        if not user_response:
            return False, "No answer provided."
            
        is_correct = str(user_response).strip().lower() == expected
        explanation = solution.get('explanation', 'Good job!')
        
        return is_correct, explanation

    @staticmethod
    def _evaluate_fill_blanks(content, solution, user_response):
        if user_response is None:
            return False, "No answer provided."
        # JSON structure: solution: {"expected": "if"}
        expected = solution.get('expected')
        correct = str(user_response).strip() == str(expected).strip()
        return correct, solution.get('explanation', '')

    @staticmethod
    def _evaluate_parsons(content, solution, user_response):
        if user_response is None:
            return False, "No answer provided."
        # JSON structure: solution: {"correct_order": ["b1", "b2", "b3", "b4"]}
        # user_response: ["b1", "b2", "b3", "b4"]
        correct = user_response == solution.get('correct_order')
        return correct, solution.get('explanation', '')

    @staticmethod
    def _evaluate_debugging(content, solution, user_response):
        if user_response is None:
            return False, "No answer provided."
        # JSON structure: solution: {"error_line_id": "l2"}
        # user_response: "l2"
        correct = str(user_response) == str(solution.get('error_line_id'))
        return correct, solution.get('explanation', '')

    # _evaluate_code is removed as logic is now in evaluate() for CODE type

class AIService:
    @staticmethod
    def _call_llm(messages, response_format_json=False):
        """
        Internal helper to call the LLM using httpx for maximum flexibility.
        Handles optional model and no-api-key scenarios better than the standard library.
        """
        import httpx
        
        base_url = os.getenv("OPENAI_API_BASE_URL") or "https://api.openai.com/v1"
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL")
        
        # Clean base_url
        if base_url.endswith("/chat/completions"):
            base_url = base_url.replace("/chat/completions", "")
        elif base_url.endswith("/chat/completions/"):
            base_url = base_url.replace("/chat/completions/", "")
        
        url = f"{base_url.rstrip('/')}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        payload = {
            "messages": messages,
        }
        if model:
            payload["model"] = model
        
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}
            
        print(f"[AI DEBUG] Calling {url} | Model: {model or 'default'} | API Key: {'Set' if api_key else 'Not Set'}")
        
        try:
            with httpx.Client(trust_env=False) as client:
                response = client.post(url, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status()
            data = response.json()
            return data['choices'][0]['message']['content']
        except Exception as e:
            error_detail = str(e)
            if hasattr(e, 'response') and e.response is not None:
                error_detail += f" | Body: {e.response.text}"
            raise Exception(f"LLM Call failed: {error_detail}")

    @staticmethod
    def get_adaptive_feedback(exercise, user_error_log):
        """
        Calls the LLM to get personalized feedback based on error history.
        """
        try:
            prompt = f"""
            The user is failing this exercise: {exercise.type}
            Content: {exercise.content}
            Recent errors: {user_error_log[-3:]}
            
            Provide short (max 2 sentences) and encouraging feedback in English.
            Explain the concept briefly without giving the answer directly.
            """
            return AIService._call_llm([{"role": "user", "content": prompt}])
        except Exception as e:
            print(f"[AI DEBUG] Feedback generation failed: {str(e)}")
            return "I've noticed you're having trouble with this concept. Don't give up!"

    @staticmethod
    def inject_reinforcement_module(user, current_module, exercise_type, user_error_log):
        """
        Generates a reinforcement module for a specific exercise type and injects it.
        Limit: 4 AI modules per original module.
        Exercises: 3 of the same type.
        """
        print(f"\n[AI DEBUG] Starting reinforcement injection for User: {user.username}, Module: {current_module.title}, Type: {exercise_type}")
        
        # 0. AI modules should NOT generate more AI modules
        if current_module.is_ai_generated:
            print(f"[AI DEBUG] SKIP: Cannot generate reinforcement for an already AI-generated module.")
            return None

        # 1. Check limit: max 4 AI modules per original module for this user
        ai_modules_count = Module.objects.filter(
            user=user, 
            source_module=current_module, 
            is_ai_generated=True
        ).count()
        
        if ai_modules_count >= 4:
            print(f"[AI DEBUG] LIMIT REACHED: User already has {ai_modules_count} AI modules for this source module.")
            return None

        # 2. Check if an AI module for THIS exercise type already exists
        existing_ai_module = Module.objects.filter(
            user=user,
            source_module=current_module,
            reinforcement_type=exercise_type,
            is_ai_generated=True
        ).exists()

        if existing_ai_module:
            print(f"[AI DEBUG] DUPLICATE: AI reinforcement for {exercise_type} already exists for this module.")
            return None

        try:
            prompt = f"""
            Generate a reinforcement module for a user who failed in the module: {current_module.title}.
            The user failed a practical exercise of type: {exercise_type}.
            Recent Errors: {user_error_log[-5:]}
            
            Instead of practical exercises, generate 3 THEORETICAL exercises (Multiple Choice Questions) to help the user understand the underlying concepts related to the mistake.
            Each exercise must have exactly 4 options: a, b, c, d.
            
            Respond ONLY with a valid JSON string with this exact structure:
            {{
                "module_title": "Theoretical Reinforcement: {current_module.title}",
                "exercises": [
                    {{ 
                        "type": "THEORY", 
                        "content": {{
                            "instruction": "Select the correct option based on the theoretical concept.",
                            "question": "...", 
                            "options": {{
                                "a": "...",
                                "b": "...",
                                "c": "...",
                                "d": "..."
                            }}
                        }}, 
                        "solution": {{ 
                            "expected": "a", 
                            "explanation": "..." 
                        }} 
                    }},
                    ... (total 3 exercises)
                ]
            }}
            Ensure all 3 exercises are of type THEORY and provide clear educational value based on the user's mistake context.
            """
            raw_content = AIService._call_llm([
                {"role": "system", "content": "You are a specialized assistant that only outputs raw JSON."},
                {"role": "user", "content": prompt}
            ])

            # Robust JSON cleanup
            clean_json = raw_content.strip()
            
            # 1. Remove markdown code blocks if present
            import re
            json_match = re.search(r'\{.*\}', clean_json, re.DOTALL)
            if json_match:
                clean_json = json_match.group(0)
            
            try:
                data = json.loads(clean_json)
                print(f"[AI DEBUG] LLM SUCCESS: Parsed JSON with {len(data.get('exercises', []))} exercises.")
            except json.JSONDecodeError as e:
                print(f"[AI DEBUG] JSON Parse Error: {str(e)} | Content: {clean_json[:100]}...")
                raise e

            with transaction.atomic():
                # 3. Create the new Module
                new_module = Module.objects.create(
                    user=user,
                    title=data['module_title'],
                    order=current_module.order + 1,
                    is_ai_generated=True,
                    source_module=current_module,
                    reinforcement_type=exercise_type, # Keep track of what triggered it
                    position_x=current_module.position_x + 100,
                    position_y=current_module.position_y + 100
                )

                # Create a dummy unit for these exercises
                unit = Unit.objects.create(
                    module=new_module,
                    title="Theoretical Review",
                    order=1
                )

                # 4. Create the 3 exercises
                for idx, ex_data in enumerate(data['exercises']):
                    AIExercise.objects.create(
                        user=user,
                        source_unit=unit,
                        type=ex_data['type'], # Should be THEORY
                        content=ex_data['content'],
                        solution=ex_data['solution'],
                        ai_metadata={"reinforcement_for": current_module.id}
                    )
                
                print(f"[AI DEBUG] DATABASE: Module and 3 exercises created successfully (ID: {new_module.id}).")

                # Initialize progress as AVAILABLE for the new AI module
                UserModuleProgress.objects.get_or_create(
                    user=user,
                    module=new_module,
                    defaults={'status': 'AVAILABLE'}
                )

                # 5. Graph re-link
                ModuleDependency.objects.get_or_create(
                    source_node=current_module,
                    target_node=new_module,
                    user=user
                )
                
                outgoing = ModuleDependency.objects.filter(source_node=current_module, user=None)
                for dep in outgoing:
                    ModuleDependency.objects.get_or_create(
                        source_node=new_module,
                        target_node=dep.target_node,
                        user=user
                    )
                
                print("[AI DEBUG] GRAPH: Dependencies linked correctly.")
                return new_module
        except Exception as e:
            error_msg = str(e)
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                error_msg += f" | Body: {e.response.text}"
            print(f"[AI DEBUG] LLM ERROR: {error_msg}")
            return None


def validate_exercise_response(exercise_id, user_payload, is_ai=False):
    """
    Validates the user response for a specific exercise.
    user_payload: { "answer": ..., "is_pyodide_success": bool, "error_log": string }
    """
    # Handle legacy cases where user_payload might be just a string
    if isinstance(user_payload, str):
        user_payload = {"response": user_payload}
        
    try:
        if is_ai:
            exercise = AIExercise.objects.get(id=exercise_id)
        else:
            exercise = MasterExercise.objects.get(id=exercise_id)
            
        return ExerciseEvaluator.evaluate(exercise, user_payload)
    except (MasterExercise.DoesNotExist, AIExercise.DoesNotExist):
        return False, "Exercise not found."

def is_module_unlocked(user, module):
    """
    Checks if a module is unlocked for a specific user based on its dependencies.
    AI-generated modules are always unlocked.
    """
    if not user.is_authenticated:
        return False

    # AI-generated modules are reinforcements and should never be locked
    if module.is_ai_generated:
        return True

    progress = UserModuleProgress.objects.filter(user=user, module=module).first()
    
    # If already completed or stuck, it's definitely "unlocked" in the sense of being accessible
    if progress and progress.status in ['COMPLETED', 'STUCK', 'AVAILABLE']:
        return True

    # Check incoming dependencies
    incoming_deps = ModuleDependency.objects.filter(
        Q(target_node=module) & (Q(user__isnull=True) | Q(user=user))
    )
    
    if not incoming_deps.exists():
        # No dependencies: it's a starting point
        return True

    # Has dependencies: check if ALL are completed
    for dep in incoming_deps:
        dep_completed = UserModuleProgress.objects.filter(
            user=user, 
            module=dep.source_node, 
            status='COMPLETED'
        ).exists()
        if not dep_completed:
            return False
            
    return True

def update_user_progress(user, module_id, exercises_completed=False, is_stuck=False):
    """
    Updates the user progress for a module and unlocks children if completed.
    """
    module = Module.objects.get(id=module_id)
    progress, created = UserModuleProgress.objects.get_or_create(
        user=user, 
        module=module,
        defaults={'status': 'AVAILABLE'}
    )
    
    if is_stuck:
        # DO NOT mark as STUCK if it's already COMPLETED (review mode)
        if progress.status != 'COMPLETED':
            progress.status = 'STUCK'
            progress.save()
    elif exercises_completed:
        progress.status = 'COMPLETED'
        progress.save()

        # Unlock child modules using ModuleDependency
        dependencies = ModuleDependency.objects.filter(
            Q(source_node=module) & (Q(user__isnull=True) | Q(user=user))
        )
        for dep in dependencies:
            target_module = dep.target_node
            
            # Check if ALL incoming dependencies of the target module are COMPLETED
            incoming_to_target = ModuleDependency.objects.filter(
                Q(target_node=target_module) & (Q(user__isnull=True) | Q(user=user))
            )
            all_parents_completed = True
            for incoming_dep in incoming_to_target:
                if not UserModuleProgress.objects.filter(
                    user=user, 
                    module=incoming_dep.source_node, 
                    status='COMPLETED'
                ).exists():
                    all_parents_completed = False
                    break
            
            if all_parents_completed:
                child_progress, created = UserModuleProgress.objects.get_or_create(
                    user=user,
                    module=target_module,
                    defaults={'status': 'AVAILABLE'}
                )
                # If it already existed but was LOCKED, unlock it
                if not created and child_progress.status == 'LOCKED':
                    child_progress.status = 'AVAILABLE'
                    child_progress.save()
    
    return progress


def generate_ai_lesson(user, module_id):
    """
    Simulated call to OpenAI to generate a reinforcement lesson.
    """
    module = Module.objects.get(id=module_id)
    
    # Update status to STUCK
    progress, _ = UserModuleProgress.objects.get_or_create(user=user, module=module)
    progress.status = 'STUCK'
    progress.save()
    
    # In a real app, this would generate AIExercises and a Module
    simulated_content = {
        "title": f"Reinforcement: {module.title}",
        "theory": "It seems you are having difficulties with this module. Here is a key summary...",
        "exercise": {
            "type": "CODE",
            "question": "What is the basis of this concept?",
            "correct_answer": "Constant practice"
        }
    }
    
    return simulated_content

