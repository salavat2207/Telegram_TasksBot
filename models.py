from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class Users(Base):
	__tablename__ = 'users'
	user_id = Column(Integer, primary_key=True, index=True)
	tg_id = Column(Integer, unique=True, index=True)
	created_at = Column(String, nullable=False)
	solved_total = Column(Integer, default=0)
	streak_current = Column(Integer, default=0)
	streak_best = Column(Integer, default=0)
	last_task_date = Column(String, nullable=True)
	# language = Column(String, nullable=False)

	task = relationship('Tasks', back_populates='user', cascade='all, delete-orphan')


class Tasks(Base):
	__tablename__ = 'tasks'
	id = Column(Integer, primary_key=True, index=True)
	date = Column(String, nullable=False, unique=False)
	question = Column(String, nullable=False)
	answer = Column(String, nullable=False)
	hint = Column(String, nullable=True)
	language = Column(String, nullable=False)

	user_id = Column(Integer, ForeignKey('users.user_id'))
	user = relationship('Users', back_populates='task')


