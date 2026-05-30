import uuid
from collections import defaultdict
import os
import requests
from io import BytesIO
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser, SAFE_METHODS
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import timedelta
from zoneinfo import ZoneInfo
from django.db.models import Count, Q, Max, Avg, Prefetch
from .excel import Excel
from rest_framework import status
from django.utils import timezone
from django.db.models import Sum, F, ExpressionWrapper, DurationField
from django.conf import settings
from .models import (
    EduquestUser,
    Image,
    AcademicYear,
    Term,
    Course,
    CourseGroup,
    UserCourseGroupEnrollment,
    Quest,
    Question,
    Answer,
    UserQuestAttempt,
    UserAnswerAttempt,
    Badge,
    UserQuestBadge,
    UserCourseBadge,
    Document,
    Cosmetic,
    StudentFeedback,
    StudentAttendanceOverride,
    UserDailyCheckin
)
from .serializers import (
    EduquestUserSerializer,
    ImageSerializer,
    AcademicYearSerializer,
    TermSerializer,
    CourseSerializer,
    CourseGroupSerializer,
    UserCourseGroupEnrollmentSerializer,
    QuestSerializer,
    QuestionSerializer,
    AnswerSerializer,
    UserQuestAttemptSerializer,
    UserAnswerAttemptSerializer,
    BadgeSerializer,
    UserQuestBadgeSerializer,
    UserCourseBadgeSerializer,
    DocumentSerializer,
    CosmeticSerializer,
    StudentFeedbackSerializer,
    UserDailyCheckinSerializer
)
from rest_framework.decorators import api_view
from django.utils.decorators import method_decorator
from rest_framework.response import Response
from django.http import HttpResponse
from openpyxl import Workbook
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

DEMO_USERS = {
    "DEMO.STUDENT@E.NTU.EDU.SG": {
        "email": "DEMO.STUDENT@E.NTU.EDU.SG",
        "username": "Demo Student",
        "nickname": "Demo Student",
        "is_staff": False,
        "password_setting": "DEMO_STUDENT_PASSWORD",
    },
    "DEMO.INSTRUCTOR@NTU.EDU.SG": {
        "email": "DEMO.INSTRUCTOR@NTU.EDU.SG",
        "username": "Demo Instructor",
        "nickname": "Demo Instructor",
        "is_staff": True,
        "password_setting": "DEMO_INSTRUCTOR_PASSWORD",
    },
}


class DemoLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        # NOTE: removed runtime gate `DEMO_LOGIN_ENABLED` so demo login
        # is always available. Be careful: enabling demo login in
        # production environments is a security risk. To re-enable the
        # gate, restore the check against `settings.DEMO_LOGIN_ENABLED`.

        email = str(request.data.get("email", "")).strip().upper()
        password = str(request.data.get("password", ""))

        demo_user = DEMO_USERS.get(email)
        if demo_user is None:
            return Response({"detail": "Invalid demo email or password."}, status=status.HTTP_401_UNAUTHORIZED)

        expected_password = getattr(settings, demo_user["password_setting"])
        if password != expected_password:
            return Response({"detail": "Invalid demo email or password."}, status=status.HTTP_401_UNAUTHORIZED)

        user, _ = EduquestUser.objects.get_or_create(
            email=demo_user["email"],
            defaults={
                "email": demo_user["email"],
                "username": demo_user["username"],
                "nickname": demo_user["username"],
                "is_staff": demo_user["is_staff"],
                "last_login": timezone.now(),
            }
        )

        fields_to_update = []
        for field in ("username", "nickname", "is_staff"):
            next_value = demo_user[field]
            if getattr(user, field) != next_value:
                setattr(user, field, next_value)
                fields_to_update.append(field)

        user.last_login = timezone.now()
        fields_to_update.append("last_login")
        if fields_to_update:
            user.save(update_fields=fields_to_update)

        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": EduquestUserSerializer(user).data,
        })

def _build_effective_attendance_pairs(quest_ids, student_ids=None):
    if not quest_ids:
        return set()

    base_query = UserQuestAttempt.objects.filter(quest_id__in=quest_ids)
    if student_ids is not None:
        base_query = base_query.filter(student_id__in=student_ids)

    base_pairs = set(base_query.values_list('quest_id', 'student_id').distinct())

    override_query = StudentAttendanceOverride.objects.filter(quest_id__in=quest_ids)
    if student_ids is not None:
        override_query = override_query.filter(student_id__in=student_ids)

    for override in override_query.values('quest_id', 'student_id', 'is_present'):
        key = (override['quest_id'], override['student_id'])
        if override['is_present']:
            base_pairs.add(key)
        else:
            base_pairs.discard(key)

    return base_pairs


def _sg_today():
    return timezone.now().astimezone(ZoneInfo("Asia/Singapore")).date()


# Test view to check the request method and data

@api_view(['GET', 'POST'])
@csrf_exempt
def test_view(request):
    return Response({
        'method': request.method,
        'data': request.data,
    })


@api_view(['GET'])
def status_view(request):
    return Response({
        'status': 'OK'
    })


class EduquestUserViewSet(viewsets.ModelViewSet):
    queryset = EduquestUser.objects.all().order_by('-id')
    serializer_class = EduquestUserSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def by_email(self, request):
        email = request.query_params.get('email')
        queryset = EduquestUser.objects.get(email=email)
        serializer = EduquestUserSerializer(queryset)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_admin(self, request):
        queryset = EduquestUser.objects.filter(is_staff=True).order_by('-id')
        serializer = EduquestUserSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_student(self, request):
        queryset = EduquestUser.objects.filter(is_staff=False, is_superuser=False).order_by('nickname', 'email')
        serializer = EduquestUserSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='daily-check-in')
    def daily_check_in(self, request):
        user = request.user
        if not isinstance(user, EduquestUser):
            return Response({"detail": "Invalid user context"}, status=status.HTTP_400_BAD_REQUEST)

        today = _sg_today()
        if user.daily_checkin_last_date == today:
            return Response({
                "checked_in": False,
                "already_checked_in": True,
                "daily_points_awarded": 0,
                "streak_bonus_awarded": 0,
                "current_streak": user.daily_checkin_streak,
                "longest_streak": user.daily_checkin_longest_streak,
                "total_points": float(user.total_points),
                "current_points": float(user.current_points),
            })

        yesterday = today - timedelta(days=1)
        if user.daily_checkin_last_date == yesterday:
            next_streak = user.daily_checkin_streak + 1
        else:
            next_streak = 1

        daily_points_awarded = 5
        streak_bonus_awarded = 20 if next_streak % 7 == 0 else 0
        points_awarded = daily_points_awarded + streak_bonus_awarded

        with transaction.atomic():
            user.daily_checkin_last_date = today
            user.daily_checkin_streak = next_streak
            user.daily_checkin_longest_streak = max(user.daily_checkin_longest_streak, next_streak)
            user.total_points += points_awarded
            user.current_points += points_awarded

            # Reset daily goals
            try:
                for goals in user.daily_goals:
                    goals['complete'] = 0
            except:
                pass

            user.save(update_fields=[
                'daily_checkin_last_date',
                'daily_checkin_streak',
                'daily_checkin_longest_streak',
                'total_points',
                'current_points',
                'daily_goals'
            ])
            # Create a record in UserDailyCheckin to track all check-in dates
            UserDailyCheckin.objects.get_or_create(student=user, checkin_date=today)
            

        return Response({
            "checked_in": True,
            "already_checked_in": False,
            "daily_points_awarded": daily_points_awarded,
            "streak_bonus_awarded": streak_bonus_awarded,
            "current_streak": user.daily_checkin_streak,
            "longest_streak": user.daily_checkin_longest_streak,
            "total_points": float(user.total_points),
            "current_points": float(user.current_points),
        })
    
    @action(detail=False, methods=['post'], url_path='calendar-daily-check-in')
    def calendar_daily_check_in(self, request):
        user = request.user
        if not isinstance(user, EduquestUser):
            return Response({"detail": "Invalid user context"}, status=status.HTTP_400_BAD_REQUEST)

        dates = list(UserDailyCheckin.objects.filter(student=user).order_by('checkin_date').values_list('checkin_date', flat=True))
        dates_iso = [d.isoformat() for d in dates]
        return Response({"checkin_dates": dates_iso})
    
    @action(detail=False, methods=['post'], url_path='update-daily-goals')
    def update_daily_goals(self, request):
        user = request.user
        if not isinstance(user, EduquestUser):
            return Response({"detail": "Invalid user context"}, status=status.HTTP_400_BAD_REQUEST)

        daily_goals = request.data.get('daily_goals')
        if daily_goals is not None:
            with transaction.atomic():
                user = EduquestUser.objects.select_for_update().get(pk=user.pk)
                current_goals_by_id = {
                    goal.get('id'): goal
                    for goal in user.daily_goals or []
                    if goal.get('id') is not None
                }
                merged_goals = []
                for goal in daily_goals:
                    merged_goal = goal.copy()
                    current_goal = current_goals_by_id.get(merged_goal.get('id'))
                    if current_goal:
                        merged_goal['complete'] = max(
                            float(current_goal.get('complete') or 0),
                            float(merged_goal.get('complete') or 0)
                        )
                    merged_goals.append(merged_goal)

                user.daily_goals = merged_goals
            user.save(update_fields=['daily_goals'])

        return Response({"detail": "Daily goals updated successfully"}, status=status.HTTP_200_OK)

class AcademicYearViewSet(viewsets.ModelViewSet):
    queryset = AcademicYear.objects.all().order_by('-id')
    serializer_class = AcademicYearSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def non_private(self, request):
        queryset = AcademicYear.objects.exclude(start_year=0).order_by('-id')
        serializer = AcademicYearSerializer(queryset, many=True)
        return Response(serializer.data)


class TermViewSet(viewsets.ModelViewSet):
    queryset = Term.objects.all().order_by('-id')
    serializer_class = TermSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def non_private(self, request):
        queryset = Term.objects.exclude(name='Private Term').order_by('-id')
        serializer = TermSerializer(queryset, many=True)
        return Response(serializer.data)


class ImageViewSet(viewsets.ModelViewSet):
    queryset = Image.objects.all().order_by('-id')
    serializer_class = ImageSerializer
    permission_classes = [IsAuthenticated]


class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all().order_by('-id')
    serializer_class = CourseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Course.objects.all().order_by('-id')

        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset

        enrolled_course_ids = UserCourseGroupEnrollment.objects.filter(
            student=self.request.user
        ).values_list('course_group__course_id', flat=True)
        return queryset.exclude(type='Private').filter(id__in=enrolled_course_ids)

    @action(detail=False, methods=['get'])
    def non_private(self, request):
        queryset = self.get_queryset().exclude(type='Private').order_by('-id')
        serializer = CourseSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_enrolled_user(self, request):
        user_id = request.query_params.get('user_id')
        if not (request.user.is_staff or request.user.is_superuser):
            user_id = request.user.id

        # Get the course group enrollments for the given user
        course_group_enrollments = UserCourseGroupEnrollment.objects.filter(student_id=user_id)
        # Extract the course IDs from the related course groups
        course_ids = CourseGroup.objects.filter(
            id__in=course_group_enrollments.values_list('course_group', flat=True)
        ).values_list('course_id', flat=True)
        # Query the courses excluding Private courses
        queryset = Course.objects.exclude(type='Private').filter(id__in=course_ids).order_by('-id')

        # Serialize the results
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class CourseGroupViewSet(viewsets.ModelViewSet):
    queryset = CourseGroup.objects.all().order_by('-id')
    serializer_class = CourseGroupSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def by_course(self, request):
        course_id = request.query_params.get('course_id')
        queryset = CourseGroup.objects.filter(course=course_id).order_by('-id')
        serializer = CourseGroupSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_private_course(self, request):
        queryset = CourseGroup.objects.filter(course__type='Private').order_by('-id')
        serializer = CourseGroupSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def non_private(self, request):
        queryset = CourseGroup.objects.exclude(course__type='Private').order_by('-id')
        serializer = CourseGroupSerializer(queryset, many=True)
        return Response(serializer.data)


class UserCourseGroupEnrollmentViewSet(viewsets.ModelViewSet):
    queryset = UserCourseGroupEnrollment.objects.all().order_by('-id')
    serializer_class = UserCourseGroupEnrollmentSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def by_course_group_and_user(self, request):
        course_group_id = request.query_params.get('course_group_id')
        user_id = request.query_params.get('user_id')
        queryset = UserCourseGroupEnrollment.objects.filter(course_group=course_group_id, student=user_id).order_by(
            '-id')
        serializer = UserCourseGroupEnrollmentSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_course_and_user(self, request):
        course_id = request.query_params.get('course_id')
        user_id = request.query_params.get('user_id')
        queryset = UserCourseGroupEnrollment.objects.filter(course_group__course=course_id, student=user_id).order_by(
            '-id')
        serializer = UserCourseGroupEnrollmentSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_course_group(self, request):
        course_group_id = request.query_params.get('course_group_id')
        if not course_group_id:
            return Response({'detail': 'course_group_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        queryset = (
            UserCourseGroupEnrollment.objects
            .filter(course_group=course_group_id)
            .select_related('student')
            .order_by('student__nickname', 'student__email')
        )
        serializer = UserCourseGroupEnrollmentSerializer(queryset, many=True)
        return Response(serializer.data)


class QuestViewSet(viewsets.ModelViewSet):
    queryset = Quest.objects.all().order_by('-id')
    serializer_class = QuestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Quest.objects.all().order_by('-id')

        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset

        enrolled_course_group_ids = UserCourseGroupEnrollment.objects.filter(
            student=self.request.user
        ).values_list('course_group_id', flat=True)
        return queryset.filter(
            Q(course_group_id__in=enrolled_course_group_ids) & ~Q(type='Private') |
            Q(organiser=self.request.user, type='Private')
        ).order_by('-id')

    @action(detail=False, methods=['get'])
    def non_private(self, request):
        queryset = self.get_queryset().exclude(type='Private').order_by('-id')
        serializer = QuestSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def private_by_user(self, request):
        user = request.user
        queryset = Quest.objects.filter(organiser=user, type='Private').order_by('-id')
        serializer = QuestSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_enrolled_user(self, request):
        user_id = request.query_params.get('user_id')
        if not (request.user.is_staff or request.user.is_superuser):
            user_id = request.user.id

        # Get all course group enrollments for the user
        course_group_enrollments = UserCourseGroupEnrollment.objects.filter(student=user_id)
        # Get all quests for the course groups
        queryset = Quest.objects.filter(
            course_group__in=course_group_enrollments.values('course_group')
        ).exclude(type='Private').order_by('-id')
        serializer = QuestSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_course_group(self, request):
        course_group_id = request.query_params.get('course_group_id')
        queryset = Quest.objects.filter(course_group=course_group_id).order_by('-id')
        serializer = QuestSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def import_quest(self, request):
        try:
            excel_file = request.FILES.get('file')
        except Exception as e:
            return Response(
                {"Error processing excel file": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not excel_file:
            return Response(
                {"No file provided, please try again"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            excel = Excel()
            excel.read_excel_sheets(excel_file)
            questions_data = excel.get_questions()
            users_data = excel.get_users()
        except Exception as e:
            return Response(
                {"Error processing excel file": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Extract other form data
            quest_data = {
                'type': request.data.get('type'),
                'name': request.data.get('name'),
                'description': request.data.get('description'),
                'status': request.data.get('status'),
                'max_attempts': request.data.get('max_attempts'),
                'course_group_id': request.data.get('course_group_id'),
                'tutorial_date': request.data.get('tutorial_date'),
                'image_id': request.data.get('image_id'),
                'organiser_id': request.data.get('organiser_id')
            }
        except Exception as e:
            return Response(
                {"Error extracting form data": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Use atomic transaction to ensure data integrity
        with transaction.atomic():
            try:
                try:
                    # Create a Quest object
                    quest_serializer = QuestSerializer(data=quest_data)
                    quest_serializer.is_valid(raise_exception=True)
                    quest = quest_serializer.save()
                    new_quest_id = quest.id
                except Exception as e:
                    raise ValidationError({"Error creating quest": str(e)})

                try:
                    questions_serializer = []
                    # Process each question in the questions_data list
                    for question_data in questions_data:
                        question_data['quest_id'] = new_quest_id
                        question_serializer = QuestionSerializer(data=question_data)
                        question_serializer.is_valid(raise_exception=True)
                        question = question_serializer.save()
                        questions_serializer.append(question_serializer.data)
                except Exception as e:
                    raise ValidationError({"Error creating questions": str(e)})

                # Enroll users and create UserQuestAttempt and UserAnswerAttempt objects
                for user_data in users_data:
                    try:
                        print(f"Processing user: {user_data['email']}")
                        user, created = EduquestUser.objects.get_or_create(
                            email=user_data['email'],
                            defaults={
                                'email': user_data['email'],
                                'username': user_data['username'],
                                'nickname': user_data['username'],
                            }
                        )
                    except Exception as e:
                        raise ValidationError({"Error creating user": str(e)})

                    try:
                        # Enroll the user in the course group
                        enrollment, enrolled = UserCourseGroupEnrollment.objects.get_or_create(
                            student=user,
                            course_group_id=quest_data['course_group_id'],
                        )
                    except Exception as e:
                        raise ValidationError({"Error enrolling new user": str(e)})

                    try:
                        # Create a UserQuestAttempt object
                        user_quest_attempt_data = {
                            'student_id': user.id,
                            'quest_id': new_quest_id
                        }
                        user_quest_attempt_serializer = UserQuestAttemptSerializer(data=user_quest_attempt_data)
                        user_quest_attempt_serializer.is_valid(raise_exception=True)
                        user_quest_attempt = user_quest_attempt_serializer.save()
                        new_user_quest_attempt_id = user_quest_attempt.id

                        # Get the generated empty-prefilled UserAnswerAttempt objects for the UserQuestAttempt
                        user_answer_attempts = UserAnswerAttempt.objects.filter(
                            user_quest_attempt=new_user_quest_attempt_id
                        )
                    except Exception as e:
                        raise ValidationError({"Error creating user quest attempt": str(e)})

                    # Update selected answers based on Excel data
                    try:
                        selected_answers = excel.get_user_answer_attempts(user.email)
                        for user_answer_attempt in user_answer_attempts:
                            for selected_answer in selected_answers:
                                if selected_answer['number'] == user_answer_attempt.question.number:
                                    if user_answer_attempt.answer.text in selected_answer['selected_answers']:
                                        user_answer_attempt.is_selected = True
                                        user_answer_attempt.save()
                    except Exception as e:
                        raise ValidationError({"Error updating selected answers": str(e)})

            except ValidationError as ve:
                return Response(
                    {"Validation Error": ve.detail},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except Exception as e:
                return Response(
                    {"Error importing quest": str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response(questions_serializer, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='bonus-game')
    def bonus_game(self, request, pk=None):
        quest = self.get_object()
        if quest.type != 'Private':
            return Response({"error": "Bonus game is only available for private quests."}, status=status.HTTP_400_BAD_REQUEST)

        if not quest.source_document:
            return Response({"error": "No source document found for this quest."}, status=status.HTTP_400_BAD_REQUEST)

        document_name = os.path.basename(quest.source_document.file.name)
        flask_url = getattr(settings, 'FLASK_MICROSERVICE_URL', 'http://localhost:5000')

        logger.info("[Bonus Game] Calling Flask microservice at %s for document=%s", flask_url, document_name)
        response = requests.post(
            f"{flask_url}/generate_bonus_game",
            json={"document_id": document_name},
            timeout=30
        )
        logger.info("[Bonus Game] Flask response status=%s", response.status_code)

        if response.status_code != 200:
            logger.error("[Bonus Game] Flask error status=%s body=%s", response.status_code, response.text[:500])
            return Response({"error": "Failed to generate bonus game."}, status=response.status_code)

        return Response(response.json())


class QuestionViewSet(viewsets.ModelViewSet):
    queryset = Question.objects.all().order_by('-id')
    serializer_class = QuestionSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        if isinstance(request.data, list):
            serializer = self.get_serializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            # Serialize the created data
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=False, methods=['get'])
    def by_quest(self, request):
        quest_id = request.query_params.get('quest_id')
        if not quest_id:
            return Response({"detail": "quest_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        queryset = Question.objects.filter(quest=quest_id).order_by('number')
        serializer = QuestionSerializer(queryset, many=True)
        return Response(serializer.data)


class AnswerViewSet(viewsets.ModelViewSet):
    queryset = Answer.objects.all().order_by('-id')
    serializer_class = AnswerSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['put'], url_path='bulk-update')
    def bulk_update(self, request):
        # Ensure the request data is a list
        if not isinstance(request.data, list):
            return Response({"error": "Expected a list of items."}, status=status.HTTP_400_BAD_REQUEST)

        # Initialize the serializer with 'many=True'
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        # Extract the validated data
        validated_data = serializer.validated_data

        # Collect the IDs of the answers to update
        answer_ids = [item['id'] for item in validated_data]

        # Retrieve the existing answers from the database
        answers = Answer.objects.filter(id__in=answer_ids)

        # Map existing answers by ID for easy lookup
        answer_dict = {answer.id: answer for answer in answers}

        updated_answers = []
        for item in validated_data:
            answer_id = item.get('id')
            if answer_id in answer_dict:
                answer_instance = answer_dict[answer_id]
                # Update the fields
                for attr, value in item.items():
                    setattr(answer_instance, attr, value)
                answer_instance.save()
                updated_answers.append(answer_instance)
            else:
                return Response({"error": f"Answer with id {answer_id} does not exist."},
                                status=status.HTTP_404_NOT_FOUND)

        # Serialize the updated answers to return in the response
        output_serializer = self.get_serializer(updated_answers, many=True)
        return Response(output_serializer.data, status=status.HTTP_200_OK)


class UserQuestAttemptViewSet(viewsets.ModelViewSet):
    queryset = UserQuestAttempt.objects.all().order_by('-id')
    serializer_class = UserQuestAttemptSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def by_user_quest(self, request):
        quest_id = request.query_params.get('quest_id')
        user_id = request.query_params.get('user_id')
        queryset = UserQuestAttempt.objects.filter(student=user_id, quest=quest_id).order_by('-id')
        serializer = UserQuestAttemptSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_quest(self, request):
        quest_id = request.query_params.get('quest_id')
        queryset = UserQuestAttempt.objects.filter(quest=quest_id).order_by('-id')
        serializer = UserQuestAttemptSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def set_all_attempts_submitted_by_quest(self, request):
        quest_id = request.query_params.get('quest_id')
        queryset = UserQuestAttempt.objects.filter(quest=quest_id)
        for instance in queryset:
            instance.submitted = True
            instance.save()
        return Response({"message": f"All attempts for quest {quest_id} have been marked as submitted."})

    @action(detail=False, methods=['post'])
    def regrade_by_quest(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        quest_id = request.query_params.get('quest_id')
        if not quest_id:
            return Response({"detail": "quest_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        attempts = UserQuestAttempt.objects.filter(quest=quest_id)
        updated_count = 0
        for attempt in attempts:
            total_score = attempt.calculate_total_score_achieved()
            attempt.total_score_achieved = total_score
            attempt.save(update_fields=['total_score_achieved'])
            updated_count += 1

        return Response({"message": f"Regraded {updated_count} attempts for quest {quest_id}."})

    @action(detail=True, methods=['post'], url_path='bonus')
    def award_bonus(self, request, pk=None):
        attempt = self.get_object()
        user = request.user

        if attempt.student_id != user.id:
            return Response({"error": "You can only claim bonus for your own attempts."}, status=status.HTTP_403_FORBIDDEN)

        if attempt.quest.type != 'Private':
            return Response({"error": "Bonus is only available for private quests."}, status=status.HTTP_400_BAD_REQUEST)

        if attempt.bonus_awarded:
            return Response({
                "bonus_awarded": True,
                "bonus_points": attempt.bonus_points
            })

        bonus_points = 5
        attempt.bonus_points = bonus_points
        attempt.bonus_awarded = True
        attempt.save(update_fields=['bonus_points', 'bonus_awarded'])

        user.total_points += bonus_points
        user.current_points += bonus_points
        user.save(update_fields=['total_points', 'current_points'])

        return Response({
            "bonus_awarded": True,
            "bonus_points": bonus_points
        })

    # @action(detail=False, methods=['patch'], url_path='bulk-update')
    # def bulk_update(self, request, *args, **kwargs):
    #     """
    #     Bulk update UserQuestAttempt
    #     """
    #     if isinstance(request.data, list):
    #         updated_attempts = []
    #         for attempt_data in request.data:
    #             attempt_id = attempt_data.get('id')
    #             if not attempt_id:
    #                 return Response({"error": "ID is required for each attempt."}, status=status.HTTP_400_BAD_REQUEST)
    #
    #             try:
    #                 # Retrieve the instance to update
    #                 attempt_instance = UserQuestAttempt.objects.get(id=attempt_id)
    #             except UserQuestAttempt.DoesNotExist:
    #                 return Response({"error": f"UserQuestAttempt with id {attempt_id} not found."},
    #                                 status=status.HTTP_404_NOT_FOUND)
    #
    #             # Use the existing serializer for each update
    #             serializer = self.get_serializer(instance=attempt_instance, data=attempt_data, partial=True)
    #             if serializer.is_valid():
    #                 serializer.save()
    #                 updated_attempts.append(serializer.data)
    #             else:
    #                 return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    #
    #         return Response({"updated_attempts": updated_attempts}, status=status.HTTP_200_OK)
    #
    #     return Response({"error": "Expected a list of data."}, status=status.HTTP_400_BAD_REQUEST)


class StudentFeedbackViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StudentFeedback.objects.all().order_by('-datetime_created')
    serializer_class = StudentFeedbackSerializer
    permission_classes = [IsAuthenticated]

    def _restrict_queryset(self, request, queryset):
        if request.user.is_staff or request.user.is_superuser:
            return queryset
        return queryset.filter(user_quest_attempt__student=request.user)

    @action(detail=False, methods=['get'])
    def by_attempt(self, request):
        attempt_id = request.query_params.get('user_quest_attempt_id') or request.query_params.get('attempt_id')
        if not attempt_id:
            return Response({"error": "user_quest_attempt_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        queryset = StudentFeedback.objects.filter(user_quest_attempt_id=attempt_id)
        queryset = self._restrict_queryset(request, queryset)
        feedback = queryset.first()
        if not feedback:
            return Response({}, status=status.HTTP_200_OK)
        serializer = self.get_serializer(feedback)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='save')
    def save_feedback(self, request):
        attempt_id = request.data.get('user_quest_attempt_id') or request.data.get('attempt_id')
        if not attempt_id:
            return Response({"error": "user_quest_attempt_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            attempt = UserQuestAttempt.objects.get(id=attempt_id)
        except UserQuestAttempt.DoesNotExist:
            return Response({"error": "User quest attempt not found."}, status=status.HTTP_404_NOT_FOUND)

        if not (request.user.is_staff or request.user.is_superuser) and attempt.student != request.user:
            return Response({"error": "Not authorized to save feedback for this attempt."}, status=status.HTTP_403_FORBIDDEN)

        defaults = {
            'quest_summary': request.data.get('quest_summary', {}),
            'subtopic_feedback': request.data.get('subtopic_feedback', []),
            'study_tips': request.data.get('study_tips', []),
            'strengths': request.data.get('strengths', []),
            'weaknesses': request.data.get('weaknesses', []),
            'recommendations': request.data.get('recommendations', ''),
            'question_feedback': request.data.get('question_feedback', {}),
        }

        feedback, _ = StudentFeedback.objects.update_or_create(
            user_quest_attempt=attempt,
            defaults=defaults
        )
        serializer = self.get_serializer(feedback)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserAnswerAttemptViewSet(viewsets.ModelViewSet):
    queryset = UserAnswerAttempt.objects.all().order_by('-id')
    serializer_class = UserAnswerAttemptSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def by_user_quest_attempt(self, request):
        user_quest_attempt_id = request.query_params.get('user_quest_attempt_id')
        queryset = UserAnswerAttempt.objects.filter(user_quest_attempt=user_quest_attempt_id).order_by('-id')
        serializer = UserAnswerAttemptSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_quest(self, request):
        quest_id = request.query_params.get('quest_id')
        queryset = UserAnswerAttempt.objects.filter(user_quest_attempt__quest=quest_id).order_by('-id')
        serializer = UserAnswerAttemptSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['patch'], url_path='bulk-update')
    def bulk_update(self, request, *args, **kwargs):
        """
        Bulk update UserAnswerAttempt
        """
        if isinstance(request.data, list):
            updated_attempts = []
            for attempt_data in request.data:
                attempt_id = attempt_data.get('id')
                if not attempt_id:
                    return Response({"error": "ID is required for each attempt."}, status=status.HTTP_400_BAD_REQUEST)

                try:
                    # Retrieve the instance to update
                    attempt_instance = UserAnswerAttempt.objects.get(id=attempt_id)
                except UserAnswerAttempt.DoesNotExist:
                    return Response({"error": f"UserAnswerAttempt with id {attempt_id} not found."},
                                    status=status.HTTP_404_NOT_FOUND)

                # Use the existing serializer for each update
                serializer = self.get_serializer(instance=attempt_instance, data=attempt_data, partial=True)
                if serializer.is_valid():
                    serializer.save()
                    updated_attempts.append(serializer.data)
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            return Response({"updated_attempts": updated_attempts}, status=status.HTTP_200_OK)

        return Response({"error": "Expected a list of data."}, status=status.HTTP_400_BAD_REQUEST)


class BadgeViewSet(viewsets.ModelViewSet):
    queryset = Badge.objects.all().order_by('-id')
    serializer_class = BadgeSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # Allow all authenticated users to view badges,
        # but only staff/superuser to create/update/delete.
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAdminUser()]


class UserQuestBadgeViewSet(viewsets.ModelViewSet):
    queryset = UserQuestBadge.objects.all().order_by('-id')
    serializer_class = UserQuestBadgeSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def by_user(self, request):
        user_id = request.query_params.get('user_id')
        queryset = UserQuestBadge.objects.filter(user_quest_attempt__student=user_id).order_by('-id')
        serializer = UserQuestBadgeSerializer(queryset, many=True)
        return Response(serializer.data)


class UserCourseBadgeViewSet(viewsets.ModelViewSet):
    queryset = UserCourseBadge.objects.all().order_by('-id')
    serializer_class = UserCourseBadgeSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def by_user(self, request):
        user_id = request.query_params.get('user_id')
        queryset = UserCourseBadge.objects.filter(user_course_group_enrollment__student=user_id).order_by('-id')
        serializer = UserCourseBadgeSerializer(queryset, many=True)
        return Response(serializer.data)


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all().order_by('-id')
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def by_user(self, request):
        user_id = request.query_params.get('user_id')
        queryset = Document.objects.filter(uploaded_by=user_id).order_by('-id')
        serializer = DocumentSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def upload(self, request):
        try:
            file = request.FILES.get('file')
            if not file:
                return Response({"No file provided, please try again"}, status=status.HTTP_400_BAD_REQUEST)
            data = {
                'uploaded_by': request.user.id,
                'file': file,
                'name': request.data.get('name'),
                'size': request.data.get('size'),
            }
            serializer = DocumentSerializer(data=data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"Error uploading document": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class CosmeticViewSet(viewsets.ModelViewSet):
    queryset = Cosmetic.objects.all().order_by('-id')
    serializer_class = CosmeticSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AnalyticsPartOneView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Current time and time one week ago
        now = timezone.now()
        last_week = now - timedelta(weeks=1)

        # 1. Total number of users excluding admin and new users since last week
        total_users = EduquestUser.objects.exclude(is_staff=True).count()
        new_users_last_week = EduquestUser.objects.exclude(is_staff=True).filter(date_joined__gte=last_week).count()
        new_users_percentage = (new_users_last_week / total_users) * 100 if total_users > 0 else 0

        # 2. Total number of course enrollments and new enrollments since last week
        total_enrollments = UserCourseGroupEnrollment.objects.exclude(course_group__course__type="Private").count()
        new_enrollments_last_week = UserCourseGroupEnrollment.objects.exclude(
            course_group__course__type="Private").filter(
            enrolled_on__gte=last_week).count()
        new_enrollments_percentage = (
                                             new_enrollments_last_week / total_enrollments) * 100 if total_enrollments > 0 else 0

        # 3. Total number of quest attempts and new attempts since last week
        total_quest_attempts = UserQuestAttempt.objects.exclude(quest__type="Private").count()
        new_quest_attempts_last_week = UserQuestAttempt.objects.exclude(quest__type="Private").filter(
            first_attempted_date__gte=last_week).count()
        new_quest_attempts_percentage = (
                                                new_quest_attempts_last_week / total_quest_attempts) * 100 if total_quest_attempts > 0 else 0

        # 4. User with the shortest non-zero time_taken and perfect score
        # Filter UserQuestBadge for users with the "Perfectionist" badge
        perfectionist_badge_attempts = UserQuestBadge.objects.filter(
            badge__name="Perfectionist"
        ).annotate(
            time_taken=ExpressionWrapper(
                F('user_quest_attempt__last_attempted_date') - F('user_quest_attempt__first_attempted_date'),
                output_field=DurationField()
            )
        ).filter(
            time_taken__gt=timedelta(seconds=0)
        ).order_by('time_taken').first()

        if perfectionist_badge_attempts:
            shortest_time_user = {
                'nickname': perfectionist_badge_attempts.user_quest_attempt.student.nickname,
                'time_taken': int(perfectionist_badge_attempts.time_taken.total_seconds() * 1000),
                # Convert to milliseconds and round to whole number
                'quest_id': perfectionist_badge_attempts.user_quest_attempt.quest.id,
                'quest_name': perfectionist_badge_attempts.user_quest_attempt.quest.name,
                'course': f"{perfectionist_badge_attempts.user_quest_attempt.quest.course_group.course.code} {perfectionist_badge_attempts.user_quest_attempt.quest.course_group.course.name}"
            }
        else:
            shortest_time_user = None

        data = {
            'user_stats': {
                'total_users': total_users,
                'new_users_percentage': new_users_percentage,
            },
            'course_enrollment_stats': {
                'total_enrollments': total_enrollments,
                'new_enrollments_percentage': new_enrollments_percentage,
            },
            'quest_attempt_stats': {
                'total_quest_attempts': total_quest_attempts,
                'new_quest_attempts_percentage': new_quest_attempts_percentage,
            },
            'shortest_time_user': shortest_time_user
        }

        return Response(data)


class AnalyticsPartTwoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user_id = self.request.query_params.get('user_id')
        option = self.request.query_params.get('option')  # course_progression, badge_progression, or both

        # Validation
        if not user_id:
            return Response({"error": "user_id is required in the URL parameters."}, status=400)
        if not option:
            return Response({"error": "option is required in the URL parameters."}, status=400)
        if option not in ['course_progression', 'badge_progression', 'both']:
            return Response({"error": "option must be either course_progression, badge_progression, or both."},
                            status=400)

        if option == 'course_progression':
            return self.get_course_progression(user_id)
        if option == 'badge_progression':
            return self.get_badge_progression(user_id)
        if option == 'both':
            return self.get_course_and_badge_progression(user_id)

    def get_course_progression(self, user_id):
        # Fetch enrollments with related course and quests in a single query
        enrollments = UserCourseGroupEnrollment.objects.filter(
            student_id=user_id
        ).exclude(
            course_group__course__name="Private Course"
        ).select_related('course_group__course').prefetch_related('course_group__quests')

        course_quest_completion = []

        for enrollment in enrollments:
            course_group = enrollment.course_group
            course = course_group.course

            quest_attempts = UserQuestAttempt.objects.filter(
                student_id=user_id,
                quest__course_group__course_id=course.id,
                submitted=True
            ).distinct('quest')

            completed_quests = quest_attempts.count()
            total_quests = course_group.quests.count()
            completion_ratio = completed_quests / total_quests if total_quests > 0 else 0

            # Get the highest score for each quest attempted in the course
            quest_scores = []
            for quest in course_group.quests.all():
                # Fetch all attempts for this quest by the user
                attempts = UserQuestAttempt.objects.filter(
                    student_id=user_id,
                    quest=quest
                )
                if attempts.exists():
                    # Aggregate the highest score achieved across all attempts for this quest
                    highest_score = attempts.aggregate(
                        highest_score=Sum('total_score_achieved')
                    )['highest_score'] or 0
                else:
                    highest_score = 0

                quest_scores.append({
                    'quest_id': quest.id,
                    'quest_name': quest.name,
                    'max_score': quest.total_max_score(),
                    'highest_score': highest_score
                })

            course_quest_completion.append({
                'course_id': course.id,
                'course_term': f"AY {course.term.academic_year.start_year} - {course.term.academic_year.end_year} {course.term.name}",
                'course_code': course.code,
                'course_name': course.name,
                'completed_quests': completed_quests,
                'total_quests': total_quests,
                'completion_ratio': round(completion_ratio, 2),  # Rounded to 2 decimal places
                'quest_scores': quest_scores
            })
        # Sort the results by completion ratio in descending order
        course_quest_completion.sort(key=lambda x: x['completion_ratio'], reverse=True)

        return Response({'user_course_progression': course_quest_completion})

    def get_badge_progression(self, user_id):
        all_badges = Badge.objects.all()
        # Fetch all quest badges and course badges earned by the user
        user_quest_badges = UserQuestBadge.objects.filter(
            user_quest_attempt__student_id=user_id
        ).select_related('badge')
        # Fetch all course badges earned by the user
        user_course_badges = UserCourseBadge.objects.filter(
            user_course_group_enrollment__student_id=user_id
        ).select_related('badge')
        # Aggregate the badge data
        badge_aggregation = {
            badge.id: {
                'badge_id': badge.id,
                'badge_name': badge.name,
                'badge_filename': badge.image.filename if badge.image else None,
                'count': 0
            } for badge in all_badges
        }

        # Increment the count for each badge earned by the user
        for badge in user_quest_badges:
            badge_aggregation[badge.badge.id]['count'] += 1

        # Increment the count for each course badge earned by the user
        for badge in user_course_badges:
            badge_aggregation[badge.badge.id]['count'] += 1

        # Filter out badges with zero count and sort by count in descending order
        badge_aggregation = [v for v in badge_aggregation.values() if v['count'] > 0]
        sorted_badge_aggregation = sorted(badge_aggregation, key=lambda x: x['count'], reverse=True)

        return Response({'user_badge_progression': sorted_badge_aggregation})

    def get_course_and_badge_progression(self, user_id):
        course_progression = self.get_course_progression(user_id).data
        badge_progression = self.get_badge_progression(user_id).data
        return Response({**course_progression, **badge_progression})


class AnalyticsPartThreeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Fetch top 5 users with the most badges with quest badge and course badge combined
        top_users = EduquestUser.objects.annotate(
            quest_badge_count=Count('attempted_quests__earned_quest_badges', distinct=True),
            course_badge_count=Count('enrolled_course_groups__earned_course_badges', distinct=True),
        ).annotate(
            total_badge_count=F('quest_badge_count') + F('course_badge_count')
        ).order_by('-total_badge_count')[:5]

        # Prefetch related badges to reduce database hits
        quest_badges = UserQuestBadge.objects.select_related('badge', 'user_quest_attempt__student').all()
        course_badges = UserCourseBadge.objects.select_related('badge', 'user_course_group_enrollment__student').all()

        user_badge_details = []
        for user in top_users:
            # Aggregate quest badges
            quest_badges_dict = {}
            for badge in quest_badges:
                if badge.user_quest_attempt.student == user:
                    badge_id = badge.badge.id
                    if badge_id not in quest_badges_dict:
                        quest_badges_dict[badge_id] = {
                            "badge_id": badge_id,
                            "badge_name": badge.badge.name,
                            "badge_filename": badge.badge.image.filename,
                            "count": 1
                        }
                    else:
                        quest_badges_dict[badge_id]["count"] += 1

            # Convert the dictionary to a list
            quest_badges_data = list(quest_badges_dict.values())

            # Aggregate course badges similarly
            course_badges_dict = {}
            for badge in course_badges:
                if badge.user_course_group_enrollment.student == user:
                    badge_id = badge.badge.id
                    if badge_id not in course_badges_dict:
                        course_badges_dict[badge_id] = {
                            "badge_id": badge_id,
                            "badge_name": badge.badge.name,
                            "badge_filename": badge.badge.image.filename,
                            "count": 1
                        }
                    else:
                        course_badges_dict[badge_id]["count"] += 1

            # Convert the dictionary to a list
            course_badges_data = list(course_badges_dict.values())

            # Add the aggregated data to the user_badge_details
            user_badge = {
                "user_id": user.id,
                "nickname": user.nickname,
                "badge_count": user.total_badge_count,  # Use the annotated total_badge_count
                "quest_badges": quest_badges_data,
                "course_badges": course_badges_data
            }
            user_badge_details.append(user_badge)

        # Get top 5 most recent badge awards from both UserQuestBadge and UserCourseBadge
        recent_quest_badges = quest_badges.order_by('-awarded_date')[:5]
        recent_course_badges = course_badges.order_by('-awarded_date')[:5]

        # Combine and sort the badges by the most recent award date
        recent_badges = sorted(
            list(recent_quest_badges) + list(recent_course_badges),
            key=lambda badge: badge.awarded_date,
            reverse=True
        )[:5]

        recent_badges_data = []
        record_id = 0
        for badge in recent_badges:
            badge_name = badge.badge.name
            awarded_date = badge.awarded_date
            quest_id = None
            quest_name = None
            if isinstance(badge, UserCourseBadge):
                user_id = badge.user_course_group_enrollment.student.id
                nickname = badge.user_course_group_enrollment.student.nickname
                course_id = badge.user_course_group_enrollment.course_group.course.id
                course_code = badge.user_course_group_enrollment.course_group.course.code
                course_name = badge.user_course_group_enrollment.course_group.course.name
            else:
                user_id = badge.user_quest_attempt.student.id
                nickname = badge.user_quest_attempt.student.nickname
                quest_id = badge.user_quest_attempt.quest.id
                quest_name = badge.user_quest_attempt.quest.name
                course_id = badge.user_quest_attempt.quest.course_group.course.id
                course_code = badge.user_quest_attempt.quest.course_group.course.code
                course_name = badge.user_quest_attempt.quest.course_group.course.name

            badge_data = {
                'record_id': record_id,
                'user_id': user_id,
                'nickname': nickname,
                'badge_name': badge_name,
                'awarded_date': awarded_date,
                'course_id': course_id,
                'course_code': course_code,
                'course_name': course_name,
                'quest_id': quest_id,
                'quest_name': quest_name,
            }
            record_id += 1
            recent_badges_data.append(badge_data)

        data = {
            'top_users_with_most_badges': user_badge_details,
            'recent_badge_awards': recent_badges_data
        }

        return Response(data)


class AnalyticsPartFourView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        """
        Retrieves comprehensive statistics and aggregations for all courses (excluding private),
        including course groups, enrollments, quests, quest progression,
        and detailed student progress for each quest.
        """
        # Step 1: Fetch all courses except those with type="private"
        courses = Course.objects.exclude(type="Private").select_related(
            'term__academic_year',  # Fetch related Term and AcademicYear
            'image'  # Fetch related Image
        ).prefetch_related(
            Prefetch(
                'groups',
                queryset=CourseGroup.objects.annotate(
                    enrolled_students_count=Count('enrolled_students')  # Annotate enrolled students count
                ).prefetch_related(
                    Prefetch(
                        'quests',
                        queryset=Quest.objects.annotate(
                            quest_completion=Count(
                                'attempted_by__student',
                                filter=Q(attempted_by__submitted=True),
                                distinct=True
                            )
                        )
                    )
                )
            )
        )

        if not courses.exists():
            return Response(
                {"message": "No courses available."},
                status=200
            )

        # Step 2: Fetch all enrollments for the fetched courses
        enrollments = UserCourseGroupEnrollment.objects.filter(
            course_group__course__in=courses
        ).select_related(
            'student',
            'course_group'
        )

        # Mapping: course_group_id -> set of student IDs
        group_to_students = defaultdict(set)
        student_id_to_username = {}

        for enrollment in enrollments:
            group_id = enrollment.course_group.id
            student = enrollment.student
            group_to_students[group_id].add(student.id)
            student_id_to_username[student.id] = student.username

        # Step 3: Fetch all UserQuestAttempt data for the fetched courses' quests and enrolled students
        user_quest_attempts = UserQuestAttempt.objects.filter(
            quest__course_group__course__in=courses,
            student__in=EduquestUser.objects.filter(
                enrolled_course_groups__course_group__course__in=courses
            ).distinct()
        ).values(
            'quest_id',
            'student_id'
        ).annotate(
            highest_score=Max('total_score_achieved')
        )

        # Build a mapping: (quest_id, student_id) -> highest_score
        quest_student_to_score = {}
        for attempt in user_quest_attempts:
            key = (attempt['quest_id'], attempt['student_id'])
            quest_student_to_score[key] = attempt['highest_score']

        # Step 4: Construct response data for all courses
        all_courses_data = []
        for course in courses:
            course_groups_data = []
            for group in course.groups.all():
                group_id = group.id
                enrolled_students_count = group.enrolled_students_count
                enrolled_student_ids = group_to_students.get(group_id, set())

                # Build a list of enrolled students with their usernames
                enrolled_students = [
                    {'student_id': student_id, 'username': student_id_to_username.get(student_id, 'Unknown')}
                    for student_id in enrolled_student_ids
                ]

                # Build quests data for each course group
                quests_data = []
                for quest in group.quests.all():
                    # For each quest, build a list of student progress
                    student_progress = []
                    for student in enrolled_students:
                        key = (quest.id, student['student_id'])
                        highest_score = quest_student_to_score.get(key, None)  # None if no attempts

                        student_progress.append({
                            'username': student['username'],
                            'highest_score': highest_score
                        })

                    quest_data = {
                        'quest_id': quest.id,
                        'quest_name': quest.name,
                        'quest_completion': quest.quest_completion,
                        'quest_max_score': quest.total_max_score(),
                        'students_progress': student_progress
                    }
                    quests_data.append(quest_data)

                # Assemble group data
                group_data = {
                    'group_id': group.id,
                    'group_name': group.name,
                    'enrolled_students': enrolled_students_count,
                    'quests': quests_data
                }
                course_groups_data.append(group_data)

            # Assemble course data
            course_data = {
                'course_id': course.id,
                'course_code': course.code,
                'course_name': course.name,
                'course_term': f"AY {course.term.academic_year.start_year} - {course.term.academic_year.end_year} {course.term.name}",
                'course_image': course.image.filename if course.image else None,
                'course_groups': course_groups_data
            }
            all_courses_data.append(course_data)

        # Step 5: Return the response data
        return Response(all_courses_data)


class StudentTutorialAttemptInsightsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        course_id = request.query_params.get('course_id')
        course_group_id = request.query_params.get('course_group_id')

        if not course_id:
            return Response({"detail": "course_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        group_queryset = CourseGroup.objects.filter(course_id=course_id)
        if course_group_id:
            group_queryset = group_queryset.filter(id=course_group_id)

        enrollments = UserCourseGroupEnrollment.objects.filter(
            course_group__in=group_queryset
        ).select_related('student', 'course_group')

        students = {}
        student_group_ids = defaultdict(set)
        for enrollment in enrollments:
            students[enrollment.student.id] = enrollment.student
            student_group_ids[enrollment.student.id].add(enrollment.course_group_id)

        tutorial_quests = Quest.objects.filter(
            course_group__in=group_queryset,
            tutorial_date__isnull=False
        ).exclude(type="Private")

        group_quest_ids = defaultdict(set)
        all_quest_ids = set()
        for quest_id, group_id in tutorial_quests.values_list('id', 'course_group_id'):
            group_quest_ids[group_id].add(quest_id)
            all_quest_ids.add(quest_id)

        effective_pairs = _build_effective_attendance_pairs(
            all_quest_ids,
            students.keys()
        )

        student_attempted_quest_ids = defaultdict(set)
        for quest_id, student_id in effective_pairs:
            student_attempted_quest_ids[student_id].add(quest_id)

        results = []
        for student_id in sorted(students.keys()):
            student = students[student_id]
            enrolled_group_ids = student_group_ids.get(student_id, set())

            relevant_quest_ids = set()
            for group_id in enrolled_group_ids:
                relevant_quest_ids.update(group_quest_ids.get(group_id, set()))

            attempted = len(student_attempted_quest_ids.get(student_id, set()).intersection(relevant_quest_ids))
            total_quests = len(relevant_quest_ids)
            percentage = int(round((attempted / total_quests) * 100)) if total_quests > 0 else 0
            results.append({
                'id': student.id,
                'email': student.email,
                'username': student.nickname or student.username,
                'total_points': float(student.total_points),
                'current_points': float(student.current_points),
                'course_group_ids': sorted(enrolled_group_ids),
                'tutorial_attempted': attempted,
                'tutorial_total': total_quests,
                'tutorial_percentage': percentage
            })

        return Response(results)


class StudentAttendanceColumnsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        course_id = request.query_params.get('course_id')
        course_group_id = request.query_params.get('course_group_id')

        if not course_id:
            return Response({"detail": "course_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        group_queryset = CourseGroup.objects.filter(course_id=course_id).order_by('name', 'id')
        if course_group_id:
            group_queryset = group_queryset.filter(id=course_group_id)

        if not group_queryset.exists():
            return Response({"columns": [], "attendance_keys": []})

        is_single_group = bool(course_group_id)
        quests = (
            Quest.objects
            .filter(course_group__in=group_queryset, tutorial_date__isnull=False)
            .exclude(type="Private")
            .select_related('course_group')
            .order_by('tutorial_date', 'id')
        )

        columns = []
        for quest in quests:
            base_label = quest.tutorial_date.strftime('%d %b %Y')
            label = base_label if is_single_group else f"{base_label} ({quest.course_group.name})"
            columns.append({
                "quest_id": quest.id,
                "course_group_id": quest.course_group_id,
                "label": label
            })

        effective_pairs = _build_effective_attendance_pairs(
            set(quests.values_list('id', flat=True))
        )
        attendance_keys = [f"{quest_id}_{student_id}" for quest_id, student_id in effective_pairs]

        return Response({
            "columns": columns,
            "attendance_keys": attendance_keys
        })


class StudentAttendanceOverrideView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        student_id = request.data.get('student_id')
        quest_id = request.data.get('quest_id')
        is_present = request.data.get('is_present')

        if student_id is None or quest_id is None or is_present is None:
            return Response(
                {"detail": "student_id, quest_id and is_present are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not isinstance(is_present, bool):
            return Response({"detail": "is_present must be boolean"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = EduquestUser.objects.get(id=student_id)
            quest = Quest.objects.select_related('course_group').get(id=quest_id)
        except EduquestUser.DoesNotExist:
            return Response({"detail": "Student not found"}, status=status.HTTP_404_NOT_FOUND)
        except Quest.DoesNotExist:
            return Response({"detail": "Quest not found"}, status=status.HTTP_404_NOT_FOUND)

        if quest.type == "Private" or quest.tutorial_date is None:
            return Response({"detail": "Only tutorial quests can be overridden"}, status=status.HTTP_400_BAD_REQUEST)

        if not UserCourseGroupEnrollment.objects.filter(student=student, course_group=quest.course_group).exists():
            return Response({"detail": "Student is not enrolled in this course group"}, status=status.HTTP_400_BAD_REQUEST)

        base_present = UserQuestAttempt.objects.filter(student=student, quest=quest).exists()
        if base_present == is_present:
            StudentAttendanceOverride.objects.filter(student=student, quest=quest).delete()
            return Response({"detail": "Attendance override cleared", "effective_present": base_present})

        StudentAttendanceOverride.objects.update_or_create(
            student=student,
            quest=quest,
            defaults={
                'is_present': is_present,
                'updated_by': request.user
            }
        )
        return Response({"detail": "Attendance override updated", "effective_present": is_present})


class StudentAttendanceWorkbookExportView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _sheet_title(raw_name, used_titles):
        cleaned = ''.join(ch for ch in raw_name if ch not in ['\\', '/', '*', '[', ']', ':', '?'])
        base = (cleaned or 'Group')[:31]
        title = base
        suffix = 1
        while title in used_titles:
            tail = f"_{suffix}"
            title = f"{base[:31 - len(tail)]}{tail}"
            suffix += 1
        used_titles.add(title)
        return title

    def get(self, request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        course_id = request.query_params.get('course_id')
        course_group_id = request.query_params.get('course_group_id')

        if not course_id:
            return Response({"detail": "course_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        group_queryset = CourseGroup.objects.filter(course_id=course_id).order_by('name', 'id')
        if course_group_id:
            group_queryset = group_queryset.filter(id=course_group_id)

        if not group_queryset.exists():
            return Response({"detail": "No course groups found for this course."}, status=status.HTTP_404_NOT_FOUND)

        course = Course.objects.filter(id=course_id).select_related('term__academic_year').first()
        workbook = Workbook()
        workbook.remove(workbook.active)
        used_titles = set()

        for course_group in group_queryset:
            sheet = workbook.create_sheet(self._sheet_title(course_group.name, used_titles))

            enrollments = (
                UserCourseGroupEnrollment.objects
                .filter(course_group=course_group)
                .select_related('student')
                .order_by('student__nickname', 'student__username', 'student__id')
            )
            students = [enrollment.student for enrollment in enrollments]
            student_ids = [student.id for student in students]

            tutorial_quests = list(
                Quest.objects
                .filter(course_group=course_group, tutorial_date__isnull=False)
                .exclude(type="Private")
                .order_by('tutorial_date', 'id')
            )

            date_headers = [
                quest.tutorial_date.strftime('%d-%b-%Y') if quest.tutorial_date else 'No Date'
                for quest in tutorial_quests
            ]
            header_row = ['Student Name', 'Email', *date_headers, 'Attendance']
            sheet.append(header_row)

            attempt_pairs = _build_effective_attendance_pairs(
                {quest.id for quest in tutorial_quests},
                student_ids
            ) if tutorial_quests and student_ids else set()

            total_sessions = len(tutorial_quests)
            for student in students:
                row_marks = []
                attempted_sessions = 0
                for quest in tutorial_quests:
                    mark = 1 if (quest.id, student.id) in attempt_pairs else 0
                    row_marks.append(mark)
                    attempted_sessions += mark

                percentage = int(round((attempted_sessions / total_sessions) * 100)) if total_sessions > 0 else 0
                attendance = f"{attempted_sessions}/{total_sessions} ({percentage}%)"
                sheet.append([student.nickname or student.username, student.email, *row_marks, attendance])

        output = BytesIO()
        workbook.save(output)
        output.seek(0)

        course_code = course.code if course and course.code else 'course'
        filename = f"student-attendance-{course_code}.xlsx"
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
