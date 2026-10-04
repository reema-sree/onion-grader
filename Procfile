web: python -c "import sys; sys.path.insert(0, '.'); from backend.seed import seed_database; seed_database()" && uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
