from rest_framework import serializers
from .utils import split_full_name
from collections import OrderedDict
from datetime import datetime
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
    UserCosmetics,
    StudentFeedback,
    UserDailyCheckin,
    Cosmetic
)


class EduquestUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = EduquestUser
        fields = ['id', 'first_name', 'last_name', 'username', 'email', 'nickname', 'last_login',
                  'updated_at', 'is_superuser', 'is_active', 'is_staff', 'total_points', 'current_points',
                  'daily_checkin_streak', 'daily_checkin_longest_streak', 'daily_checkin_last_date', 'daily_goals']
        read_only_fields = ['first_name', 'last_name', 'is_superuser', 'updated_at', 'username']

    # def create(self, validated_data):
    #     print(validated_data)
    #     username = validated_data['username']
    #     validated_data['email'] = validated_data['email'].upper()
    #     nickname = username.replace("#", "")
    #     first_name, last_name = split_full_name(nickname)
    #     # Default handling if nickname is not provided
    #     user = EduquestUser.objects.create(
    #         first_name=first_name,
    #         last_name=last_name,
    #         nickname=nickname,
    #         **validated_data
    #     )
    #     return user


class EduquestUserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = EduquestUser
        fields = ['id', 'email', 'nickname']


class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image
        fields = '__all__'


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = '__all__'


class TermSerializer(serializers.ModelSerializer):
    # Use PrimaryKeyRelatedField for writing operations
    academic_year_id = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all(),
        source='academic_year',  # Maps 'academic_year_id' to the 'academic_year' model field
        write_only=True
    )
    # Use nested serializer for reading operations
    academic_year = AcademicYearSerializer(read_only=True)

    class Meta:
        model = Term
        fields = '__all__'


    def update(self, instance, validated_data):
        # Handle 'academic_year' update if provided
        academic_year = validated_data.pop('academic_year', None)
        if academic_year:
            instance.academic_year = academic_year

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance


class CourseSerializer(serializers.ModelSerializer):
    # Use PrimaryKeyRelatedField for writing operations
    term_id = serializers.PrimaryKeyRelatedField(
        queryset=Term.objects.all(),
        source='term',  # Maps 'term_id' to the 'term' model field
        write_only=True
    )
    image_id = serializers.PrimaryKeyRelatedField(
        queryset=Image.objects.all(),
        source='image',  # Maps 'image_id' to the 'image' model field
        write_only=True
    )
    coordinators = serializers.PrimaryKeyRelatedField(
        queryset=EduquestUser.objects.all(),
        many=True,
        write_only=True,
        required=True  # Ensure that coordinators must be provided
    )
    # Use nested serializer for reading operations
    term = TermSerializer(read_only=True)
    image = ImageSerializer(read_only=True)
    coordinators_summary = EduquestUserSummarySerializer(many=True, read_only=True, source='coordinators')
    total_students_enrolled = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = '__all__'

    def get_total_students_enrolled(self, obj):
        return obj.total_students_enrolled()

    def validate_coordinators(self, value):
        """
        Ensure that at least one coordinator is provided.
        """
        if not value:
            raise serializers.ValidationError("At least one coordinator must be assigned to the course.")
        return value

    def create(self, validated_data):
        # Extract the coordinators
        coordinators = validated_data.pop('coordinators', [])

        # Create the Course instance without setting the coordinators
        course = Course.objects.create(**validated_data)

        # Set the many-to-many relationship separately
        course.coordinators.set(coordinators)

        return course

    def update(self, instance, validated_data):
        term = validated_data.pop('term', None)
        if term:
            instance.term = term

        image = validated_data.pop('image', None)
        if image:
            instance.image = image

        # Handle many-to-many relationships
        coordinators = validated_data.pop('coordinators', None)
        if coordinators is not None:
            if not coordinators:
                raise serializers.ValidationError({"coordinators": "At least one coordinator must be assigned to the course."})
            instance.coordinators.set(coordinators)

        # Handle status updates and related logic...
        # [Your existing update logic here]

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class CourseSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ['id', 'name', 'code', 'term', 'status']


class CourseGroupSerializer(serializers.ModelSerializer):
    course_id = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.all(),
        source='course',
        write_only=True
    )
    instructor_id = serializers.PrimaryKeyRelatedField(
        queryset=EduquestUser.objects.all(),
        source='instructor',
        write_only=True
    )
    course = CourseSummarySerializer(read_only=True)
    instructor = EduquestUserSummarySerializer(read_only=True)
    total_students_enrolled = serializers.SerializerMethodField()

    class Meta:
        model = CourseGroup
        fields = ['id', 'course', 'course_id', 'instructor_id', 'instructor', 'name',
                  'session_day', 'session_time', 'total_students_enrolled']

    def get_total_students_enrolled(self, obj):
        return obj.total_students_enrolled()

    def update(self, instance, validated_data):
        course = validated_data.pop('course', None)
        if course:
            instance.course = course

        instructor = validated_data.pop('instructor', None)
        if instructor:
            instance.instructor = instructor

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class CourseGroupSummarySerializer(serializers.ModelSerializer):
    course = CourseSummarySerializer(read_only=True)
    class Meta:
        model = CourseGroup
        fields = ['id', 'name', 'course']


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = '__all__'


class UserCourseGroupEnrollmentSerializer(serializers.ModelSerializer):
    course_group_id = serializers.PrimaryKeyRelatedField(
        queryset=CourseGroup.objects.all(),
        source='course_group',
        write_only=True
    )
    student_id = serializers.PrimaryKeyRelatedField(
        queryset=EduquestUser.objects.all(),
        source='student',
        # write_only=True
    )
    course_group = CourseGroupSerializer(read_only=True)
    student = EduquestUserSummarySerializer(read_only=True)

    class Meta:
        model = UserCourseGroupEnrollment
        fields = ['id', 'course_group_id', 'course_group', 'student_id', 'student', 'enrolled_on', 'completed_on']

    def validate(self, attrs):
        student = attrs.get('student')
        course_group = attrs.get('course_group')
        instance = self.instance

        # Check if an enrollment for this student in the same course group already exists
        if UserCourseGroupEnrollment.objects.filter(student=student, course_group=course_group).exclude(id=instance.id if instance else None).exists():
            raise serializers.ValidationError({
                'enrollment': 'This student is already enrolled in this course group.'
            })

        # Check if the student is already enrolled in another course group within the same course
        course = course_group.course
        if UserCourseGroupEnrollment.objects.filter(student=student, course_group__course=course).exclude(id=instance.id if instance else None).exists():
            raise serializers.ValidationError({
                'enrollment': 'This student is already enrolled in another course group within the same course.'
            })

        return attrs

    def update(self, instance, validated_data):
        course_group = validated_data.pop('course_group', None)
        if course_group and instance.course_group != course_group:
            instance.course_group = course_group
            # Reset the enrollment date if the course group is changed
            instance.enrolled_on = datetime.now()
            # Reset the completion date if the course group is changed
            instance.completed_on = None

        student = validated_data.pop('student', None)
        if student:
            instance.student = student

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class UserCourseGroupEnrollmentSummarySerializer(serializers.ModelSerializer):
    course_group = CourseGroupSummarySerializer(read_only=True)
    student_id = serializers.PrimaryKeyRelatedField(
        queryset=EduquestUser.objects.all(),
        source='student',
    )

    class Meta:
        model = UserCourseGroupEnrollment
        fields = ['id', 'course_group', 'student_id']


class QuestSerializer(serializers.ModelSerializer):
    course_group_id = serializers.PrimaryKeyRelatedField(
        queryset=CourseGroup.objects.all(),
        source='course_group',
        write_only=True
    )
    organiser_id = serializers.PrimaryKeyRelatedField(
        queryset=EduquestUser.objects.all(),
        source='organiser',
        write_only=True
    )
    image_id = serializers.PrimaryKeyRelatedField(
        queryset=Image.objects.all(),
        source='image',
        write_only=True
    )
    source_document_id = serializers.PrimaryKeyRelatedField(
        queryset=Document.objects.all(),
        source='source_document',
        write_only=True,
        required=False
    )

    course_group = CourseGroupSerializer(read_only=True)
    organiser = EduquestUserSummarySerializer(read_only=True)
    image = ImageSerializer(read_only=True)
    source_document = DocumentSerializer(read_only=True)
    total_max_score = serializers.SerializerMethodField(read_only=True)
    total_questions = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Quest
        fields = '__all__'

    def get_total_max_score(self, obj):
        return obj.total_max_score()

    def get_total_questions(self, obj):
        return obj.total_questions()

    def update(self, instance, validated_data):
        course_group = validated_data.pop('course_group', None)
        if course_group:
            instance.course_group = course_group

        organiser = validated_data.pop('organiser', None)
        if organiser:
            instance.organiser = organiser

        image = validated_data.pop('image', None)
        if image:
            instance.image = image

        source_document = validated_data.pop('source_document', None)
        if source_document is not None:
            instance.source_document = source_document

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class QuestSummarySerializer(serializers.ModelSerializer):
    course_group = CourseGroupSummarySerializer(read_only=True)

    class Meta:
        model = Quest
        fields = ['id', 'course_group', 'name']


class AnswerSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)  # Make 'id' writeable
    class Meta:
        model = Answer
        fields = ['id', 'text', 'is_correct', 'reason']


class QuestionSerializer(serializers.ModelSerializer):
    quest_id = serializers.PrimaryKeyRelatedField(
        queryset=Quest.objects.all(),
        source='quest',
    )
    answers = AnswerSerializer(many=True)

    class Meta:
        model = Question
        fields = ['id', 'quest_id', 'text', 'number', 'max_score', 'hint', 'question_type', 'structured_data', 'answers']

    def validate(self, data):
        answers = data.get('answers', [])
        if not answers:
            raise serializers.ValidationError("Answers cannot be empty.")
        return data

    def create(self, validated_data):
        # Check if validated_data is a list (bulk creation)
        if isinstance(validated_data, list):
            questions = []
            for item in validated_data:
                answers_data = item.pop('answers')
                question = Question.objects.create(**item)
                self._create_answers(question, answers_data)
                questions.append(question)
            return questions
        else:
            # Single object creation
            answers_data = validated_data.pop('answers')
            question = Question.objects.create(**validated_data)
            self._create_answers(question, answers_data)
            return question

    def _create_answers(self, question, answers_data):
        for answer_data in answers_data:
            Answer.objects.create(question=question, **answer_data)



class UserQuestAttemptSerializer(serializers.ModelSerializer):
    quest_id = serializers.PrimaryKeyRelatedField(
        queryset=Quest.objects.all(),  # Handles both read and write
        source='quest'  # Maps to the 'quest' ForeignKey field in the model
    )
    student_id = serializers.PrimaryKeyRelatedField(
        queryset=EduquestUser.objects.all(),  # Handles both read and write
        source='student'  # Maps to the 'student' ForeignKey field in the model
    )
    # quest = QuestSerializer(read_only=True)
    # student = EduquestUserSummarySerializer(read_only=True)
    time_taken = serializers.ReadOnlyField()

    class Meta:
        model = UserQuestAttempt
        fields = ['id', 'quest_id', 'student_id', 'submitted', 'time_taken',
                  'total_score_achieved', 'bonus_points', 'bonus_awarded',
                  'first_attempted_date', 'last_attempted_date']

    def validate(self, data):
        student = data.get('student')
        quest = data.get('quest')

        if not student or not quest:
            raise serializers.ValidationError("student_id and quest_id must be provided.")

        # Check if the student is enrolled in the course group
        course_group = quest.course_group
        if not UserCourseGroupEnrollment.objects.filter(student=student, course_group=course_group).exists():
            raise serializers.ValidationError("Student must be enrolled in the course group to attempt this quest.")

        # Check the number of existing attempts
        # Only validate the number of existing attempts during creation
        if self.instance is None:
            existing_attempts = UserQuestAttempt.objects.filter(student=student, quest=quest).count()
            if existing_attempts >= quest.max_attempts:
                raise serializers.ValidationError(f"Maximum number of attempts ({quest.max_attempts}) reached for this quest.")

        return data

    def get_time_taken(self, obj):
        if isinstance(obj, OrderedDict):
            return None
        return obj.time_taken()

    def create(self, validated_data):
        # Pop student and quest from validated data
        student = validated_data.pop('student')
        quest = validated_data.pop('quest')

        # Create a UserQuestAttempt instance
        user_quest_attempt = UserQuestAttempt.objects.create(student=student, quest=quest, **validated_data)

        # Create UserAnswerAttempt for each question in the quest
        questions = Question.objects.filter(quest=user_quest_attempt.quest)
        user_answer_attempts = []

        for question in questions:
              answers = Answer.objects.filter(question=question)
              for answer in answers:
                  user_answer_attempts.append(UserAnswerAttempt(
                      user_quest_attempt=user_quest_attempt,
                      question=question,
                      answer=answer,
                      is_selected=False,
                  ))
        # Bulk create all UserAnswerAttempt instances
        UserAnswerAttempt.objects.bulk_create(user_answer_attempts)

        return user_quest_attempt


    def update(self, instance, validated_data):
        student = validated_data.pop('student', None)
        if student:
            instance.student = student

        quest = validated_data.pop('quest', None)
        if quest:
            instance.quest = quest

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class UserQuestAttemptSummarySerializer(serializers.ModelSerializer):
    quest = QuestSummarySerializer(read_only=True)
    student_id = serializers.PrimaryKeyRelatedField(
        queryset=EduquestUser.objects.all(),
        source='student',
    )

    class Meta:
        model = UserQuestAttempt
        fields = ['id', 'quest', 'student_id', 'submitted', 'time_taken',
                  'total_score_achieved']


class UserAnswerAttemptSerializer(serializers.ModelSerializer):
    user_quest_attempt_id = serializers.PrimaryKeyRelatedField(
        queryset=UserQuestAttempt.objects.all(),
        source='user_quest_attempt',
        # write_only=True
    )
    question_id = serializers.PrimaryKeyRelatedField(
        queryset=Question.objects.all(),
        source='question',
        write_only=True
    )
    answer_id = serializers.PrimaryKeyRelatedField(
        queryset=Answer.objects.all(),
        source='answer',
        write_only=True
    )
    question = QuestionSerializer(read_only=True)
    answer = AnswerSerializer(read_only=True)

    class Meta:
        model = UserAnswerAttempt
        fields = [
            'id',
            'user_quest_attempt_id',
            'question_id',
            'question',
            'answer_id',
            'answer',
            'is_selected',
            'hint_used',
            'score_achieved'
        ]
        # read_only_fields = ['score_achieved']  # Score is calculated and shouldn't be set directly

    def create(self, validated_data):
        return UserAnswerAttempt.objects.create(**validated_data)

    def update(self, instance, validated_data):
        # Since foreign keys shouldn't change, we don't need to update them
        instance.is_selected = validated_data.get('is_selected', instance.is_selected)
        instance.hint_used = validated_data.get('hint_used', instance.hint_used)
        instance.score_achieved = validated_data.get('score_achieved', instance.score_achieved)
        instance.save()
        return instance


class BulkUpdateUserAnswerAttemptSerializer(serializers.Serializer):
    """
    Serializer to bulk update 'is_selected' field for multiple UserAnswerAttempt instances.
    """
    ids = serializers.ListField(
        child=serializers.IntegerField(),  # Expecting a list of UserAnswerAttempt IDs
        write_only=True
    )
    is_selected = serializers.BooleanField()

    class Meta:
        fields = ['ids', 'is_selected']

    def update(self, validated_data):
        ids = validated_data['ids']
        is_selected = validated_data['is_selected']

        # Retrieve the instances based on the IDs provided
        user_answer_attempts = UserAnswerAttempt.objects.filter(id__in=ids)

        # Iterate over each instance and apply the custom update logic
        for instance in user_answer_attempts:
            instance_data = {'is_selected': is_selected}
            # Call the existing update method logic for each instance
            self.context['view'].get_serializer().update(instance, instance_data)

        # Optionally return the updated records or a success message
        return user_answer_attempts


class BadgeSerializer(serializers.ModelSerializer):
    image_id = serializers.PrimaryKeyRelatedField(
        queryset=Image.objects.all(),
        source='image',
        write_only=True
    )
    image = ImageSerializer(read_only=True)
    class Meta:
        model = Badge
        fields = '__all__'


class CosmeticSerializer(serializers.ModelSerializer):
    cosmetic_id = serializers.PrimaryKeyRelatedField(
        queryset=Cosmetic.objects.all(),
        source='cosmetic',
        write_only=True
    )
    class Meta:
        model = Cosmetic
        fields = '__all__'


class UserCosmeticsSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=EduquestUser.objects.all(),
        source='user',
        write_only=True
    )
    profile_picture_id = serializers.PrimaryKeyRelatedField(
        queryset=Cosmetic.objects.all().filter(type=Cosmetic.TypeOfCosmetic.Picture),
        source='profile_picture',
        write_only=True,
        allow_null=True
    )
    profile_border_id = serializers.PrimaryKeyRelatedField(
        queryset=Cosmetic.objects.all().filter(type=Cosmetic.TypeOfCosmetic.Border),
        source='profile_border',
        write_only=True,
        allow_null=True
    )
    banner_id = serializers.PrimaryKeyRelatedField(
        queryset=Cosmetic.objects.all().filter(type=Cosmetic.TypeOfCosmetic.Banner),
        source='banner',
        write_only=True,
        allow_null=True
    )
    displayed_badges = serializers.PrimaryKeyRelatedField(
        queryset=Badge.objects.all(),
        many=True,
        source='displayed_badges'
    )

    class Meta:
        model = UserCosmetics
        fields = [
            'id',
            'user_id',
            'profile_picture_id',
            'profile_background',
            'profile_border_id',
            'banner_id',
            'displayed_badges',
            'about_me',
            'created_at',
            'updated_at',
        ]

    def update(self, instance, validated_data):
        displayed_badges = validated_data.pop('displayed_badges', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if displayed_badges is not None:
            instance.displayed_badges.set(displayed_badges)
        return instance


class UserCourseBadgeSerializer(serializers.ModelSerializer):
    badge_id = serializers.PrimaryKeyRelatedField(
        queryset=Badge.objects.all(),
        source='badge',
        write_only=True
    )
    user_course_group_enrollment_id = serializers.PrimaryKeyRelatedField(
        queryset=UserCourseGroupEnrollment.objects.all(),
        source='user_course_group_enrollment',
        write_only=True
    )
    badge = BadgeSerializer(read_only=True)
    user_course_group_enrollment = UserCourseGroupEnrollmentSummarySerializer(read_only=True)

    class Meta:
        model = UserCourseBadge
        fields = '__all__'

    def update(self, instance, validated_data):
        badge = validated_data.pop('badge', None)
        if badge:
            instance.badge = badge

        user_course_group_enrollment = validated_data.pop('user_course_group_enrollment', None)
        if user_course_group_enrollment:
            instance.user_course_group_enrollment = user_course_group_enrollment

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class UserQuestBadgeSerializer(serializers.ModelSerializer):
    badge_id = serializers.PrimaryKeyRelatedField(
        queryset=Badge.objects.all(),
        source='badge',
        write_only=True
    )
    user_quest_attempt_id = serializers.PrimaryKeyRelatedField(
        queryset=UserQuestAttempt.objects.all(),
        source='user_quest_attempt',
        write_only=True
    )
    badge = BadgeSerializer(read_only=True)
    user_quest_attempt = UserQuestAttemptSummarySerializer(read_only=True)
    class Meta:
        model = UserQuestBadge
        fields = '__all__'

    def update(self, instance, validated_data):
        badge = validated_data.pop('badge', None)
        if badge:
            instance.badge = badge

        user_quest_attempt = validated_data.pop('user_quest_attempt', None)
        if user_quest_attempt:
            instance.user_quest_attempt = user_quest_attempt

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class StudentFeedbackSerializer(serializers.ModelSerializer):
    user_quest_attempt_id = serializers.PrimaryKeyRelatedField(
        queryset=UserQuestAttempt.objects.all(),
        source='user_quest_attempt',
        write_only=True
    )
    user_quest_attempt = UserQuestAttemptSummarySerializer(read_only=True)

    class Meta:
        model = StudentFeedback
        fields = '__all__'


class UserDailyCheckinSerializer(serializers.ModelSerializer):
    student_id = serializers.PrimaryKeyRelatedField(
        queryset=EduquestUser.objects.all(),
        source='student',
        write_only=True
    )
    student = EduquestUserSummarySerializer(read_only=True)

    class Meta:
        model = UserDailyCheckin
        fields = ['id', 'student', 'checkin_date']
        read_only_fields = ['id']

