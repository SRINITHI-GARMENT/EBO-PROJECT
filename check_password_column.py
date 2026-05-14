from app import app, db
from sqlalchemy import text

with app.app_context():
    rows = db.session.execute(text("SELECT table_schema, table_name, column_name, character_maximum_length FROM information_schema.columns WHERE table_name='users' AND column_name='password' ")).fetchall()
    print(rows)
