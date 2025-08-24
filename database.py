from sqlalchemy	import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker



DATABASE_URL = 'sqlite:///base.db'




engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()

def create_db_and_tables():
	Base.metadata.create_all(bind=engine)

def get_db():
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()


if __name__ == "__main__":
	create_db_and_tables()
	print("База данных и таблицы созданы успешно.")

