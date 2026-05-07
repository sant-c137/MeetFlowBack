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
from django.db.models import Q
import json

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as rest_status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from .models import (
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

