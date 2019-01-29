from datetime import datetime, timedelta

import pytest
from loguru import logger

from server.api.blueprints.lessons import get_lesson_data, handle_places
from server.api.database.models import (Lesson, Place, Student, Topic,
                                        WorkDay)
from server.consts import DATE_FORMAT
from server.error_handling import RouteError

tomorrow = (datetime.now() + timedelta(days=1))


def test_lessons(auth, teacher, student, meetup, dropoff, requester):
    auth.login(email=student.user.email)
    Lesson.create(teacher=teacher, student=student, creator=student.user,
                  duration=40, date=datetime(year=2018, month=11, day=27, hour=13, minute=00),
                  meetup_place=meetup, dropoff_place=dropoff)
    resp = requester.get("/lessons/")
    assert isinstance(resp.json['data'], list)
    assert 'next_url' in resp.json
    assert 'prev_url' in resp.json


def test_student_new_lesson(auth, teacher, student, requester, topic):
    auth.login(email=student.user.email)
    date = (datetime.now().replace(hour=22, minute=40)).strftime(DATE_FORMAT)
    kwargs = {
        "teacher_id": teacher.id,
        "day": 1,
        "from_hour": 00,
        "from_minutes": 0,
        "to_hour": 23,
        "to_minutes": 59,
        "on_date": datetime.now().date()
    }
    WorkDay.create(**kwargs)
    logger.debug(f"added work day for {teacher}")
    resp = requester.post("/lessons/",
                          json={'date': date,
                                "meetup_place": "test",
                                "dropoff_place": "test",
                                })
    print(resp.json)
    assert not resp.json['data']['is_approved']
    assert resp.json["data"]["lesson_number"] == len(
        Lesson.query.filter_by(student=student).all())


def test_update_topics(auth, teacher, student, requester, topic):
    auth.login(email=teacher.user.email)
    date = (tomorrow.replace(hour=13, minute=00)).strftime(DATE_FORMAT)
    resp = requester.post("/lessons/",
                          json={'date': date, 'student_id': student.id,
                                'meetup_place': 'test', 'dropoff_place': 'test'})
    lesson_id = resp.json["data"]["id"]
    resp = requester.post(f"/lessons/{lesson_id}/topics",
                          json={'topics': {'progress': [], 'finished': [topic.id]}})
    assert topic.id == resp.json["data"]["topics"][0]["id"]
    assert resp.json["data"]["topics"][0]["is_finished"]


@pytest.mark.parametrize(
    ("student_id", "topics", "error"),
    (
        (None, {}, "Lesson must have a student assigned."),
        (1, {'progress': [5]}, "Invalid topic id."),
    )
)
def test_invalid_update_topics(auth, teacher, requester, topic, student_id, topics, error):
    auth.login(email=teacher.user.email)
    date = (tomorrow.replace(hour=13, minute=00)).strftime(DATE_FORMAT)
    resp = requester.post("/lessons/",
                          json={'date': date, 'student_id': student_id,
                                'meetup_place': 'test', 'dropoff_place': 'test'})
    lesson_id = resp.json["data"]["id"]
    resp = requester.post(f"/lessons/{lesson_id}/topics",
                          json={'topics': topics})
    assert resp.status_code == 400
    assert resp.json["message"] == error


def test_hour_not_available(auth, teacher, student, requester):
    auth.login(email=student.user.email)
    date = (tomorrow.replace(hour=12, minute=00)).strftime(DATE_FORMAT)
    kwargs = {
        "teacher_id": teacher.id,
        "day": 1,
        "from_hour": 13,
        "from_minutes": 0,
        "to_hour": 17,
        "to_minutes": 0,
        "on_date": tomorrow.date(),
    }
    WorkDay.create(**kwargs)
    logger.debug(f"added work day for {teacher}")
    resp = requester.post("/lessons/",
                          json={'date': date, "meetup_place": "test", "dropoff_place": "test"})
    assert 'not available' in resp.json['message']


def test_teacher_new_lesson_without_student(auth, teacher, student, requester):
    auth.login(email=teacher.user.email)
    date = (tomorrow.replace(hour=13, minute=00)).strftime(DATE_FORMAT)
    resp = requester.post("/lessons/",
                          json={'date': date})
    assert resp.json['data']['is_approved']


def test_teacher_new_lesson_with_student(auth, teacher, student, requester):
    auth.login(email=teacher.user.email)
    date = (tomorrow.replace(hour=13, minute=00)).strftime(DATE_FORMAT)
    resp = requester.post("/lessons/",
                          json={'date': date, 'student_id': student.id,
                                'meetup_place': 'test', 'dropoff_place': 'test'})
    assert resp.json['data']['is_approved']


def test_delete_lesson(auth, teacher, student, meetup, dropoff, requester):
    auth.login(email=student.user.email)
    lesson = Lesson.create(teacher=teacher, student=student,
                           creator=student.user, duration=40, date=datetime.now(),
                           meetup_place=meetup, dropoff_place=dropoff)
    resp = requester.delete(f"/lessons/{lesson.id}")
    assert "successfully" in resp.json['message']


def test_approve_lesson(auth, teacher, student, meetup, dropoff, requester):
    auth.login(email=teacher.user.email)
    lesson = Lesson.create(teacher=teacher, student=student,
                           creator=teacher.user, duration=40, date=datetime.now(),
                           meetup_place=meetup, dropoff_place=dropoff)
    resp = requester.get(f"/lessons/{lesson.id}/approve")
    assert "approved" in resp.json['message']
    resp = requester.get(f"/lessons/7/approve")
    assert "not exist" in resp.json['message']
    assert lesson.is_approved


def test_user_edit_lesson(app, auth, student, teacher, meetup, dropoff, requester):
    """ test that is_approved turns false when user edits lesson"""
    auth.login(email=student.user.email)
    lesson = Lesson.create(teacher=teacher, student=student,
                           creator=student.user, duration=40, date=datetime.now(),
                           meetup_place=meetup, dropoff_place=dropoff)
    resp = requester.post(f"/lessons/{lesson.id}",
                          json={'meetup_place': 'no'})
    assert 'successfully' in resp.json['message']
    assert 'no' == resp.json['data']['meetup_place']['name']
    assert not resp.json['data']['is_approved']


def test_handle_places(student: Student, meetup: Place):
    assert handle_places('t', 'tst', None) == (None, None)
    assert handle_places(meetup.name, '', student) == (meetup, None)
    new_meetup, new_dropoff = handle_places('aa', 'bb', student)
    assert new_meetup.name == 'aa'
    assert new_meetup.times_used == 1
    assert new_dropoff.times_used == 1


@pytest.mark.parametrize(
    ("data_dict", "error"),
    (
        ({"date": (datetime.now() - timedelta(minutes=2)
                   ).strftime(DATE_FORMAT)}, "Date is not valid."),
        ({"date": (tomorrow.strftime(DATE_FORMAT))}, "This hour is not available."),
    ),
)
def test_student_invalid_get_lesson_data(student, data_dict: dict, error: str):
    with pytest.raises(RouteError) as e:
        get_lesson_data(data_dict, student.user)
    assert e.value.description == error


@pytest.mark.parametrize(
    ("data_dict", "error"),
    (
        ({"date": (datetime.now() + timedelta(days=2)).replace(hour=10, minute=0).strftime(DATE_FORMAT), "student_id": 0},
         "No student with this ID."),
    )
)
def test_teacher_invalid_get_lesson_data(teacher, data_dict: dict, error: str):
    with pytest.raises(RouteError) as e:
        get_lesson_data(data_dict, teacher.user)
    assert e.value.description == error


def test_valid_get_lesson_data(student):
    date = ((tomorrow + timedelta(days=1)).replace(hour=00,
                                                   minute=00)).strftime(DATE_FORMAT)
    data_dict = {'date': date, "meetup_place": "test", "dropoff_place": "test"}
    get_lesson_data(data_dict, student.user)


def test_lesson_number(teacher, student, meetup, dropoff):
    lessons = []
    for _ in range(2):
        lessons.append(Lesson.create(teacher=teacher, student=student,
                                     creator=student.user, duration=40, date=datetime.now(),
                                     meetup_place=meetup, dropoff_place=dropoff))
    assert lessons[1].lesson_number == student.new_lesson_number - 1


def test_topics_for_lesson(app):
    topic = Topic.create(title="not important",
                         min_lesson_number=1, max_lesson_number=2)
    assert topic in Lesson.topics_for_lesson(1)