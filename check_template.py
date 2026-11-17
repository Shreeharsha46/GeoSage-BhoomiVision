from app import create_app
app = create_app()
from jinja2 import Environment, FileSystemLoader
env = app.jinja_env
try:
    template = env.get_template('analysis/detail.html')
    print('Template compiles successfully!')
except Exception as e:
    print('Error:', e)