import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import run
from alembic.config import Config
from alembic import command
command.upgrade(Config('alembic.ini'),'head')
