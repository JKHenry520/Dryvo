from datetime import datetime, timedelta
from typing import Iterable, Tuple

from loguru import logger
from sqlalchemy import func
from sqlalchemy.ext.hybrid import hybrid_method
from sqlalchemy.orm import backref

from server.api.database import db
from server.api.database.mixins import (
    Column,
    Model,
    SurrogatePK,
    reference_col,
    relationship,
)
from server.api.database.models import Lesson
from server.api.utils import get_slots


class Teacher(SurrogatePK, Model):
    """A teacher of the app."""

    __tablename__ = "teachers"
    user_id = reference_col("users", nullable=False)
    user = relationship(
        "User", backref=backref("teacher", uselist=False), uselist=False
    )
    price = Column(db.Integer, nullable=False)
    phone = Column(db.String, nullable=False)
    price_rating = Column(db.Float, nullable=True)
    availabillity_rating = Column(db.Float, nullable=True)
    content_rating = Column(db.Float, nullable=True)
    lesson_duration = Column(db.Integer, default=40, nullable=False)

    def __init__(self, **kwargs):
        """Create instance."""
        db.Model.__init__(self, **kwargs)

    def work_hours_for_date(self, date: datetime):
        work_hours = self.work_days.filter_by(on_date=date.date()).all()
        if not work_hours:
            weekday = date.isoweekday()
            work_hours = self.work_days.filter_by(day=weekday).all()
            logger.debug(f"No specific days found. Going with default")

        logger.debug(f"found these work days on the specific date: {work_hours}")
        return work_hours

    def available_hours(
        self, requested_date: datetime
    ) -> Iterable[Tuple[datetime, datetime]]:
        """
        1. calculate available hours - decrease existing lessons times from work hours
        2. calculate lesson hours from available hours by default lesson duration
        MUST BE 24-hour format. 09:00, not 9:00
        """
        available = []
        if not requested_date:
            return available

        work_hours = self.work_hours_for_date(requested_date)
        existing_lessons = self.lessons.filter(
            func.extract("day", Lesson.date) == requested_date.day
        ).filter(func.extract("month", Lesson.date) == requested_date.month)
        taken_lessons = [
            (lesson.date, lesson.date + timedelta(minutes=lesson.duration))
            for lesson in existing_lessons.filter(Lesson.student_id != None).all()
        ]
        work_hours.sort(key=lambda x: x.from_hour)  # sort from early to late
        for day in work_hours:
            hours = (
                requested_date.replace(hour=day.from_hour, minute=day.from_minutes),
                requested_date.replace(hour=day.to_hour, minute=day.to_minutes),
            )
            yield from get_slots(
                hours, taken_lessons, timedelta(minutes=self.lesson_duration)
            )

        for lesson in existing_lessons.filter_by(student_id=None).all():
            yield (lesson.date, lesson.date + timedelta(minutes=lesson.duration))

    @hybrid_method
    def filter_lessons(self, filter_args):
        """
        Future: more teacher filter to come.
        """
        lessons_query = self.lessons
        deleted = False
        if "deleted" in filter_args:
            deleted = True
        if filter_args.get("show") == "history":
            lessons_query = lessons_query.filter(Lesson.date < datetime.today())
        else:
            lessons_query = lessons_query.filter(Lesson.date > datetime.today())

        order_by_args = filter_args.get("order_by", "date desc").split()
        order_by = getattr(Lesson, order_by_args[0])
        order_by = getattr(order_by, order_by_args[1])()
        return lessons_query.filter_by(deleted=deleted).order_by(order_by)

    def to_dict(self):
        return {
            "price": self.price,
            "phone": self.phone,
            "lesson_duration": self.lesson_duration,
            "price_rating": self.price_rating,
            "availabillity_rating": self.availabillity_rating,
            "content_rating": self.content_rating,
        }