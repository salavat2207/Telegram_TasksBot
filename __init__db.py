from sqlalchemy.orm import Session
from database import SessionLocal, engine
from models import Users, Tasks, Base
from base.tasks import tasks




Base.metadata.create_all(bind=engine)

# Запуск сессии
db: Session = SessionLocal()

# Создание пользователей (только если у элемента есть все нужные ключи)
for item in tasks:
	required_keys = {
		'tg_id', 'created_at', 'solved_total',
		'streak_current', 'streak_best', 'last_task_date'
	}
	if isinstance(item, dict) and required_keys.issubset(item.keys()):
		db.add(Users(
			tg_id=item['tg_id'],
			created_at=item['created_at'],
			solved_total=item['solved_total'],
			streak_current=item['streak_current'],
			streak_best=item['streak_best'],
			last_task_date=item['last_task_date']
		))

# Создание задач
for task in tasks:
	task_model = Tasks(
		date=task['date'],
		question=task['question'],
		answer=task['answer'],
		hint=task['hint'],
		language=task['language']
	)
	db.add(task_model)





# Сохранение изменений в базе данных
db.commit()
# Закрытие сессии
db.close()
print("✅ База данных и задачи успешно созданы и заполнены.")
